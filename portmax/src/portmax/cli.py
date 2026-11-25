"""The `portmax` command."""

from __future__ import annotations

import argparse
import sys


def _mock(args: argparse.Namespace) -> int:
    if args.action == "serve":
        import uvicorn

        from portmax.mock_portal.app import PortalConfig, create_app

        config = PortalConfig(captcha="fixed" if args.fixed_captcha else "random")
        uvicorn.run(create_app(config=config), host=args.host, port=args.port)
        return 0
    from portmax.mock_portal.scripted import record_mock_fixtures

    connector = record_mock_fixtures()
    print(f"recorded fixtures and golden files in {connector.root}")
    return 0


def _mcp(args: argparse.Namespace) -> int:
    from portmax.adapters.mcp_server import main as serve

    serve()
    return 0


def _api(args: argparse.Namespace) -> int:
    import os

    import uvicorn

    from portmax.api import DevTokens, create_api
    from portmax.store import Store

    store = Store(os.environ.get("PORTMAX_DATABASE_URL", "sqlite:///portmax.db"))
    uvicorn.run(create_api(store, DevTokens()), host=args.host, port=args.port)
    return 0


def _gateway_schema(args: argparse.Namespace) -> int:
    import json

    from portmax.adapters.gateway import tool_schemas

    print(json.dumps(tool_schemas(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portmax", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    mock = commands.add_parser("mock", help="the mock college portal")
    mock.add_argument("action", choices=["serve", "fixtures"])
    mock.add_argument("--host", default="127.0.0.1")
    mock.add_argument("--port", type=int, default=8765)
    mock.add_argument("--fixed-captcha", action="store_true", help="CAPTCHA is always PM42X")
    mock.set_defaults(run=_mock)

    commands.add_parser("mcp", help="serve the five tools over MCP (stdio)").set_defaults(run=_mcp)

    api = commands.add_parser("api", help="serve the API the Android app talks to")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.set_defaults(run=_api)

    commands.add_parser(
        "gateway-schema", help="print the tool definitions for the AgentCore Gateway Lambda target"
    ).set_defaults(run=_gateway_schema)

    args = parser.parse_args(argv)
    result: int = args.run(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
