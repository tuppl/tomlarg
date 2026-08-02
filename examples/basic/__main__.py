import json
from pathlib import Path

import tomlarg

CONFIG = Path(__file__).with_name("config.toml")


def main() -> None:
    parser = tomlarg.ArgumentParser(
        prog="basic",
        description="Every TOML key becomes a flag, tables and arrays included.",
        toml_file=CONFIG,
    )
    parser.add_argument("--port", type=int, help="port to listen on")
    parser.add_argument("--labels", type=json.loads, help="labels as a JSON object")

    args = parser.parse_args()

    print(f"name            = {args.name!r}")
    print(f"port            = {args.port!r}")
    print(f"debug           = {args.debug!r}")
    print(f"tags            = {args.tags!r}")
    print(f"updated         = {args.updated!r}")
    print(f"db.host         = {args.db.host!r}")
    print(f"db.pool.size    = {args.db.pool.size!r}")
    print(f"servers[1].port = {args.servers[1].port!r}")
    print(f"labels          = {args.labels!r}")


if __name__ == "__main__":
    main()
