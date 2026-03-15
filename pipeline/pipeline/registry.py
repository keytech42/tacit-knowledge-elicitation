"""Generic strategy registry with @register decorator."""

from __future__ import annotations

from typing import Any

_REGISTRIES: dict[str, dict[str, type]] = {}


def register(category: str, name: str):
    """Register a strategy class under a category and name."""
    def decorator(cls):
        _REGISTRIES.setdefault(category, {})[name] = cls
        return cls
    return decorator


def get_strategy(category: str, name: str, **kwargs: Any):
    """Instantiate a registered strategy by category and name."""
    registry = _REGISTRIES.get(category)
    if not registry:
        available = list(_REGISTRIES.keys())
        raise KeyError(f"Unknown category '{category}'. Available: {available}")
    cls = registry.get(name)
    if not cls:
        available = list(registry.keys())
        raise KeyError(f"Unknown {category} strategy '{name}'. Available: {available}")
    return cls(**kwargs)


def list_strategies(category: str) -> list[str]:
    """List registered strategy names for a category."""
    return list(_REGISTRIES.get(category, {}).keys())
