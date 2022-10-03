#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from typing import Any, Dict, List, Set

import pytest

from my.commands import (HIDDEN_ARGUMENT, OPTIONAL_ARGUMENT, REQUIRED_ARGUMENT,
                         Command, CommandProcessRunner, ExposeArguments,
                         ProcessRunner, SequentialProcessRunner,
                         StdinConverter, args, final_value)
from my.commands.arguments import _OPTIONAL_ARGUMENT


@pytest.fixture
def simple_commands():
    return [Command("hello"), Command("fine")]


@pytest.fixture
def commands_with_hole():
    return Command(cmd=...), SequentialProcessRunner()


@pytest.fixture
def command_class():
    @dataclass
    class Notify(CommandProcessRunner):
        body: str
        title: str = ""

    return Notify


def test_piped_composition(simple_commands):
    c1, c2 = simple_commands
    composed = c1 | c2

    assert composed == SequentialProcessRunner(c1, c2, piped=True)


def test_find_hole_in_command():
    c = Command(cmd=...)
    assert c._arguments() == {
        "cmd": {
            "args": ["command"],
            "exclude": False,
            "kwargs": {},
        }
    }


base_arguments = {"help"}


def check_action_attributes(
    expected_arguments: Dict[str, Dict[str, Any]], actions: List[argparse.Action], excluded: Set[str] = set()
) -> bool:

    actions_name = set()

    for action in actions:
        if action.dest in excluded:
            continue
        assert action.dest in expected_arguments
        actions_name.add(action.dest)
        expected_action = expected_arguments[action.dest]
        for attr_name, attr_value in expected_action.items():
            assert getattr(action, attr_name) == attr_value

    assert actions_name == set(expected_arguments.keys())
    return True


def parser_for_command(command: ExposeArguments):
    parser = argparse.ArgumentParser(add_help=False)
    command.add_arguments(parser, add_all_fields=True)

    return parser


def check_command_arguments(
    command: ExposeArguments, expected_arguments: Dict[str, Dict[str, Any]], excluded: Set[str] = set()
) -> bool:
    parser = parser_for_command(command)
    return check_action_attributes(expected_arguments, parser._actions, excluded=excluded)


def test_find_holes_in_commands(command_class):
    Notify = command_class
    c = SequentialProcessRunner(Command(cmd=...), Notify(body=...))

    expected_args = {
        "command": {"dest": "command", "option_strings": [], "required": True},
        "body": {"dest": "body", "option_strings": [], "required": True},
    }
    check_command_arguments(c, expected_args)


def test_add_all_fields_with_lambda():
    @dataclass
    class A(ExposeArguments):
        default_argument: str = args(default="ABC")

    assert A(default_argument=OPTIONAL_ARGUMENT)._arguments(add_all_fields=False) == {}


def test_stdin_converter_does_not_expose_ellipsis():
    @dataclass
    class A(ExposeArguments):
        default_argument: str = args(default="ABC")

    stdin_conv = StdinConverter(target=A(...), converter=lambda _: {})
    expected_args = {}
    check_command_arguments(stdin_conv, expected_args)


def test_stdin_converter_does_not_expose_nested_ellipsis():
    @dataclass
    class A(ExposeArguments):
        default_argument: str = args(default="ABC")

    stdin_conv = StdinConverter(target=SequentialProcessRunner(A(...), A(...)), converter=lambda _: {})
    expected_args = {}
    check_command_arguments(stdin_conv, expected_args)


def test_stdin_converter_does_not_expose_ellipsis_but_required_argument():
    @dataclass
    class A(ExposeArguments):
        default_argument: str = args(default="ABC")

    @dataclass
    class B(ExposeArguments):
        b: str

    stdin_conv = StdinConverter(target=SequentialProcessRunner(A(...), B(b=REQUIRED_ARGUMENT)), converter=lambda _: {})
    expected_args = {
        "b": {"dest": "b", "option_strings": [], "required": True},
    }
    check_command_arguments(stdin_conv, expected_args)


def test_expose_arguments_on_simple_default():
    @dataclass
    class A(ExposeArguments):
        default_argument: str = "ABC"

    assert A(default_argument=OPTIONAL_ARGUMENT)._arguments(add_all_fields=True) == {
        "default_argument": {"args": ["--default-argument"], "exclude": False, "kwargs": {"default": "ABC"}}
    }
    assert A(default_argument=REQUIRED_ARGUMENT)._arguments(add_all_fields=True) == {
        "default_argument": {"args": ["default_argument"], "exclude": False, "kwargs": {}}
    }
    assert (
        A()._arguments(add_all_fields=False) == {}
    ), "The argument was not created with args so it should not be exposed"


def test_expose_arguments_with_args():
    @dataclass
    class A(ExposeArguments):
        default_argument: str = args(default="ABC")

    assert A(default_argument=OPTIONAL_ARGUMENT)._arguments(add_all_fields=True) == {
        "default_argument": {"args": ["--default-argument"], "exclude": False, "kwargs": {"default": "ABC"}}
    }


def test_expose_optional_argument_subclass():
    @dataclass
    class A(ExposeArguments):
        default_argument: str

    class _SPECIAL_OPTIONAL_ARGUMENT(_OPTIONAL_ARGUMENT):
        pass

    SPECIAL_OPTIONAL_ARGUMENT = _SPECIAL_OPTIONAL_ARGUMENT()

    assert A(default_argument=SPECIAL_OPTIONAL_ARGUMENT(default="ABC"))._arguments(add_all_fields=True) == {
        "default_argument": {"args": ["--default-argument"], "exclude": False, "kwargs": {"default": "ABC"}}
    }


def test_expose_arguments_of_subclass():
    @dataclass
    class A(ExposeArguments):
        default_argument: str

    @dataclass
    class B(A):
        default_argument: str = "hello"

    cmd = B(default_argument=OPTIONAL_ARGUMENT)
    assert cmd._arguments(add_all_fields=True) == {
        "default_argument": {"args": ["--default-argument"], "exclude": False, "kwargs": {"default": "hello"}}
    }

    check_command_arguments(
        cmd,
        {
            "default_argument": {
                "dest": "default_argument",
                "option_strings": ["--default-argument"],
                "required": False,
                "default": "hello",
            }
        },
    )

    cmd2 = B(default_argument=...)
    check_command_arguments(
        cmd2,
        {
            "default_argument": {
                "dest": "default_argument",
                "option_strings": [],
                "required": True,
            }
        },
    )


def test_expose_arguments_simple_fields():
    @dataclass
    class A(ExposeArguments):
        default_argument: str

    @dataclass
    class B(A):
        default_argument: str = "hello"

    # - If the field value is set to Ellipsis (...), then it becomes a REQUIRED FIELD.
    check_command_arguments(
        B(...),
        {"default_argument": {"dest": "default_argument", "required": True}},
    )

    # - If the field value is set to a different value than the default value in metaclass B, then the field is SKIPPED.
    check_command_arguments(
        B(default_argument="world"),
        {},
    )

    # - If the field value is set to some value when the field has no default value, then the field is SKIPPED.
    check_command_arguments(
        A(default_argument="world"),
        {},
    )

    # If the field value is an OPTIONAL_ARGUMENT then it becomes an OPTIONAL FIELD.
    check_command_arguments(
        B(OPTIONAL_ARGUMENT),
        {"default_argument": {"dest": "default_argument", "required": False, "default": "hello"}},
    )

    # If the field value is an HIDDEN_ARGUMENT then it is skipped
    check_command_arguments(
        B(HIDDEN_ARGUMENT),
        {},
    )


def test_expose_arguments_args_fields():
    @dataclass
    class A(ExposeArguments):
        default_argument: str

    @dataclass
    class B(A):
        default_argument: str = args(default="hello")

    # - If the field value is set to Ellipsis (...), then it becomes a REQUIRED FIELD.
    check_command_arguments(
        B(...),
        {"default_argument": {"dest": "default_argument", "required": True}},
    )

    # - If the field value is set to a different value than the default value in metaclass B, then the field is SKIPPED.
    check_command_arguments(
        B(default_argument="world"),
        {},
    )

    # - If the field value is set to some value when the field has no default value, then the field is SKIPPED.
    check_command_arguments(
        A(default_argument="world"),
        {},
    )

    # If the field value is an OPTIONAL_ARGUMENT then it becomes an OPTIONAL FIELD.
    check_command_arguments(
        B(OPTIONAL_ARGUMENT),
        {"default_argument": {"dest": "default_argument", "required": False, "default": "hello"}},
    )

    # If the field value is an HIDDEN_ARGUMENT then it is skipped
    check_command_arguments(
        B(HIDDEN_ARGUMENT),
        {},
    )


def test_override_argparse_fields():
    @dataclass
    class A(ExposeArguments):
        default_argument: int

    check_command_arguments(
        A(REQUIRED_ARGUMENT("renamed_argument")),
        {"default_argument": {"dest": "default_argument", "required": True, "metavar": "renamed_argument"}},
        excluded=base_arguments,
    )


@pytest.mark.skip("Not yet implemented")
def test_argparse_boolean_as_flag():
    # TODO Test args() is below but also need to test direct assignment "default_argument: bool = True"
    @dataclass
    class A(ExposeArguments):
        default_argument: bool = args(default=True)

    assert False


def test_override_argparse_type():
    @dataclass
    class A(ExposeArguments):
        default_argument: int

    type_constructor = lambda x: len(f"this is {x}")

    check_command_arguments(
        A(REQUIRED_ARGUMENT(type=type_constructor)),
        {"default_argument": {"dest": "default_argument", "required": True, "type": type_constructor}},
        excluded=base_arguments,
    )


def test_override_argparse_name():
    @dataclass
    class A(ExposeArguments):
        default_argument: int

    cmd = A(REQUIRED_ARGUMENT("pomodoro_count", type=int))

    parser = argparse.ArgumentParser()
    cmd.add_arguments(parser, add_all_fields=True)

    assert cmd.with_arguments(**vars(parser.parse_args(["5"]))).default_argument == 5


def test_override_argparse_name_optional():
    @dataclass
    class A(ExposeArguments):
        default_argument: int = args(default=2)

    cmd = A(OPTIONAL_ARGUMENT("--count", metavar="pomodoro_count", type=int))

    parser = argparse.ArgumentParser()
    cmd.add_arguments(parser, add_all_fields=True)

    assert cmd.with_arguments(**vars(parser.parse_args(["--count", "5"]))).default_argument == 5


def test_with_arguments_simple():
    @dataclass
    class A(ExposeArguments):
        default_argument: str = "hello"

    assert A(default_argument=...).with_arguments(default_argument="world").default_argument == "world"
    assert A().with_arguments(default_argument="world").default_argument == "world"


def test_final_value_is_not_exposed():
    @dataclass
    class A(ExposeArguments):
        action: str

    @dataclass
    class B(A):
        action: str = final_value("set_to_something")

    cmd = B()
    assert check_command_arguments(cmd, {})


def test_hidden_argument_type(command_class):
    cmd = command_class(body="Abc", title=HIDDEN_ARGUMENT)
    assert check_command_arguments(cmd, {})


def test_cannot_hide_argument_type():
    @dataclass
    class A(ExposeArguments):
        default_argument: str

    cmd = A(default_argument=HIDDEN_ARGUMENT)
    assert check_command_arguments(cmd, {})

    with pytest.raises(ValueError):
        cmd.with_arguments()


# TODO Test that default argument is found
# TODO Test that args() adds type, default, default_factory,...
# TODO Test that simple default argument has {"args": ("<arg_name>",)} in _arguments
# TODO Test default argument of type List
# TODO Test that overridden argument by subclass does not show in _arguments (eg. PomodoroAction)
# TODO Test that an optional argument set on creation does not show up
# TODO Test that an optional argument set to ... shows up
# TODO Test _arguments with multiple commands (sequential)
# TODO Test _arguments with recursive commands (Kitty(width=..., cmd=...))
# TODO Test _arguments with recursive classes that implement ExposeArguments [A(subcmd=Sequential(B(cmd=...), C(body=...)))]
# TODO Test _arguments with StdinConverter (should not show up for the moment)
# TODO Test that hidden fields do not appear in args
# TODO Test that hidden fields remain when with_arguments is called
