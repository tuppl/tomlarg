# Examples

```bash
python examples/basic
python examples/layered
```

## basic

Every TOML key becomes a flag. Tables are addressed with dots, arrays of tables
by index. Declaring a flag yourself keeps its type and help text, and the TOML
value becomes its default.

```python
parser = tomlarg.ArgumentParser(toml_file=CONFIG)
parser.add_argument("--port", type=int, help="port to listen on")
parser.add_argument("--labels", type=json.loads, help="labels as a JSON object")
```

Values are reached by attribute, with arrays of tables as real lists:

```python
args.db.pool.size  # 5
args.servers[1].port  # 8002
```

| Command | Result |
| --- | --- |
| `basic` | `port = 8080` — from TOML |
| `basic --port 9999` | `port = 9999` — command line overrides TOML value |
| `basic --db.pool.size 50` | `db.pool.size = 50` |
| `basic --servers.1.port 9999` | `servers[1].port = 9999` |
| `basic --tags x,y` | `tags = ['x', 'y']` |
| `basic --tags=` | `tags = []` |
| `basic --debug` | `debug = True` |
| `basic --no-debug` | `debug = False` |
| `basic --updated 2020-01-02T03:04:05Z` | parsed as a `datetime` |
| `basic --labels '{"env":"dev"}'` | `labels = {'env': 'dev'}` |

Types come from the TOML value, so `--port` takes an integer, `--updated` takes
an ISO timestamp, and booleans get both spellings. `--tags=` and a bare `--tags`
both give an empty list.

`--help` lists every flag, including the ones TOML supplied:

```
options:
  -h, --help            show this help message and exit
  --port PORT           port to listen on
  --labels LABELS       labels as a JSON object
  --name NAME
  --debug, --no-debug
  --tags [TAGS]
  --updated UPDATED
  --db.host DB.HOST
  --db.port DB.PORT
  --db.pool.size DB.POOL.SIZE
  --servers.0.host SERVERS.0.HOST
  --servers.0.port SERVERS.0.PORT
  --servers.1.host SERVERS.1.HOST
  --servers.1.port SERVERS.1.PORT
```

Only `--port` and `--labels` carry help text, because only those were declared.
`--labels` was declared as one JSON flag, so `[labels]` is not expanded — there
is no `--labels.env`. Every other table is expanded.

## layered

Sources are applied in the order added, and merging is per key.

```python
parser.add_toml(HERE / "base.toml")
parser.add_toml(HERE / "prod.toml")
```

```toml
# base.toml                  # prod.toml
[db]                         [db]
host = "localhost"           host = "db.internal"
port = 5432
                             [db.pool]
[db.pool]                    size = 20
size = 5
timeout = 30
```

```
db.host         = 'db.internal'   <- prod.toml
db.port         = 5432            <- base.toml, untouched by prod
db.pool.size    = 20              <- prod.toml
db.pool.timeout = 30              <- base.toml, untouched by prod
```

Arrays are replaced whole rather than merged.

`dict(args)` converts back to plain data, with tables as dicts and arrays of
tables as lists:

```json
{
  "name": "myapp",
  "db": {
    "host": "db.internal",
    "port": 5432,
    "pool": {
      "size": 20,
      "timeout": 30
    }
  }
}
```

## Notes

Index addressing overrides a field of an existing element; it cannot change the
length of an array. Use a declared JSON flag to write a new array.

Values starting with `-` need the `=` form, since argparse reads a leading dash
as another flag: `--tags=-1,-2`.
