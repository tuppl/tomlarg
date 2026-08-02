import json
from pathlib import Path

import tomlarg

HERE = Path(__file__).parent


def main() -> None:
    parser = tomlarg.ArgumentParser(
        prog="layered",
        description="Later sources override earlier ones key by key.",
    )
    parser.add_toml(HERE / "base.toml")
    parser.add_toml(HERE / "prod.toml")

    args = parser.parse_args()

    print(f"name            = {args.name!r}")
    print(f"db.host         = {args.db.host!r}")
    print(f"db.port         = {args.db.port!r}")
    print(f"db.pool.size    = {args.db.pool.size!r}")
    print(f"db.pool.timeout = {args.db.pool.timeout!r}")
    print()
    print(json.dumps(dict(args), indent=2))


if __name__ == "__main__":
    main()
