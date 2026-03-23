"""Centralized configuration service for SciLEx.

Provides a single entry point for loading, merging, and saving configuration.
Replaces the scattered config loading pattern (load_all_configs + advanced merge)
that was duplicated across run_collection.py, aggregate_collect.py, scilex_api.py,
push_to_zotero.py, export_to_bibtex.py, and enrich_with_hf.py.

Usage:
    # From CLI entry points (reads YAML files):
    config = SciLExConfig.from_files()

    # From web API (pass dicts directly, no file I/O):
    config = SciLExConfig.from_dicts(main_config, api_config)

    # Access config values:
    config.main["keywords"]
    config.api["SemanticScholar"]["api_key"]
    config.quality_filters["require_abstract"]
"""

import copy
import logging
from pathlib import Path

import yaml

from scilex.config_defaults import get_default_quality_filters

logger = logging.getLogger(__name__)

# Package directory where config files live (scilex/)
_PACKAGE_DIR = Path(__file__).parent


class SciLExConfig:
    """Unified configuration container for SciLEx.

    Holds main config, API config, and merged quality filters.
    Constructed via from_files() or from_dicts() class methods.
    """

    def __init__(self, main_config: dict, api_config: dict):
        self.main = main_config
        self.api = api_config

    @property
    def quality_filters(self) -> dict:
        """Quality filters with defaults applied for any unspecified keys."""
        merged = get_default_quality_filters()
        merged.update(self.main.get("quality_filters", {}))
        return merged

    @classmethod
    def from_files(cls, config_dir: Path | None = None) -> "SciLExConfig":
        """Load configuration from YAML files on disk.

        Reads scilex.config.yml, api.config.yml, and optionally
        scilex.advanced.yml for advanced overrides.

        Args:
            config_dir: Directory containing config files.
                        Defaults to the scilex/ package directory.

        Returns:
            SciLExConfig with all configs loaded and merged.
        """
        if config_dir is None:
            config_dir = _PACKAGE_DIR

        config_dir = Path(config_dir)

        # Load main config
        main_path = config_dir / "scilex.config.yml"
        main_config = _load_yaml(main_path)

        # Load API config
        api_path = config_dir / "api.config.yml"
        api_config = _load_yaml(api_path)

        # Merge optional advanced config
        advanced_path = config_dir / "scilex.advanced.yml"
        if advanced_path.is_file():
            advanced_config = _load_yaml(advanced_path) or {}
            _merge_advanced_config(main_config, advanced_config)
            logger.info("Loaded advanced config from %s", advanced_path)

        return cls(main_config, api_config)

    @classmethod
    def from_dicts(
        cls, main_config: dict, api_config: dict | None = None
    ) -> "SciLExConfig":
        """Create config from in-memory dictionaries.

        Used by the web API to avoid file I/O. Deep-copies inputs
        to prevent mutation of the caller's data.

        Args:
            main_config: Main configuration dictionary.
            api_config: API configuration dictionary (default: empty).

        Returns:
            SciLExConfig wrapping the provided dicts.
        """
        return cls(
            copy.deepcopy(main_config),
            copy.deepcopy(api_config or {}),
        )

    def save_main_config(self, path: Path | None = None) -> None:
        """Save main configuration to YAML file.

        Args:
            path: Target file path. Defaults to scilex/scilex.config.yml.
        """
        if path is None:
            path = _PACKAGE_DIR / "scilex.config.yml"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.main, f, default_flow_style=False)

    def save_api_config(self, path: Path | None = None) -> None:
        """Save API configuration to YAML file.

        Args:
            path: Target file path. Defaults to scilex/api.config.yml.
        """
        if path is None:
            path = _PACKAGE_DIR / "api.config.yml"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.api, f, default_flow_style=False)


def _load_yaml(file_path: Path) -> dict:
    """Load a YAML file, raising FileNotFoundError if missing.

    Args:
        file_path: Path to the YAML file.

    Returns:
        Parsed YAML content as a dictionary.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path) as f:
        return yaml.safe_load(f) or {}


def _merge_advanced_config(main_config: dict, advanced_config: dict) -> None:
    """Merge advanced config into main config (mutates main_config).

    Quality filters are deep-merged; other keys are added only if absent.

    Args:
        main_config: Main configuration to merge into.
        advanced_config: Advanced overrides to apply.
    """
    for key, value in advanced_config.items():
        if key == "quality_filters" and isinstance(value, dict):
            if "quality_filters" not in main_config:
                main_config["quality_filters"] = {}
            main_config["quality_filters"].update(value)
        elif key not in main_config:
            main_config[key] = value
