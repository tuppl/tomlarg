import datetime
import tomllib
from types import MappingProxyType

import pytest

from tomlarg.merge import deep_merge


def test_empty():
    base = {}
    overlay = {}
    assert deep_merge(base, overlay) == {}


def test_empty_overlay_keeps_base():
    base = {"a": 1}
    overlay = {}
    assert deep_merge(base, overlay) == {"a": 1}


def test_empty_base_takes_overlay():
    base = {}
    overlay = {"a": 1}
    assert deep_merge(base, overlay) == {"a": 1}


def test_overlay_wins():
    base = {"a": 1}
    overlay = {"a": 2}
    assert deep_merge(base, overlay) == {"a": 2}


def test_falsy_overlay_values_win():
    base = {"a": 1, "flag": True}
    overlay = {"a": 0, "flag": False}
    assert deep_merge(base, overlay) == {"a": 0, "flag": False}


def test_disjoint_keys_are_kept():
    base = {"a": 1}
    overlay = {"b": 2}
    assert deep_merge(base, overlay) == {"a": 1, "b": 2}


def test_tables_merge_per_leaf():
    base = {"db": {"host": "x", "port": 5432}}
    overlay = {"db": {"host": "y"}}
    assert deep_merge(base, overlay) == {"db": {"host": "y", "port": 5432}}


def test_nested_tables_merge_per_leaf():
    base = {"db": {"pool": {"size": 5, "timeout": 30}}}
    overlay = {"db": {"pool": {"size": 10}}}
    assert deep_merge(base, overlay) == {"db": {"pool": {"size": 10, "timeout": 30}}}


def test_empty_overlay_table_keeps_base_table():
    base = {"db": {"host": "x"}}
    overlay = {"db": {}}
    assert deep_merge(base, overlay) == {"db": {"host": "x"}}


def test_array_of_tables_is_replaced_whole():
    base = {"servers": [{"host": "a"}, {"host": "b"}]}
    overlay = {"servers": [{"host": "c"}]}
    assert deep_merge(base, overlay) == {"servers": [{"host": "c"}]}


def test_arrays_are_replaced_not_concatenated():
    base = {"ports": [1, 2, 3]}
    overlay = {"ports": [4]}
    assert deep_merge(base, overlay) == {"ports": [4]}


def test_empty_overlay_array_clears_base_array():
    base = {"ports": [1, 2]}
    overlay = {"ports": []}
    assert deep_merge(base, overlay) == {"ports": []}


def test_array_element_types_are_not_checked():
    base = {"ports": [1, 2]}
    overlay = {"ports": ["a"]}
    assert deep_merge(base, overlay) == {"ports": ["a"]}


def test_mixed_type_arrays_are_legal_toml():
    base = tomllib.loads('x = [1, "a", true]')
    overlay = tomllib.loads("x = [1979-05-27, 2.5]")
    assert deep_merge(base, overlay) == {"x": [datetime.date(1979, 5, 27), 2.5]}


def test_a_mixed_array_replaces_a_uniform_one():
    base = {"x": [1, 2]}
    overlay = {"x": [1, "a", True]}
    assert deep_merge(base, overlay) == {"x": [1, "a", True]}


def test_a_uniform_array_replaces_a_mixed_one():
    base = {"x": [1, "a", True]}
    overlay = {"x": [1, 2]}
    assert deep_merge(base, overlay) == {"x": [1, 2]}


def test_an_array_holding_a_table_is_a_plain_array():
    base = {"x": [{"a": 1}, 2]}
    overlay = {"x": [3]}
    assert deep_merge(base, overlay) == {"x": [3]}


def test_array_replacing_table_raises():
    base = {"servers": {"host": "c"}}
    overlay = {"servers": [{"host": "a"}, {"host": "b"}]}
    with pytest.raises(ValueError, match="cannot replace table 'servers'"):
        deep_merge(base, overlay)


def test_table_replacing_array_raises():
    base = {"servers": [{"host": "a"}, {"host": "b"}]}
    overlay = {"servers": {"host": "c"}}
    with pytest.raises(ValueError, match="cannot replace array of tables 'servers'"):
        deep_merge(base, overlay)


def test_scalar_replacing_table_raises():
    base = {"a": {"b": 1}}
    overlay = {"a": 2}
    with pytest.raises(ValueError, match="cannot replace table 'a' with integer"):
        deep_merge(base, overlay)


def test_table_replacing_scalar_raises():
    base = {"a": 2}
    overlay = {"a": {"b": 1}}
    with pytest.raises(ValueError, match="cannot replace integer 'a' with table"):
        deep_merge(base, overlay)


def test_array_replacing_array_of_tables_raises():
    base = {"servers": [{"host": "a"}]}
    overlay = {"servers": [1, 2]}
    with pytest.raises(ValueError, match="cannot replace array of tables 'servers'"):
        deep_merge(base, overlay)


def test_mixed_array_replacing_array_of_tables_raises():
    base = {"servers": [{"host": "a"}]}
    overlay = {"servers": [{"host": "a"}, 2]}
    with pytest.raises(ValueError, match="cannot replace array of tables 'servers'"):
        deep_merge(base, overlay)


def test_array_of_tables_replacing_empty_array_raises():
    base = {"servers": []}
    overlay = {"servers": [{"host": "a"}]}
    with pytest.raises(ValueError, match="cannot replace array 'servers'"):
        deep_merge(base, overlay)


def test_scalar_type_change_raises():
    base = {"port": 8080}
    overlay = {"port": "8080"}
    with pytest.raises(ValueError, match="cannot replace integer 'port' with string"):
        deep_merge(base, overlay)


def test_int_widening_to_float_raises():
    base = {"timeout": 30}
    overlay = {"timeout": 1.5}
    with pytest.raises(ValueError, match="cannot replace integer 'timeout' with float"):
        deep_merge(base, overlay)


def test_bool_and_int_are_distinct():
    base = {"flag": True}
    overlay = {"flag": 1}
    with pytest.raises(ValueError, match="cannot replace boolean 'flag' with integer"):
        deep_merge(base, overlay)


def test_conflict_is_reported_by_full_path():
    base = {"db": {"pool": {"size": 5}}}
    overlay = {"db": {"pool": {"size": "5"}}}
    with pytest.raises(
        ValueError, match="cannot replace integer 'db.pool.size' with string"
    ):
        deep_merge(base, overlay)


def test_key_order_is_base_then_new_overlay_keys():
    base = {"b": 1, "a": 1}
    overlay = {"c": 1, "b": 2}
    assert list(deep_merge(base, overlay)) == ["b", "a", "c"]


def test_nested_key_order_is_base_then_new_overlay_keys():
    base = {"db": {"b": 1, "a": 1}}
    overlay = {"db": {"c": 1, "b": 2}}
    assert list(deep_merge(base, overlay)["db"]) == ["b", "a", "c"]


def test_repeated_merge_applies_sources_in_order():
    first = {"db": {"host": "a", "port": 1}}
    second = {"db": {"host": "b"}}
    third = {"db": {"port": 2}}
    merged = deep_merge(deep_merge(first, second), third)
    assert merged == {"db": {"host": "b", "port": 2}}


def test_merge_is_associative():
    first = {"db": {"host": "a"}}
    second = {"db": {"port": 1}}
    third = {"db": {"host": "b"}}
    left = deep_merge(deep_merge(first, second), third)
    right = deep_merge(first, deep_merge(second, third))
    assert left == right


def test_self_merge_is_identity():
    base = {"db": {"host": "x"}}
    assert deep_merge(base, base) == {"db": {"host": "x"}}
    assert base == {"db": {"host": "x"}}


def test_non_dict_mappings_are_accepted():
    base = MappingProxyType({"db": MappingProxyType({"host": "x", "port": 1})})
    overlay = MappingProxyType({"db": MappingProxyType({"host": "y"})})
    assert deep_merge(base, overlay) == {"db": {"host": "y", "port": 1}}


def test_mapping_values_are_converted_only_where_keys_collide():
    proxy = MappingProxyType({"host": "x"})
    assert type(deep_merge({}, {"db": proxy})["db"]) is MappingProxyType
    assert type(deep_merge({"db": {"port": 1}}, {"db": proxy})["db"]) is dict


def test_inputs_are_not_mutated():
    base = {"db": {"host": "x"}}
    overlay = {"db": {"port": 1}}
    deep_merge(base, overlay)
    assert base == {"db": {"host": "x"}}
    assert overlay == {"db": {"port": 1}}
