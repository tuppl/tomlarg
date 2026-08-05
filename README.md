# TomlArg

A unified TOML + CLI parser for configurable Python projects. Every TOML key-value pair becomes a command-line flag with a default value.

`tomlarg` exposes an `ArgumentParser` which subclasses `argparse.ArgumentParser` to allow drop-in replacement - extending support for reading TOML files and keeping argument parsing functionality.

## Features

- Multiple TOML sources from file, string, or already-parsed dict.
- Tables flattened into dotted flags (`--db.pool.size`) at any depth.
- Arrays of tables index-addressable (`--servers.1.port`).
- Values typed from the TOML: strings, integers, floats, booleans, datetimes, dates, times and arrays.
- No dependencies.
- For Python >=3.12.

## Install

```bash
pip install tomlarg
```

## Quickstart

```toml
# config.toml
name = "myapp"
port = 8080
debug = false
tags = ["web", "api"]

[db]
host = "localhost"

[db.pool]
size = 5

[[servers]]
host = "s1"
port = 8001

[[servers]]
host = "s2"
port = 8002
```

```python
# main.py
import tomlarg

parser = tomlarg.ArgumentParser(toml_file="config.toml")

args = parser.parse_args()

args.name  # 'myapp'
args.db.pool.size  # 5
args.servers[1].port  # 8002
dict(args)  # the whole tree as plain data
```

```bash
$ python3 main.py --db.pool.size 50 --tags x,y --no-debug
```

## Usage

| TOML | Flag | Read back as |
| --- | --- | --- |
| `port = 8080` | `--port` | `args.port` |
| `[db]` `host = "x"` | `--db.host` | `args.db.host` |
| `[db.pool]` `size = 5` | `--db.pool.size` | `args.db.pool.size` |
| `[[servers]]` `port = 1` | `--servers.0.port` | `args.servers[0].port` |
| `debug = false` | `--debug` / `--no-debug` | `args.debug` |
| `tags = ["a"]` | `--tags a,b,c` | `args.tags` |

Types come from the TOML value, so `--port` takes an integer, `--updated` takes a datetime, and `--tags` takes a comma-separated list whose element type is inferred. `--tags=` or a bare `--tags` gives an empty list.

## API

### `ArgumentParser(*args, toml_file=None, toml_str=None, toml_dict=None, delimiter=".", **kwargs)`

Takes everything `argparse.ArgumentParser` takes. The three TOML arguments are shorthand for the `add_toml*` methods below, applied in the order listed.

```python
parser = tomlarg.ArgumentParser(prog="myapp", toml_file="config.toml")
```

`delimiter` sets the separator used for generated flags and for reading values back. Results stay nested whichever separator is chosen.

```python
parser = tomlarg.ArgumentParser(delimiter="__", toml_file="config.toml")
parser.parse_args(["--db__pool__size", "50"]).db.pool.size  # 50
```

### `add_toml(path)`

Record a TOML file, given as a `Path` or `str`. A missing file raises `FileNotFoundError` here, not at parse time.

```python
parser.add_toml("profile.toml")
```

### `add_toml_str(text)`

Record a TOML document. Malformed TOML raises `tomllib.TOMLDecodeError` here, not at parse time.

```python
parser.add_toml_str("[user]\nname = 'x'")
```

### `add_toml_dict(data)`

Record already-parsed TOML. `data` is any `Mapping`, which is how a table from an enclosing document is passed.

```python
parser.add_toml_dict(pyproject["tool"]["myapp"])
```

Sources merge in the order added, key by key, so a later source overrides only the leaves it names:

```toml
# base.toml                # prod.toml
[db]                       [db]
host = "localhost"         host = "db.internal"
port = 5432
[db.pool]                  [db.pool]
size = 5                   size = 20
timeout = 30
```

```
db.host         = 'db.internal'   # from prod
db.port         = 5432            # kept from base
db.pool.size    = 20              # from prod
db.pool.timeout = 30              # kept from base
```

### `add_argument(*args, **kwargs)`

Inherited from argparse, with the same signature. A flag you declare keeps its `type=`, `help=` and everything else, and the TOML value becomes its default. Sources are applied at parse time, so this may be called before or after them.

Declaring a flag for a *table* stops that table being expanded, which is the escape hatch for passing one whole:

```python
parser.add_argument(
    "--labels", type=json.loads, help="Labels"
)  # --labels '{"env":"dev"}'
```

### `parse_args(args=None, namespace=None)`

Applies the sources, then parses. **Precedence, highest first: command line, TOML, `add_argument` defaults.**

Returns a `tomlarg.Namespace`, a subclass of `argparse.Namespace` addressable by delimited path. `args.db.pool.size` and `getattr(args, "db.pool.size")` resolve the same value, and `dict(args)` converts the whole tree back to plain data with arrays of tables as real lists.

### `parse_known_args(args=None, namespace=None)`

As argparse, returning the namespace and the unrecognised arguments.

```python
parser.parse_known_args(["--nope"])  # (Namespace(port=8080), ['--nope'])
```

### `format_help()` and `format_usage()`

Apply the sources too, so TOML-derived flags are listed without parsing first.

## Examples

Example of overriding `--db.host` and `--servers.1.port` flags:
```bash
$ python3 examples/basic --db.host db.internal --servers.1.port 9999
```

Example showing multiple TOML sources can be added:
```bash
$ python3 examples/layered
```

Example of printing help and usage message:
```bash
$ python3 examples/basic --help
usage: basic [-h] [--port PORT] [--labels LABELS] [--name NAME] [--debug | --no-debug]
             [--tags [TAGS]] [--updated UPDATED] [--db.host DB.HOST]
             [--db.port DB.PORT] [--db.pool.size DB.POOL.SIZE]
             [--servers.0.host SERVERS.0.HOST] [--servers.0.port SERVERS.0.PORT]
             [--servers.1.host SERVERS.1.HOST] [--servers.1.port SERVERS.1.PORT]

options:
  -h, --help            show this help message and exit
  --port PORT           port to listen on
  --labels LABELS       labels as a JSON object
  --name NAME
  --debug, --no-debug
  --tags [TAGS]
  --updated UPDATED
  --db.host DB.HOST
  ...
```

> See [examples](examples/).

## Errors

| Situation | Error |
| --- | --- |
| Two sources give a key different types | `cannot replace integer 'port' with string` |
| A key needs a flag another argument owns | `TOML key 'port' needs --port, which is already taken by an argument storing to 'p'` |
| One dest nests inside another | `'db' is both a value and a prefix of 'db.host'` |
| A key is named after a built-in flag | `TOML key 'help' is the dest of --help, which stores nothing` |
| A value has no command-line spelling | `unsupported TOML value type for 'when': unknown` |
| A key is empty, or holds the delimiter | `key '' is empty, so it has no flag` |
| A source is not a mapping | `TOML data must be a mapping, not list` |

## Todo

- TOML comment parser to attach argument parameters e.g. choices, required, deprecated.
- Abbreviating dotted keys (`allow_abbrev` defaults to false currently).
- Subparsers.
