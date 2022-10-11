import argparse
import sys

from dynaconf import Dynaconf

import my.config.my as myconfig


def print_config(args):
    from pprint import pprint

    conf_file = myconfig.user_conf_dir / myconfig.settings_filename
    conf = Dynaconf(
        settings_files=[conf_file],
        load_dotenv=False,
        loaders=[],
    )

    my_config = conf.loaded_by_loaders["toml"]["MY"]

    pprint(my_config.to_dict(), width=80)


def init_config(args):
    conf = myconfig.user_conf_dir / myconfig.settings_filename
    if not myconfig.user_conf_dir.exists():
        myconfig.user_conf_dir.mkdir(parents=True)

    if not conf.exists():
        conf.open("w").close()
        print(f"Configuration created at {conf}")
    elif conf.exists() and conf.is_dir():
        print(f"Path {conf} exists but it is a directory.")
        sys.exit(1)
    else:
        print(f"User configuration file already exists: {conf}")
        sys.exit(1)


def argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Handle config for Marvelous Yeti and plugins",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    actions = parser.add_subparsers(dest="action", title="Action")
    # Create new config file
    init_parser = actions.add_parser("init")
    init_parser.set_defaults(func=init_config)

    # Create new config file
    print_config_parser = actions.add_parser("show")
    print_config_parser.set_defaults(func=print_config)

    return parser


def main():
    parser = argparser()

    args = parser.parse_args()
    if not getattr(args, "func", None):
        print(parser.format_usage())
        sys.exit(1)
    args.func(args)
