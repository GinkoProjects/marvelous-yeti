import logging
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass, field
from typing import (Any, Callable, Dict, Generator, Generic, List, Optional,
                    Tuple, Type, TypeVar)

T = TypeVar("T")


@dataclass
class AttrTreeConfig(Generic[T]):
    expose_leafs_items: bool = True
    item_name: Callable[[T], str] = lambda x: x.name
    item_value: Callable[[T], Any] = lambda x: x.cls


@dataclass
class AttrTree(Generic[T]):
    name: str
    config: AttrTreeConfig[T]
    root: bool = False
    exposed: Dict[str, T] = field(default_factory=dict, init=False)
    leafs: Dict[str, "AttrTree"] = field(default_factory=dict, init=False)

    def _expose_item(self, item: T, only_attr: bool = True):
        name = self.config.item_name(item)
        assert (
            name not in self.leafs
        ), f"Cannot add item with name '{name}' ({item}) because it has the same name as a group."
        if not only_attr:
            self.exposed[name] = item

        if self.config.expose_leafs_items:
            setattr(self, name, self.config.item_value(item))

    def add_item(self, item: T, hierarchy: Optional[List[str]]) -> Tuple[Optional[str], "AttrTree"]:
        self._expose_item(item, only_attr=bool(hierarchy))
        if not hierarchy:
            return None, self

        leaf_name, *rest = hierarchy
        if not hasattr(self, leaf_name):
            leaf = AttrTree(name=leaf_name, config=self.config)
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
