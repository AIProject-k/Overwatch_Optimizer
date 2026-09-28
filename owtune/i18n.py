"""화면 문구 번역. 한국어 원문을 그대로 키로 쓰고, 영어는 data/en.json에서 찾는다.

사전에 없는 문구는 한국어 그대로 보여준다(tests/test_i18n.py가 빠진 번역을 잡는다).
"""
from __future__ import annotations

import json
from pathlib import Path

LANGS = [("ko", "한국어"), ("en", "English")]
_EN: dict[str, str] = json.loads((Path(__file__).with_name("data") / "en.json").read_text(encoding="utf-8"))
_lang = "ko"


def set_lang(code: str) -> None:
    global _lang
    _lang = code if code in dict(LANGS) else "ko"


def lang() -> str:
    return _lang


def t(text: str, **kw) -> str:
    s = _EN.get(text, text) if _lang == "en" else text
    return s.format(**kw) if kw else s
