project = "SciLEx"
copyright = "2026, Celian Ringwald, Benjamin Navet"
author = "Celian Ringwald, Benjamin Navet"
release = "1.0.0"

extensions = [
    "myst_parser",
]

myst_enable_extensions = [
    "colon_fence",
    "strikethrough",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_logo = "../img/projectLogoScilex.png"

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
