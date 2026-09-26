"""The built frontend is served from the API's own origin -- including at "/".

Production has a single origin: the backend serves web_app/dist itself, which is
what lets the session cookie be SameSite=Strict. The site root is where that
broke. GET / is also the API's JSON banner, registered ahead of the SPA
fallback, so a browser opening the bare domain -- and the installed web app,
whose manifest start_url is "/" -- got JSON instead of the app. CI only ever
requested /index.html, which is why it went unnoticed.

CI's backend job has no built frontend, so these tests point the server at a
stand-in dist/ rather than depending on one existing.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402

BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


@pytest.fixture()
def dist(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div></body></html>', encoding="utf-8",
    )
    monkeypatch.setattr(main, "_DIST", tmp_path)
    return tmp_path


def test_a_browser_opening_the_site_root_gets_the_app(dist):
    r = TestClient(main.app).get("/", headers={"Accept": BROWSER_ACCEPT})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert 'id="root"' in r.text
    assert "accept" in r.headers.get("vary", "").lower()


def test_api_clients_still_get_the_json_banner(dist):
    r = TestClient(main.app).get("/", headers={"Accept": "application/json"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "CogniSense API"
    assert "NOT a medical diagnostic device" in body["disclaimer"]
    assert "accept" in r.headers.get("vary", "").lower(), (
        "without Vary a cache could hand browsers the JSON, or scripts the page"
    )


def test_without_a_built_frontend_the_root_is_json_for_everyone(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_DIST", tmp_path / "not-built")
    r = TestClient(main.app).get("/", headers={"Accept": BROWSER_ACCEPT})
    assert r.json()["name"] == "CogniSense API"
