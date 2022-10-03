import logging
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass, field
from typing import (Any, Callable, Dict, Generator, Generic, List, Optional,
                    Tuple, Type, TypeVar)

from my.commands import ProcessRunner
from my.plugins.common import ExternalCommand, ExternalProcess, PluginRegistry

if sys.version_info < (3, 10):
    from importlib_metadata import EntryPoint, entry_points
else:
    from importlib.metadata import EntryPoint, entry_points

TProcessRunner = TypeVar("TProcessRunner", bound="ProcessRunner")
T = TypeVar("T")

logger = logging.getLogger(__name__)


@dataclass
class NamedTreeConfig(Generic[T]):
    expose_leafs_items: bool = True
    item_name: Callable[[T], str] = lambda x: x.name
    item_value: Callable[[T], Any] = lambda x: x.cls


@dataclass
class NamedTree(Generic[T]):
    name: str
    config: NamedTreeConfig[T]
    root: bool = False
    exposed: Dict[str, T] = field(default_factory=dict, init=False)
    leafs: Dict[str, "NamedTree"] = field(default_factory=dict, init=False)

    def _expose_item(self, item: T, only_attr: bool = True):
        name = self.config.item_name(item)
        assert (
            name not in self.leafs
        ), f"Cannot add item with name '{name}' ({item}) because it has the same name as a group."
        if not only_attr:
            self.exposed[name] = item

        if self.config.expose_leafs_items:
            setattr(self, name, self.config.item_value(item))

    def add_item(self, item: T, hierarchy: List[str] | None) -> Tuple[Optional[str], "NamedTree"]:
        self._expose_item(item, only_attr=bool(hierarchy))
        if not hierarchy:
            return None, self

        leaf_name, *rest = hierarchy
        if not hasattr(self, leaf_name):
            leaf = NamedTree(name=leaf_name, config=self.config)
            setattr(self, leaf_name, leaf)
            self.leafs[leaf_name] = leaf

        self.leafs[leaf_name].add_item(item, hierarchy=rest)

        return leaf_name, self.leafs[leaf_name]

    def all_items(self) -> Dict[str, T]:
        items: Dict[str, T] = dict(self.exposed)
        for leafs in self.leafs.values():
            items.update(leafs.all_items())

        return items

    def __getitem__(self, name: str) -> T:
        # HACK Quick and dirty, should split the path and access recursively
        return dict(self.as_list())[name]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "items": list(self.exposed.keys()),
            **{gname: grp.as_dict() for gname, grp in self.leafs.items()},
        }

    def __len__(self) -> int:
        return len(self.exposed) + sum(len(l) for l in self.leafs.values())

    def _as_list(self) -> List[Tuple[List[str], T]]:
        """Return a list of (path, item). The path is a list of node taken up to access the item. It is
        constructed in reverse order for performance reasons (faster to add to the end of a list)"""

        def _add_node_name(l: List[str]) -> List[str]:
            # We don't add the root name
            if self.root:
                return l
            else:
                return l + [self.name]

        sublist = []
        # Add items exposed on this node
        for name, item in self.exposed.items():
            sublist.append((_add_node_name([name]), item))

        for l in self.leafs.values():
            for hierarchy, item in l._as_list():
                sublist.append((_add_node_name(hierarchy), item))

        return sublist

    def as_list(self, joiner=".") -> List[Tuple[str, T]]:
        lst = []
        for hierarchy, item in self._as_list():
            lst.append((joiner.join(reversed(hierarchy)), item))
        return lst

    def add_arguments(
        self, parser: ArgumentParser, path: List[str], process_parser_kwargs: Dict[str, Any] = {}, **kwargs
    ):
        this_parser = parser.add_subparsers(title=self.name)

        # Add exposed
        for process_name, external_process in self.exposed.items():
            process_parser = this_parser.add_parser(process_name, **process_parser_kwargs)
            process_parser.set_defaults(function_name=".".join(path + [process_name]))
            external_process.process.add_arguments(process_parser, **kwargs)

        for leaf in self.leafs.values():
            leaf_parser = this_parser.add_parser(leaf.name)
            leaf_parser.set_defaults(function_name=".".join(path + [leaf.name]))
            leaf.add_arguments(leaf_parser, path + [leaf.name], process_parser_kwargs=process_parser_kwargs, **kwargs)


@dataclass
class Plugin:
    name: str
    module: str  # TODO Is not really the expected module path, see what we can do about it
    _commands: NamedTree[ExternalCommand] = field(
        default_factory=lambda: NamedTree[ExternalCommand](
            name="__cmds__", config=NamedTreeConfig(expose_leafs_items=True), root=True
        ),
        init=False,
    )
    _processes: NamedTree[ExternalProcess] = field(
        default_factory=lambda: NamedTree[ExternalProcess](
            name="__processes__", config=NamedTreeConfig(expose_leafs_items=False), root=True
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

    def hierarchy_for_process(self, process: ExternalProcess) -> List[str] | None:
        if process.export_path:
            return process.export_path.split(".")
        else:
            return None

    def hierarchy_for_command(self, cmd: ExternalCommand) -> List[str] | None:
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

        export_path = ".".join(hierarchy)  # TODO Use export path to construct groups
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


if __name__ == "__main__":
    from pprint import pprint

    pprint({pname: p.as_dict() for pname, p in plugin_loader.plugins.items()})
