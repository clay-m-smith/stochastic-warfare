"""Centralized logging for all simulation modules."""

from __future__ import annotations

import logging
from pathlib import Path

_LOG_NAMESPACE = "stochastic_warfare"
_FORMAT = "[%(asctime)s] %(name)s %(levelname)s: %(message)s"

_configured = False


def get_logger(module_name: str) -> logging.Logger:
    """Return a namespaced logger for *module_name*.

    The returned logger lives under the ``stochastic_warfare`` hierarchy,
    so ``get_logger("core.rng")`` yields logger ``stochastic_warfare.core.rng``.
    """
    return logging.getLogger(f"{_LOG_NAMESPACE}.{module_name}")


def configure_logging(
    level: str = "WARNING",
    log_file: Path | None = None,
    *,
    module_levels: dict[str, str] | None = None,
) -> None:
    """Set up root formatter, handlers, and optional per-module levels.

    Parameters
    ----------
    level:
        Default level for the ``stochastic_warfare`` logger hierarchy.
    log_file:
        If provided, also log to this file.
    module_levels:
        Mapping of module names to level strings, e.g.
        ``{"core.rng": "DEBUG"}``.  Applied as overrides on top of *level*.
    """
    global _configured  # noqa: PLW0603

    root = logging.getLogger(_LOG_NAMESPACE)
    root.setLevel(level.upper())

    # Avoid duplicate handlers on repeated calls
    root.handlers.clear()

    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_file is not None:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if module_levels:
        for module_name, mod_level in module_levels.items():
            logging.getLogger(f"{_LOG_NAMESPACE}.{module_name}").setLevel(
                mod_level.upper()
            )

    _configured = True
