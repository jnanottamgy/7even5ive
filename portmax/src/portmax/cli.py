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
    if args.action == "seed":
        import os

        from portmax.mock_portal.scripted import seed_demo

        url = os.environ.get("PORTMAX_DATABASE_URL", "sqlite:///portmax.db")
        saved = seed_demo(url, args.student)
        print(f"{args.student} connected to the mock portal; saved {saved} in {url}")
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


def _forge(args: argparse.Namespace) -> int:
    import json
    from datetime import date
    from pathlib import Path

    from portmax.forge import workflow

    action = args.action
    if action == "capture":
        from portmax.forge.capture import capture

        done = capture(args.url, Path(args.out))
        print(f"recorded {done.har}; fill in {done.notes}, then run `portmax forge sanitize`")
        return 0
    if action == "sanitize":
        from portmax.forge.sanitize import Identity, sanitize

        raw = Path(args.target)
        identity = Identity(
            usn=args.usn,
            name=args.name,
            dob=date.fromisoformat(args.dob) if args.dob else None,
            phone=args.phone,
            email=args.email,
        )
        clean, report = sanitize(json.loads(raw.read_text()), identity, args.portal_host)
        out = raw.with_name("sanitized.har")
        out.write_text(json.dumps(clean, indent=1))
        raw.with_name("sanitize-report.json").write_text(json.dumps(report.as_json(), indent=2))
        if args.delete_raw:
            raw.unlink()
        print(json.dumps({k: v for k, v in report.as_json().items() if k != "secret_hashes"}))
        print(f"wrote {out}")
        return 0
    draft = Path(args.target)
    if action == "engineer":
        from portmax.forge.engineer import EngineerJob, run_engineer

        job = EngineerJob(
            college=draft.name,
            draft_dir=draft,
            har_path=Path(args.har),
            report_path=Path(args.report),
            notes_path=Path(args.notes) if args.notes else None,
            model=args.model,
        )
        result = run_engineer(job)
        print(json.dumps(result or {}, default=str)[:2000])
        return 0 if result else 1
    if action == "fixtures":
        print(f"saved {workflow.fixtures_from_capture(draft, Path(args.har))} pages as fixtures")
        return 0
    if action == "answers":
        print(json.dumps(workflow.current_answers(draft), indent=2))
        return 0
    if action == "accept":
        print(f"golden files saved for {workflow.accept_golden(draft)}")
        return 0
    hashes = workflow.load_report_hashes(Path(args.report) if args.report else None)
    if action in ("check", "verify"):
        from portmax.forge.verify import verify

        outcome = verify(draft, secret_hashes=hashes, require_golden=action == "verify")
        for check in outcome.checks:
            print(f"{'pass' if check.ok else 'FAIL'}  {check.name}  {check.detail}")
        return 0 if outcome.ok else 1
    if action == "publish":
        made_by = {"hand_written": False, "rae_version": args.rae_version, "model": args.model}
        print(f"published to {workflow.publish(draft, secret_hashes=hashes, made_by=made_by)}")
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="portmax", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    mock = commands.add_parser("mock", help="the mock college portal")
    mock.add_argument("action", choices=["serve", "fixtures", "seed"])
    mock.add_argument("--student", default="demo", help="seed: the student id to save under")
    mock.add_argument("--host", default="127.0.0.1")
    mock.add_argument("--port", type=int, default=8765)
    mock.add_argument("--fixed-captcha", action="store_true", help="CAPTCHA is always PM42X")
    mock.set_defaults(run=_mock)

    commands.add_parser("mcp", help="serve the five tools over MCP (stdio)").set_defaults(run=_mcp)

    api = commands.add_parser("api", help="serve the API the Android app talks to")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.set_defaults(run=_api)

    forge = commands.add_parser("forge", help="build a college's connector from a recorded visit")
    forge.add_argument(
        "action",
        choices=[
            "capture", "sanitize", "engineer", "fixtures", "check", "answers", "accept",
            "verify", "publish",
        ],
    )  # fmt: skip
    forge.add_argument(
        "target", help="capture: output folder; sanitize: raw HAR; else: draft folder"
    )
    forge.add_argument("--url", help="capture: the portal's login page")
    forge.add_argument("--out", default="captures/portal", help="capture: where to save")
    forge.add_argument("--har", help="the sanitised recording")
    forge.add_argument("--report", help="sanitize-report.json, for the leak check")
    forge.add_argument("--notes", help="what-i-saw.md")
    forge.add_argument("--model", help="engineer: the model to use")
    forge.add_argument("--rae-version", default="0.16.0")
    forge.add_argument("--portal-host", help="sanitize: the portal's host, if not the first page")
    forge.add_argument("--usn")
    forge.add_argument("--name")
    forge.add_argument("--dob", help="YYYY-MM-DD")
    forge.add_argument("--phone")
    forge.add_argument("--email")
    forge.add_argument("--delete-raw", action="store_true")
    forge.set_defaults(run=_forge)

    commands.add_parser(
        "gateway-schema", help="print the tool definitions for the AgentCore Gateway Lambda target"
    ).set_defaults(run=_gateway_schema)

    args = parser.parse_args(argv)
    result: int = args.run(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
