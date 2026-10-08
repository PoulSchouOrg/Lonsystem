"""Håndhævelse af dagsplan_view/dagsplan_edit over rigtige HTTP-kald (2026-10-08).

De øvrige Dagsplan-tests kalder route-funktionerne direkte og springer dermed
FastAPIs Depends(require_permission(...)) over - her går kaldene gennem en
lille testapp med samme routere og SessionMiddleware som main.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import asyncio
import json

import pytest
from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from database.models import AppUser, Base, Role, Vehicle
from database.session import get_db
from routers import dagsplan_router


class _AsgiClient:
    """Minimal HTTP-klient direkte mod ASGI-app'en (fastapi.testclient kræver
    httpx, som ikke er en del af requirements.txt). Husker session-cookien."""

    def __init__(self, app):
        self.app = app
        self.cookie = None

    def request(self, method, url, body=None):
        path, _, query = url.partition("?")
        payload = json.dumps(body).encode() if body is not None else b""
        headers = [(b"content-type", b"application/json")]
        if self.cookie:
            headers.append((b"cookie", self.cookie.encode()))
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method.upper(), "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": query.encode(), "headers": headers,
            "client": ("test", 1), "server": ("test", 80), "root_path": "",
        }
        sent = {"done": False}
        status = {}

        async def receive():
            if not sent["done"]:
                sent["done"] = True
                return {"type": "http.request", "body": payload, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                for k, v in message.get("headers", []):
                    if k.lower() == b"set-cookie":
                        self.cookie = v.decode().split(";", 1)[0]

        asyncio.run(self.app(scope, receive, send))
        return status["code"]

    def get(self, url):
        return self.request("get", url)

    def post(self, url, json=None):
        return self.request("post", url, json)

    def patch(self, url, json=None):
        return self.request("patch", url, json)

    def delete(self, url):
        return self.request("delete", url)


@pytest.fixture
def client():
    # StaticPool: én delt forbindelse, så :memory:-databasen er den samme
    # uanset hvilken tråd FastAPI kører synkrone endpoints i.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        Role(name="ingen", display_name="Ingen", permissions=[]),
        Role(name="se", display_name="Se", permissions=["dagsplan_view"]),
        Role(name="ret", display_name="Ret", permissions=["dagsplan_view", "dagsplan_edit"]),
        AppUser(id=1, name="Ingen", initials="ING", role="ingen", password_hash="x"),
        AppUser(id=2, name="Se", initials="SE", role="se", password_hash="x"),
        AppUser(id=3, name="Ret", initials="RET", role="ret", password_hash="x"),
        Vehicle(id=1, registration_number="BN47449", vehicle_number="52", vognpark=True),
    ])
    session.commit()

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.include_router(dagsplan_router.router)
    app.include_router(dagsplan_router.vehicle_absence_router)

    @app.post("/_test_login/{user_id}")
    def _login(user_id: int, request: Request):
        request.session["user_id"] = user_id

    app.dependency_overrides[get_db] = lambda: session
    yield _AsgiClient(app)
    session.close()


def _as(client, user_id):
    client.post(f"/_test_login/{user_id}")
    return client


CALLS = {
    "view": [
        ("get", "/api/dagsplan?date=2026-09-09", None),
        ("get", "/api/vehicle-absences?date=2026-09-09", None),
    ],
    "edit": [
        ("patch", "/api/dagsplan/assignment", {"date": "2026-09-09", "vehicle_id": 1, "task": "Grus"}),
        ("patch", "/api/dagsplan/extra-assignment", {"date": "2026-09-09", "slot": 1, "task": "Grus"}),
        ("post", "/api/vehicle-absences", {"vehicle_id": 1, "date_from": "2026-09-09", "comment": "Syn"}),
        ("delete", "/api/vehicle-absences/999", None),
    ],
}


def _call(client, method, url, body):
    return client.request(method, url, body)


@pytest.mark.parametrize("method,url,body", CALLS["view"] + CALLS["edit"])
def test_not_logged_in_gets_401(client, method, url, body):
    assert _call(client, method, url, body) == 401


@pytest.mark.parametrize("method,url,body", CALLS["view"] + CALLS["edit"])
def test_without_permissions_gets_403(client, method, url, body):
    assert _call(_as(client, 1), method, url, body) == 403


@pytest.mark.parametrize("method,url,body", CALLS["view"])
def test_view_permission_can_read(client, method, url, body):
    assert _call(_as(client, 2), method, url, body) == 200


@pytest.mark.parametrize("method,url,body", CALLS["edit"])
def test_view_permission_cannot_edit(client, method, url, body):
    assert _call(_as(client, 2), method, url, body) == 403


@pytest.mark.parametrize("method,url,body", CALLS["edit"])
def test_edit_permission_can_edit(client, method, url, body):
    # 404 for sletning af et ikke-eksisterende fravær betyder at rettighedstjekket blev passeret
    assert _call(_as(client, 3), method, url, body) in (200, 201, 404)
