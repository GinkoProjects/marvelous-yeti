import logging
import sys
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass, field
from typing import (Any, Dict, Generic, List, Optional, Tuple, Type, TypeVar,
                    Union)

from my.commands import ProcessRunner

TProcessRunner = TypeVar("TProcessRunner", bound="ProcessRunner")

logger = logging.getLogger(__name__)


@dataclass
class ExternalCommand:
    cls: Type[TProcessRunner]
    name: str = ""
    export_path: str = ""
    module: str = field(default="", init=False)

    def __post_init__(self):
        if not self.name:
            self.name = self.cls.__name__
        self.module = self.cls.__module__


@dataclass
class ExternalProcess:
    name: str
    process: TProcessRunner
    export_path: str = ""


@dataclass
class PluginRegistry:
    name: Optional[str] = None
    commands: List[ExternalCommand] = field(default_factory=list, init=False)
    processes: List[ExternalProcess] = field(default_factory=list, init=False)
    # Register other types (processes, ...)

    def _register(self, command: ExternalCommand) -> Type[TProcessRunner]:
        self.commands.append(command)
        return command.cls

    def add_process(self, name: str, process: TProcessRunner, export_path: str = ""):
        self.processes.append(ExternalProcess(name=name, process=process, export_path=export_path))

    def register(self, *args, **kwargs):
        """Decorator to register a plugin.

        Example usage::

            @plug.register
            @dataclass
            class GetPublicIP(CommandProcessRunner):
                ...

        or
            @plug.register(path="my_plugins.network")
            @dataclass
            class GetPublicIP(CommandProcessRunner):
                ...

        """

        if len(args) == 1 and len(kwargs) == 0:
            # Usage as decorator without arguments (ie. @plug.register)
            # The first argument is the decorated class.
            cls = args[0]
            if not issubclass(cls, ProcessRunner):
                logger.info("Class %s is not a subclass of ProcessRunner", cls)
                # raise ValueError(f"Class {cls} is not a subclass of ProcessRunner")
            cmd = ExternalCommand(cls)
            return self._register(cmd)
        else:
            # Usage as decorator with arguments (ie @plug.register(path="xxx")).
            # The arguments will be used in _register
            def register_class(cls: Type[TProcessRunner]):
                cmd = ExternalCommand(cls, *args, **kwargs)
                return self._register(cmd)

            return register_class
