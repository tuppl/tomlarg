import argparse
import copy
import datetime
import pickle

import pytest

from tomlarg.namespace import Namespace


@pytest.fixture
def data():
    return {
        "name": "prod",
        "tags": ["a", "b"],
        "db": {"host": "localhost", "pool": {"size": 5}},
        "servers": [{"host": "s1", "port": 8001}, {"host": "s2", "port": 8002}],
    }


@pytest.fixture
def ns():
    return Namespace(
        name="prod",
        tags=["a", "b"],
        db=Namespace(host="localhost", pool=Namespace(size=5)),
        servers=[
            Namespace(host="s1", port=8001),
            Namespace(host="s2", port=8002),
        ],
    )


class TestAccess:
    def test_plain_attribute(self, ns):
        assert ns.name == "prod"

    def test_attribute_chaining(self, ns):
        assert ns.db.pool.size == 5

    def test_dotted_getattr_resolves_the_same_value(self, ns):
        assert getattr(ns, "db.pool.size") == ns.db.pool.size

    def test_dotted_getattr_indexes_lists(self, ns):
        assert getattr(ns, "servers.1.port") == 8002

    def test_dotted_setattr(self, ns):
        setattr(ns, "db.host", "changed")
        assert ns.db.host == "changed"

    def test_dotted_setattr_into_a_list(self, ns):
        setattr(ns, "servers.0.port", 9999)
        assert ns.servers[0].port == 9999
        assert ns.servers[1].port == 8002

    def test_plain_setattr_replaces_a_subtree(self, ns):
        ns.db = Namespace(host="other")
        assert dict(ns)["db"] == {"host": "other"}

    def test_missing_attribute_raises(self, ns):
        with pytest.raises(AttributeError):
            _ = ns.nope

    def test_missing_dotted_attribute_raises(self, ns):
        with pytest.raises(AttributeError):
            getattr(ns, "db.nope")

    def test_index_beyond_the_list_raises(self, ns):
        with pytest.raises(IndexError):
            getattr(ns, "servers.5.port")

    def test_named_segment_into_a_list_raises(self, ns):
        with pytest.raises(ValueError, match="invalid literal for int"):
            getattr(ns, "servers.first.port")

    def test_descending_into_a_leaf_raises(self, ns):
        with pytest.raises(AttributeError):
            getattr(ns, "name.nope")

    @pytest.mark.parametrize("path", ["db..host", "db.", ".db", "."])
    def test_malformed_path_raises(self, ns, path):
        with pytest.raises(AttributeError):
            getattr(ns, path)

    @pytest.mark.parametrize("path", ["db..host", "db.", ".db", "."])
    def test_malformed_path_raises_on_assignment(self, ns, path):
        with pytest.raises(AttributeError):
            setattr(ns, path, 1)


class TestDottedAssignment:
    def test_missing_parent_raises(self, ns):
        with pytest.raises(AttributeError, match="nope"):
            setattr(ns, "nope.x", 1)

    def test_index_beyond_the_list_raises(self, ns):
        with pytest.raises(IndexError):
            setattr(ns, "servers.5.port", 1)

    def test_leaf_parent_raises(self, ns):
        with pytest.raises(AttributeError):
            setattr(ns, "name.x", 1)

    def test_empty_namespace_cannot_take_a_dotted_path(self):
        with pytest.raises(AttributeError, match="db"):
            setattr(Namespace(), "db.host", 1)

    def test_parents_must_be_seeded_first(self):
        ns = Namespace(db=Namespace())
        setattr(ns, "db.host", "x")
        assert ns.db.host == "x"


class TestCopying:
    def test_copy(self, ns, data):
        assert dict(copy.copy(ns)) == data

    def test_deepcopy(self, ns, data):
        assert dict(copy.deepcopy(ns)) == data

    def test_deepcopy_is_independent(self, ns):
        clone = copy.deepcopy(ns)
        setattr(clone, "db.host", "changed")
        setattr(clone, "servers.0.port", 9999)
        assert ns.db.host == "localhost"
        assert ns.servers[0].port == 8001

    def test_copy_shares_nested_namespaces(self, ns):
        assert copy.copy(ns).db is ns.db

    def test_pickle(self, ns, data):
        assert dict(pickle.loads(pickle.dumps(ns))) == data

    def test_pickle_is_independent(self, ns):
        clone = pickle.loads(pickle.dumps(ns))
        setattr(clone, "db.pool.size", 99)
        assert ns.db.pool.size == 5


class TestIter:
    def test_round_trips_to_plain_data(self, ns, data):
        assert dict(ns) == data

    def test_converts_nested_namespaces(self, ns, data):
        assert dict(ns)["db"] == data["db"]

    def test_restores_arrays_of_tables_as_lists(self, ns, data):
        assert dict(ns)["servers"] == data["servers"]

    def test_scalar_array_is_untouched(self, ns):
        assert dict(ns)["tags"] == ["a", "b"]

    def test_sub_namespace_converts_on_its_own(self, ns, data):
        assert dict(ns.db) == data["db"]

    def test_reflects_mutation(self, ns):
        setattr(ns, "servers.1.port", 9999)
        assert dict(ns)["servers"][1]["port"] == 9999

    def test_empty(self):
        assert dict(Namespace()) == {}

    def test_yields_key_value_pairs(self):
        assert list(Namespace(a=1, b=2)) == [("a", 1), ("b", 2)]

    def test_keys_is_not_defined_so_dict_recurses(self, ns):
        assert not hasattr(ns, "keys")


class TestPlainConversion:
    def test_no_namespace_survives_inside_a_table(self):
        ns = Namespace(x={"k": Namespace(a=1)})
        assert dict(ns) == {"x": {"k": {"a": 1}}}

    def test_no_namespace_survives_inside_a_nested_table(self):
        ns = Namespace(x={"k": {"j": Namespace(a=1)}})
        assert dict(ns) == {"x": {"k": {"j": {"a": 1}}}}

    def test_no_namespace_survives_inside_a_table_in_an_array(self):
        ns = Namespace(x=[{"k": Namespace(a=1)}])
        assert dict(ns) == {"x": [{"k": {"a": 1}}]}

    def test_no_namespace_survives_inside_nested_arrays(self):
        ns = Namespace(x=[[Namespace(a=1)]])
        assert dict(ns) == {"x": [[{"a": 1}]]}

    @pytest.mark.parametrize(
        "value",
        [{"a": 1}, [1, 2], [{"a": 1}]],
        ids=["table", "array", "array-of-table"],
    )
    def test_containers_are_rebuilt(self, value):
        ns = Namespace(x=value)
        assert dict(ns)["x"] == value
        assert dict(ns)["x"] is not value

    def test_mutating_the_result_does_not_reach_the_namespace(self):
        ns = Namespace(labels={"env": "prod"})
        dict(ns)["labels"]["env"] = "changed"
        assert ns.labels == {"env": "prod"}

    def test_scalars_are_shared(self):
        moment = datetime.datetime(2020, 1, 2, tzinfo=datetime.UTC)
        ns = Namespace(t=moment)
        assert dict(ns)["t"] is moment

    def test_tuples_are_left_alone(self):
        pair = (1, 2)
        assert dict(Namespace(x=pair))["x"] is pair


class TestArgparseCompatibility:
    def test_contains(self, ns):
        assert "db" in ns
        assert "nope" not in ns

    def test_vars_stays_live(self, ns):
        assert isinstance(vars(ns)["db"], Namespace)

    def test_vars_is_not_the_converted_form(self, ns):
        assert not isinstance(vars(ns)["db"], dict)

    def test_equality_compares_attributes(self):
        assert Namespace(a=1) == Namespace(a=1)
        assert Namespace(a=1) != Namespace(a=2)

    def test_repr_shows_attributes(self):
        assert repr(Namespace(a=1)) == "Namespace(a=1)"

    def test_nherits_argparse_namespace(self):
        assert issubclass(Namespace, argparse.Namespace)
