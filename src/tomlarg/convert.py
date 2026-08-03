import argparse
import datetime
from collections.abc import Callable
from typing import Any

from .types import TomlType, copy_value, type_of


def to_bool(text: str) -> bool:
    """
    Parse a command-line spelling of a boolean.

    TOML has only true and false, so no other spelling is accepted.
    """
    lowered = text.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise ValueError(f"invalid boolean {text!r}: expected 'true' or 'false'")


_CONVERTERS: dict[TomlType, Callable[[str], Any]] = {
    TomlType.STRING: str,
    TomlType.INTEGER: int,
    TomlType.FLOAT: float,
    TomlType.BOOLEAN: to_bool,
    TomlType.DATETIME: datetime.datetime.fromisoformat,
    TomlType.DATE: datetime.date.fromisoformat,
    TomlType.TIME: datetime.time.fromisoformat,
}


def converter_for(value: Any) -> Callable[[str], Any] | None:
    """
    Return a string converter matching the type of a TOML value, or None when
    the type has no command-line spelling.
    """
    return _CONVERTERS.get(type_of(value))


def comma_separated(element: Callable[[str], Any]) -> Callable[[str], list[Any]]:
    """
    Build a converter reading a comma-separated list, empty text giving [].
    """

    def convert(text: str) -> list[Any]:
        if text == "":
            return []
        return [element(part) for part in text.split(",")]

    return convert


def element_converter(values: list[Any]) -> Callable[[str], Any]:
    """
    Return the converter shared by every element of an array, falling back to
    str when the elements disagree or have no converter.
    """
    types = {type_of(value) for value in values}
    if len(types) == 1:
        converter = converter_for(values[0])
        if converter is not None:
            return converter
    return str


class StoreArray(argparse.Action):
    """
    Store an array under its own list.

    argparse assigns const and converted values by reference, so without this
    every parse of the same parser would hand out one shared list.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, list(values))


class BooleanOptional(argparse.Action):
    """
    Store a boolean, giving every option string a negated spelling.

    argparse.BooleanOptionalAction builds that spelling from a literal ``--``,
    so the prefix is taken from the option string itself instead.
    """

    def __init__(self, option_strings: list[str], dest: str, **kwargs: Any) -> None:
        spellings = []
        self._negative = set()
        for option in option_strings:
            negative = f"{option[:2]}no-{option[2:]}"
            spellings += [option, negative]
            self._negative.add(negative)
        super().__init__(spellings, dest, nargs=0, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, option_string not in self._negative)

    def format_usage(self) -> str:
        return " | ".join(self.option_strings)


def argument_kwargs(key: str, value: Any) -> dict[str, Any]:
    """
    Build the add_argument keyword arguments describing a TOML value.

    Booleans become negatable flags and arrays take a comma-separated value.
    """
    toml_type = type_of(value)
    if toml_type is TomlType.BOOLEAN:
        return {"action": BooleanOptional, "default": value}
    if toml_type in (TomlType.ARRAY, TomlType.ARRAY_OF_TABLES):
        return {
            "action": StoreArray,
            "nargs": "?",
            "const": [],
            "type": comma_separated(element_converter(value)),
            "default": copy_value(value),
        }
    converter = _CONVERTERS.get(toml_type)
    if converter is None:
        raise ValueError(f"unsupported TOML value type for {key!r}: {toml_type}")
    return {"type": converter, "default": value}
