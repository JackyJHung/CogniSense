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


# --------------------------------------------------------------------------
# The built app's own API calls, which all go to /api/...
#
# In development Vite strips the prefix; in production nothing did, so every
# call fell through to the SPA fallback -- a GET came back as index.html with
# a 200, a POST as a 405 -- and the deployed web app could not log in. These
# drive the API exactly as the built app does.
# --------------------------------------------------------------------------

@pytest.fixture()
def web(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base, get_db
    from app.models import (  # noqa: F401
        checkin, image_association, push, reminder, security, session, user,
    )

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


SIGNUP = {
    "username": "web_user", "password": "a-long-passphrase", "age": 70,
    "gender": "female", "race": "white", "wake_time": "07:00:00", "sleep_time": "22:00:00",
}


def test_the_built_app_reaches_the_api_under_api(web):
    assert web.get("/api/health").json() == {"status": "ok"}

    r = web.post("/api/users/signup", json=SIGNUP)
    assert r.status_code == 201, r.text
    # The session arrives as the cookie, as it does for the browser.
    me = web.get("/api/users/me")
    assert me.status_code == 200
    assert me.headers["content-type"].startswith("application/json")
    assert me.json()["username"] == "web_user"


def test_csrf_still_guards_api_calls(web):
    web.post("/api/users/signup", json=SIGNUP)
    # A cookie-authenticated POST without the double-submit token is refused
    # under /api exactly as at the root...
    assert web.post("/api/users/logout", json={"all_devices": False}).status_code == 403
    # ...and allowed with it.
    token = web.cookies.get("cognisense_csrf")
    r = web.post("/api/users/logout", json={"all_devices": False},
                 headers={"X-CSRF-Token": token})
    assert r.status_code == 200, r.text


def test_an_unknown_api_path_is_a_404_not_the_page(web, dist):
    r = web.get("/api/no-such-endpoint", headers={"Accept": BROWSER_ACCEPT})
    assert r.status_code == 404
    assert 'id="root"' not in r.text
    banner = web.get("/api", headers={"Accept": BROWSER_ACCEPT})
    assert banner.json()["name"] == "CogniSense API"
