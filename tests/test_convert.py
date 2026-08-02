import argparse
import datetime

import pytest

from tomlarg.convert import (
    argument_kwargs,
    comma_separated,
    converter_for,
    element_converter,
    to_bool,
)


class TestToBool:
    @pytest.mark.parametrize("text", ["true", "True", " TRUE "])
    def test_true(self, text):
        assert to_bool(text) is True

    @pytest.mark.parametrize("text", ["false", "False", " FALSE "])
    def test_false(self, text):
        assert to_bool(text) is False

    @pytest.mark.parametrize("text", ["yes", "no", "on", "off", "1", "0"])
    def test_spellings_toml_does_not_have_are_rejected(self, text):
        with pytest.raises(ValueError, match="expected 'true' or 'false'"):
            to_bool(text)

    @pytest.mark.parametrize("text", ["", "maybe", "2", "truthy"])
    def test_anything_else_raises(self, text):
        with pytest.raises(ValueError, match="invalid boolean"):
            to_bool(text)


class TestConverterFor:
    def test_bool_is_not_treated_as_int(self):
        assert converter_for(True) is to_bool

    def test_datetime_is_not_treated_as_date(self):
        convert = converter_for(datetime.datetime(2020, 1, 2, 3, 4))  # noqa: DTZ001
        assert convert("2020-01-02T03:04") == datetime.datetime(2020, 1, 2, 3, 4)  # noqa: DTZ001

    def test_date(self):
        convert = converter_for(datetime.date(2020, 1, 2))
        assert convert("2020-01-02") == datetime.date(2020, 1, 2)

    def test_time(self):
        convert = converter_for(datetime.time(7, 32))
        assert convert("07:32") == datetime.time(7, 32)

    @pytest.mark.parametrize("value, expected", [(1, int), (1.5, float), ("x", str)])
    def test_scalars(self, value, expected):
        assert converter_for(value) is expected

    @pytest.mark.parametrize("value", [None, object(), [1], {"a": 1}])
    def test_unsupported_types_have_no_converter(self, value):
        assert converter_for(value) is None


class TestCommaSeparated:
    def test_splits_and_converts(self):
        assert comma_separated(int)("1,2,3") == [1, 2, 3]

    def test_empty_text_is_an_empty_list(self):
        assert comma_separated(int)("") == []

    def test_single_element(self):
        assert comma_separated(str)("a") == ["a"]


class TestElementConverter:
    def test_uniform_elements(self):
        assert element_converter([1, 2]) is int

    def test_mixed_elements_fall_back_to_str(self):
        assert element_converter([1, "a"]) is str

    def test_empty_array_falls_back_to_str(self):
        assert element_converter([]) is str

    def test_elements_without_a_converter_fall_back_to_str(self):
        assert element_converter([None, None]) is str


class TestArgumentKwargs:
    def test_bool_becomes_a_negatable_flag(self):
        assert argument_kwargs("debug", False) == {
            "action": argparse.BooleanOptionalAction,
            "default": False,
        }

    def test_scalar_carries_its_converter_and_default(self):
        assert argument_kwargs("port", 8080) == {"type": int, "default": 8080}

    def test_array_is_optional_and_defaults_to_the_toml_value(self):
        kwargs = argument_kwargs("tags", ["a", "b"])
        assert kwargs["nargs"] == "?"
        assert kwargs["const"] == []
        assert kwargs["default"] == ["a", "b"]
        assert kwargs["type"]("x,y") == ["x", "y"]

    def test_array_of_tables_is_treated_as_an_array(self):
        kwargs = argument_kwargs("servers", [{"host": "a"}])
        assert kwargs["nargs"] == "?"
        assert kwargs["default"] == [{"host": "a"}]

    def test_unsupported_value_names_the_key_and_type(self):
        with pytest.raises(
            ValueError, match="unsupported TOML value type for 'x': unknown"
        ):
            argument_kwargs("x", None)

    def test_table_names_the_key_and_type(self):
        with pytest.raises(
            ValueError, match="unsupported TOML value type for 'x': table"
        ):
            argument_kwargs("x", {"a": 1})
