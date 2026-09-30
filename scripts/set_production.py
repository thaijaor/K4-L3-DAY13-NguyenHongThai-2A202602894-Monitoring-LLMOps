"""Chuyển label `production` của prompt sang một version (promote hoặc rollback).

Ví dụ: python scripts/set_production.py 2   # promote v2
       python scripts/set_production.py 1   # rollback về v1
Restart API sau khi đổi label vì SDK cache prompt 60s.
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


def main() -> int:
    configure_utf8_stdio()
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print(__doc__)
        return 2
    load_dotenv(REPO_ROOT / ".env")
    from langfuse import get_client

    client = get_client()
    name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    version = int(sys.argv[1])
    current = client.get_prompt(name, type="text", label="production", cache_ttl_seconds=0).version
    # Langfuse chỉ cho một version giữ label `production`; gắn vào version mới sẽ gỡ khỏi version cũ.
    client.update_prompt(name=name, version=version, new_labels=["production"])
    after = client.get_prompt(name, type="text", label="production", cache_ttl_seconds=0).version
    print(f"{name} production: v{current} -> v{after}")
    return 0 if after == version else 1


if __name__ == "__main__":
    raise SystemExit(main())
