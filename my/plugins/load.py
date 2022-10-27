import logging
import sys
from argparse import ArgumentParser, _SubParsersAction
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
    commands: AttrTree[ExternalCommand] = field(
        default_factory=lambda: AttrTree[ExternalCommand](
            config=AttrTreeConfig(expose_leafs_items=True, item_name=lambda x: x.name, item_value=lambda x: x.cls),
        ),
        init=False,
    )
    processes: AttrTree[ExternalProcess] = field(
        default_factory=lambda: AttrTree[ExternalProcess](
            config=AttrTreeConfig(expose_leafs_items=False, item_name=lambda x: x.name, item_value=lambda x: x.process),
        ),
        init=False,
    )

    def __str__(self) -> str:
        return f"<Plugin {self.name}: commands={len(self.commands)}, processes={len(self.processes)}>"

    def __repr__(self) -> str:
        return str(self)

    # def __getattr__(self, name):
    #     if hasattr(self.processes, name):
    #         return getattr(self.processes, name)
    #     else:
    #         return getattr(self.commands, name)

    # def __dir__(self) -> List[str]:
    #     d = super().__dir__()
    #     dp = self.processes.__dir__()
    #     dc = self.commands.__dir__()
    #     return d + dp + dc

    def add_command(self, cmd: ExternalCommand):
        self.commands.add_item(cmd, path=".".join(self.hierarchy_for_command(cmd)))

    def add_process(self, process: ExternalProcess):
        self.processes.add_item(process, path=".".join(self.hierarchy_for_process(process)))

    def hierarchy_for_process(self, process: ExternalProcess) -> List[str]:
        path = process.export_path or ""
        return path.split(".")

    def hierarchy_for_command(self, cmd: ExternalCommand) -> List[str]:
        path = cmd.export_path or ""
        return path.split(".")

    def all_commands(self) -> Dict[str, ExternalCommand]:
        return self.commands.as_dict()

    def as_dict(self) -> Dict[str, Any]:
        return {"module": self.module, "commands": self.commands.as_dict(), "processes": self.processes.as_dict()}

    def add_arguments(self, parser: ArgumentParser, process_parser_kwargs: Dict[str, Any] = {}, **kwargs):
        parser.set_defaults(retrieve_func=lambda func_name: self.processes[func_name].process, function_name=self.name)

        parsers_sub: Dict[str, _SubParsersAction] = {"": parser.add_subparsers(title="actions")}

        def get_or_create_module_parser(path: str) -> _SubParsersAction:
            if path not in parsers_sub:
                *parents, this = path.rsplit(".", 1)
                parent_parser = get_or_create_module_parser(parents[0] if parents else "")

                this_parser = parent_parser.add_parser(this, **process_parser_kwargs)
                this_parser.set_defaults(function_name=path)

                parsers_sub[path] = this_parser.add_subparsers(title=this)

            return parsers_sub[path]

        for process_path, process in self.processes.as_list():
            *parent, process_name = process_path.rsplit(".", 1)
            this_parser = get_or_create_module_parser(parent[0] if parent else "")
            process_parser = this_parser.add_parser(process_name)
            process.add_arguments(process_parser, **kwargs)


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
            proc_dict = plug.processes.as_dict()

            print_group(proc_dict, depth=0)

        return out.getvalue()
