import tomllib
from types import MappingProxyType

import pytest

from tomlarg.flatten import flatten


@pytest.fixture
def document():
    return tomllib.loads("""
name = "prod"
tags = ["a", "b"]
empty_list = []

[db]
host = "localhost"

[db.pool]
size = 5

[empty_table]

[[servers]]
host = "s1"

[[servers]]
host = "s2"

[[servers.disks]]
mount = "/"
""")


class TestFlatten:
    def test_empty(self):
        assert flatten({}) == {}

    def test_scalars_are_leaves(self):
        assert flatten({"a": 1, "b": "x", "c": True}) == {"a": 1, "b": "x", "c": True}

    def test_table_is_descended(self):
        assert flatten({"db": {"host": "x"}}) == {"db.host": "x"}

    def test_nested_tables_are_descended(self):
        assert flatten({"a": {"b": {"c": 1}}}) == {"a.b.c": 1}

    def test_array_of_tables_is_indexed(self):
        data = {"servers": [{"host": "s1"}, {"host": "s2"}]}
        assert flatten(data) == {"servers.0.host": "s1", "servers.1.host": "s2"}

    def test_nested_array_of_tables(self):
        data = {"servers": [{"disks": [{"mount": "/"}]}]}
        assert flatten(data) == {"servers.0.disks.0.mount": "/"}

    @pytest.mark.parametrize(
        "value",
        [["a", "b"], [1, 2], [], [1, {"a": 2}], [{"a": 1}, 2], [[1, 2], [3]]],
        ids=["strings", "ints", "empty", "table-last", "table-first", "nested-arrays"],
    )
    def test_arrays_that_are_not_all_tables_are_leaves(self, value):
        assert flatten({"x": value}) == {"x": value}

    def test_empty_table_is_a_leaf(self):
        assert flatten({"a": 1, "empty": {}}) == {"a": 1, "empty": {}}

    def test_nested_empty_table_is_a_leaf(self):
        assert flatten({"a": {"b": {}}}) == {"a.b": {}}

    def test_empty_table_in_an_array_of_tables_keeps_its_index(self):
        assert flatten({"servers": [{}]}) == {"servers.0": {}}

    def test_empty_entry_does_not_gap_the_indexes(self):
        assert flatten({"servers": [{}, {"host": "s2"}]}) == {
            "servers.0": {},
            "servers.1.host": "s2",
        }

    def test_numeric_table_keys_are_indistinguishable_from_indexes(self):
        assert flatten({"s": {"0": {"h": 1}}}) == {"s.0.h": 1}
        assert flatten({"s": [{"h": 1}]}) == {"s.0.h": 1}

    def test_non_dict_mappings_are_descended(self):
        data = MappingProxyType({"db": MappingProxyType({"host": "x"})})
        assert flatten(data) == {"db.host": "x"}

    def test_leaf_values_are_not_copied(self):
        tags = ["a", "b"]
        assert flatten({"tags": tags})["tags"] is tags

    def test_input_is_not_mutated(self):
        data = {"db": {"host": "x"}}
        flatten(data)
        assert data == {"db": {"host": "x"}}

    def test_paths_keep_document_order(self):
        data = {"z": 1, "a": {"y": 2, "b": 3}, "m": 4}
        assert list(flatten(data)) == ["z", "a.y", "a.b", "m"]


class TestDelimiter:
    def test_custom_delimiter(self):
        assert flatten({"db": {"host": "x"}}, delimiter="__") == {"db__host": "x"}

    def test_key_containing_delimiter_raises(self):
        with pytest.raises(ValueError, match="contains the delimiter"):
            flatten({"tool.ruff": {"line-length": 88}})

    def test_key_containing_delimiter_raises_when_nested(self):
        with pytest.raises(ValueError, match="contains the delimiter"):
            flatten({"tool": {"a.b": 1}})

    def test_key_is_legal_under_a_different_delimiter(self):
        assert flatten({"tool.ruff": {"n": 1}}, delimiter="__") == {"tool.ruff__n": 1}

    def test_empty_delimiter_rejects_every_key(self):
        with pytest.raises(ValueError, match="contains the delimiter ''"):
            flatten({"a": 1}, delimiter="")


class TestKeys:
    @pytest.mark.parametrize(
        "data",
        [
            {1: "a"},
            {"t": {1: "a"}},
            {"t": {"u": {1: "a"}}},
            {"servers": [{1: "a"}]},
            {"servers": [{"host": "s1"}, {"disks": [{1: "a"}]}]},
        ],
        ids=["top-level", "table", "nested-table", "array-of-tables", "nested-array"],
    )
    def test_non_string_key_raises(self, data):
        with pytest.raises(TypeError, match="key 1 is not a string: int"):
            flatten(data)

    @pytest.mark.parametrize(
        "key, expected",
        [
            (2.5, "key 2.5 is not a string: float"),
            (True, "key True is not a string: bool"),
            (None, "key None is not a string: NoneType"),
            (("a", "b"), r"key \('a', 'b'\) is not a string: tuple"),
        ],
        ids=["float", "bool", "none", "tuple"],
    )
    def test_non_string_key_error_names_the_key_and_type(self, key, expected):
        with pytest.raises(TypeError, match=expected):
            flatten({key: 1})

    def test_empty_key_is_kept(self):
        assert tomllib.loads('"" = 1') == {"": 1}
        assert flatten({"": 1}) == {"": 1}

    def test_empty_key_emits_a_path_that_is_illegal_as_a_key(self):
        assert flatten({"": {"a": 1}}) == {".a": 1}
        with pytest.raises(ValueError, match="contains the delimiter"):
            flatten({".a": 1})


class TestLeaves:
    def test_table_is_kept_whole(self):
        data = {"labels": {"env": "prod"}}
        assert flatten(data, leaves={"labels"}) == {"labels": {"env": "prod"}}

    def test_nested_table_is_kept_whole(self):
        data = {"db": {"host": "x", "pool": {"size": 5}}}
        assert flatten(data, leaves={"db.pool"}) == {
            "db.host": "x",
            "db.pool": {"size": 5},
        }

    def test_array_of_tables_is_kept_whole(self):
        data = {"servers": [{"host": "s1"}, {"host": "s2"}]}
        assert flatten(data, leaves={"servers"}) == {"servers": data["servers"]}

    def test_leaf_inside_an_array_of_tables(self):
        data = {"servers": [{"host": "s1", "disks": [{"mount": "/"}]}]}
        assert flatten(data, leaves={"servers.0.disks"}) == {
            "servers.0.host": "s1",
            "servers.0.disks": [{"mount": "/"}],
        }

    def test_leaf_on_a_scalar_changes_nothing(self):
        assert flatten({"a": 1}, leaves={"a"}) == {"a": 1}

    def test_unmatched_leaf_is_ignored(self):
        data = {"db": {"host": "x"}}
        assert flatten(data, leaves={"nope"}) == {"db.host": "x"}

    @pytest.mark.parametrize("leaves", [["db.pool"], ("db.pool",), {"db.pool"}])
    def test_any_collection_of_leaves(self, leaves):
        data = {"db": {"pool": {"size": 5}}}
        assert flatten(data, leaves=leaves) == {"db.pool": {"size": 5}}

    def test_leaves_are_spelled_with_the_delimiter_in_use(self):
        data = {"db": {"pool": {"size": 5}}}
        assert flatten(data, delimiter="__", leaves={"db__pool"}) == {
            "db__pool": {"size": 5}
        }
        assert flatten(data, delimiter="__", leaves={"db.pool"}) == {
            "db__pool__size": 5
        }

    def test_leaf_string_does_not_match_substrings(self):
        assert flatten({"b": {"c": 1}}, leaves="db.host") == {"b.c": 1}

    def test_leaf_string_may_be_a_nested_path(self):
        data = {"db": {"host": "x", "pool": {"size": 5}}}
        assert flatten(data, leaves="db.pool") == {
            "db.host": "x",
            "db.pool": {"size": 5},
        }

    def test_leaf_value_is_not_copied(self):
        labels = {"env": "prod"}
        assert flatten({"labels": labels}, leaves={"labels"})["labels"] is labels

    def test_keys_below_a_leaf_are_not_validated(self):
        data = {"labels": {1: "a"}}
        assert flatten(data, leaves={"labels"}) == {"labels": {1: "a"}}


def test_full_document(document):
    assert flatten(document) == {
        "name": "prod",
        "tags": ["a", "b"],
        "empty_list": [],
        "empty_table": {},
        "db.host": "localhost",
        "db.pool.size": 5,
        "servers.0.host": "s1",
        "servers.1.host": "s2",
        "servers.1.disks.0.mount": "/",
    }
