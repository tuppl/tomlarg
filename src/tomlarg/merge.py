from collections.abc import Mapping
from typing import Any

from .types import is_table, type_of


def deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """
    Merge overlay onto base, recursing into tables and replacing any other
    value outright. Replacing a value with one of a different type raises
    ValueError. Neither input is mutated.
    """

    def merge(
        base: Mapping[str, Any], overlay: Mapping[str, Any], prefix: str
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in overlay.items():
            if key in merged:
                existing = merged[key]
                existing_type, value_type = type_of(existing), type_of(value)
                if existing_type is not value_type:
                    raise ValueError(
                        f"cannot replace {existing_type} {prefix + key!r} "
                        f"with {value_type}"
                    )
                if is_table(existing):
                    merged[key] = merge(existing, value, f"{prefix}{key}.")
                    continue
            merged[key] = value
        return merged

    return merge(base, overlay, "")
