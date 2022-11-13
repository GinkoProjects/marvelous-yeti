import argparse
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Set

import pytest

from my.commands import Command
from my.commands.tests.test_arguments import check_action_attributes
from my.plugins.load import ExternalProcess, Plugin, PluginLoader

if sys.version_info < (3, 10):
    from importlib_metadata import EntryPoint
else:
    from importlib.metadata import EntryPoint


def this_is_a_function():
    return "Definitely!"


def expose_as_entrypoint(name, group, fn) -> EntryPoint:
    assert fn.__name__ not in globals() or globals()[fn.__name__] == fn
    globals()[fn.__name__] = fn
    entrypoint_value = f"{fn.__module__}:{fn.__name__}"
    return EntryPoint(name=name, group=group, value=entrypoint_value)


def test_process_tree_example():
    """An example of a plugin exposing processes with multiple levels"""

    @dataclass
    class A(Command):
        i: int

    plug = Plugin("test_plug", "my.test")
    # Process should be exported as "hello world"
    p1 = ExternalProcess("world", process=A(i=..., cmd="None"), export_path="hello")
    plug.add_process(p1)

    # Process should be exported as "plain"
    p2 = ExternalProcess("plain", process=Command("echo 'this is plain'"), export_path="")
    plug.add_process(p2)

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--bg", action="store_true")

    plug.add_arguments(parser, process_parser_kwargs={"parents": [common_parser]}, add_all_fields=True)

    expected_arguments = {
        "debug": {"dest": "debug", "option_strings": ["--debug"], "required": False},
        "hello": {
            "world": {
                "bg": {"dest": "bg", "option_strings": ["--bg"], "required": False},
                "i": {"dest": "i", "option_strings": [], "required": True},
            },
            "bg": {"dest": "bg", "option_strings": ["--bg"], "required": False},
        },
        "plain": {"bg": {"dest": "bg", "option_strings": ["--bg"], "required": False}},
    }

    assert check_action_attributes(expected_arguments, parser._actions, excluded=set(["help"]))


def test_entrypoint_creation():
    e = expose_as_entrypoint("name", "my.group", this_is_a_function)
    fn = e.load()
    assert fn() == "Definitely!"


def test_plugin_loader_command():
    @dataclass
    class A(Command):
        i: int

    cmd_entrypoint = expose_as_entrypoint("Printer", "my.plugins.command", A)

    p = PluginLoader()
    p.load_command(cmd_entrypoint)

    assert "test_discover_and_load" in p.plugins
    assert p.plugins["test_discover_and_load"].commands.as_list() == [("Printer", A)]
