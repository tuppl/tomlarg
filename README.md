# TomlArg

A unified TOML + CLI parser for configurable Python projects. Every TOML key-value pair becomes a command-line flag with a default value.

## Features

- Drop-in replacement for `argparse.ArgumentParser`.
- Flag precedence is command line, then TOML, then `add_argument` defaults.
- Multiple TOML sources can be specified from file, string, or already-parsed dict.
- TOML sources merge in the order added, where a later source overrides only the keys it names.
- Tables are flattened into dotted flags (`--db.pool.size`) at any depth.
- Arrays of tables are index-addressable (`--servers.1.port`, `--servers.2.port`).
- Values are typed as hinted from the TOML: strings, integers, floats, booleans, datetimes, dates, times and arrays.
- Boolean keys generate affirmative and negated flags: `--debug` and `--no-debug`.
- Arrays take a comma-separated value (`--tags a,b,c`), with `--tags=` or a bare `--tags` giving an empty one.
- `--help` lists TOML-derived flags alongside declared ones.
- No dependencies beyond Python 3.12+.

## Install

```bash
pip install tomlarg
```

## Example Code

```python
# import argparse
import tomlarg

# TOML can be given via constructor.
parser = tomlarg.ArgumentParser(toml_file="config.toml")
parser.add_argument("--port", type=int)

# Or TOML can be given via add_toml* methods.
parser.add_toml("profile.toml")
parser.add_toml_str("""
[user]
name = "User"
""")

args = parser.parse_args()
args.db.host  # from [db] host
args.servers[1].port  # from the second [[servers]]

data = dict(args)  # to plain dict
```

## Example Usage

Simple example:
```bash
python3 examples/basic --db.host db.internal --servers.1.port 9999
```

Example showing multiple TOML sources:
```bash
python3 examples/layered
```

See [examples](examples/).

## Todo

- TOML comment parser to attach argument parameters e.g. choices, required, deprecated.
- Subparsers.
