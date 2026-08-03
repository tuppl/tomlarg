import argparse
import datetime
import json
import tomllib
from types import MappingProxyType

import pytest

from tomlarg import ArgumentParser
from tomlarg.namespace import Namespace

# Rejecting an unrecognised argument raises ArgumentError when exit_on_error is false
# Python before 3.12.5 exits instead so accept either.
REJECTED = (argparse.ArgumentError, SystemExit)


def parser(toml, **kwargs):
    return ArgumentParser(exit_on_error=False, toml_str=toml, **kwargs)


def errors_twice(p):
    messages = []
    for _ in range(2):
        with pytest.raises((TypeError, ValueError)) as raised:
            p.parse_args([])
        messages.append(str(raised.value))
    return messages


class TestSources:
    def test_constructor_is_keyword_only_so_prog_is_not_shadowed(self):
        assert ArgumentParser("myprog").prog == "myprog"

    def test_constructor_toml_dict(self):
        p = ArgumentParser(toml_dict={"foo": 1})
        assert p.parse_args([]).foo == 1

    def test_constructor_toml_file(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text("foo = 1")
        assert ArgumentParser(toml_file=path).parse_args([]).foo == 1

    def test_toml_file_accepts_a_str_path(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text("foo = 1")
        assert ArgumentParser(toml_file=str(path)).parse_args([]).foo == 1

    def test_add_toml_reads_a_file(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('[db]\nhost = "localhost"\n')

        p = ArgumentParser(exit_on_error=False)
        p.add_toml(path)

        assert getattr(p.parse_args([]), "db.host") == "localhost"

    def test_missing_file_raises_when_added(self, tmp_path):
        p = ArgumentParser(exit_on_error=False)

        with pytest.raises(FileNotFoundError):
            p.add_toml(tmp_path / "absent.toml")

    def test_malformed_toml_raises_when_added(self):
        p = ArgumentParser(exit_on_error=False)

        with pytest.raises(tomllib.TOMLDecodeError):
            p.add_toml_str("foo = ")

    def test_add_toml_dict_requires_an_argument(self):
        with pytest.raises(TypeError):
            ArgumentParser(exit_on_error=False).add_toml_dict()

    @pytest.mark.parametrize("data", [[1, 2], "hello", None, 42, {1, 2}])
    def test_add_toml_dict_rejects_a_non_mapping(self, data):
        with pytest.raises(TypeError, match="TOML data must be a mapping"):
            ArgumentParser(exit_on_error=False).add_toml_dict(data)

    def test_a_non_mapping_is_rejected_when_added_not_when_parsed(self):
        with pytest.raises(TypeError, match="must be a mapping, not list"):
            ArgumentParser(exit_on_error=False, toml_dict=[1, 2])

    def test_add_toml_dict_accepts_any_mapping(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict(MappingProxyType({"foo": 1}))

        assert p.parse_args([]).foo == 1

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

    def test_source_added_after_a_parse_takes_effect(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_str("foo = 1")

        assert p.parse_args([]).foo == 1

        p.add_toml_str('bar = "x"\nfoo = 2')

        assert dict(p.parse_args([])) == {"foo": 2, "bar": "x"}

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
    def test_cli_wins_over_toml(self):
        p = parser('foo = 10\nbar = "hello"')

        assert p.parse_args([]).foo == 10
        assert p.parse_args(["--foo", "99"]).foo == 99
        assert p.parse_args(["--foo", "99"]).bar == "hello"

    def test_toml_wins_over_a_declared_default(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--port", type=int, default=1)
        p.add_toml_str("port = 8080")

        assert p.parse_args([]).port == 8080
        assert p.parse_args(["--port", "3"]).port == 3

    def test_toml_wins_over_a_default_declared_afterwards(self):
        p = ArgumentParser(exit_on_error=False, toml_str="port = 8080")
        p.add_argument("--port", type=int, default=1)

        assert p.parse_args([]).port == 8080

    def test_declared_default_survives_a_silent_toml(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--other", type=int, default=1)
        p.add_toml_str("port = 8080")

        assert dict(p.parse_args([])) == {"other": 1, "port": 8080}

    def test_conflicting_types_across_sources_are_rejected_at_parse(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_str("port = 1")
        p.add_toml_str('port = "a"')

        with pytest.raises(
            ValueError, match="cannot replace integer 'port' with string"
        ):
            p.parse_args([])

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

    @pytest.mark.parametrize(
        "toml, argv, expected",
        [
            ("debug = false", [], False),
            ("debug = false", ["--debug"], True),
            ("debug = false", ["--no-debug"], False),
            ("debug = true", [], True),
            ("debug = true", ["--no-debug"], False),
        ],
    )
    def test_bool_uses_optional_negation(self, toml, argv, expected):
        assert parser(toml).parse_args(argv).debug is expected

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

    def test_a_negative_scalar_does_not_need_the_equals_form(self):
        p = parser("offset = 0")

        assert p.parse_args(["--offset", "-1"]).offset == -1
        assert p.parse_args(["--offset=-1"]).offset == -1

    def test_empty_array_takes_a_flag_and_falls_back_to_str(self):
        p = parser("servers = []")

        assert p.parse_args([]).servers == []
        assert p.parse_args(["--servers", "a,b"]).servers == ["a", "b"]

    @pytest.mark.parametrize(
        "toml, default",
        [
            ("matrix = [[1, 2], [3, 4]]", [[1, 2], [3, 4]]),
            ("matrix = [1, { a = 2 }]", [1, {"a": 2}]),
        ],
        ids=["nested-arrays", "table-element"],
    )
    def test_arrays_of_containers_flatten_to_str(self, toml, default):
        p = parser(toml)

        assert p.parse_args([]).matrix == default
        assert p.parse_args(["--matrix", "5,6"]).matrix == ["5", "6"]


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
        with pytest.raises(REJECTED):
            parser(toml).parse_args(["--servers.5.port", "1"])

    def test_out_of_range_index_is_not_a_known_argument(self, toml):
        _, extras = parser(toml).parse_known_args(["--servers.5.port", "1"])
        assert extras == ["--servers.5.port", "1"]

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


class TestKeys:
    def test_dotted_key_is_settable(self):
        args = parser('[db]\nhost = "localhost"').parse_args(
            ["--db.host", "example.com"]
        )

        assert getattr(args, "db.host") == "example.com"

    def test_key_that_is_not_an_identifier(self):
        p = parser("line-length = 88")

        assert getattr(p.parse_args([]), "line-length") == 88
        assert getattr(p.parse_args(["--line-length", "100"]), "line-length") == 100

    def test_nested_key_that_is_not_an_identifier(self):
        p = parser("[tool.ruff]\nline-length = 88")

        assert "--tool.ruff.line-length" in p.format_help()
        assert getattr(p.parse_args([]).tool.ruff, "line-length") == 88
        assert dict(p.parse_args(["--tool.ruff.line-length", "100"])) == {
            "tool": {"ruff": {"line-length": 100}}
        }


class TestDelimiter:
    @pytest.fixture
    def toml(self):
        return '[db]\nhost = "x"\nport = 5432\n\n[[servers]]\nname = "s1"'

    def test_flags_use_the_delimiter(self, toml):
        help_text = parser(toml, delimiter="__").format_help()

        assert "--db__host" in help_text
        assert "--servers__0__name" in help_text
        assert "--db.host" not in help_text

    def test_results_are_still_nested(self, toml):
        args = parser(toml, delimiter="__").parse_args(["--db__host", "y"])

        assert args.db.host == "y"
        assert args.db.port == 5432
        assert args.servers[0].name == "s1"

    def test_delimited_path_resolves_the_same_value(self, toml):
        args = parser(toml, delimiter="__").parse_args([])

        assert args.db__host == "x"
        assert args.servers__0__name == "s1"

    def test_round_trips_to_the_source_shape(self, toml):
        assert dict(parser(toml, delimiter="__").parse_args([])) == tomllib.loads(toml)

    def test_the_delimiter_is_not_a_parsed_value(self, toml):
        assert "_Namespace__delimiter" not in vars(
            parser(toml, delimiter="__").parse_args([])
        )

    def test_a_dotted_key_is_legal_under_another_delimiter(self):
        p = ArgumentParser(
            exit_on_error=False, toml_dict={"tool.ruff": 88}, delimiter="__"
        )

        assert getattr(p.parse_args(["--tool.ruff", "100"]), "tool.ruff") == 100

    def test_nesting_is_rejected_using_the_delimiter(self):
        p = ArgumentParser(exit_on_error=False, delimiter="__")
        p.add_argument("--db")

        with pytest.raises(ValueError, match="both a value and a prefix"):
            p.add_argument("--db__host")

    def test_empty_delimiter_is_rejected(self):
        with pytest.raises(ValueError, match="delimiter must not be empty"):
            ArgumentParser(delimiter="")


class TestPositionals:
    def test_positional_coexists_with_toml(self):
        p = parser("port = 8080")
        p.add_argument("src")

        assert dict(p.parse_args(["f.txt"])) == {"port": 8080, "src": "f.txt"}

    def test_variadic_positional_takes_its_default_from_toml(self):
        p = parser('files = ["a.txt"]')
        p.add_argument("files", nargs="*")

        assert p.parse_args([]).files == ["a.txt"]
        assert p.parse_args(["b.txt"]).files == ["b.txt"]


class TestHelp:
    def test_lists_toml_derived_flags(self):
        help_text = parser('[db]\nhost = "x"\nport = 5432').format_help()
        assert "--db.host" in help_text
        assert "--db.port" in help_text

    def test_usage_lists_toml_derived_flags(self):
        assert "--db.host" in parser('[db]\nhost = "x"').format_usage()

    def test_usage_does_not_disturb_a_later_parse(self):
        p = parser("foo = 1")
        p.format_usage()

        assert p.format_usage() == p.format_usage()
        assert p.parse_args([]).foo == 1

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
        def clashing():
            p = ArgumentParser(exit_on_error=False)
            p.add_argument("--port", dest="p", type=int)
            p.add_toml_str("port = 8080")
            return p

        expected = "'port' needs --port.*storing to 'p'"

        with pytest.raises(ValueError, match=expected):
            clashing().parse_args([])

        with pytest.raises(ValueError, match=expected):
            clashing().format_help()

    def test_an_option_string_clash_is_raised_about_again(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--port", dest="p", type=int)
        p.add_toml_str("port = 8080")

        first, second = errors_twice(p)

        assert "'port' needs --port" in first
        assert first == second

    def test_an_unsupported_value_is_raised_about_again(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict({"when": object()})

        first, second = errors_twice(p)

        assert "unsupported TOML value type for 'when'" in first
        assert first == second

    def test_a_non_string_key_is_raised_about_again(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict({"db": {1: "a"}})

        first, second = errors_twice(p)

        assert "key 1 is not a string: int" in first
        assert first == second

    def test_keys_after_a_failure_are_never_bound(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_toml_dict({"aaa": 1, "bad": object(), "zzz": 2})

        first, second = errors_twice(p)

        assert first == second
        assert "--zzz" not in p._option_string_actions

    def test_unknown_flag_still_errors(self):
        with pytest.raises(REJECTED):
            parser("foo = 1").parse_args(["--nope", "1"])


class TestDeclaredDottedDests:
    def test_dest_no_toml_source_describes(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--db.tags", default=[])

        assert dict(p.parse_args([])) == {"db": {"tags": []}}

    def test_dest_no_toml_source_describes_with_a_caller_namespace(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--db.tags", default=[])

        assert dict(p.parse_args([], namespace=Namespace())) == {"db": {"tags": []}}

    def test_dest_beside_a_table_the_toml_does_describe(self):
        p = ArgumentParser(exit_on_error=False, toml_str='[db]\nhost = "x"')
        p.add_argument("--db.tags", default=[])

        assert dict(p.parse_args([])) == {"db": {"host": "x", "tags": []}}

    def test_container_defaults_stay_independent(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--db.tags", default=[])
        p.parse_args([]).db.tags.append("polluted")

        assert p.parse_args([]).db.tags == []

    def test_index_beyond_the_array_is_named(self):
        p = ArgumentParser(exit_on_error=False, toml_str='[[servers]]\nhost = "s1"')
        p.add_argument("--servers.5.tags", default=[])

        with pytest.raises(ValueError, match="'servers.5.tags' indexes '5'"):
            p.parse_args([])

    def test_a_suppressed_dest_makes_no_table(self):
        p = ArgumentParser(exit_on_error=False)
        p.add_argument("--db.tags", default=argparse.SUPPRESS)

        assert dict(p.parse_args([])) == {}


class TestPrefixChars:
    @pytest.fixture
    def plus(self):
        def build(toml):
            return ArgumentParser(exit_on_error=False, prefix_chars="+", toml_str=toml)

        return build

    def test_flags_use_the_declared_prefix(self, plus):
        assert plus("foo = 1").parse_args(["++foo", "2"]).foo == 2

    def test_dotted_flags_use_it_too(self, plus):
        args = plus('[db]\nhost = "x"').parse_args(["++db.host", "y"])

        assert args.db.host == "y"

    def test_a_boolean_is_still_negatable(self, plus):
        p = plus("debug = true")

        assert p.parse_args([]).debug is True
        assert p.parse_args(["++no-debug"]).debug is False
        assert p.parse_args(["++debug"]).debug is True

    def test_an_array_still_takes_a_comma_separated_value(self, plus):
        assert plus('tags = ["a"]').parse_args(["++tags", "x,y"]).tags == ["x", "y"]

    def test_help_lists_both_boolean_spellings(self, plus):
        help_text = plus("debug = false").format_help()

        assert "++debug" in help_text
        assert "++no-debug" in help_text

    def test_the_first_prefix_char_is_the_one_used(self):
        p = ArgumentParser(exit_on_error=False, prefix_chars="/+", toml_str="foo = 1")

        assert p.parse_args(["//foo", "2"]).foo == 2

    def test_the_default_prefix_is_unchanged(self):
        p = parser("debug = true\nfoo = 1")

        assert p.parse_args(["--no-debug", "--foo", "2"]).debug is False
        assert "--no-debug" in p.format_help()


class TestReservedDests:
    def test_a_key_named_after_the_help_flag_is_rejected(self):
        p = parser('help = "hi"')

        with pytest.raises(ValueError, match="'help' is the dest of --help"):
            p.parse_args([])

    def test_a_table_named_after_the_help_flag_is_rejected(self):
        p = parser("[help]\ncolor = true")

        with pytest.raises(ValueError, match="'help' is the dest of --help"):
            p.parse_args([])

    def test_a_key_named_after_a_declared_version_flag_is_rejected(self):
        p = parser('version = "1.2.3"')
        p.add_argument("--version", action="version", version="1.0")

        with pytest.raises(ValueError, match="'version' is the dest of --version"):
            p.parse_args([])

    def test_version_is_ordinary_until_the_flag_is_declared(self):
        assert dict(parser('version = "1.2.3"').parse_args([])) == {"version": "1.2.3"}

    def test_add_help_frees_the_name(self):
        p = ArgumentParser(exit_on_error=False, add_help=False, toml_str='help = "hi"')

        assert dict(p.parse_args([])) == {"help": "hi"}

    def test_a_nested_key_of_that_name_is_untouched(self):
        assert dict(parser("[db]\nhelp = 1").parse_args([])) == {"db": {"help": 1}}

    def test_an_empty_key_is_rejected_rather_than_given_a_bare_flag(self):
        p = ArgumentParser(exit_on_error=False, toml_dict={"": 1, "ok": 2})

        with pytest.raises(ValueError, match="key '' is empty"):
            p.parse_args([])

    def test_a_similar_name_is_untouched(self):
        p = parser("[helper]\ncolor = true")

        assert "--helper.color" in p.format_help()
        assert dict(p.parse_args([])) == {"helper": {"color": True}}


class TestSuppressedDefaults:
    @pytest.fixture
    def suppressed(self):
        def build(toml):
            p = ArgumentParser(exit_on_error=False, toml_str=toml)
            p.add_argument("--port", type=int, default=argparse.SUPPRESS)
            return p

        return build

    def test_a_key_no_source_names_stays_suppressed(self, suppressed):
        assert dict(suppressed("other = 1").parse_args([])) == {"other": 1}

    def test_a_key_the_toml_names_is_supplied(self, suppressed):
        assert dict(suppressed("port = 8080").parse_args([])) == {"port": 8080}

    def test_a_caller_namespace_is_supplied_the_same_value(self, suppressed):
        args = suppressed("port = 8080").parse_args([], namespace=Namespace())

        assert dict(args) == {"port": 8080}

    def test_a_plain_namespace_is_supplied_the_same_value(self, suppressed):
        args = suppressed("port = 8080").parse_args([], namespace=argparse.Namespace())

        assert vars(args) == {"port": 8080}

    def test_the_cli_still_wins(self, suppressed):
        args = suppressed("port = 8080").parse_args(["--port", "9"])

        assert dict(args) == {"port": 9}


class TestAbbreviation:
    def test_a_prefix_of_a_dotted_flag_is_not_a_flag(self):
        with pytest.raises(REJECTED):
            parser('[db]\nhost = "x"').parse_args(["--db", "y"])

    def test_the_whole_flag_still_works(self):
        args = parser('[db]\nhost = "x"').parse_args(["--db.host", "y"])

        assert args.db.host == "y"

    def test_an_unrelated_key_does_not_change_the_outcome(self):
        for toml in ('[db]\nhost = "x"', '[db]\nhost = "x"\nport = 5432'):
            with pytest.raises(REJECTED):
                parser(toml).parse_args(["--db", "y"])

    def test_a_prefix_of_an_indexed_flag_is_not_a_flag(self):
        with pytest.raises(REJECTED):
            parser('[[servers]]\nhost = "s1"').parse_args(["--servers", "x"])

    def test_it_can_be_asked_for(self):
        p = parser('[db]\nhost = "x"', allow_abbrev=True)

        assert p.parse_args(["--db", "y"]).db.host == "y"


class TestCallerSuppliedNamespace:
    def test_table_is_nested(self):
        args = parser('[db]\nhost = "x"').parse_args([], namespace=Namespace())

        assert dict(args) == {"db": {"host": "x"}}
        assert args.db.host == "x"

    def test_nested_table_is_nested(self):
        args = parser("[db.pool]\nsize = 5").parse_args([], namespace=Namespace())

        assert dict(args) == {"db": {"pool": {"size": 5}}}

    def test_array_of_tables_is_nested(self):
        args = parser('[[servers]]\nhost = "s1"').parse_args([], namespace=Namespace())

        assert dict(args) == {"servers": [{"host": "s1"}]}
        assert args.servers[0].host == "s1"

    def test_value_given_on_the_cli(self):
        args = parser('[db]\nhost = "x"').parse_args(
            ["--db.host", "y"], namespace=Namespace()
        )

        assert args.db.host == "y"

    def test_parse_known_args_takes_the_same_path(self):
        args, _ = parser('[db]\nhost = "x"').parse_known_args([], namespace=Namespace())

        assert dict(args) == {"db": {"host": "x"}}

    def test_caller_attributes_are_kept(self):
        args = parser('[db]\nhost = "x"').parse_args(
            [], namespace=Namespace(extra="keep")
        )

        assert dict(args) == {"extra": "keep", "db": {"host": "x"}}

    def test_a_partly_built_namespace_is_completed(self):
        args = parser('[db.pool]\nsize = 5\n[db]\nhost = "x"').parse_args(
            [], namespace=Namespace(db=Namespace())
        )

        assert dict(args) == {"db": {"pool": {"size": 5}, "host": "x"}}

    def test_a_caller_value_wins_over_the_toml_default(self):
        args = parser('[db]\nhost = "x"').parse_args(
            [], namespace=Namespace(db=Namespace(host="mine"))
        )

        assert args.db.host == "mine"


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

    def test_a_plain_argparse_namespace_stays_flat(self):
        args = parser('[db]\nhost = "x"').parse_args([], namespace=argparse.Namespace())

        assert getattr(args, "db.host") == "x"
        assert not hasattr(args, "db")
