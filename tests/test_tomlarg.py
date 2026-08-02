import argparse
import datetime
import json
import tomllib

import pytest

from tomlarg import ArgumentParser
from tomlarg.namespace import Namespace


def test_multiple_args():
    parser = ArgumentParser(exit_on_error=False)
    parser.add_toml_str('foo = 10\nbar = "hello"\n')

    args = parser.parse_args(["--foo", "99", "--bar", "world"])

    assert args.foo == 99
    assert args.bar == "world"


def test_dotted_key_arg():
    parser = ArgumentParser(exit_on_error=False)
    parser.add_toml_str('[db]\nhost = "localhost"\n')

    args = parser.parse_args(["--db.host", "example.com"])

    assert getattr(args, "db.host") == "example.com"


def test_list_arg(): ...


def test_arg_with_list_value(): ...


def test_arg_with_dict_value(): ...


def test_arg_overrides_toml():
    def parse(argv):
        parser = ArgumentParser(exit_on_error=False)
        parser.add_toml_str('foo = 10\nbar = "hello"\n')
        return parser.parse_args(argv)

    assert parse([]).foo == 10
    assert parse(["--foo", "99"]).foo == 99
    assert parse(["--foo", "99"]).bar == "hello"


def test_add_toml_reads_a_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[db]\nhost = "localhost"\n')

    parser = ArgumentParser(exit_on_error=False)
    parser.add_toml(path)

    assert getattr(parser.parse_args([]), "db.host") == "localhost"


def parser(toml, **kwargs):
    return ArgumentParser(exit_on_error=False, toml_str=toml, **kwargs)


class TestSources:
    def test_constructor_is_keyword_only_so_prog_is_not_shadowed(self):
        assert ArgumentParser("myprog").prog == "myprog"

    def test_constructor_toml_str(self):
        assert parser("foo = 1").parse_args([]).foo == 1

    def test_constructor_toml_dict(self):
        p = ArgumentParser(toml_dict={"foo": 1})
        assert p.parse_args([]).foo == 1

    def test_constructor_toml_file(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text("foo = 1")
        assert ArgumentParser(toml_file=path).parse_args([]).foo == 1

    def test_add_toml_dict_requires_a_dict(self):
        with pytest.raises(TypeError):
            ArgumentParser(exit_on_error=False).add_toml_dict()

    def test_add_toml_dict_accepts_an_empty_dict(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict({})

        assert vars(p.parse_args([])) == {}

    def test_empty_dict_does_not_disturb_other_sources(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict({})
        p.add_toml_dict({"foo": 1})
        p.add_toml_dict({})

        assert p.parse_args([]).foo == 1

    def test_constructor_toml_dict_empty(self):
        assert vars(ArgumentParser(toml_dict={}).parse_args([])) == {}

    def test_add_toml_may_follow_add_argument(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--port", type=int, help="port to listen on")
        p.add_toml_str("port = 8080")

        assert p.parse_args([]).port == 8080
        assert "port to listen on" in p.format_help()

    def test_add_argument_may_follow_add_toml(self):
        p = ArgumentParser(exit_on_error=False, toml_str="port = 8080")
        p.add_argument("--port", type=int, help="port to listen on")

        assert p.parse_args([]).port == 8080
        assert "port to listen on" in p.format_help()


class TestLayering:
    def test_later_source_wins_per_leaf(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_str('[db]\nhost = "x"\nport = 5432')
        p.add_toml_str('[db]\nhost = "y"')

        args = p.parse_args([])

        assert args.db.host == "y"
        assert args.db.port == 5432

    def test_cli_still_wins_over_every_layer(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_str('[db]\nhost = "x"')
        p.add_toml_str('[db]\nhost = "y"')

        assert p.parse_args(["--db.host", "z"]).db.host == "z"


class TestTypes:
    def test_int_and_float(self):
        args = parser("i = 1\nf = 1.5").parse_args(["--i", "2", "--f", "2.5"])
        assert args.i == 2
        assert args.f == 2.5

    def test_bool_uses_optional_negation(self):
        p = parser("debug = false")
        assert p.parse_args([]).debug is False
        assert p.parse_args(["--debug"]).debug is True
        assert p.parse_args(["--no-debug"]).debug is False

    def test_bool_default_true_is_negatable(self):
        p = parser("debug = true")
        assert p.parse_args([]).debug is True
        assert p.parse_args(["--no-debug"]).debug is False

    def test_datetime(self):
        args = parser("t = 1979-05-27T07:32:00Z").parse_args([])
        assert args.t == datetime.datetime(1979, 5, 27, 7, 32, tzinfo=datetime.UTC)

    def test_datetime_override(self):
        args = parser("t = 1979-05-27T07:32:00").parse_args(["--t", "2020-01-02T03:04"])
        assert args.t == datetime.datetime(2020, 1, 2, 3, 4)  # noqa: DTZ001

    def test_date_and_time(self):
        args = parser("d = 1979-05-27\nc = 07:32:00").parse_args([])
        assert args.d == datetime.date(1979, 5, 27)
        assert args.c == datetime.time(7, 32)

    def test_date_override_is_not_confused_with_datetime(self):
        args = parser("d = 1979-05-27").parse_args(["--d", "2020-01-02"])
        assert args.d == datetime.date(2020, 1, 2)
        assert not isinstance(args.d, datetime.datetime)


class TestArrays:
    def test_default_comes_from_toml(self):
        assert parser('tags = ["a", "b"]').parse_args([]).tags == ["a", "b"]

    def test_comma_separated(self):
        assert parser('tags = ["a"]').parse_args(["--tags", "x,y"]).tags == ["x", "y"]

    def test_empty_via_equals(self):
        assert parser('tags = ["a"]').parse_args(["--tags="]).tags == []

    def test_empty_via_following_flag(self):
        p = parser('tags = ["a"]\ndebug = false')
        assert p.parse_args(["--tags", "--debug"]).tags == []

    def test_empty_at_end_of_argv(self):
        assert parser('tags = ["a"]').parse_args(["--tags"]).tags == []

    def test_repeating_replaces(self):
        args = parser('tags = ["a"]').parse_args(["--tags", "x,y", "--tags", "z"])
        assert args.tags == ["z"]

    def test_element_type_is_inferred(self):
        assert parser("ports = [1, 2]").parse_args(["--ports", "3,4"]).ports == [3, 4]

    def test_mixed_array_elements_fall_back_to_str(self):
        args = parser('x = [1, "a"]').parse_args(["--x", "3,b"])
        assert args.x == ["3", "b"]

    def test_leading_dash_needs_the_equals_form(self):
        assert parser("ports = [1]").parse_args(["--ports=-1,-2"]).ports == [-1, -2]


class TestResultsAreIndependent:
    def test_mutating_an_empty_array_does_not_reach_the_next_parse(self):
        p = parser('tags = ["a"]')
        p.parse_args(["--tags"]).tags.append("polluted")

        assert p.parse_args(["--tags"]).tags == []

    def test_mutating_a_default_does_not_reach_the_next_parse(self):
        p = parser('tags = ["a", "b"]')
        p.parse_args([]).tags.append("polluted")

        assert p.parse_args([]).tags == ["a", "b"]

    def test_mutating_a_cli_value_does_not_reach_the_next_parse(self):
        p = parser('tags = ["a"]')
        p.parse_args(["--tags", "x,y"]).tags.append("polluted")

        assert p.parse_args(["--tags", "x,y"]).tags == ["x", "y"]

    def test_the_source_dict_is_not_mutated(self):
        source = {"tags": ["a", "b"]}
        p = ArgumentParser(exit_on_error=False, toml_dict=source)
        p.parse_args([]).tags.append("polluted")

        assert source == {"tags": ["a", "b"]}

    def test_two_parses_yield_separate_arrays(self):
        p = parser('tags = ["a"]')
        assert p.parse_args([]).tags is not p.parse_args([]).tags

    def test_nested_arrays_are_independent(self):
        p = parser("[db]\nports = [1, 2]")
        p.parse_args([]).db.ports.append(3)

        assert p.parse_args([]).db.ports == [1, 2]

    def test_array_of_tables_elements_are_independent(self):
        p = parser('[[servers]]\nhost = "s1"')
        p.parse_args([]).servers[0].host = "changed"

        assert p.parse_args([]).servers[0].host == "s1"

    def test_declared_leaf_table_is_independent(self):
        p = ArgumentParser(exit_on_error=False, toml_str='[labels]\nenv = "prod"')
        p.add_argument("--labels", type=json.loads)
        p.parse_args([]).labels["env"] = "polluted"

        assert p.parse_args([]).labels == {"env": "prod"}

    def test_caller_supplied_namespaces_do_not_share_arrays(self):
        p = parser('tags = ["a", "b"]')
        p.parse_args([], namespace=Namespace()).tags.append("polluted")

        assert p.parse_args([], namespace=Namespace()).tags == ["a", "b"]

    def test_caller_supplied_namespace_does_not_alias_the_action_default(self):
        p = parser('tags = ["a"]')
        args = p.parse_args([], namespace=Namespace())
        action = next(a for a in p._actions if a.dest == "tags")

        assert args.tags is not action.default


class TestArraysOfTables:
    @pytest.fixture
    def toml(self):
        return (
            '[[servers]]\nhost = "s1"\nport = 8001\n'
            '[[servers]]\nhost = "s2"\nport = 8002'
        )

    def test_indexed_flags_are_generated(self, toml):
        help_text = parser(toml).format_help()
        assert "--servers.0.host" in help_text
        assert "--servers.1.port" in help_text

    def test_element_field_override(self, toml):
        args = parser(toml).parse_args(["--servers.1.port", "9999"])
        assert args.servers[1].port == 9999
        assert args.servers[0].port == 8001

    def test_out_of_range_index_is_rejected(self, toml):
        with pytest.raises(argparse.ArgumentError):
            parser(toml).parse_args(["--servers.5.port", "1"])

    def test_round_trips_to_the_source_shape(self, toml):
        assert dict(parser(toml).parse_args([])) == tomllib.loads(toml)


class TestEmptyTables:
    def test_gets_no_flag_of_its_own(self):
        assert "--empty" not in parser("[empty]").format_help()

    def test_round_trips(self):
        assert dict(parser("[empty]").parse_args([])) == {"empty": {}}

    def test_nested_round_trips(self):
        assert dict(parser("[db.pool]").parse_args([])) == {"db": {"pool": {}}}

    def test_entry_in_an_array_of_tables_round_trips(self):
        toml = '[[servers]]\n[[servers]]\nhost = "s2"'
        args = parser(toml).parse_args([])

        assert dict(args) == {"servers": [{}, {"host": "s2"}]}
        assert "--servers.0" not in parser(toml).format_help()

    def test_siblings_still_get_flags(self):
        p = parser('[empty]\n[db]\nhost = "x"')

        assert p.parse_args(["--db.host", "y"]).db.host == "y"
        assert dict(p.parse_args([]))["empty"] == {}


class TestSuppression:
    @pytest.fixture
    def toml(self):
        return '[labels]\nenv = "prod"\nteam = "platform"'

    @pytest.fixture
    def declared(self, toml):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--labels", type=json.loads)
        p.add_toml_str(toml)
        return p

    def test_declared_table_is_not_expanded(self, declared):
        help_text = declared.format_help()

        assert "--labels" in help_text
        assert "--labels.env" not in help_text

    def test_declared_table_keeps_the_toml_value_as_its_default(self, declared):
        assert declared.parse_args([]).labels == {"env": "prod", "team": "platform"}

    def test_declared_table_is_replaced_wholesale_from_the_cli(self, declared):
        args = declared.parse_args(["--labels", '{"env": "dev"}'])

        assert args.labels == {"env": "dev"}

    def test_undeclared_table_is_expanded(self, toml):
        assert "--labels.env" in parser(toml).format_help()


class TestHelp:
    def test_lists_toml_derived_flags(self):
        help_text = parser('[db]\nhost = "x"\nport = 5432').format_help()
        assert "--db.host" in help_text
        assert "--db.port" in help_text

    def test_applies_toml_only_once(self):
        p = parser("foo = 1")
        assert p.format_help() == p.format_help()
        assert p.parse_args([]).foo == 1


class TestErrors:
    def test_unsupported_value_type_names_the_key(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict({"when": object()})

        with pytest.raises(ValueError, match="when"):
            p.parse_args([])

    def test_non_string_key_names_the_key(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict({"db": {1: "a"}})

        with pytest.raises(TypeError, match="key 1 is not a string: int"):
            p.parse_args([])

    def test_value_that_is_also_a_prefix_is_rejected(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--db")

        with pytest.raises(ValueError, match="both a value and a prefix"):
            p.add_argument("--db.host")

    def test_prefix_that_is_also_a_value_is_rejected(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--db.host")

        with pytest.raises(ValueError, match="both a value and a prefix"):
            p.add_argument("--db")

    def test_toml_value_clashing_with_declared_prefix_is_rejected(self):
        p = parser("db = 1")
        p.add_argument("--db.host")

        with pytest.raises(ValueError, match="both a value and a prefix"):
            p.parse_args([])

    def test_toml_key_clashing_with_a_declared_option_string_is_rejected(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--port", dest="p", type=int)
        p.add_toml_str("port = 8080")

        with pytest.raises(ValueError, match="'port' needs --port"):
            p.parse_args([])

    def test_option_string_clash_names_the_declared_dest(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--port", dest="p", type=int)
        p.add_toml_str("port = 8080")

        with pytest.raises(ValueError, match="storing to 'p'"):
            p.format_help()

    def test_unknown_flag_still_errors(self):
        with pytest.raises(argparse.ArgumentError):
            parser("foo = 1").parse_args(["--nope", "1"])


class TestParseKnownArgs:
    def test_returns_extras(self):
        args, extras = parser("foo = 1").parse_known_args(["--nope"])
        assert args.foo == 1
        assert extras == ["--nope"]

    def test_caller_supplied_namespace_is_used(self):
        ns = Namespace()
        args, _ = parser("foo = 1").parse_known_args([], namespace=ns)
        assert args is ns
        assert args.foo == 1
