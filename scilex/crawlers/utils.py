import os
import re

import yaml

# Query/form parameters whose value must never reach a log line.
_SECRET_PARAM_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"((?:api[_-]?key|access[_-]?token|inst[_-]?token|token|key)=)"
    r"[^&\s\"'<>]+",
    re.IGNORECASE,
)


def sanitize_secrets(text):
    """Mask API keys and tokens (``apikey=``, ``api_key=``, ``token=``...) in text.

    Works on URLs as well as on free-form error messages that embed a URL.

    Args:
        text: String that may contain credentials (non-strings are stringified).

    Returns:
        str: The text with credential values replaced by ``***REDACTED***``.
    """
    return _SECRET_PARAM_PATTERN.sub(r"\1***REDACTED***", str(text))


def load_yaml_config(file_path):
    """
    Load a YAML configuration file.

    Args:
        file_path (str): Path to the YAML file.

    Returns:
        dict: Parsed YAML content as a dictionary.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path) as ymlfile:
        return yaml.safe_load(ymlfile)


def load_all_configs(config_files):
    """
    Load multiple YAML configurations based on a dictionary of file paths.

    Config files are resolved relative to the scilex package directory
    (where scilex.config.yml and api.config.yml live).

    Args:
        config_files (dict): A dictionary where keys are config names and values are relative file paths.

    Returns:
        dict: A dictionary containing loaded configurations keyed by their names.
    """
    # Resolve relative to the scilex/ package directory (parent of crawlers/)
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return {
        key: load_yaml_config(os.path.join(package_dir, path))
        for key, path in config_files.items()
    }
