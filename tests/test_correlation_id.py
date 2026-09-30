from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app

BODY = {"user_id": "student-01", "session_id": "session-01", "feature": "qa", "message": "Explain observability"}


def _post(headers: dict[str, str] | None = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/chat", json=BODY, headers=headers or {})

    return asyncio.run(send())


def test_generates_id_and_returns_headers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post()
    cid = response.headers["x-request-id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", cid)
    assert response.json()["correlation_id"] == cid
    assert int(response.headers["x-response-time-ms"]) >= 0


def test_reuses_valid_incoming_id_and_rejects_unsafe(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    assert _post({"x-request-id": "req-client01"}).headers["x-request-id"] == "req-client01"
    unsafe = _post({"x-request-id": "bad id\ninjected"}).headers["x-request-id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", unsafe)


def test_logs_are_enriched_and_ids_do_not_leak(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    first = _post().headers["x-request-id"]
    second = _post().headers["x-request-id"]
    assert first != second

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    api_events = [e for e in events if e.get("service") == "api"]
    assert {e["correlation_id"] for e in api_events} == {first, second}
    for e in api_events:
        assert {"user_id_hash", "session_id", "feature", "model", "env"} <= e.keys()
        assert e["user_id_hash"] != BODY["user_id"]
