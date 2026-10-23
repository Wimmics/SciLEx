"""Domain templates and saved profiles for ``scilex-init`` (issue #48).

``scilex-init --template <name>`` writes ``scilex.config.yml`` from either a built-in
domain template (``scilex/templates/*.yml``) or a profile saved earlier with
``scilex-init --save-profile <name>`` (``~/.config/scilex/profiles/<name>.yml``).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
DEFAULT_CONFIG_PATH = PACKAGE_DIR / "scilex.config.yml"
PROFILES_DIR_ENV = "SCILEX_PROFILES_DIR"
_PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def profiles_dir() -> Path:
    """Directory holding saved profiles (override with ``SCILEX_PROFILES_DIR``)."""
    override = os.environ.get(PROFILES_DIR_ENV)
    if override:
        return Path(override)
    return Path.home() / ".config" / "scilex" / "profiles"


def list_templates() -> list[str]:
    """Names of the built-in domain templates."""
    return sorted(path.stem for path in TEMPLATES_DIR.glob("*.yml"))


def list_profiles() -> list[str]:
    """Names of the user's saved profiles."""
    directory = profiles_dir()
    return (
        sorted(path.stem for path in directory.glob("*.yml"))
        if directory.is_dir()
        else []
    )


def _validate_name(name: str) -> str:
    if not _PROFILE_NAME.match(name):
        raise ValueError(
            f"Invalid name '{name}': use letters, digits, '.', '_' or '-' only."
        )
    return name


def resolve_template(name: str) -> Path:
    """Locate a template by name: saved profiles first, then built-in templates.

    Raises:
        FileNotFoundError: If no template or profile has that name.
    """
    _validate_name(name)
    for candidate in (profiles_dir() / f"{name}.yml", TEMPLATES_DIR / f"{name}.yml"):
        if candidate.is_file():
            return candidate
    available = ", ".join(list_templates() + list_profiles())
    raise FileNotFoundError(
        f"Unknown template or profile '{name}'. Available: {available}"
    )


def apply_template(name: str, output: Path, force: bool = False) -> Path:
    """Copy a template or profile to ``output``.

    Raises:
        FileExistsError: If ``output`` exists and ``force`` is False.
    """
    source = resolve_template(name)
    if output.exists() and not force:
        raise FileExistsError(f"{output} already exists (use --force to overwrite)")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output)
    return output


def save_profile(name: str, config_path: Path, force: bool = False) -> Path:
    """Save ``config_path`` as profile ``name``.

    Raises:
        FileNotFoundError: If the current config does not exist.
        FileExistsError: If the profile exists and ``force`` is False.
    """
    _validate_name(name)
    if not config_path.is_file():
        raise FileNotFoundError(f"No configuration to save: {config_path}")
    target = profiles_dir() / f"{name}.yml"
    if target.exists() and not force:
        raise FileExistsError(
            f"Profile '{name}' already exists (use --force to overwrite)"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_path, target)
    return target


def main(argv: list[str] | None = None) -> int:
    """Entry point of ``scilex-init``."""
    parser = argparse.ArgumentParser(
        prog="scilex-init",
        description="Create scilex.config.yml from a domain template or saved profile.",
    )
    parser.add_argument("--template", metavar="NAME", help="Template or profile name")
    parser.add_argument(
        "--list-templates", action="store_true", help="List templates and profiles"
    )
    parser.add_argument(
        "--save-profile",
        metavar="NAME",
        help="Save the current config as ~/.config/scilex/profiles/NAME.yml",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Config file to write (--template) or read (--save-profile)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args(argv)

    if not (args.list_templates or args.template or args.save_profile):
        parser.print_help()
        return 1

    try:
        if args.list_templates:
            print("Built-in templates:")
            for name in list_templates():
                print(f"  {name}")
            profiles = list_profiles()
            print("Saved profiles:" if profiles else "Saved profiles: (none)")
            for name in profiles:
                print(f"  {name}")
        if args.save_profile:
            path = save_profile(args.save_profile, args.config, args.force)
            print(f"Profile saved: {path}")
        if args.template:
            path = apply_template(args.template, args.config, args.force)
            print(f"Configuration written: {path}")
            print("Next: edit keywords/years/collect_name, then run scilex-collect.")
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
