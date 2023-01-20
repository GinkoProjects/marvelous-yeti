#!/usr/bin/env python3

import logging
import select
import shlex
import subprocess
import sys
import time
from argparse import ArgumentParser
from copy import deepcopy
from dataclasses import Field, dataclass, field, fields, replace
from datetime import datetime
from io import BufferedReader, StringIO
from types import MethodType
from typing import (IO, Any, Callable, Dict, Generator, Generic, List,
                    Optional, Tuple, TypeVar, Union)

from my.commands.arguments import (ExposeArguments, args, field_value,
                                   final_value, smart_replace)

logger = logging.getLogger(__name__)


########################################################################################################################

T = TypeVar("T")
TProc = TypeVar("TProc", bound="ProcessRunner")


def escape_arg(s: str) -> str:
    """Returns a string that can be safely given to a shell as a single arg"""
    return shlex.quote(s)


@dataclass
class ProcessRunner(ExposeArguments):
    def run(self, /, stdin=None, stdout=None, **kwargs) -> Generator[str, None, None]:
        ...

    def prepare(self: TProc, **kwargs) -> TProc:
        return self.with_arguments(**kwargs)

    def __str__(self):
        return type(self).__name__

    def __or__(self, other):
        """Pipe the output of the first command to the input of the second one."""
        assert isinstance(other, ProcessRunner)

        # TODO Update to Python 3.10 to have pattern matching

        # Special case: the StdinConverter can only be runned on a complete output, so we
        # cannot create a SequentialProcessRunner with piped commands.
        if isinstance(other, StdinConverter):
            return SequentialProcessRunner(self, other, piped=False)

        if isinstance(self, SequentialProcessRunner):
            if self.piped:
                return SequentialProcessRunner(*self.subprocesses, other, piped=True)
            else:
                return SequentialProcessRunner(self, other, piped=True)

        return SequentialProcessRunner(self, other, piped=True)

    def description(self, description):
        self._description = description
        return self


@dataclass
class CommandProcessRunner(ProcessRunner):
    text: bool = field(init=False, default=True)

    def finalize_cmd(self) -> str:
        pass

    def prepare_cmd(self, **kwargs) -> str:
        return self.finalize_cmd().format(**kwargs)

    def create_args(self, kwargs: Dict[str, Union[List[str], str]], *positional_args: str, joiner="=") -> str:
        args = []
        for k, v in kwargs.items():
            if isinstance(v, list):
                subargs = v
            else:
                subargs = [v]

            for sub in subargs:
                if sub is None:
                    args.append(k)
                else:
                    args.append(f"{k}{joiner}{escape_arg(sub)}")

        for pos_arg in positional_args:
            args.append(escape_arg(pos_arg))

        return " ".join(args)

    def _run_async(self, /, stdin=None, stdout=None, **kwargs) -> Tuple[subprocess.Popen, Optional[IO], Optional[IO]]:
        complete_cmd = self.prepare_cmd(**kwargs)

        # See complete documentation https://docs.python.org/3/library/subprocess.html#subprocess.Popen
        # TODO Setup stdout/stdin to be non-blocking https://stackoverflow.com/questions/68674166/how-to-combine-stdin-with-stdout
        # TODO Python Subprocess presentation https://realpython.com/python-subprocess/#connecting-two-processes-together-with-pipes
        proc = subprocess.Popen(
            complete_cmd,
            shell=True,
            text=self.text,
            stdin=stdin if stdin else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if self.text else None,
            encoding="utf-8" if self.text else None,
            close_fds=False,
        )

        return proc, proc.stdout, proc.stderr

    def run(self, /, stdin=None, stdout=None, **kwargs) -> Generator[str, None, None]:
        proc, proc_stdout, proc_stderr = self._run_async(stdin=stdin, **kwargs)

        stdout_poll = select.poll()
        if proc_stdout is not None:
            stdout_poll.register(proc_stdout, select.POLLIN)
        stderr_poll = select.poll()
        if proc_stderr is not None:
            stderr_poll.register(proc_stderr, select.POLLIN)

        run_once_more = True
        while proc.poll() is None or run_once_more:
            run_once_more = proc.poll() is None
            while p := stdout_poll.poll(1) and proc_stdout is not None:
                orig_line = proc_stdout.readline()
                if not orig_line:
                    break
                line = orig_line[:-1]
                line = line if self.text else line.decode("utf-8")
                if stdout:
                    stdout.write(line)
                yield line

            while stderr_poll.poll(1) and proc_stderr is not None:
                ## Currently, we don't yield stderr lines as we don't want them
                ## tangled with the rest but we can print them
                orig_line = proc_stderr.readline()
                if not orig_line:
                    break
                line = orig_line[:-1]
                line = line if self.text else line.decode("utf-8")
                if stdout:
                    stdout.write(line)

            time.sleep(0.1)

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, proc.args)

        return

    def __str__(self):
        if type(self) is CommandProcessRunner:
            return f"Command[{self.finalize_cmd()}]"
        else:
            return super().__str__()


class CommandLike:
    def __set_name__(self, owner, name):
        self._name = "_" + name

    def __get__(self, obj, type):
        return getattr(obj, self._name)

    def __set__(self, obj, value):
        if isinstance(value, (str, type(Ellipsis))):
            value = Command(cmd=value)

        assert isinstance(value, Command)

        setattr(obj, self._name, value)


@dataclass(init=False)
class SequentialProcessRunner(ProcessRunner):
    subprocesses: List[ProcessRunner] = field(default_factory=list)
    piped: bool = False

    def __init__(self, *subprocesses: ProcessRunner, piped: bool = False):
        self.subprocesses = list(subprocesses)
        self.piped = piped

    def prepare(self, **kwargs) -> "SequentialProcessRunner":
        return SequentialProcessRunner(*[s.prepare(**kwargs) for s in self.subprocesses], piped=self.piped)

    def _run_async(
        self, /, stdin=None, stdout=None, **kwargs
    ) -> Tuple[subprocess.Popen, BufferedReader, BufferedReader]:
        processes = []
        close_stdout = False
        for i, sub in enumerate(self.subprocesses, start=1):
            # Don't close the stdout of the last process
            if i == len(self.subprocesses):
                close_stdout = False

            process, proc_stdout, proc_stderr = sub._run_async(stdin=stdin, stdout=stdout, **kwargs)
            processes.append(process)

            # Close the previous process's stdout pipe so the previous process can receive SIGPIPE if this process closes
            # Example here: https://docs.python.org/3/library/subprocess.html?highlight=popen#replacing-bin-sh-shell-command-substitution
            if close_stdout:
                stdin.close()

            # Pipe this process output to the next process input
            stdin = proc_stdout
            close_stdout = True

        last_proc = processes[-1]
        return last_proc, last_proc.stdout, last_proc.stderr

    def run(self, /, stdin=None, stdout=None, **kwargs) -> Generator[str, None, None]:
        outputs = []
        if not self.piped:
            sub_outputs = []
            for sub in self.subprocesses:
                try:
                    if isinstance(sub, StdinConverter):
                        sub_outputs = sub.run_with_output("\n".join(sub_outputs), stdin=stdin, stdout=stdout, **kwargs)
                    else:
                        sub_outputs = list(sub.run(stdin=stdin, stdout=stdout, **kwargs))
                    outputs.extend(sub_outputs)
                except subprocess.CalledProcessError as e:
                    logger.info(f"Process {sub} failed with error {str(e)}")
                    raise
        else:

            proc, proc_stdout, proc_stderr = self._run_async(stdin=stdin, stdout=stdout, **kwargs)
            # Wait for the last process to finish
            proc.wait()

            outputs_str = proc_stdout.read()
            if isinstance(outputs_str, bytes):
                outputs_str = outputs_str.decode("utf-8")

            outputs = outputs_str.split("\n")[:-1]

        return outputs

    def __str__(self):
        joiner = " | " if self.piped else ", "
        sub = joiner.join([str(p) for p in self.subprocesses])
        return f"{super().__str__()}[{sub}]"

    def add_arguments(self, parser: ArgumentParser, add_all_fields: bool = False) -> None:
        for process in self.subprocesses:
            process.add_arguments(parser, add_all_fields=add_all_fields)

    ## We don't need this helper function as we ask subprocesses to add their own
    ## arguments, but it could be helpful if we need to debugging or enforcing some
    ## rules on how the arguments can be used.
    # def _arguments(self) -> Dict[str, object]:
    #     args = {}
    #     for process in self.subprocesses:
    #         for arg in process._arguments():
    #             ...


@dataclass
class StdinConverter(ProcessRunner):
    target: ProcessRunner
    converter: Callable[[str], Dict[str, object]]

    def add_arguments(self, parser, add_all_fields: bool) -> None:
        # We want to expose fields that are optional and those that are REQUIRED but not set to "..."
        only_add_fields = lambda self, field: getattr(self, field.name) is not ...
        self.target.add_arguments(parser, add_all_fields=only_add_fields)

    def run_with_output(self, output: str, /, stdin=None, stdout=None, **kwargs) -> Generator[str, None, None]:
        process = smart_replace(self.target, **self.converter(output))
        return process.run(stdin=stdin, stdout=stdout, **kwargs)


@dataclass
class Command(CommandProcessRunner):
    cmd: str = args("command")

    def finalize_cmd(self) -> str:
        return self.cmd


@dataclass
class CommandBinaryMode(Command):
    def __post_init__(self):
        self.text = False


@dataclass
class Print(ProcessRunner):
    obj: Any

    def run(self, /, stdin=None, stdout=None, **kwargs) -> Generator[str, None, None]:
        from pprint import pformat

        yield pformat(self.obj)

        return
