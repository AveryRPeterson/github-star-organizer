import json


class ConfigError(Exception):
    """Raised when config.json is invalid or missing."""
    pass


def load_config() -> dict:
    """
    Load and validate config.json from current directory.

    Returns:
        Parsed config dictionary with 'lists' and 'keywords' keys

    Raises:
        ConfigError: If config.json is missing, invalid JSON, or missing required keys
    """
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except FileNotFoundError as e:
        raise ConfigError("config.json not found") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json is invalid JSON: {e}") from e

    # Validate required keys
    if "lists" not in config:
        raise ConfigError("config.json missing required key: 'lists'")
    if "keywords" not in config:
        raise ConfigError("config.json missing required key: 'keywords'")

    if not isinstance(config["lists"], dict):
        raise ConfigError("config['lists'] must be a dictionary")
    if not isinstance(config["keywords"], dict):
        raise ConfigError("config['keywords'] must be a dictionary")

    return config
