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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portmax", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    mock = commands.add_parser("mock", help="the mock college portal")
    mock.add_argument("action", choices=["serve", "fixtures"])
    mock.add_argument("--host", default="127.0.0.1")
    mock.add_argument("--port", type=int, default=8765)
    mock.add_argument("--fixed-captcha", action="store_true", help="CAPTCHA is always PM42X")
    mock.set_defaults(run=_mock)

    args = parser.parse_args(argv)
    result: int = args.run(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
