"""Tạo prompt day13-chat v1 (baseline, production) và v2 (candidate) trong project Langfuse cá nhân.

Chạy một lần; nếu prompt đã có đủ 2 version thì chỉ in trạng thái hiện tại.
Promote/rollback label `production` làm trên Langfuse UI để có evidence trước/sau.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2 = (
    "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}\n"
    "Answer in at most 3 short bullet points, using only the docs above."
)


def main() -> int:
    configure_utf8_stdio()
    load_dotenv(REPO_ROOT / ".env")
    from langfuse import get_client

    client = get_client()
    name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")

    try:
        latest = client.get_prompt(name, type="text", label="latest", cache_ttl_seconds=0)
        existing = latest.version
    except Exception:
        existing = 0

    if existing == 0:
        client.create_prompt(name=name, type="text", prompt=V1, labels=["baseline", "production"])
        client.create_prompt(name=name, type="text", prompt=V2, labels=["candidate"])
    elif existing == 1:
        client.create_prompt(name=name, type="text", prompt=V2, labels=["candidate"])

    for label in ("baseline", "candidate", "production"):
        p = client.get_prompt(name, type="text", label=label, cache_ttl_seconds=0)
        print(f"{name} [{label}] -> version {p.version}")
    client.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
