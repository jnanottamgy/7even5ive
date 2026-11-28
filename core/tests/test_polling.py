"""The cards the phone polls every few seconds: tagged, so an unchanged poll is a bodiless 304,
and gzipped when the phone accepts it, through Lambda too."""
import base64
import gzip
import json

from fastapi.testclient import TestClient

from datetime import timedelta

from conftest import file_item
from seventy5 import clock, demo
from seventy5.api import create


def _client(a):
    return TestClient(create(a)), {"Authorization": f"Bearer {demo.TOKEN}"}


def test_an_unchanged_poll_is_a_bodiless_304_and_a_change_gets_a_new_tag(make_app):
    a, sid = make_app()
    client, h = _client(a)
    first = client.get("/api/cards", headers=h)
    assert first.status_code == 200
    tag = first.headers["etag"]
    assert tag.startswith('"') and tag.endswith('"')
    assert "student" in first.json() and "due_this_week" in first.json()

    again = client.get("/api/cards", headers=h | {"If-None-Match": tag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == tag

    # Something changes for this student (a new deadline is filed): the next poll is a full
    # answer with a new tag.
    soon = (clock.now().astimezone(clock.IST) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    file_item(a, sid, text="OS lab record due soon", title="OS lab record", due=soon)
    changed = client.get("/api/cards", headers=h | {"If-None-Match": tag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != tag


def test_the_cards_go_gzipped_when_accepted_and_plain_when_not(make_app):
    a, _ = make_app()
    client, h = _client(a)
    zipped = client.get("/api/cards", headers=h | {"Accept-Encoding": "gzip"})
    assert zipped.headers.get("content-encoding") == "gzip"
    plain = client.get("/api/cards", headers=h | {"Accept-Encoding": "identity"})
    assert plain.headers.get("content-encoding") is None
    # The same JSON either way (the test client unzips by itself), and the same tag.
    assert zipped.json() == plain.json()
    assert zipped.headers["etag"] == plain.headers["etag"]


def test_through_lambda_a_gzipped_answer_is_base64_and_a_304_has_no_body(make_app):
    from mangum import Mangum

    a, _ = make_app()
    handler = Mangum(create(a), lifespan="off")

    def event(headers):
        return {
            "version": "2.0", "routeKey": "$default", "rawPath": "/api/cards", "rawQueryString": "",
            "headers": {"authorization": f"Bearer {demo.TOKEN}"} | headers,
            "requestContext": {"http": {"method": "GET", "path": "/api/cards", "protocol": "HTTP/1.1",
                                        "sourceIp": "203.0.113.7", "userAgent": "okhttp"},
                               "requestId": "r", "routeKey": "$default", "stage": "$default"},
            "isBase64Encoded": False,
        }

    out = handler(event({"accept-encoding": "gzip"}), None)
    assert out["statusCode"] == 200
    assert out["isBase64Encoded"] is True
    cards = json.loads(gzip.decompress(base64.b64decode(out["body"])))
    assert "due_this_week" in cards
    tag = out["headers"]["etag"]

    unchanged = handler(event({"accept-encoding": "gzip", "if-none-match": tag}), None)
    assert unchanged["statusCode"] == 304
    assert not unchanged["body"]
