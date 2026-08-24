"""Build-time application resources.

The tracked catalog remains in the repository-level ``data/`` directory.
Packaging copies that single source into ``resources/data`` in the built wheel;
the source checkout deliberately contains no duplicate catalog.
"""
