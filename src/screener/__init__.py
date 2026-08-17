"""Configurable financial screener."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .engine import ScreenerEngine

__all__ = [
    "ScreenerEngine",
    "apply_filters",
    "load_latest_universe",
    "load_screener_config",
]


def __getattr__(name: str) -> Any:
    """Lazily expose the public API without pre-loading the CLI module."""
    if name not in __all__:
        raise AttributeError(name)
    from . import engine

    return getattr(engine, name)
