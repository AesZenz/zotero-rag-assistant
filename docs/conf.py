# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add the project root to sys.path so autodoc can import src/ modules.
sys.path.insert(0, os.path.abspath(".."))

# -- Project information -------------------------------------------------------

project = "zotero-rag-assistant"
copyright = "2026, AesZenz"
author = "AesZenz"

version = "0.1.0"
release = "0.1.0"

# -- General configuration -----------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Napoleon (Google-style docstrings) ----------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True

# -- autodoc defaults ----------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"

# -- HTML output ---------------------------------------------------------------

html_theme = "shibuya"
html_static_path = ["_static"]
