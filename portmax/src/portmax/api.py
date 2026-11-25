"""The HTTP API the Android app talks to.

    GET  /v1/connectors/{college}  the fetch plan and keep-alive settings for the phone
    GET  /v1/runner.js             the script the app's WebView injects to run the plan
    POST /v1/pages                 pages the phone fetched; we parse, save answers, drop pages

A keep-alive ping is an ordinary upload of its one page, so one endpoint covers both.
"""

# No `from __future__ import annotations` here: FastAPI must read the dependency annotations,
# which name functions defined inside create_api, at definition time.

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from portmax.connector import Connector, load_connector
from portmax.contract import utc_now
from portmax.errors import NotSupported, SessionExpired, UnsafePlan
from portmax.ingest import ingest
from portmax.manifest import keepalive_interval_minutes, needs_push_wakeup
from portmax.pages import Page
from portmax.store import Store

RUNNER_JS = Path(__file__).parent / "runner" / "portmax-runner.js"


class Authenticator(Protocol):
    def student_for(self, token: str) -> str | None: ...


class DevTokens:
    """Development sign-in: fixed tokens from PORTMAX_DEV_TOKENS ("token:student,...").

    Hack day replaces this with the app's real sign-in (a verified Supabase JWT).
    """

    def __init__(self, spec: str | None = None) -> None:
        raw = spec if spec is not None else os.environ.get("PORTMAX_DEV_TOKENS", "")
        pairs = (item.split(":", 1) for item in raw.split(",") if ":" in item)
        self.tokens = {token.strip(): student.strip() for token, student in pairs}

    def student_for(self, token: str) -> str | None:
        return self.tokens.get(token)


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    college: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    pages: list[Page] = Field(min_length=1, max_length=60)


def create_api(
    store: Store,
    auth: Authenticator,
    connectors: Callable[[str], Connector] = load_connector,
) -> FastAPI:
    app = FastAPI(title="PortMax", docs_url=None, redoc_url=None)

    def student(authorization: Annotated[str | None, Header()] = None) -> str:
        token = (authorization or "").removeprefix("Bearer ").strip()
        found = auth.student_for(token) if token else None
        if found is None:
            raise HTTPException(401, "sign in to the app first")
        return found

    def connector_for(college: str) -> Connector:
        try:
            return connectors(college)
        except (FileNotFoundError, ModuleNotFoundError) as error:
            raise HTTPException(404, f"no connector for {college}") from error

    @app.get("/v1/connectors/{college}")
    def connector_settings(college: str, _: Annotated[str, Depends(student)]) -> dict[str, Any]:
        connector = connector_for(college)
        manifest = connector.manifest
        return {
            "college": manifest.college,
            "name": manifest.name,
            "connector_version": manifest.connector_version,
            "login_path": manifest.login_path,
            "markers": manifest.markers.model_dump(),
            "keepalive_minutes": keepalive_interval_minutes(manifest.session),
            "push_wakeup": needs_push_wakeup(manifest.session),
            "refresh_minutes": manifest.refresh_minutes,
            "plan": connector.plan.model_dump(by_alias=True),
        }

    @app.get("/v1/runner.js")
    def runner() -> Response:
        return Response(RUNNER_JS.read_text(), media_type="application/javascript")

    @app.post("/v1/pages")
    def pages(upload: Upload, student_id: Annotated[str, Depends(student)]) -> JSONResponse:
        connector = connector_for(upload.college)
        try:
            result = ingest(store, connector, student_id, upload.pages, utc_now())
        except SessionExpired as error:
            return JSONResponse({"code": error.code, "detail": error.detail}, status_code=409)
        except (UnsafePlan, NotSupported) as error:
            return JSONResponse({"code": error.code, "detail": error.detail}, status_code=400)
        return JSONResponse(
            {
                "fetched_at": result.fetched_at.isoformat(),
                "saved": result.saved,
                "failed": result.failed,
            }
        )

    return app
