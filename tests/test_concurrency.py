from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx

from app import agent as agent_module
from app import logging_config
from app.main import app

SLOW_RETRIEVAL_S = 0.4


def test_slow_retrieval_does_not_block_other_requests(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")

    def slow_retrieve(message: str) -> list[str]:
        time.sleep(SLOW_RETRIEVAL_S)  # mô phỏng vector store chậm (rag_slow)
        return ["doc"]

    monkeypatch.setattr(agent_module, "retrieve", slow_retrieve)

    async def send_concurrently(n: int) -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await asyncio.gather(
                *(
                    client.post(
                        "/chat",
                        json={"user_id": f"u{i}", "session_id": f"s{i}", "feature": "qa", "message": "hello"},
                    )
                    for i in range(n)
                )
            )

    started = time.perf_counter()
    responses = asyncio.run(send_concurrently(5))
    elapsed = time.perf_counter() - started

    assert all(r.status_code == 200 for r in responses)
    assert len({r.headers["x-request-id"] for r in responses}) == 5
    # Nếu chặn event loop, 5 request chạy nối tiếp: >= 5 * 0.4s = 2s.
    assert elapsed < 2 * SLOW_RETRIEVAL_S + 0.5
