"""
Spacy model management utilities for SciLEx.

Provides functions to check, install, and load spacy models with user interaction.
"""

import logging
import subprocess
import sys
from typing import Optional


def is_spacy_model_installed(model_name: str = "en_core_web_sm", suppress_warnings: bool = True) -> bool:
    """
    Check if a spacy model is installed.

    Args:
        model_name: Name of the spacy model to check
        suppress_warnings: If True, suppress logging warnings during check

    Returns:
        True if model is installed, False otherwise
    """
    try:
        import spacy
        # Temporarily suppress warnings
        if suppress_warnings:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                spacy.load(model_name)
        else:
            spacy.load(model_name)
        return True
    except (OSError, ImportError):
        return False


def install_spacy_model(model_name: str = "en_core_web_sm") -> bool:
    """
    Install a spacy model using uv.

    Args:
        model_name: Name of the spacy model to install

    Returns:
        True if installation succeeded, False otherwise
    """
    try:
        logging.info(f"Installing spacy model '{model_name}'...")

        # Check for uv
        import shutil
        uv_path = shutil.which("uv")

        if not uv_path:
            logging.error("uv is not available for spacy model installation")
            logging.error("Please install manually: uv pip install en-core-web-sm")
            return False

        # Use uv pip install
        # The spacy download command just downloads the model package from PyPI
        # Package names use hyphens, not underscores
        package_name = model_name.replace("_", "-")
        cmd = ["uv", "pip", "install", package_name]
        logging.info(f"Using uv pip to install spacy model (uv path: {uv_path})")

        logging.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            logging.info(f"Successfully installed spacy model '{model_name}'")

            # Reload the model in fuzzy_matching module
            try:
                from src.fuzzy_matching import reload_spacy_model
                if reload_spacy_model():
                    logging.info("Spacy model loaded successfully")
                else:
                    logging.warning("Could not load spacy model after installation")
            except ImportError:
                pass  # Module might not be imported yet

            return True
        else:
            logging.error(f"Failed to install spacy model '{model_name}'")
            logging.error(f"Error output: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logging.error(f"Timeout while installing spacy model '{model_name}'")
        return False
    except Exception as e:
        logging.error(f"Error installing spacy model '{model_name}': {e}")
        return False


def prompt_install_spacy_model(model_name: str = "en_core_web_sm") -> bool:
    """
    Prompt user to install spacy model if not found.

    Args:
        model_name: Name of the spacy model

    Returns:
        True if model is now available (was installed or already present), False otherwise
    """
    if is_spacy_model_installed(model_name):
        return True

    # Use hyphens for package name
    package_name = model_name.replace("_", "-")
    install_cmd = f"uv pip install {package_name}"

    print(f"\n{'='*70}")
    print(f"SPACY MODEL NOT FOUND: '{model_name}'")
    print(f"{'='*70}")
    print(f"The spacy model '{model_name}' is required for optimal fuzzy matching.")
    print(f"Without it, SciLEx will use simplified text normalization (less accurate).")
    print(f"")
    print(f"Benefits of installing the model:")
    print(f"  • Better lemmatization (e.g., 'algorithms' → 'algorithm')")
    print(f"  • Improved stop word removal")
    print(f"  • Higher accuracy in fuzzy keyword matching")
    print(f"")
    print(f"Model size: ~12 MB")
    print(f"Installation time: ~30 seconds")
    print(f"{'='*70}")

    response = input(f"\nInstall spacy model '{model_name}' now? [Y/n]: ").strip().lower()

    if response in ('', 'y', 'yes'):
        return install_spacy_model(model_name)
    else:
        logging.warning(f"Spacy model '{model_name}' not installed. Using fallback normalization.")
        print(f"\nContinuing without spacy model (using fallback normalization)...")
        print(f"To install later, run: {install_cmd}\n")
        return False


def ensure_spacy_model(
    model_name: str = "en_core_web_sm",
    auto_install: bool = False,
    silent: bool = False
) -> bool:
    """
    Ensure spacy model is available, with optional auto-installation.

    Args:
        model_name: Name of the spacy model
        auto_install: If True, install without prompting
        silent: If True, don't show prompts or warnings (just log)

    Returns:
        True if model is available, False otherwise
    """
    if is_spacy_model_installed(model_name):
        if not silent:
            logging.info(f"Spacy model '{model_name}' is installed ✓")
        return True

    if auto_install:
        logging.info(f"Auto-installing spacy model '{model_name}'...")
        return install_spacy_model(model_name)

    if silent:
        package_name = model_name.replace("_", "-")
        logging.warning(
            f"Spacy model '{model_name}' not found. "
            f"Install with: uv pip install {package_name}"
        )
        return False

    return prompt_install_spacy_model(model_name)


def check_fuzzy_matching_dependencies() -> dict:
    """
    Check all dependencies for fuzzy matching functionality.

    Returns:
        Dictionary with dependency status:
        {
            'spacy': bool,
            'spacy_model': bool,
            'thefuzz': bool,
            'all_available': bool
        }
    """
    status = {
        'spacy': False,
        'spacy_model': False,
        'thefuzz': False,
        'all_available': False
    }

    # Check spacy
    try:
        import spacy
        status['spacy'] = True
    except ImportError:
        logging.warning("Spacy not installed. Install with: uv pip install spacy")

    # Check spacy model
    if status['spacy']:
        status['spacy_model'] = is_spacy_model_installed()

    # Check thefuzz
    try:
        import thefuzz
        status['thefuzz'] = True
    except ImportError:
        logging.warning("thefuzz not installed. Install with: uv pip install thefuzz")

    status['all_available'] = all([status['spacy'], status['spacy_model'], status['thefuzz']])

    return status
