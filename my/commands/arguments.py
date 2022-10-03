#!/usr/bin/env python3

from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import MISSING, Field, dataclass, field, fields, replace
from typing import Any, Callable, Dict, List, Tuple, TypeVar, Union

TExpose = TypeVar("TExpose", bound="ExposeArguments")
_T = TypeVar("_T")

ARGPARSE_METADATA_NAME = "argparse"


class _SPECIAL_ARGUMENT:
    def __call__(self, *argparse_args, **argparse_kwargs):
        new_obj = self.__class__()
        # TODO ONLY FOR POSITIONAL ARGUMENTS: If a name is given in *args, use it at the metavar name
        # TODO FOR OPTIONAL ARGUMENTS: possible to change the metavar name eg. --foo METAVAR
        if "dest" in argparse_kwargs:
            raise AttributeError("Setting 'dest' is not supported (it breaks the parsing afterwards)")
        new_obj.argparse_args = argparse_args
        new_obj.argparse_kwargs = argparse_kwargs
        return new_obj


class _REQUIRED_ARGUMENT(_SPECIAL_ARGUMENT):
    aliases = [Ellipsis]


class _HIDDEN_ARGUMENT(_SPECIAL_ARGUMENT):
    pass


class _OPTIONAL_ARGUMENT(_SPECIAL_ARGUMENT):
    pass


REQUIRED_ARGUMENT = _REQUIRED_ARGUMENT()
HIDDEN_ARGUMENT = _HIDDEN_ARGUMENT()
OPTIONAL_ARGUMENT = _OPTIONAL_ARGUMENT()

_SPECIAL_ARGUMENT_VALUES = [REQUIRED_ARGUMENT, HIDDEN_ARGUMENT, OPTIONAL_ARGUMENT]


def is_special_argument(obj: Any, special_args: Union[List[Any], Tuple[Any], Any] = _SPECIAL_ARGUMENT_VALUES) -> bool:
    if isinstance(special_args, list):
        special_args = tuple(special_args)
    if not isinstance(special_args, tuple):
        special_args = tuple([special_args])
    aliases = tuple([alias for arg in special_args for alias in getattr(arg, "aliases", [])])
    types = tuple([type(arg) for arg in special_args + aliases if type(arg) is not type])
    return isinstance(obj, types) or any(obj == arg for arg in special_args)


def smart_replace(obj, **kwargs):
    # Find all recursive props first
    new_props = {}
    for k, v in kwargs.items():
        # HACK FIXME Clumsy attempt to support smart replacement in list fields
        # If the field name is XXXX[], then apply smart replacement to all elements in self.XXXX
        if k.endswith("[]"):
            real_k = k[:-2]
            obj_list = getattr(obj, real_k)
            # HACK: dirty way of filtering out keys that won't work for the subobject!
            new_props[real_k] = [
                smart_replace(e, **{k_: v_ for k_, v_ in v.items() if hasattr(e, k_)}) for e in obj_list
            ]
        elif isinstance(v, dict):
            new_props[k] = smart_replace(getattr(obj, k), **v)
        else:
            new_props[k] = v

    return replace(obj, **new_props)


def field_value(val: _T) -> _T:
    return field(default_factory=_to_default_factory(val))


def _to_default_factory(val: _T) -> Callable[[], _T]:
    return lambda: deepcopy(val)


def final_value(value: _T, *f_args, **kwargs) -> _T:
    return args(*f_args, exclude=True, default_factory=_to_default_factory(value), **kwargs)


def args(*args: _T, **kwargs) -> _T:
    field_kwargs = {}
    if "default" in kwargs:
        field_kwargs["default"] = kwargs["default"]
    elif "default_factory" in kwargs:
        field_kwargs["default_factory"] = kwargs["default_factory"]
    return field(
        metadata={
            ARGPARSE_METADATA_NAME: {"args": list(args), "kwargs": kwargs, "exclude": kwargs.get("exclude", False)}
        },
        **field_kwargs,
    )


def argslug(s: str) -> str:
    # TODO Are there other problematic chars that are allowed in python identifiers but not in cli ?
    return s.replace("_", "-")


class ExposeArguments:
    def add_arguments(self, parser: ArgumentParser, add_all_fields: bool = False) -> None:
        for _, argparse_args in self._arguments(add_all_fields=add_all_fields).items():
            if argparse_args.get("exclude", False):
                continue
            parser.add_argument(*argparse_args["args"], **argparse_args["kwargs"])

        for f in fields(self):
            if type(f.type) is type and issubclass(f.type, ExposeArguments):
                getattr(self, f.name).add_arguments(parser, add_all_fields=add_all_fields)

    def _arguments(
        self, add_all_fields: Union[bool, Callable[[TExpose, Field[Any]], bool]] = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Create arguments from metaclass fields

        For an instance X of a metaclass B, subclassing A (highest priority first):
        - If the field value is a special one from _SPECIAL_ARGUMENT_VALUES:
          - REQUIRED_ARGUMENT: the field becomes a REQUIRED field
          - HIDDEN_ARGUMENT: the field is SKIPPED
          - OPTIONAL_ARGUMENT: the field becomes an OPTIONAL field with the metaclass default value as its value
        - Else:
           - If the field value is set to a different value than the default value in metaclass B, then the field is SKIPPED.
           - If the field value is set to some value when the field has no default value, then the field is SKIPPED.
           - If the field value is the default value set in metaclass B then it becomes an OPTIONAL FIELD.

        For a field `this_is_a_field`:
        - If it is required, it becomes a positional argument `this_is_a_field` (argument field name: `this_is_a_field`)
        - If it is optional, it becomes an optional argument `--this-is-a-field` (argument field name: `this_is_a_field`)
        """
        if isinstance(add_all_fields, bool):
            include_field = lambda _1, _2: add_all_fields
        else:
            include_field = add_all_fields

        args = {}
        for f in fields(self):
            # Skip fields not present in __init__
            if f.init is False:
                continue

            # ======== FIELD VALUE =======================
            field_name = f.name
            field_val = getattr(self, field_name)
            default_val = (
                f.default
                if f.default is not MISSING
                else f.default_factory()
                if f.default_factory is not MISSING
                else None
            )

            # If the field is not required
            if not is_special_argument(field_val, [REQUIRED_ARGUMENT, OPTIONAL_ARGUMENT]):
                continue

            # Special argument but the predicate decided to skip it
            if not include_field(self, f):
                continue

            # We have actual metadata on the field so we use it
            if ARGPARSE_METADATA_NAME in f.metadata:
                argparse_args = deepcopy(f.metadata[ARGPARSE_METADATA_NAME])
            else:
                # We construct some basic arguments
                argparse_args = {"args": [], "exclude": False, "kwargs": {"default": field_val}}

            # ======== ARGUMENT NAME =====================
            # Use the field name if args is not specified
            if not argparse_args["args"]:
                arg_name = f.name
            else:
                arg_name = argparse_args["args"][0]

            field_is_optional = False
            if field_val == default_val or is_special_argument(field_val, OPTIONAL_ARGUMENT):
                arg_name = argslug("--" + arg_name)
                field_is_optional = True

            # ======== ARGUMENT DEFAULT ==================
            if is_special_argument(field_val, OPTIONAL_ARGUMENT):
                argparse_args["kwargs"]["default"] = default_val
            elif is_special_argument(field_val, REQUIRED_ARGUMENT) and "default" in argparse_args["kwargs"]:
                # Field is required, so we delete the default value
                del argparse_args["kwargs"]["default"]

            argparse_args["args"] = [
                arg_name,
            ]

            # Override argparse args and kwargs if they are set on the special argument
            if is_special_argument(field_val):
                if new_args := getattr(field_val, "argparse_args", []):
                    argparse_args["args"] = new_args
                if new_kwargs := getattr(field_val, "argparse_kwargs", {}):
                    argparse_args["kwargs"].update(new_kwargs)

            # TODO Right now, arguments set on the field are overriden by arguments set on the special value except
            #      for "dest" which is defined by the field_name. Should it be possible to define it on the field ?
            # dest should always be the field name to keep namespace coherent (so an argument A cannot be written as B)
            if argslug(argparse_args["args"][0]) != argslug(arg_name):
                if field_is_optional:
                    argparse_args["kwargs"]["dest"] = field_name
                else:
                    # With positional field, the name shown in usage is the metavar but it's not the
                    # 'dest' name we want to use (we want to keep `field_name` as the dest). So we
                    # swap the metavar and the dest (first argument in the positional values)
                    argparse_args["kwargs"]["metavar"] = argparse_args["args"][0]
                    argparse_args["args"] = tuple([field_name, *argparse_args["args"][1:]])

            args[field_name] = argparse_args

        return args

    def with_arguments(self: TExpose, **kwargs) -> TExpose:
        new_fields = {}
        # Replace subfields that also expose arguments
        for f in fields(self):
            if type(f.type) is type and issubclass(f.type, ExposeArguments):
                new_fields[f.name] = getattr(self, f.name).with_arguments(**kwargs)
            if is_special_argument(getattr(self, f.name), HIDDEN_ARGUMENT):
                field_value = (
                    f.default
                    if f.default is not MISSING
                    else f.default_factory()
                    if f.default_factory is not MISSING
                    else ...
                )
                if field_value is ...:
                    raise ValueError(f"Field {f.name} was hidden but does not have a default value or factory.")
                new_fields[f.name] = field_value

        useful_kwargs = {}
        for field_name, new_value in kwargs.items():
            # TODO Check that the field `field_name` in fields(self) did actually enable argparse
            if hasattr(self, field_name) and not is_special_argument(new_value, REQUIRED_ARGUMENT):
                # assert (
                #     getattr(self, field_name) == ...
                # ), "We can only override values that were set to the Ellipsis right now"
                useful_kwargs[field_name] = new_value

        # TODO See if there are common keys in the dicts
        # ATM: we use useful_args as the base and override with new_fields if the key exists in both.
        useful_kwargs.update(new_fields)

        return replace(self, **useful_kwargs)
