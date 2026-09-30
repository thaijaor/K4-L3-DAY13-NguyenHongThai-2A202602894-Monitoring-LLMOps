from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import dashboard, logging_config

NOW = datetime(2026, 9, 30, 4, 0, tzinfo=timezone.utc)


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _sent(minutes_ago: int, latency: int, success: bool = True) -> dict:
    return {
        "ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "event": "response_sent",
        "latency_ms": latency,
        "ttft_ms": 50,
        "tokens_in": 30,
        "tokens_out": 100,
        "cost_usd": 0.002,
        "quality_score": 0.8,
        "tool_success": success,
    }


def _received(minutes_ago: int) -> dict:
    return {"ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "event": "request_received"}


def test_compute_matches_dashboard_contract(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    _write(
        log_path,
        [
            _received(90), _sent(90, 9999),  # ngoài cửa sổ 60 phút
            _received(5), _sent(5, 400),
            _received(5), _sent(5, 3500),
            _received(4),
            {"ts": (NOW - timedelta(minutes=4)).isoformat(), "event": "request_failed",
             "error_type": "RuntimeError", "tool_success": False},
        ],
    )

    d = dashboard.compute(now=NOW)

    assert d["traffic_total"] == 3
    assert d["latency_now"]["p95"] == 3500
    assert d["slow_count"] == 1  # chỉ request 3500 ms vượt ngưỡng 2000 ms của challenge
    assert round(d["error_rate_total"], 2) == 33.33
    assert d["error_breakdown"] == {"RuntimeError": 1}
    assert round(d["retrieval_success"], 2) == 66.67
    assert d["tokens_in"] == 60 and d["tokens_out"] == 200
    assert "Quality proxy" in dashboard.render_html()
