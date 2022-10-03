import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from my.commands import ProcessRunner

if sys.version_info < (3, 10):
    from importlib_metadata import EntryPoint, entry_points
else:
    from importlib.metadata import EntryPoint, entry_points

TProcessRunner = TypeVar("TProcessRunner", bound="ProcessRunner")

logger = logging.getLogger(__name__)


@dataclass
class ExternalCommand:
    cls: Type[TProcessRunner]
    name: str = ""
    export_path: str = ""
    module: str = field(default="", init=False)

    def __post_init__(self):
        if not self.name:
            self.name = self.cls.__name__
        self.module = self.cls.__module__


@dataclass
class PluginRegistry:
    name: Optional[str] = None
    commands: List[ExternalCommand] = field(default_factory=list, init=False)
    # Register other types (processes, ...)

    def _register(self, command: ExternalCommand) -> Type[TProcessRunner]:
        self.commands.append(command)
        return command.cls

    def register(self, *args, **kwargs):
        """Decorator to register a plugin.

        Example usage::

            @plug.register
            @dataclass
            class GetPublicIP(CommandProcessRunner):
                ...

        or
            @plug.register(path="my_plugins.network")
            @dataclass
            class GetPublicIP(CommandProcessRunner):
                ...

        """

        if len(args) == 1 and len(kwargs) == 0:
            # Usage as decorator without arguments (ie. @plug.register)
            # The first argument is the decorated class.
            cls = args[0]
            if not issubclass(cls, ProcessRunner):
                logger.warn("Class %s is not a subclass of ProcessRunner", cls)
                # raise ValueError(f"Class {cls} is not a subclass of ProcessRunner")
            cmd = ExternalCommand(cls)
            return self._register(cmd)
        else:
            # Usage as decorator with arguments (ie @plug.register(path="xxx")).
            # The arguments will be used in _register
            def register_class(cls: Type[TProcessRunner]):
                cmd = ExternalCommand(cls, *args, **kwargs)
                return self._register(cmd)

            return register_class


@dataclass
class CommandGroup:
    name: str
    parent: Optional["CommandGroup"] = None
    commands: Dict[str, ExternalCommand] = field(default_factory=dict)
    groups: Dict[str, "CommandGroup"] = field(default_factory=dict)

    def _expose_command(self, command: ExternalCommand, only_attr: bool = True):
        assert command.name not in self.groups, f"Cannot add command {command.name} with same name as a group"
        if not only_attr:
            self.commands[command.name] = command
        setattr(self, command.cls.__name__, command.cls)

    def _get_or_create_command_group(
        self, command: ExternalCommand, hierarchy: List[str] | None
    ) -> Tuple[Optional[str], "CommandGroup"]:
        self._expose_command(command, only_attr=bool(hierarchy))
        if not hierarchy:
            return None, self

        group_name, *rest = hierarchy
        if not hasattr(self, group_name):
            subgroup = CommandGroup(parent=self, name=group_name)
            setattr(self, group_name, subgroup)
            self.groups[group_name] = subgroup

        self.groups[group_name]._get_or_create_command_group(command, hierarchy=rest)

        return group_name, self.groups[group_name]

    def add_command(
        self, command: ExternalCommand, hierarchy: List[str] | None = None
    ) -> Tuple[Optional[str], "CommandGroup"]:
        return self._get_or_create_command_group(command, hierarchy)

    def all_commands(self) -> Dict[str, ExternalCommand]:
        commands: Dict[str, ExternalCommand] = dict(self.commands)
        for subgr in self.groups.values():
            commands.update(subgr.all_commands())

        return commands

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "commands": list(self.commands.keys()),
            **{gname: grp.as_dict() for gname, grp in self.groups.items()},
        }


@dataclass
class Plugin:
    name: str
    module: str
    _root: CommandGroup = field(default_factory=lambda: CommandGroup(name="__root__"), init=False)

    def add_command(self, cmd: ExternalCommand):
        setattr(self, cmd.cls.__name__, cmd.cls)
        group_name, group = self._root.add_command(cmd, hierarchy=self.hierarchy_for_command(cmd))
        if group_name and not hasattr(self, group_name):
            setattr(self, group_name, group)

    def hierarchy_for_command(self, cmd: ExternalCommand) -> List[str] | None:
        if cmd.export_path:
            return cmd.export_path.split(".")
        else:
            return None

    def all_commands(self) -> Dict[str, ExternalCommand]:
        return self._root.all_commands()

    def as_dict(self) -> Dict[str, Any]:
        return {"module": self.module, "groups": self._root.as_dict()}


@dataclass
class PluginLoader:
    plugins: Dict[str, Plugin] = field(init=False, default_factory=dict)

    def plugin_name(self, module: str) -> str:
        return module.split(".")[0]

    def get_or_create_plugin_for_module(self, module: str) -> Plugin:
        plug_name = self.plugin_name(module)
        if plug_name not in self.plugins:
            self.plugins[plug_name] = Plugin(name=plug_name, module=module)
        return self.plugins[plug_name]

    def get_name_and_hierarchy_from_entrypoint(self, ep: EntryPoint) -> Tuple[str, List[str]]:
        *hierarchy, name = ep.name.split("__")
        return name, hierarchy

    def load_command(self, cmd_entrypoint: EntryPoint):
        plugin = self.get_or_create_plugin_for_module(cmd_entrypoint.module)
        cls = cmd_entrypoint.load()
        if not issubclass(cls, ProcessRunner):
            logger.warn(f"Class {cls} is not a subclass of ProcessRunner. Did not load")
            # raise ValueError(f"Class {cls} is not a subclass of ProcessRunner. Did not load")

        # Split the entrypoint name into plugin name, hierarchy.
        # Eg. google__user__authenticate pointing to GoogleAuthentication becomes "authenticate, ['google', 'user']"
        # and will be exposed as plugins.google.user.GoogleAuthentication
        command_name, hierarchy = self.get_name_and_hierarchy_from_entrypoint(cmd_entrypoint)
        export_path = ".".join(hierarchy)
        cmd = ExternalCommand(cls, name=command_name, export_path=export_path)
        plugin.add_command(cmd)

    def load_registry(self, reg_entrypoint: EntryPoint):
        plugin = self.get_or_create_plugin_for_module(reg_entrypoint.module)
        registry: PluginRegistry = reg_entrypoint.load()

        entrypoint_name, hierarchy = self.get_name_and_hierarchy_from_entrypoint(reg_entrypoint)

        if not isinstance(registry, PluginRegistry):
            logger.warn(f"Object {registry} is not an instance of PluginRegistry")
            # raise ValueError(f"Object {registry} is not an instance of PluginRegistry")

        # Base export path of:
        # - PluginRegister("oauth") exposed with google__auth is "google.oauth" (PluginRegister name overrides)
        # - PluginRegister() exposed with google__auth is "google"
        # - PluginRegister() exposed with auth is ""
        if registry.name:
            hierarchy.append(registry.name)
        base_export_path = ".".join(hierarchy)

        for command in registry.commands:
            command.export_path = command.export_path or base_export_path
            plugin.add_command(command)
