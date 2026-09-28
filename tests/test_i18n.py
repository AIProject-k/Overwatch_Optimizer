"""영어 사전(data/en.json)에 빠진 문구가 없는지 확인."""
import ast
import json
import re
from pathlib import Path

from owtune import display_service, i18n, recommender
from owtune.ui import settings_page, theme

PKG = Path(__file__).resolve().parents[1] / "owtune"
EN = json.loads((PKG / "data" / "en.json").read_text(encoding="utf-8"))
_HANGUL = re.compile(r"[가-힣]")


def _t_literals() -> set[str]:
    """코드에서 t("...")로 부르는 한국어 문자열."""
    out = set()
    for f in PKG.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t" and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                out.add(node.args[0].value)
    return out


def _data_strings() -> set[str]:
    """데이터·상수에 들어 있어 표시할 때 t(변수)로 번역되는 문자열."""
    d = recommender.OPTIONS_DATA
    out = {c["label"] for c in d["display_modes"]["choices"]}
    for o in d["options"]:
        out |= {o["name"], o["desc"]} | {lab for lab, _ in o["choices"]}
    for w in d["why"].values():
        out |= set(w.values())
    for _, name, desc in recommender.PRIORITIES:
        out |= {name, desc}
    for text, _, _, tip in theme.BADGES.values():
        out |= {text, tip}
    out |= set(settings_page.FACT_DESC) | set(settings_page.FACT_DESC.values())
    out |= {label for tid, label in settings_page.TABS if tid != "lang"}
    out |= set(display_service._TECH.values()) | set(display_service._DISP_MSG.values())
    return out


def required() -> set[str]:
    return {s for s in _t_literals() | _data_strings() if _HANGUL.search(s)}


def test_every_korean_string_has_english():
    missing = sorted(required() - EN.keys())
    assert not missing, "en.json에 없는 문구:\n" + "\n".join(missing)


def test_placeholders_match():
    ph = re.compile(r"\{(\w+)\}")
    bad = [k for k, v in EN.items() if set(ph.findall(k)) != set(ph.findall(v))]
    assert not bad, bad


def test_english_has_no_hangul():
    assert not [v for v in EN.values() if _HANGUL.search(v)]


def test_t_switches_language():
    try:
        i18n.set_lang("en")
        assert i18n.t("유지") == EN["유지"]
        assert i18n.t("{n}건 변경 · {k}건 유지", n=3, k=2) == EN["{n}건 변경 · {k}건 유지"].format(n=3, k=2)
        i18n.set_lang("ko")
        assert i18n.t("유지") == "유지"
    finally:
        i18n.set_lang("ko")
