import argparse
import contextlib
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .convert import argument_kwargs
from .flatten import flatten
from .merge import deep_merge
from .namespace import Namespace
from .types import copy_value, is_array, is_array_of_tables, is_table


class ArgumentParser(argparse.ArgumentParser):
    """
    argparse.ArgumentParser whose defaults can come from TOML.

    Tables are addressable as dotted flags (``--db.host``) and arrays of tables
    by index (``--servers.1.port``). Sources are recorded when added and applied
    at parse time, so add_toml and add_argument may be called in either order
    and --help lists every TOML-derived flag.

    Precedence (to lowest): command line, TOML, add_argument defaults.
    """

    def __init__(
        self,
        *args: Any,
        toml_file: Path | str | None = None,
        toml_str: str | None = None,
        toml_dict: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._sources: list[Mapping[str, Any]] = []
        self._merged: dict[str, Any] = {}
        self._leaves: set[str] = set()
        super().__init__(*args, **kwargs)
        if toml_file is not None:
            self.add_toml(toml_file)
        if toml_str is not None:
            self.add_toml_str(toml_str)
        if toml_dict is not None:
            self.add_toml_dict(toml_dict)

    def add_toml(self, path: Path | str) -> None:
        """
        Record the contents of a TOML file as a source of defaults.
        """
        with open(path, "rb") as f:
            self.add_toml_dict(tomllib.load(f))

    def add_toml_str(self, text: str) -> None:
        """
        Record a TOML document as a source of defaults.
        """
        self.add_toml_dict(tomllib.loads(text))

    def add_toml_dict(self, data: Mapping[str, Any]) -> None:
        """
        Record already-parsed TOML data as a source of defaults.
        """
        self._sources.append(data)

    def add_argument(self, *args: Any, **kwargs: Any) -> argparse.Action:
        """
        Register an argument, rejecting a dest/attribute that is nested inside another.
        """
        action: argparse.Action = super().add_argument(*args, **kwargs)

        def _reject_nesting(value: str, nested: str) -> None:
            if nested.startswith(value + "."):
                raise ValueError(
                    f"{value!r} is both a value and a prefix of {nested!r}; "
                    "one would overwrite the other"
                )

        for other in self._actions:
            if other is not action:
                _reject_nesting(action.dest, other.dest)
                _reject_nesting(other.dest, action.dest)
        return action

    def _action_for(self, dest: str) -> argparse.Action | None:
        return next((a for a in self._actions if a.dest == dest), None)

    def _bind(self, path: str, value: Any) -> None:
        """
        Make value the default for path, adding the flag if it is undeclared.

        An undeclared table has no command-line spelling, so it is left alone
        rather than given a flag.
        """
        action = self._action_for(path)
        if action is not None:
            if action.default is not argparse.SUPPRESS:
                action.default = value
            return
        if is_table(value):
            return
        option = f"--{path}"
        taken = self._option_string_actions.get(option)
        if taken is not None:
            raise ValueError(
                f"TOML key {path!r} needs {option}, which is already taken by "
                f"an argument storing to {taken.dest!r}; give that argument "
                f"dest={path!r} or rename the TOML key"
            )
        self.add_argument(option, dest=path, **argument_kwargs(path, value))

    def _apply_toml(self) -> None:
        """
        Merge the pending sources and bind every leaf of the result.

        Dests already declared by add_argument are treated as leaves, so a
        declared table keeps its TOML value whole instead of being expanded.
        """
        if not self._sources:
            return
        for source in self._sources:
            self._merged = deep_merge(self._merged, source)
        self._sources = []
        self._leaves = {action.dest for action in self._actions}
        for path, value in flatten(self._merged, leaves=self._leaves).items():
            self._bind(path, value)

    def parse_known_args(
        self,
        args: Sequence[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> tuple[Namespace, list[str]]:
        self._apply_toml()

        def seed(node: Mapping[str, Any], prefix: str) -> Namespace:
            """
            Build a namespace skeleton from TOML data, so that tables become
            nested namespaces and arrays of tables become real lists.
            """
            ns = Namespace()
            for key, value in node.items():
                path = prefix + key
                if path in self._leaves:
                    built: Any = copy_value(value)
                elif is_table(value):
                    built = seed(value, path + ".")
                elif is_array_of_tables(value):
                    built = [seed(item, f"{path}.{i}.") for i, item in enumerate(value)]
                else:
                    built = copy_value(value)
                object.__setattr__(ns, key, built)
            return ns

        if namespace is None:
            namespace = seed(self._merged, "")
        else:
            self._copy_container_defaults(namespace)
        return super().parse_known_args(args, namespace)

    def _copy_container_defaults(self, namespace: argparse.Namespace) -> None:
        """
        Prevents argparse from assigning default reference namespaces which
        shares tables or arrays between multiple parses.
        """
        for action in self._actions:
            if not (is_table(action.default) or is_array(action.default)):
                continue
            with contextlib.suppress(AttributeError, IndexError, ValueError):
                if not hasattr(namespace, action.dest):
                    setattr(namespace, action.dest, copy_value(action.default))

    def format_usage(self) -> str:
        self._apply_toml()
        return super().format_usage()

    def format_help(self) -> str:
        self._apply_toml()
        return super().format_help()
