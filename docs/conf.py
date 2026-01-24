"""Sphinx configuration for civicrm-py documentation."""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath("../src"))

project = "civicrm-py"
copyright = f"{datetime.now().year}, Jacob Coffee"
author = "Jacob Coffee"
release = "0.1.0"
version = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinxcontrib.mermaid",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"
language = "en"

# Napoleon (Google docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True
napoleon_attr_annotations = True

# Autodoc
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
    "show-inheritance": True,
}
autodoc_class_signature = "separated"
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autodoc_inherit_docstrings = True

# Autosummary
autosummary_generate = True

# Intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "msgspec": ("https://jcristharif.com/msgspec/", None),
    "litestar": ("https://docs.litestar.dev/latest/", None),
    "django": ("https://docs.djangoproject.com/en/5.0/", "https://docs.djangoproject.com/en/5.0/_objects/"),
}

# TODO extension
todo_include_todos = True

# MyST
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "html_admonition",
    "html_image",
    "replacements",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

# Copy button
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True
copybutton_remove_prompts = True

suppress_warnings = ["myst.header"]

# HTML
html_theme = "shibuya"
html_title = "civicrm-py"
html_static_path = ["_static"]

html_theme_options = {
    "accent_color": "crimson",
    "github_url": "https://github.com/JacobCoffee/civicrm-py",
    "discussion_url": "https://github.com/JacobCoffee/civicrm-py/discussions",
    "nav_links": [
        {"title": "CiviCRM", "url": "https://civicrm.org/"},
        {"title": "PyPI", "url": "https://pypi.org/project/civicrm-py/"},
    ],
}

html_context = {
    "source_type": "github",
    "source_user": "JacobCoffee",
    "source_repo": "civicrm-py",
    "source_version": "main",
    "source_docs_path": "/docs/",
}
