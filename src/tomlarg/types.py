import datetime
from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class TomlType(StrEnum):
    """
    The types a TOML value can have, named as they read in an error message.
    """

    TABLE = "table"
    ARRAY_OF_TABLES = "array of tables"
    ARRAY = "array"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    TIME = "time"
    UNKNOWN = "unknown"


# Order of scalars matters so types aren't miscontrued as a latter type.
_SCALARS: tuple[tuple[type, TomlType], ...] = (
    (bool, TomlType.BOOLEAN),
    (datetime.datetime, TomlType.DATETIME),
    (datetime.date, TomlType.DATE),
    (datetime.time, TomlType.TIME),
    (int, TomlType.INTEGER),
    (float, TomlType.FLOAT),
    (str, TomlType.STRING),
)


def is_table(value: Any) -> bool:
    """
    Report whether a value is a table.
    """
    return isinstance(value, Mapping)


def is_array(value: Any) -> bool:
    """
    Report whether a value is an array.
    """
    return isinstance(value, list)


def is_array_of_tables(value: Any) -> bool:
    """
    Report whether a value is a non-empty array whose elements are all tables.
    """
    return is_array(value) and len(value) > 0 and all(is_table(item) for item in value)


def copy_value(value: Any) -> Any:
    """
    Rebuild every container in a value so the result shares no mutable state
    with the original. Leaf scalars are shared, being immutable.
    """
    if is_table(value):
        return {key: copy_value(item) for key, item in value.items()}
    if is_array(value):
        return [copy_value(item) for item in value]
    return value


def type_of(value: Any) -> TomlType:
    """
    Report the TOML type of a value, UNKNOWN for anything TOML cannot hold.
    """
    if is_table(value):
        return TomlType.TABLE
    if is_array_of_tables(value):
        return TomlType.ARRAY_OF_TABLES
    if is_array(value):
        return TomlType.ARRAY
    for cls, toml_type in _SCALARS:
        if isinstance(value, cls):
            return toml_type
    return TomlType.UNKNOWN
