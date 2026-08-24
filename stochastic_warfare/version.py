"""Installed-distribution version authority."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


DISTRIBUTION_NAME = "stochastic-warfare"


def installed_version() -> str:
    """Read the version from installed distribution metadata."""
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        # Source-only imports have no second hard-coded version authority.
        return "0+uninstalled"


__version__ = installed_version()
