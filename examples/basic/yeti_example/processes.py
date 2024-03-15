from my.commands import (
    HIDDEN_ARGUMENT,
    OPTIONAL_ARGUMENT,
    REQUIRED_ARGUMENT,
    Command,
    CommandBinaryMode,
    Print,
    SequentialProcessRunner,
    StdinConverter,
)
from my.plugins.load import PluginRegistry

from yeti_example.notes import ListNotes, NewNote

# We refer to this plugin repository in the pyproject.toml
processes = PluginRegistry()


# Helper dictionnary to define the different commands.
# The key is the command path, dot separated, and the value is the command.
# Example "notes.new": NewNote(...) will be exposed as `my notes new` in the command line.
COMMANDS = {
    "notes.new": NewNote(
        title=REQUIRED_ARGUMENT,
        add_date=OPTIONAL_ARGUMENT(default=True, action="store_true"),
        notebook=OPTIONAL_ARGUMENT,
    ),
    "notes.list": ListNotes(notebook=OPTIONAL_ARGUMENT),
}

for path, command in COMMANDS.items():
    *export_path, name = path.split(".")
    processes.add_process(name, command, export_path=".".join(export_path))
