"""사양·목표·현재 설정 → 변경 계획. 파일을 쓰지 않고 계획만 만든다."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .display_service import Monitor
from .i18n import t

_DATA = Path(__file__).with_name("data")
OPTIONS_DATA = json.loads((_DATA / "options.json").read_text(encoding="utf-8"))
GPU_TIERS = json.loads((_DATA / "gpu_tiers.json").read_text(encoding="utf-8"))

PRIORITIES = [
    ("balance", "균형", "화질 유지와 목표 FPS의 균형"),
    ("quality", "화질 우선", "선명도와 장면 표현"),
    ("perf", "성능 우선", "높은 FPS와 프레임 안정성"),
    ("quiet", "조용하게", "불필요한 GPU 부하 완화"),
]
TARGETS = [100, 120, 144, 165, 240]
_COSTLY = ("preset", "shadow", "effects", "model")  # 등급이 낮을수록 먼저 낮추는 옵션


@dataclass
class Option:
    id: str
    tab: str
    key: str
    evidence: str
    name: str
    desc: str
    choices: list[tuple[str, str]]
    advanced: bool = False
    manual: bool = False  # 자동 추천에서 건드리지 않음(사용자가 직접 고름)
    unit: str = ""
    free_int: tuple[int, int] | None = None

    def label(self, value: str | None) -> str:
        if value is None:
            return t("기본값")
        for lab, v in self.choices:
            if v == value:
                return t(lab) + self.unit
        return f"{value}{self.unit}" if self.free_int else t("값 {value}", value=value)

    def step_down(self, value: str, n: int) -> str:
        vals = [v for _, v in self.choices]
        if value not in vals or n <= 0:
            return value
        return vals[max(0, vals.index(value) - n)]


OPTIONS: list[Option] = [
    Option(o["id"], o["tab"], o["key"], o["evidence"], o["name"], o["desc"],
           [tuple(c) for c in o["choices"]], o.get("advanced", False), o.get("manual", False),
           o.get("unit", ""), tuple(o["free_int"]) if "free_int" in o else None)
    for o in OPTIONS_DATA["options"]
]
OPTION_BY_ID = {o.id: o for o in OPTIONS}
MODES = OPTIONS_DATA["display_modes"]


def gpu_tier(gpu_name: str | None) -> str | None:
    """등급표에 있으면 'high'/'mid'/'low', 없으면 None(미등록)."""
    if not gpu_name:
        return None
    name = gpu_name.lower()
    entries = [(pat.lower(), tier) for tier, pats in GPU_TIERS["tiers"].items() for pat in pats]
    for pat, tier in sorted(entries, key=lambda e: -len(e[0])):  # 'rtx 4070 super'가 'rtx 4070'보다 먼저
        if pat in name:
            return tier
    return None


def current_mode(render: dict[str, str]) -> str | None:
    raw = render.get(MODES["key"])
    if raw is None:
        return MODES["absent_means"]
    for c in MODES["choices"]:
        if c["values"][MODES["key"]] == raw:
            return c["id"]
    return None


def mode_label(mode_id: str | None) -> str:
    for c in MODES["choices"]:
        if c["id"] == mode_id:
            return t(c["label"])
    return t("알 수 없음")


def suggest_hz(monitor: Monitor | None, target_fps: int) -> int | None:
    """목표 FPS 이상인 지원 주사율 중 가장 낮은 값. 없으면 최대값."""
    if not monitor or not monitor.rates:
        return None
    above = [r for r in monitor.rates if r >= target_fps]
    return min(above) if above else max(monitor.rates)


@dataclass
class Goal:
    target_fps: int = 120
    priority: str = "balance"
    mode: str | None = None  # None → 현재 화면 모드 유지
    monitor: Monitor | None = None
    apply_display: bool = False
    display_hz: int | None = None
    overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class PlanRow:
    id: str
    name: str
    cur: str
    rec: str
    changed: bool
    why: str
    badge: str  # confirmed | seen | community | override | manual
    writes: dict[str, str] = field(default_factory=dict)


@dataclass
class Plan:
    rows: list[PlanRow]
    tier: str | None
    display_change: tuple[str, int, int] | None  # (장치, 현재 Hz, 새 Hz)

    @property
    def writes(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in self.rows:
            if r.changed:
                out.update(r.writes)
        return out

    @property
    def n_changed(self) -> int:
        return sum(r.changed for r in self.rows)


def auto_value(opt: Option, goal: Goal, tier: str | None, vram: int | None,
               render: dict[str, str]) -> str | None:
    """사용자 지정이 없을 때의 추천값. None이면 추천하지 않음(현재 유지)."""
    if opt.manual:
        return render.get(opt.key)
    if opt.id == "frame_mode":
        return "0"
    if opt.id == "fps_cap":
        cap = goal.target_fps
        if goal.priority == "quiet":
            hz = goal.display_hz if goal.apply_display and goal.display_hz else (
                goal.monitor.hz if goal.monitor else None)
            if hz:
                cap = min(cap, hz)
        return str(cap)
    value = OPTIONS_DATA["profiles"][goal.priority].get(opt.id)
    if value is None:
        return None
    steps = {"high": 0, "mid": 1, "low": 2, None: 1}[tier]  # 미등록은 보수적으로 한 단계 낮춤
    if opt.id in _COSTLY:
        value = opt.step_down(value, steps)
    if opt.id == "texture":
        gb = (vram or 0) / 1024 ** 3
        cap = "2" if vram and gb < 6 else "3" if not vram or gb < 8 else "4"
        if int(value) > int(cap):
            value = cap
    return value


def _why(opt_id: str, priority: str) -> str:
    w = OPTIONS_DATA["why"].get(opt_id, {})
    return t(w.get(priority) or w.get("d", ""))


def build_plan(render: dict[str, str], goal: Goal, gpu_name: str | None, vram: int | None,
               confirmed: set[str]) -> Plan:
    tier = gpu_tier(gpu_name)
    rows: list[PlanRow] = []

    # 화면 모드 — 여러 키를 함께 바꾼다
    cur_mode = current_mode(render)
    want = goal.mode or cur_mode
    if want:
        choice = next(c for c in MODES["choices"] if c["id"] == want)
        changed = any(render.get(k) != v for k, v in choice["values"].items())
        rows.append(PlanRow("mode", t("화면 모드"), mode_label(cur_mode),
                            t(choice["label"]) if changed else t("유지"), changed,
                            t("사용자 선택") if goal.mode else t("현재 모드 유지"),
                            "confirmed" if MODES["key"] in confirmed else MODES["evidence"],
                            dict(choice["values"])))

    # 전체 화면에서만 게임이 직접 주사율을 고른다(창·테두리 없는 창은 Windows 값을 따름)
    if want == "full" and goal.display_hz:
        cur, rec = render.get("FullScreenRefresh"), str(goal.display_hz)
        rows.append(PlanRow("fs_refresh", t("전체 화면 주사율"), f"{cur}Hz" if cur else t("기본값"),
                            f"{rec}Hz" if cur != rec else t("유지"), cur != rec,
                            t("전체 화면일 때 게임이 요청하는 주사율 · 모니터 지원 모드 중 선택"),
                            "confirmed" if "FullScreenRefresh" in confirmed else "seen",
                            {"FullScreenRefresh": rec} if cur != rec else {}))

    for opt in OPTIONS:
        cur = render.get(opt.key)
        override = goal.overrides.get(opt.id)
        rec = override if override is not None else auto_value(opt, goal, tier, vram, render)
        changed = rec is not None and rec != cur
        if override is not None:
            badge, why = "override", t("상세 설정에서 직접 지정")
        elif opt.manual:
            badge, why = "manual", t("찢어짐·지연 선호에 따라 상세 설정에서 직접 선택")
        else:
            badge = "confirmed" if opt.key in confirmed else opt.evidence
            why = _why(opt.id, goal.priority)
        rows.append(PlanRow(opt.id, t(opt.name), opt.label(cur),
                            opt.label(rec) if changed else t("유지"), changed, why, badge,
                            {opt.key: rec} if changed else {}))

    display_change = None
    m = goal.monitor
    if goal.apply_display and m and not m.virtual and goal.display_hz in m.rates:
        changed = goal.display_hz != m.hz
        rows.append(PlanRow("display", t("Windows 주사율"), f"{m.hz}Hz",
                            f"{goal.display_hz}Hz" if changed else t("유지"), changed,
                            t("{name} 지원 모드 · 15초 안에 '유지'를 눌러야 확정", name=m.name), "display"))
        if changed:
            display_change = (m.device, m.hz, goal.display_hz)

    return Plan(rows, tier, display_change)
