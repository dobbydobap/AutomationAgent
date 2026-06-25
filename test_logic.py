"""
test_logic.py
──────────────
Tiny self-check for the pure logic that needs no browser or API key.
Run it directly:  python test_logic.py
"""

import json

from agent.agent import _normalize_url
from agent.llm_agent import _strip_json


def test() -> None:
    # URL normalisation: bare hosts get https://, real schemes are left alone.
    assert _normalize_url("amazon.com") == "https://amazon.com"
    assert _normalize_url("http://x.com") == "http://x.com"
    assert _normalize_url(" https://y.com ") == "https://y.com"

    # Action JSON is recovered whether it is fenced or wrapped in prose.
    assert json.loads(_strip_json('```json\n{"action":"done"}\n```'))["action"] == "done"
    assert json.loads(_strip_json('sure: {"action":"click","index":3}'))["index"] == 3

    print("logic self-check ok")


if __name__ == "__main__":
    test()
