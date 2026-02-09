"""Basic import tests to verify the package is installed correctly."""

import scilex


def test_version():
    assert hasattr(scilex, "__version__")
    assert scilex.__version__ == "0.1.0"


def test_import_crawlers():
    from scilex.crawlers import collectors
    from scilex.crawlers import utils

    assert hasattr(utils, "load_all_configs")
    assert hasattr(collectors, "API_collector")


def test_import_citations():
    from scilex.citations import citations_tools

    assert citations_tools is not None
