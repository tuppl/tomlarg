import datetime
from types import MappingProxyType

import pytest

from tomlarg.types import TomlType, is_array, is_array_of_tables, is_table, type_of


class TestIsTable:
    @pytest.mark.parametrize("value", [{}, {"a": 1}, MappingProxyType({"a": 1})])
    def test_mappings_are_tables(self, value):
        assert is_table(value) is True

    @pytest.mark.parametrize("value", [[], [{"a": 1}], "a", 1, None])
    def test_anything_else_is_not(self, value):
        assert is_table(value) is False


class TestIsArray:
    @pytest.mark.parametrize("value", [[], [1, 2], [{"a": 1}]])
    def test_lists_are_arrays(self, value):
        assert is_array(value) is True

    @pytest.mark.parametrize("value", [{}, "ab", (1, 2), 1, None])
    def test_anything_else_is_not(self, value):
        assert is_array(value) is False


class TestIsArrayOfTables:
    @pytest.mark.parametrize(
        "value", [[{"a": 1}], [{"a": 1}, {"b": 2}], [MappingProxyType({"a": 1})]]
    )
    def test_arrays_of_tables(self, value):
        assert is_array_of_tables(value) is True

    def test_empty_array_is_not(self):
        assert is_array_of_tables([]) is False

    def test_mixed_elements_are_not(self):
        assert is_array_of_tables([{"a": 1}, 2]) is False

    @pytest.mark.parametrize("value", [[1, 2], {"a": 1}, "a"])
    def test_anything_else_is_not(self, value):
        assert is_array_of_tables(value) is False


class TestTypeOf:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ({}, TomlType.TABLE),
            ({"a": 1}, TomlType.TABLE),
            (MappingProxyType({"a": 1}), TomlType.TABLE),
            ([{"a": 1}], TomlType.ARRAY_OF_TABLES),
            ([], TomlType.ARRAY),
            ([1, 2], TomlType.ARRAY),
            ([{"a": 1}, 2], TomlType.ARRAY),
            ("a", TomlType.STRING),
            (1, TomlType.INTEGER),
            (1.5, TomlType.FLOAT),
            ("2020-01-02", TomlType.STRING),
            (datetime.date(2020, 1, 2), TomlType.DATE),
            (datetime.time(7, 32), TomlType.TIME),
            (None, TomlType.UNKNOWN),
            (object(), TomlType.UNKNOWN),
        ],
    )
    def test_types(self, value, expected):
        assert type_of(value) is expected

    def test_bool_is_not_an_integer(self):
        assert type_of(True) is TomlType.BOOLEAN

    def test_datetime_is_not_a_date(self):
        moment = datetime.datetime(2020, 1, 2, 3, 4, tzinfo=datetime.UTC)
        assert type_of(moment) is TomlType.DATETIME


class TestTomlTypeNames:
    def test_formats_as_its_name(self):
        assert f"{TomlType.ARRAY_OF_TABLES}" == "array of tables"
