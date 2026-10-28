"""Persistent configuration for napari-tiled.

Stores and loads user settings (URL, username) from a YAML file
in the platform-appropriate config directory.
"""

import logging
from pathlib import Path

import platformdirs
import yaml

_logger = logging.getLogger(__name__)

CONFIG_DIR = Path(platformdirs.user_config_dir("napari-tiled"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"
_BUNDLED_CONFIG = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    """Load configuration from config.yaml.

    Checks the user config directory first, then falls back to the
    bundled config.yaml shipped with the package.
    Returns an empty dict if neither exists or is invalid.
    """
    for path in (CONFIG_FILE, _BUNDLED_CONFIG):
        if path.exists():
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                _logger.warning("Failed to read config from %s", path)
    return {}


def save_config(config: dict) -> None:
    """Save configuration to config.yaml."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
    except Exception:
        _logger.warning("Failed to write config to %s", CONFIG_FILE)


def get_saved_url() -> str:
    """Return the saved URL, or empty string."""
    return load_config().get("url", "")


def get_saved_username() -> str:
    """Return the saved username, or empty string."""
    return load_config().get("username", "")


def save_login_info(url: str, username: str) -> None:
    """Save the login URL and username to config.yaml."""
    config = load_config()
    config["url"] = url
    config["username"] = username
    save_config(config)
