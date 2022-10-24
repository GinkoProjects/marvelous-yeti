import argparse
from dataclasses import dataclass
from typing import Any, Dict, List, Set

import pytest

from my.utils import AttrTree, AttrTreeConfig


@dataclass
class Dog:
    name: str
    race: str
    age: float

    @property
    def race_hierarchy(self) -> List[str]:
        return self.race.split(".")

    @property
    def hierarchy(self) -> List[str]:
        return self.race_hierarchy + [self.name]

    @property
    def full_name(self) -> str:
        return ".".join(self.hierarchy)


@pytest.fixture
def simple_dogs():
    return [
        Dog(name="Ollie", race="bully.frenchy", age=2.1),
        Dog(name="Falco", race="shepard.border.collie", age=5),
        Dog(name="Momo", race="shepard.aussie", age=3.2),
        Dog(name="Lucky", race="bully", age=10),
        Dog(name="Rouky", race="", age=2),
    ]


@pytest.fixture
def additional_dogs():
    return [Dog(name="Lucky", race="shepard", age=12), Dog(name="Rouky", race="gundog.beagle", age=2.7)]


@pytest.fixture
def duplicate_dogs(simple_dogs, additional_dogs):
    return simple_dogs + additional_dogs


@pytest.fixture(params=[0, 1])
def dogs(request, simple_dogs, duplicate_dogs):
    return [simple_dogs, duplicate_dogs][request.param]


def create_dog_tree(dogs: List[Dog]) -> AttrTree[Dog]:
    tree = AttrTree(
        name="__root__",
        root=True,
        config=AttrTreeConfig(expose_leafs_items=True, item_name=lambda x: x.name, item_value=lambda x: x),
    )
    for dog in dogs:
        tree.add_item(dog, hierarchy=dog.race_hierarchy)

    return tree


def test_retrieve_dog_with_full_path(dogs):
    dog_tree = create_dog_tree(dogs)
    for dog in dogs:
        assert dog_tree[dog.full_name] == dog


def test_retrieve_dog_only_with_name_no_duplicate(simple_dogs):
    dog_tree = create_dog_tree(simple_dogs)
    for dog in simple_dogs:
        assert getattr(dog_tree, dog.name) == dog


def test_retrieve_dog_walking_down_the_tree_with_attributes(dogs):
    dog_tree = create_dog_tree(dogs)
    for dog in dogs:
        current_node = dog_tree

        for next_elem in dog.hierarchy:
            current_node = getattr(current_node, next_elem)

        assert current_node == dog


def test_retrieve_dog_walking_down_the_tree_at_all_steps_no_duplicate(simple_dogs):
    dog_tree = create_dog_tree(simple_dogs)
    for dog in simple_dogs:
        current_node = dog_tree

        for next_elem in dog.hierarchy:
            assert getattr(current_node, dog.name) == dog
            current_node = getattr(current_node, next_elem)

        assert current_node == dog


def test_retrieve_dog_only_with_name_does_not_work_with_duplicates(duplicate_dogs, additional_dogs):
    dog_tree = create_dog_tree(duplicate_dogs)
    duplicate_names = [d.name for d in additional_dogs]
    for dog in duplicate_dogs:
        assert getattr(dog_tree, dog.name) == dog or dog.name in duplicate_names
