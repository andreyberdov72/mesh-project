# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys
sys.path.insert(0, os.path.abspath('../openwrt-generator'))
sys.path.insert(0, os.path.abspath('../bulk-flasher'))

project = 'Mesh-project'
copyright = '2026, Steblyna Yurii'
author = 'Steblyna Yurii'
release = '0.1'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.doctest',
    'sphinx.ext.viewcode',
    'myst_parser',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store','MeshGraphViewer','Meshnet-lab','**/openwrt-imagebuilder-*','myvenv']


language = 'ua'
locale_dirs = ['locale/']
gettext_compact = False 

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

doctest_global_setup = '''
import sys
import os
sys.path.insert(0, os.path.abspath('../openwrt-generator'))
from generate_configs import assign_ips, build_ethernet_ports, build_wifi_mesh_links, generate_mesh_key
'''

html_context = {
    'display_language_switcher': True,
    'languages': [
        ('ua', 'Українська'),
        ('en', 'English'),
    ],
}

