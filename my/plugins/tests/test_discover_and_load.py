import argparse
from dataclasses import dataclass
from typing import Any, Dict, List, Set

import pytest

from my.commands import Command
from my.commands.tests.test_arguments import check_action_attributes
from my.plugins.load import ExternalProcess, Plugin


def test_process_tree_example():
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
