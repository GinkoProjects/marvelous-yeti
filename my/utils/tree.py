import logging
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass, field
from typing import (Any, Callable, Dict, Generator, Generic, List, Optional,
                    Tuple, Type, TypeVar, Union)

T = TypeVar("T")


@dataclass
class AttrTreeConfig(Generic[T]):
    expose_leafs_items: bool = True
    item_name: Callable[[T], str] = lambda x: x.name
    item_value: Callable[[T], Any] = lambda x: x.cls


@dataclass
class AttrItem(Generic[T]):
    path: str
    item_name: str
    item: T

    @property
    def fullpath(self) -> str:
        if self.path:
            return self.path + "." + self.item_name
        else:
            return self.item_name


@dataclass(frozen=True)
class AttrTreeView(Generic[T]):
    origin: "AttrTree"
    path: str

    def __dir__(self) -> List[str]:
        return self.origin._exposed_elements(self.path)

    def __getattr__(self, name):
        fullname = self.path + "." + name
        return self.origin.get_item(fullname)

    def __str__(self):
        return f"AttrTreeView(path={self.path}, items={self.__dir__()})"

    def __repr__(self):
        return f"AttrTreeView(path={self.path}, items={self.__dir__()})"


@dataclass
class AttrTree(Generic[T]):
    config: AttrTreeConfig[T]
    _exposed: Dict[str, T] = field(default_factory=dict, init=False)
    _items: List[AttrItem[T]] = field(default_factory=list, init=False)

    def add_item(self, item: T, path):
        new_item = AttrItem(path=path, item_name=self.config.item_name(item), item=item)
        self._exposed[new_item.fullpath] = self.config.item_value(item)
        self._items.append(new_item)

    def _element_is_item(self, fullname):
        return fullname in self._exposed

    def _exposed_elements(self, path: str) -> List[str]:
        exposed = list(set(k[len(path) :] for k in self._exposed.keys() if k.startswith(path)))
        exposed = [s[1 if s.startswith(".") else 0 :] for s in exposed]
        if not self.config.expose_leafs_items:
            modules = set()
            items = set()
            for m in exposed:
                *module, name = m.split(".")
                if module:
                    modules.add(module[0])
                else:
                    items.add(name)

            exposed = list(modules) + list(items)
        return exposed

    def _path_is_module(self, path: str) -> bool:
        return any(k.startswith(path) and k != path for k in self._exposed.keys())

    def get_partial_name(self, fullpath) -> T:
        *path, name = fullpath.split(".")
        path = ".".join(path)
        keys = [k for k in self._exposed.keys() if k.startswith(path) and k.endswith(name)]
        if len(keys) == 1:
            return self.get_item(keys[0])
        else:
            raise AttributeError()

    def get_item(self, fullpath) -> Union[T, AttrTreeView[T]]:
        if fullpath in self._exposed:
            return self._exposed[fullpath]
        elif self._path_is_module(fullpath):
            return AttrTreeView(origin=self, path=fullpath)
        return self.get_partial_name(fullpath)

    def __getitem__(self, name):
        return getattr(self, name)

    def __getattr__(self, name):
        return self.get_item(name)

    def __dir__(self) -> List[str]:
        d = super().__dir__()
        return d + self._exposed_elements("")

    def __len__(self) -> int:
        return len(self._exposed)

    def as_list(self) -> List[Tuple[str, T]]:
        return list(self._exposed.items())

    def as_dict(self) -> Dict[str, T]:
        return self._exposed.copy()

    def as_tree(self):
        # TODO
        pass
