import logging
import os

import yaml


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


def api_collector_decorator(api_name):
    """
    Decorator to handle logging and exception management for API collectors.

    Args:
        api_name (str): The name of the API being collected.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            logging.info(f"-------{api_name} Collection Process Started-------")
            try:
                func(*args, **kwargs)
                logging.info(f"{api_name} Collection Completed Successfully.")
            except Exception as e:
                logging.error(f"{api_name} Collection Failed: {str(e)}")

        return wrapper

    return decorator
