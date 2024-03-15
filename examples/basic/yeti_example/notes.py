from pathlib import Path

from dataclasses import dataclass
from datetime import datetime

from my.commands import (
    CommandProcessRunner,
    args,
)


@dataclass
class NewNote(CommandProcessRunner):
    title: str
    add_date: bool = True
    notebook: str = args(default="~/notes.txt")

    def run(self, **kwargs):
        note_text = f"{self.title}"
        if self.add_date:
            note_text = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {note_text}"

        with Path(self.notebook).expanduser().open("a") as f:
            f.write("# " + note_text + "\n")

        return ""


@dataclass
class ListNotes(CommandProcessRunner):
    notebook: str = args(default="~/notes.txt")

    def run(self, **kwargs):
        with Path(self.notebook).expanduser().open() as f:
            for l in f.readlines():
                yield l.rstrip("\n")
