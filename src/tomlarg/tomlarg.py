import argparse
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
        delimiter: str = ".",
        **kwargs: Any,
    ) -> None:
        if not delimiter:
            raise ValueError("delimiter must not be empty")
        self._sources: list[Mapping[str, Any]] = []
        self._merged: dict[str, Any] = {}
        self._leaves: set[str] = set()
        self._delimiter = delimiter
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
            if nested.startswith(value + self._delimiter):
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
        flat = flatten(self._merged, self._delimiter, self._leaves)
        for path, value in flat.items():
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
            ns = Namespace(self._delimiter)
            for key, value in node.items():
                path = prefix + key
                if path in self._leaves:
                    built: Any = copy_value(value)
                elif is_table(value):
                    built = seed(value, path + self._delimiter)
                elif is_array_of_tables(value):
                    built = [
                        seed(item, f"{path}{self._delimiter}{i}{self._delimiter}")
                        for i, item in enumerate(value)
                    ]
                else:
                    built = copy_value(value)
                object.__setattr__(ns, key, built)
            return ns

        def graft(target: Namespace, skeleton: Namespace) -> None:
            """
            Add whatever the skeleton has and the target lacks, so a caller's
            namespace gains the tables that dotted dests are assigned through.
            """
            for key, value in vars(skeleton).items():
                existing = getattr(target, key, None)
                if isinstance(existing, Namespace) and isinstance(value, Namespace):
                    graft(existing, value)
                elif not hasattr(target, key):
                    object.__setattr__(target, key, value)

        if namespace is None:
            namespace = seed(self._merged, "")
        elif isinstance(namespace, Namespace):
            graft(namespace, seed(self._merged, ""))
        self._open_dest_paths(namespace)
        self._copy_container_defaults(namespace)
        return super().parse_known_args(args, namespace)

    def _open_dest_paths(self, namespace: argparse.Namespace) -> None:
        """
        Create the tables a dotted dest is assigned through, so that a declared
        argument no TOML source describes still has somewhere to be stored.
        """
        if not isinstance(namespace, Namespace):
            return
        for action in self._actions:
            if action.default is argparse.SUPPRESS:
                continue
            *parents, _ = action.dest.split(self._delimiter)
            node: Any = namespace
            for segment in parents:
                node = self._open_path(node, segment, action.dest)

    def _open_path(self, node: Any, segment: str, dest: str) -> Any:
        """
        Resolve one segment of dest, adding an empty table where none is held.
        """
        if is_array(node):
            if not (segment.isdigit() and int(segment) < len(node)):
                raise ValueError(
                    f"argument dest {dest!r} indexes {segment!r}, which is "
                    "beyond the array it addresses"
                )
            return node[int(segment)]
        child = getattr(node, segment, None)
        if child is None:
            child = Namespace(self._delimiter)
            object.__setattr__(node, segment, child)
        return child

    def _copy_container_defaults(self, namespace: argparse.Namespace) -> None:
        """
        Prevents argparse from assigning default reference namespaces which
        shares tables or arrays between multiple parses.
        """
        for action in self._actions:
            if not (is_table(action.default) or is_array(action.default)):
                continue
            if not hasattr(namespace, action.dest):
                setattr(namespace, action.dest, copy_value(action.default))

    def format_usage(self) -> str:
        self._apply_toml()
        return super().format_usage()

    def format_help(self) -> str:
        self._apply_toml()
        return super().format_help()
