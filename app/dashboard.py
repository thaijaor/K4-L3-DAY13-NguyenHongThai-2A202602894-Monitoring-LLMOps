"""Dashboard runtime 6 panel, đọc data/logs.jsonl theo contract config/dashboard.yaml."""
from __future__ import annotations

import html
import math
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from . import logging_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "dashboard.yaml"
CHALLENGE_PATH = Path(__file__).resolve().parents[1] / "config" / "challenge.json"


def _slow_threshold_ms() -> int:
    """Ngưỡng request chậm của challenge (nếu có), để incident dưới ngưỡng SLO vẫn hiện rõ."""
    try:
        return int(json.loads(CHALLENGE_PATH.read_text(encoding="utf-8"))["latency_threshold_ms"])
    except (OSError, ValueError, KeyError):
        return 2000

W, H = 520, 200
PAD_L, PAD_R, PAD_T, PAD_B = 52, 16, 14, 28


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def _load_events(window_start: datetime) -> list[dict[str, Any]]:
    path = logging_config.LOG_PATH
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if ts >= window_start:
            rec["_minute"] = ts.replace(second=0, microsecond=0)
            events.append(rec)
    return events


def compute(now: datetime | None = None) -> dict[str, Any]:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["dashboard"]
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(minutes=cfg["time_range_minutes"])
    events = _load_events(start)

    by_minute: dict[datetime, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for e in events:
        by_minute[e["_minute"]][e["event"]].append(e)
    minutes = sorted(by_minute)

    received = [e for e in events if e["event"] == "request_received"]
    sent = [e for e in events if e["event"] == "response_sent"]
    failed = [e for e in events if e["event"] == "request_failed"]
    tool_events = [e for e in sent + failed if e.get("tool_success") is not None]

    def series(event: str, fn) -> list[tuple[datetime, float]]:
        return [(m, fn(by_minute[m][event])) for m in minutes if by_minute[m][event]]

    lat = lambda p: series("response_sent", lambda es: _percentile([e["latency_ms"] for e in es], p))
    return {
        "cfg": cfg,
        "now": now,
        "start": start,
        "latency": {
            "P50": lat(50),
            "P95": lat(95),
            "P99": lat(99),
            "TTFT P95": series("response_sent", lambda es: _percentile([e["ttft_ms"] for e in es], 95)),
        },
        "latency_now": {
            "p50": _percentile([e["latency_ms"] for e in sent], 50),
            "p95": _percentile([e["latency_ms"] for e in sent], 95),
            "p99": _percentile([e["latency_ms"] for e in sent], 99),
            "ttft_p95": _percentile([e["ttft_ms"] for e in sent], 95),
        },
        "slow_threshold_ms": (slow_ms := _slow_threshold_ms()),
        "slow_count": sum(e["latency_ms"] > slow_ms for e in sent),
        "traffic": series("request_received", len),
        "traffic_total": len(received),
        "error_rate": [
            (m, 100 * len(by_minute[m]["request_failed"]) / len(by_minute[m]["request_received"]))
            for m in minutes
            if by_minute[m]["request_received"]
        ],
        "error_rate_total": 100 * len(failed) / len(received) if received else 0.0,
        "error_breakdown": dict(Counter(e.get("error_type") or "unknown" for e in failed)),
        "retrieval_success": (
            100 * sum(e["tool_success"] is True for e in tool_events) / len(tool_events) if tool_events else 100.0
        ),
        "cost": series("response_sent", lambda es: sum(e["cost_usd"] for e in es)),
        "cost_total": sum(e["cost_usd"] for e in sent),
        "tokens_in": sum(e["tokens_in"] for e in sent),
        "tokens_out": sum(e["tokens_out"] for e in sent),
        "quality": series("response_sent", lambda es: sum(e["quality_score"] for e in es) / len(es)),
        "quality_mean": sum(e["quality_score"] for e in sent) / len(sent) if sent else 0.0,
    }


# ---------- SVG helpers ----------

def _x(t: datetime, start: datetime, end: datetime) -> float:
    span = (end - start).total_seconds() or 1
    return PAD_L + (W - PAD_L - PAD_R) * (t - start).total_seconds() / span


def _nice_max(v: float) -> float:
    """Làm tròn trục lên 1/2/2.5/5 x 10^n để nhãn tick dễ đọc."""
    if v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    for step in (1, 2, 2.5, 5, 10):
        if step * 10**exp >= v:
            return step * 10**exp
    return 10 ** (exp + 1)


def _y(v: float, vmax: float) -> float:
    return PAD_T + (H - PAD_T - PAD_B) * (1 - v / vmax)


def _axes(start: datetime, end: datetime, vmax: float, unit: str) -> str:
    parts = []
    for i in range(6):
        v = vmax * i / 5
        y = _y(v, vmax)
        parts.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{PAD_L - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{_fmt(v, unit)}</text>')
    for i in range(7):
        t = start + (end - start) * i / 6
        x = _x(t, start, end)
        parts.append(
            f'<text x="{x:.1f}" y="{H - 8}" class="tick" text-anchor="middle">{_local(t):%H:%M}</text>'
        )
    return "".join(parts)


def _threshold(value: float, vmax: float, label: str) -> str:
    y = _y(value, vmax)
    return (
        f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" class="thr"/>'
        f'<text x="{PAD_L + 4}" y="{y - 4:.1f}" class="thr-label">{html.escape(label)}</text>'
    )


def _fmt(v: float, unit: str) -> str:
    if unit == "usd":
        return f"${v:.3f}" if v < 1 else f"${v:.2f}"
    if unit == "percent":
        return f"{v:g}%"
    if unit == "score_0_to_1":
        return f"{v:.2f}"
    return f"{v:,.0f}"


def _local(t: datetime) -> datetime:
    return t.astimezone(timezone(timedelta(hours=7)))


def _line_chart(data: dict[str, list[tuple[datetime, float]]], start, end, unit, thr, thr_label, vmin_max=1.0) -> str:
    vmax = _nice_max(max([v for pts in data.values() for _, v in pts] + [thr, vmin_max]) * 1.1)
    if unit == "score_0_to_1":
        vmax = 1.0  # điểm quality luôn trong [0, 1]
    body = [_axes(start, end, vmax, unit), _threshold(thr, vmax, thr_label)]
    for i, (name, pts) in enumerate(data.items(), start=1):
        if not pts:
            continue
        path = " ".join(f"{_x(t, start, end):.1f},{_y(v, vmax):.1f}" for t, v in pts)
        body.append(f'<polyline points="{path}" class="line s{i}"/>')
        for t, v in pts:
            body.append(
                f'<circle cx="{_x(t, start, end):.1f}" cy="{_y(v, vmax):.1f}" r="4" class="dot s{i}">'
                f"<title>{html.escape(name)} {_local(t):%H:%M}: {_fmt(v, unit)} {unit}</title></circle>"
            )
    return f'<svg viewBox="0 0 {W} {H}" role="img">{"".join(body)}</svg>'


def _bar_chart(pts: list[tuple[datetime, float]], start, end, unit, thr, thr_label) -> str:
    vmax = _nice_max(max([v for _, v in pts] + [thr, 1e-9]) * 1.1)
    bw = max(4.0, (W - PAD_L - PAD_R) / 60 - 2)
    body = [_axes(start, end, vmax, unit), _threshold(thr, vmax, thr_label)]
    for t, v in pts:
        x = _x(t, start, end) - bw / 2
        y = _y(v, vmax)
        body.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(0.0, _y(0, vmax) - y):.1f}" rx="2" class="bar s1">'
            f"<title>{_local(t):%H:%M}: {_fmt(v, unit)} {unit}</title></rect>"
        )
    return f'<svg viewBox="0 0 {W} {H}" role="img">{"".join(body)}</svg>'


def _legend(names: list[str]) -> str:
    return '<div class="legend">' + "".join(
        f'<span><i class="sw s{i}"></i>{html.escape(n)}</span>' for i, n in enumerate(names, start=1)
    ) + "</div>"


def _stat(label: str, value: str, ok: bool) -> str:
    status = "ok" if ok else "breach"
    icon = "✓" if ok else "!"
    return f'<div class="stat"><div class="stat-label">{label}</div><div class="stat-value">{value}</div><div class="badge {status}">{icon} {"OK" if ok else "Vượt ngưỡng"}</div></div>'


def _panel(pid: str, title: str, unit: str, stats: str, chart: str, legend: str = "") -> str:
    return (
        f'<section class="panel" id="{pid}"><header><h2>{html.escape(title)}</h2>'
        f'<span class="unit">đơn vị: {unit}</span></header><div class="stats">{stats}</div>{legend}{chart}</section>'
    )


def render_html() -> str:
    d = compute()
    cfg, start, end = d["cfg"], d["start"], d["now"]
    thr = {p["id"]: p["threshold"]["value"] for p in cfg["panels"]}
    titles = {p["id"]: p["title"] for p in cfg["panels"]}
    ln = d["latency_now"]

    panels = [
        _panel(
            "latency", titles["latency"], "ms",
            _stat("P50", f'{ln["p50"]:,.0f} ms', True)
            + _stat("P95", f'{ln["p95"]:,.0f} ms', ln["p95"] <= thr["latency"])
            + _stat("P99", f'{ln["p99"]:,.0f} ms', True)
            + _stat("TTFT P95", f'{ln["ttft_p95"]:,.0f} ms', True)
            + _stat(f'Request > {d["slow_threshold_ms"]:,} ms', f'{d["slow_count"]}', d["slow_count"] == 0),
            _line_chart(d["latency"], start, end, "ms", thr["latency"], f'SLO P95 ≤ {thr["latency"]:,} ms'),
            _legend(list(d["latency"])),
        ),
        _panel(
            "traffic", titles["traffic"], "requests/phút",
            _stat("Tổng request (60 phút)", f'{d["traffic_total"]:,}', d["traffic_total"] > 0),
            _bar_chart(d["traffic"], start, end, "req/min", thr["traffic"], f'tối thiểu {thr["traffic"]} req/phút'),
        ),
        _panel(
            "errors", titles["errors"], "%",
            _stat("Error rate", f'{d["error_rate_total"]:.1f}%', d["error_rate_total"] <= thr["errors"])
            + _stat("Retrieval success", f'{d["retrieval_success"]:.1f}%', d["retrieval_success"] >= 90)
            + _stat(
                "Breakdown",
                ", ".join(f"{k}: {v}" for k, v in d["error_breakdown"].items()) or "không có lỗi",
                not d["error_breakdown"],
            ),
            _line_chart({"Error rate": d["error_rate"]}, start, end, "percent", thr["errors"], f'ngưỡng ≤ {thr["errors"]}%', 5),
        ),
        _panel(
            "cost", titles["cost"], "USD",
            _stat("Tổng cost (60 phút)", f'${d["cost_total"]:.4f}', d["cost_total"] <= thr["cost"])
            + _stat("Ngưỡng", f'${thr["cost"]:.2f}', True),
            _bar_chart(d["cost"], start, end, "usd", thr["cost"] / 60, f'${thr["cost"]}/60 phút ≈ ${thr["cost"] / 60:.3f}/phút'),
        ),
        _panel(
            "tokens", titles["tokens"], "tokens",
            _stat("Input tokens", f'{d["tokens_in"]:,}', d["tokens_in"] <= thr["tokens"])
            + _stat("Output tokens", f'{d["tokens_out"]:,}', d["tokens_out"] <= thr["tokens"]),
            _token_bars(d["tokens_in"], d["tokens_out"], thr["tokens"]),
        ),
        _panel(
            "quality", titles["quality"], "điểm 0–1",
            _stat("Mean quality", f'{d["quality_mean"]:.2f}', d["quality_mean"] >= thr["quality"]),
            _line_chart({"Quality mean": d["quality"]}, start, end, "score_0_to_1", thr["quality"], f'ngưỡng ≥ {thr["quality"]}'),
        ),
    ]
    return PAGE.format(
        title=html.escape(cfg["title"]),
        refresh=cfg["refresh_seconds"],
        range_from=f"{_local(start):%Y-%m-%d %H:%M}",
        range_to=f"{_local(end):%H:%M}",
        minutes=cfg["time_range_minutes"],
        panels="".join(panels),
    )


def _token_bars(tokens_in: int, tokens_out: int, thr: float) -> str:
    vmax = max(tokens_in, tokens_out, thr) * 1.15
    width = W - PAD_L - PAD_R
    rows = []
    for i, (name, v) in enumerate((("Input", tokens_in), ("Output", tokens_out)), start=1):
        y = PAD_T + 20 + (i - 1) * 60
        rows.append(
            f'<text x="{PAD_L - 6}" y="{y + 22}" class="tick" text-anchor="end">{name}</text>'
            f'<rect x="{PAD_L}" y="{y}" width="{max(2.0, width * v / vmax):.1f}" height="32" rx="4" class="bar s{i}">'
            f"<title>{name}: {v:,} tokens</title></rect>"
            f'<text x="{PAD_L + width * v / vmax + 6:.1f}" y="{y + 21}" class="val">{v:,}</text>'
        )
    tx = PAD_L + width * thr / vmax
    rows.append(
        f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{PAD_T}" y2="{H - PAD_B}" class="thr"/>'
        f'<text x="{tx - 4:.1f}" y="{H - PAD_B + 16}" class="thr-label" text-anchor="end">ngưỡng {thr:,.0f}/field</text>'
    )
    return f'<svg viewBox="0 0 {W} {H}" role="img">{"".join(rows)}</svg>'


PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh}">
<title>{title}</title>
<style>
:root {{ color-scheme: light; --surface: #fcfcfb; --page: #f3f2ee; --ink: #0b0b0b; --ink-2: #52514e; --grid: #e4e2dc;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --ok: #1a7f37; --bad: #c62828; }}
@media (prefers-color-scheme: dark) {{ :root {{ color-scheme: dark; --surface: #1a1a19; --page: #111110; --ink: #fff; --ink-2: #c3c2b7;
  --grid: #33332f; --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --ok: #4cc26a; --bad: #ff6b6b; }} }}
body {{ margin: 0; padding: 16px; background: var(--page); color: var(--ink); font: 14px/1.4 system-ui, sans-serif; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }} .meta {{ color: var(--ink-2); margin-bottom: 16px; }}
.grid6 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr)); gap: 16px; }}
.panel {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 10px; padding: 14px; }}
.panel header {{ display: flex; justify-content: space-between; align-items: baseline; }}
h2 {{ font-size: 15px; margin: 0 0 8px; }} .unit {{ color: var(--ink-2); font-size: 12px; }}
.stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 6px; }}
.stat-label {{ color: var(--ink-2); font-size: 12px; }} .stat-value {{ font-size: 18px; font-weight: 600; }}
.badge {{ font-size: 11px; font-weight: 600; }} .badge.ok {{ color: var(--ok); }} .badge.breach {{ color: var(--bad); }}
.legend {{ display: flex; gap: 14px; font-size: 12px; color: var(--ink-2); }}
.sw {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }}
svg {{ width: 100%; height: auto; display: block; }}
.grid {{ stroke: var(--grid); stroke-width: 1; }} .tick {{ fill: var(--ink-2); font-size: 11px; }} .val {{ fill: var(--ink); font-size: 12px; }}
.thr {{ stroke: var(--bad); stroke-width: 1.5; stroke-dasharray: 5 4; }} .thr-label {{ fill: var(--bad); font-size: 11px; }}
.line {{ fill: none; stroke-width: 2; }} .dot {{ stroke: var(--surface); stroke-width: 2; }}
.s1 {{ stroke: var(--s1); }} .dot.s1, .bar.s1, .sw.s1 {{ fill: var(--s1); background: var(--s1); }}
.s2 {{ stroke: var(--s2); }} .dot.s2, .bar.s2, .sw.s2 {{ fill: var(--s2); background: var(--s2); }}
.s3 {{ stroke: var(--s3); }} .dot.s3, .sw.s3 {{ fill: var(--s3); background: var(--s3); }}
.s4 {{ stroke: var(--s4); }} .dot.s4, .sw.s4 {{ fill: var(--s4); background: var(--s4); }}
.bar {{ stroke: none; }}
@media (max-width: 520px) {{ .grid6 {{ grid-template-columns: 1fr; }} }}
</style></head><body>
<h1>{title}</h1>
<div class="meta">Nguồn: data/logs.jsonl · Time range: {minutes} phút ({range_from} → {range_to}, GMT+7) · Tự refresh {refresh}s</div>
<div class="grid6">{panels}</div>
</body></html>"""
