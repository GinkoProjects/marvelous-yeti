# My Yeti (my)

[![test](https://github.com/GinkoProjects/my-yeti/actions/workflows/run_tests.yaml/badge.svg?branch=main)](https://github.com/GinkoProjects/my-yeti/actions/workflows/run_tests.yaml)

Compose and organize your own commands, should them be shell scripts, Python functions,... 

Use `python -m my.plugins` to see the loaded plugins and available commands.

## Example usage

Go to `examples/basic` and do `pip install -e .`. This will add commands `notes.new` and `notes.list` that you can call with `my notes new` and `my notes list --stdout`
