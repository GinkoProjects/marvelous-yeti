import logging
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass, field
from io import StringIO
from typing import (Any, Callable, Dict, Generator, Generic, List, Optional,
                    Tuple, Type, TypeVar)

from my.commands import ProcessRunner
from my.plugins.common import ExternalCommand, ExternalProcess, PluginRegistry
from my.utils import AttrTree, AttrTreeConfig

if sys.version_info < (3, 10):
    from importlib_metadata import EntryPoint, entry_points
else:
    from importlib.metadata import EntryPoint, entry_points

TProcessRunner = TypeVar("TProcessRunner", bound="ProcessRunner")

logger = logging.getLogger(__name__)


@dataclass
class Plugin:
    name: str
    module: str  # TODO Is not really the expected module path, see what we can do about it
    _commands: AttrTree[ExternalCommand] = field(
        default_factory=lambda: AttrTree[ExternalCommand](
            name="__cmds__", config=AttrTreeConfig(expose_leafs_items=True), root=True
        ),
        init=False,
    )
    _processes: AttrTree[ExternalProcess] = field(
        default_factory=lambda: AttrTree[ExternalProcess](
            name="__processes__", config=AttrTreeConfig(expose_leafs_items=False), root=True
        ),
        init=False,
    )

    def __str__(self) -> str:
        return f"<Plugin {self.name}: commands={len(self._commands)}, processes={len(self._processes)}>"

    def __repr__(self) -> str:
        return str(self)

    def add_command(self, cmd: ExternalCommand):
        setattr(self, cmd.cls.__name__, cmd.cls)
        group_name, group = self._commands.add_item(cmd, hierarchy=self.hierarchy_for_command(cmd))
        if group_name and not hasattr(self, group_name):
            setattr(self, group_name, group)

    def add_process(self, process: ExternalProcess):
        group_name, group = self._processes.add_item(process, hierarchy=self.hierarchy_for_process(process))
        if group_name and not hasattr(self, group_name):
            setattr(self, group_name, group)

    def hierarchy_for_process(self, process: ExternalProcess) -> Optional[List[str]]:
        if process.export_path:
            return process.export_path.split(".")
        else:
            return None

    def hierarchy_for_command(self, cmd: ExternalCommand) -> Optional[List[str]]:
        if cmd.export_path:
            return cmd.export_path.split(".")
        else:
            return None

    def all_commands(self) -> Dict[str, ExternalCommand]:
        return self._commands.all_items()

    def as_dict(self) -> Dict[str, Any]:
        return {"module": self.module, "commands": self._commands.as_dict(), "processes": self._processes.as_dict()}

    def add_arguments(self, parser: ArgumentParser, process_parser_kwargs: Dict[str, Any] = {}, **kwargs):
        parser.set_defaults(retrieve_func=lambda func_name: self._processes[func_name].process, function_name=self.name)
        self._processes.add_arguments(parser, path=[], process_parser_kwargs=process_parser_kwargs, **kwargs)


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
            logger.warn(f"Class {cls} is not a subclass of ProcessRunner")
            # raise ValueError(f"Class {cls} is not a subclass of ProcessRunner. Did not load")

        # Split the entrypoint name into plugin name, hierarchy.
        # Eg. google__user__authenticate pointing to GoogleAuthentication becomes "authenticate, ['google', 'user']"
        # and will be exposed as plugins.google.user.GoogleAuthentication
        command_name, hierarchy = self.get_name_and_hierarchy_from_entrypoint(cmd_entrypoint)
        export_path = ".".join(hierarchy)
        cmd = ExternalCommand(cls, name=command_name, export_path=export_path)
        plugin.add_command(cmd)

    def load_process(self, proc_entrypoint: EntryPoint):
        plugin = self.get_or_create_plugin_for_module(proc_entrypoint.module)
        process = proc_entrypoint.load()
        if not isinstance(process, ProcessRunner):
            logger.warn(f"Process {process} is not an instance of ProcessRunner. Did not load")

        process_name, hierarchy = self.get_name_and_hierarchy_from_entrypoint(proc_entrypoint)

        export_path = ".".join(hierarchy)
        proc = ExternalProcess(name=process_name, process=process, export_path=export_path)

        plugin.add_process(proc)

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

        for process in registry.processes:
            # TODO
            # process.export_path =
            plugin.add_process(process)

    def processes_tree(self) -> str:
        out = StringIO()
        # chars = "│├└─"
        chars = "    "

        def indent(depth: int) -> str:
            return f"{chars[0]}  " * depth

        def print_group(grp, depth: int):
            # Print name
            if depth != 0:
                print(indent(depth), " ", grp["name"], sep="", file=out)
            # Print items
            last_item_num = len(grp["items"])
            for i, item in enumerate(grp["items"], start=1):
                print(indent(depth), chars[2] if last_item_num else chars[1], chars[3] * 2, " ", item, sep="", file=out)

            # Print subgroups
            for k, val in grp.items():
                if k in ["name", "items"]:
                    continue

                print_group(val, depth + 1)

        for plug_name, plug in self.plugins.items():
            print(plug.name, file=out)
            proc_dict = plug._processes.as_dict()

            print_group(proc_dict, depth=0)

        return out.getvalue()
