import argparse
from collections.abc import Iterator
from typing import Any, Self

from .types import is_array, is_table


def _child(node: Any, segment: str) -> Any:
    return node[int(segment)] if is_array(node) else getattr(node, segment)


def _set_child(node: Any, segment: str, value: Any) -> None:
    if is_array(node):
        node[int(segment)] = value
    else:
        setattr(node, segment, value)


def _plain(value: Any) -> Any:
    """
    Rebuild a value as plain data. Namespaces are made dicts.
    """
    if isinstance(value, Namespace):
        return dict(value)
    if is_table(value):
        return {key: _plain(item) for key, item in value.items()}
    if is_array(value):
        return [_plain(item) for item in value]
    return value


class Namespace(argparse.Namespace):
    """
    Namespace which inherits ``argspace.Namespace`` which is used to hold CLI
    arguments as object attributes.

    This Namespace is addressable using delimited paths e.g. ``ns.db.host`` and
    ``getattr(ns, "db.host")`` resolve to the same value. Integer segments
    index into lists, which is what lets arrays of tables round-trip.

    The delimiter is held in a slot rather than an attribute, so it stays out
    of ``vars()`` and cannot be mistaken for a TOML key.
    """

    __slots__ = ("__delimiter",)

    def __new__(cls, delimiter: str = ".", **kwargs: Any) -> Self:
        namespace = super().__new__(cls)
        object.__setattr__(namespace, "_Namespace__delimiter", delimiter)
        return namespace

    def __init__(self, delimiter: str = ".", **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @property
    def _delimiter(self) -> str:
        return object.__getattribute__(self, "_Namespace__delimiter")

    def _walk(self, path: str) -> tuple[Any, str]:
        """
        Resolve every segment of path but the last, returning the node reached
        and the segment left over.
        """
        *parents, leaf = path.split(self._delimiter)
        if not leaf or not all(parents):
            raise AttributeError(path)
        node: Any = self
        for segment in parents:
            node = _child(node, segment)
        return node, leaf

    def __setattr__(self, name: str, value: Any) -> None:
        if self._delimiter not in name:
            object.__setattr__(self, name, value)
            return
        node, leaf = self._walk(name)
        _set_child(node, leaf, value)

    def __getattr__(self, name: str) -> Any:
        if self._delimiter not in name:
            raise AttributeError(name)
        node, leaf = self._walk(name)
        return _child(node, leaf)

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        """
        Yield (key, value) pairs, converting nested namespaces to dicts so that
        dict(ns) rebuilds the whole tree.
        """
        for key, value in vars(self).items():
            yield key, _plain(value)
