from collections.abc import Collection, Mapping
from typing import Any

from .types import is_array_of_tables, is_table


def flatten(
    data: Mapping[str, Any],
    delimiter: str = ".",
    leaves: Collection[str] = (),
) -> dict[str, Any]:
    """
    Flatten TOML data into delimited paths.

    Tables are descended into and arrays of tables are indexed, so
    ``{"servers": [{"host": "s1"}]}`` becomes ``{"servers.0.host": "s1"}``.

    Paths named in leaves are kept whole rather than descended into, and a
    string names a single leaf.
    """
    if not delimiter:
        raise ValueError("delimiter must not be empty")
    if isinstance(leaves, str):
        leaves = {leaves}
    flat: dict[str, Any] = {}

    def descend(node: Mapping[str, Any], prefix: str) -> None:
        for key, value in node.items():
            if not isinstance(key, str):
                raise TypeError(f"key {key!r} is not a string: {type(key).__name__}")
            if delimiter in key:
                raise ValueError(f"key {key!r} contains the delimiter {delimiter!r}")
            path = prefix + key
            if path in leaves:
                flat[path] = value
            elif is_table(value):
                place(value, path)
            elif is_array_of_tables(value):
                for index, item in enumerate(value):
                    place(item, f"{path}{delimiter}{index}")
            else:
                flat[path] = value

    def place(table: Mapping[str, Any], path: str) -> None:
        """
        Descend a table, or keep an empty one whole so its path survives.
        """
        if table:
            descend(table, path + delimiter)
        else:
            flat[path] = table

    descend(data, "")
    return flat
