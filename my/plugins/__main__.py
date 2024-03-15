from .__init__ import loader

from pprint import pformat


def pprint(*args, **kwargs):
    formated_args = []
    for arg in args:
        if isinstance(arg, str):
            formated_args.append(arg)
        else:
            formated_args.append(pformat(arg))
    print(*formated_args, **kwargs)


for plugin_name, plugin in loader.plugins.items():
    pprint(f"For plugin '{plugin_name}'")
    pprint("# Processes:")
    pprint(plugin.processes.as_dict())
    pprint()
    pprint("# Commands:")
    pprint(plugin.commands.as_dict())
    pprint()
