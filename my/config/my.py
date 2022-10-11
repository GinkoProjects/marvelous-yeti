from dynaconf import Dynaconf
from platformdirs import site_config_path, user_config_path

app = "marvelous-yeti"
author = "GinkoProjects"

settings_filename = "my.toml"

user_conf_dir = user_config_path(appname=app, appauthor=author, roaming=True)
site_conf_dir = site_config_path(appname=app, appauthor=author)

conf_dirs = [user_conf_dir, site_conf_dir]

settings = Dynaconf(
    envvar_prefix="MARV_YETI",
    settings_files=[conf_dir / settings_filename for conf_dir in conf_dirs],
)
