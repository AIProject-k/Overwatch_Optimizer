"""02 상세 설정 — 화면 / 그래픽 / 프레임·지연 / 언어.

여기서 고른 값은 바로 쓰지 않고 '직접 지정'으로 홈의 변경 계획에 들어간다.
Windows 주사율만 '지금 변경'으로 바로 바꿀 수 있다(15초 유지 확인 포함).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QHBoxLayout, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from . import theme as T
from .home import facts, hz_text
from .model import AppModel
from .widgets import Segmented, badge, clear, dot, frame, label
from ..i18n import LANGS, t
from ..recommender import MODES, OPTIONS, auto_value, current_mode, gpu_tier, mode_label

# 언어 탭 이름은 어느 언어로 보고 있어도 찾을 수 있게 두 언어를 함께 쓴다
TABS = [("display", "화면"), ("gfx", "그래픽"), ("frame", "프레임·지연"), ("lang", "언어 · Language")]

FACT_DESC = {
    "Windows 활성 주사율": "현재 디스플레이 경로의 화면 갱신 설정. 창·테두리 없는 창 모드는 이 값을 따릅니다.",
    "지원 주사율": "현재 해상도와 연결에서 선택 가능한 모드. HDMI·DP 연결 방식에 따라 다를 수 있습니다.",
    "프레임 속도 방식": "디스플레이 기반이면 FPS가 모니터 Hz에 묶입니다.",
    "게임 FPS 상한": "게임의 렌더링 상한. 60Hz 화면에서도 더 높게 설정할 수 있습니다.",
    "수직 동기화": "켜면 FPS가 모니터 Hz에 맞춰집니다.",
    "창 모드 주사율 저장값": "게임이 Windows 주사율을 그대로 기록하는 값. 이 PC에서 144로 바꾼 값이 "
                         "게임 실행 뒤 120(당시 Windows 값)으로 돌아가, 이 값만 바꿔선 효과가 없는 것으로 보입니다.",
}


class SettingsPage(QWidget):
    def __init__(self, model: AppModel, on_change_display, on_language, tab: str = "display"):
        super().__init__()
        self.m = model
        self.tab = tab
        self.advanced = False
        self.on_change_display = on_change_display
        self.on_language = on_language
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar, bl = frame("tabBar", QHBoxLayout, (24, 20, 24, 0), 4)
        group = QButtonGroup(self)
        self.tab_btns = {}
        for tid, text in TABS:
            b = QPushButton((t(text) if tid != "lang" else text).replace("&", "&&"))
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, x=tid: self._set_tab(x))
            group.addButton(b)
            self.tab_btns[tid] = b
            bl.addWidget(b)
        bl.addStretch(1)
        self.clear_btn = QPushButton(t("직접 지정 초기화"))
        self.clear_btn.setObjectName("link")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.m.clear_overrides)
        bl.addWidget(self.clear_btn)
        bl.addSpacing(14)
        self.adv = QCheckBox(t("고급 옵션 보기"))
        self.adv.setCursor(Qt.PointingHandCursor)
        self.adv.toggled.connect(self._set_adv)
        bl.addWidget(self.adv)
        root.addWidget(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(24, 20, 24, 28)
        self.body.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self.tab_btns[tab].setChecked(True)
        model.changed.connect(self.render)

    def _set_tab(self, tab: str) -> None:
        self.tab = tab
        self.render()

    def _set_adv(self, on: bool) -> None:
        self.advanced = on
        self.render()

    # ---------------- 화면 탭 ----------------
    def _monitor_btn(self, mon, selected: bool) -> QPushButton:
        b = QPushButton()
        b.setObjectName("monitor")
        b.setCheckable(True)
        b.setChecked(selected)
        b.setEnabled(not mon.virtual)
        b.setCursor(Qt.PointingHandCursor if not mon.virtual else Qt.ForbiddenCursor)
        b.setMinimumHeight(58)
        lay = QHBoxLayout(b)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)
        radio = QWidget()
        radio.setFixedSize(14, 14)
        ring = T.ACCENT if selected else T.DIM
        radio.setStyleSheet(f"border:2px solid {ring};border-radius:7px;"
                            f"background:{T.ACCENT if selected else 'transparent'};")
        lay.addWidget(radio)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(label(mon.name, "h"))
        conn = f" · {mon.connection}" if mon.connection else ""
        names.addWidget(label(f"{mon.device}{conn} · {mon.adapter}", "muted"))
        lay.addLayout(names, 1)
        right = QVBoxLayout()
        right.setSpacing(2)
        r = label(f"{mon.width}×{mon.height} · {hz_text(mon)}", "mono")
        r.setStyleSheet(f"color:{T.SUB};")
        r.setAlignment(Qt.AlignRight)
        right.addWidget(r)
        same = sum(x.name == mon.name for x in self.m.monitors) > 1
        tag = t("가상 화면 · 진단만") if mon.virtual else t("주 모니터") if mon.primary else \
            t("같은 모델명") if same else t("보조 모니터")
        tg = label(tag, "muted")
        tg.setAlignment(Qt.AlignRight)
        if mon.virtual:
            tg.setStyleSheet(f"color:{T.WARN};font-size:11px;")
        right.addWidget(tg)
        lay.addLayout(right)
        for w in b.findChildren(QWidget):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        b.clicked.connect(lambda _=False, d=mon.device: self.m.set_monitor(d))
        return b

    def _display_tab(self) -> None:
        m = self.m
        row = QHBoxLayout()
        row.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(22)

        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(label(t("대상 모니터"), "h"))
        box.addWidget(label(t("이름이 같은 모니터는 디스플레이 경로(\\\\.\\DISPLAYn)로 구분합니다."), "muted"))
        sel = m.monitor
        if not m.monitors:
            box.addWidget(label(t("활성 모니터를 찾지 못했습니다."), "sub"))
        for mon in m.monitors:
            box.addWidget(self._monitor_btn(mon, sel is not None and mon.device == sel.device))
        left.addLayout(box)

        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(label(t("게임 화면 모드"), "h"))
        cur = current_mode(m.snap.render) if m.snap else None
        seg = Segmented()
        seg.setMaximumWidth(420)
        seg.set_items([(t(c["label"]), c["id"]) for c in MODES["choices"]], m.mode or cur, current=cur,
                      enabled=m.snap is not None)
        seg.picked.connect(lambda v: m.set_mode(v, cur))
        box.addWidget(seg)
        box.addWidget(label(t("현재 파일 값: {mode} · 값 대응은 커뮤니티 근거(WindowMode 0/1/2). "
                              "고른 모드는 홈의 변경 계획에 들어갑니다.", mode=mode_label(cur)), "muted", wrap=True))
        left.addLayout(box)

        sizes = QHBoxLayout()
        sizes.setSpacing(12)
        r = m.snap.render if m.snap else {}
        ww, wh = r.get("WindowedWidth"), r.get("WindowedHeight")
        for k, v in ((t("게임 창 크기"), f"{ww} × {wh}" if ww and wh else t("기본값")),
                     (t("Windows 디스플레이 해상도"), f"{sel.width} × {sel.height}" if sel else t("미확인"))):
            cell, cl = frame("card", margins=(14, 12, 14, 12), spacing=6)
            cl.addWidget(label(k, "muted"))
            v_lab = label(v, "mono")
            v_lab.setStyleSheet("font-size:14px;")
            cl.addWidget(v_lab)
            sizes.addWidget(cell)
        sizes.addStretch(1)
        left.addLayout(sizes)

        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(label(t("Windows 주사율"), "h"))
        box.addWidget(label(t("현재 해상도와 연결에서 지원되는 모드만 선택할 수 있습니다."), "muted"))
        rates = QHBoxLayout()
        rates.setSpacing(6)
        hz = m.display_hz
        can = bool(sel and not sel.virtual and sel.rates)
        for v in (sel.rates if can else []):
            b = QPushButton(f"{v}Hz")
            b.setObjectName("pick")
            b.setCheckable(True)
            b.setChecked(v == hz)
            b.setMinimumWidth(84)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=v: m.set_display_hz(v))
            rates.addWidget(b)
        now = QPushButton(t("지금 변경"))
        now.setObjectName("ghost")
        now.setMinimumHeight(34)
        now.setCursor(Qt.PointingHandCursor)
        now.setEnabled(can and hz is not None and hz != sel.hz)
        now.clicked.connect(lambda: self.on_change_display(sel.device, sel.hz, hz))
        rates.addSpacing(8)
        rates.addWidget(now)
        rates.addStretch(1)
        box.addLayout(rates)
        box.addWidget(label(t("홈의 ‘Windows 주사율도 변경’을 켜면 권장 설정과 함께 적용됩니다. "
                              "고르지 않으면 목표 FPS 이상인 가장 낮은 주사율을 제안합니다."), "muted", wrap=True))
        left.addLayout(box)
        left.addStretch(1)
        row.addLayout(left, 1)

        card, cl = frame("card")
        card.setFixedWidth(380)
        head, hl = frame("cardHead", margins=(16, 14, 16, 14), spacing=4)
        hl.addWidget(label(t("주사율과 FPS"), "h"))
        hl.addWidget(label(t("서로 다른 곳에 저장된 값입니다. 하나를 바꿔도 나머지는 바뀌지 않습니다."), "sub", wrap=True))
        cl.addWidget(head)
        for k, v, warn in facts(m):
            f, fl = frame("row", margins=(16, 10, 16, 10), spacing=3)
            top = QHBoxLayout()
            top.addWidget(label(t(k)))
            top.addStretch(1)
            val = label(v, "mono")
            val.setStyleSheet(f"color:{T.WARN if warn else T.TEXT};")
            top.addWidget(val)
            fl.addLayout(top)
            if k in FACT_DESC:
                fl.addWidget(label(t(FACT_DESC[k]), "muted", wrap=True))
            cl.addWidget(f)
        row.addWidget(card, 0, Qt.AlignTop)
        self.body.addLayout(row)

    # ---------------- 그래픽·프레임 탭 ----------------
    def _option_rows(self, tab: str) -> None:
        m = self.m
        render = m.snap.render if m.snap else {}
        goal = m.goal()
        g = m.gpu
        tier = gpu_tier(g.name if g else None)
        wrap = QVBoxLayout()
        wrap.setSpacing(0)
        if tab == "frame":
            wrap.addWidget(label(t("수직 동기화와 트리플 버퍼링은 모니터 환경과 찢어짐·지연 선호에 따라 결과가 달라서 "
                                   "자동으로 바꾸지 않습니다. 원하는 값을 직접 고르세요."), "sub", wrap=True))
            wrap.addSpacing(6)
        for opt in OPTIONS:
            if opt.tab != tab or (opt.advanced and not self.advanced):
                continue
            cur = render.get(opt.key)
            auto = auto_value(opt, goal, tier, g.vram_bytes if g else None, render)
            override = m.overrides.get(opt.id)
            planned = override if override is not None else auto if auto is not None else cur

            f, fl = frame("row", QHBoxLayout, (0, 16, 0, 16), 24)
            info = QVBoxLayout()
            info.setSpacing(5)
            top = QHBoxLayout()
            top.setSpacing(10)
            name = label(t(opt.name))
            name.setStyleSheet("font-size:14px;font-weight:600;")
            top.addWidget(name)
            kind = "override" if override is not None else "manual" if opt.manual else \
                "confirmed" if opt.key in m.store.confirmed else opt.evidence
            top.addWidget(badge(kind))
            top.addStretch(1)
            info.addLayout(top)
            info.addWidget(label(t(opt.desc), "sub", wrap=True))
            state = label(t("현재 {cur} · 계획 {plan}", cur=opt.label(cur), plan=opt.label(planned)), "mono")
            state.setStyleSheet(f"color:{T.MUTED};font-size:11px;")
            state.setToolTip(t("파일 키: {key}", key=opt.key))
            info.addWidget(state)
            fl.addLayout(info, 1)

            choices = [(t(lab), v) for lab, v in opt.choices]
            if opt.free_int:  # 목표 FPS를 직접 입력한 경우 등 목록 밖 값도 보여준다
                known = {v for _, v in choices}
                extra = {x for x in (planned, cur) if x and x not in known and x.isdigit()}
                choices = sorted(choices + [(x, x) for x in extra], key=lambda c: int(c[1]))
            seg = Segmented(accent=True)
            seg.set_items(choices, planned, current=cur, enabled=m.snap is not None)
            seg.picked.connect(lambda v, o=opt, a=auto: m.set_override(o.id, None if v == a else v))
            fl.addWidget(seg, 0, Qt.AlignVCenter)
            wrap.addWidget(f)

        legend = QHBoxLayout()
        legend.setContentsMargins(0, 14, 0, 0)
        legend.setSpacing(8)
        legend.addWidget(dot(T.SUB, 4))
        legend.addWidget(label(t("현재 파일 값"), "muted"))
        legend.addSpacing(12)
        sq = dot(T.ACCENT, 10)
        sq.setStyleSheet(f"background:{T.ACCENT};border-radius:2px;")
        legend.addWidget(sq)
        legend.addWidget(label(t("홈의 변경 계획에 들어갈 값"), "muted"))
        legend.addStretch(1)
        wrap.addLayout(legend)

        holder = QWidget()
        holder.setMaximumWidth(900)
        holder.setLayout(wrap)
        wrap.setContentsMargins(0, 0, 0, 0)
        self.body.addWidget(holder)

    # ---------------- 언어 탭 ----------------
    def _lang_tab(self) -> None:
        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(label(t("언어"), "h"))
        box.addWidget(label(t("앱 화면에 쓸 언어를 고르세요. 게임 설정 파일은 바뀌지 않습니다."), "muted"))
        for code, name in LANGS:
            on = code == self.m.lang
            b = QPushButton()
            b.setObjectName("monitor")
            b.setCheckable(True)
            b.setChecked(on)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(48)
            b.setMaximumWidth(420)
            lay = QHBoxLayout(b)
            lay.setContentsMargins(14, 10, 14, 10)
            lay.setSpacing(12)
            radio = QWidget()
            radio.setFixedSize(14, 14)
            radio.setStyleSheet(f"border:2px solid {T.ACCENT if on else T.DIM};border-radius:7px;"
                                f"background:{T.ACCENT if on else 'transparent'};")
            lay.addWidget(radio)
            lay.addWidget(label(name, "h"), 1)
            code_lab = label(code.upper(), "key")
            lay.addWidget(code_lab)
            for w in b.findChildren(QWidget):
                w.setAttribute(Qt.WA_TransparentForMouseEvents)
            b.clicked.connect(lambda _=False, c=code: self.on_language(c) if c != self.m.lang else None)
            box.addWidget(b)
        self.body.addLayout(box)

    def render(self) -> None:
        clear(self.body)
        self.clear_btn.setVisible(bool(self.m.overrides) and self.tab in ("gfx", "frame"))
        self.adv.setVisible(self.tab in ("gfx", "frame"))
        if self.tab == "display":
            self._display_tab()
        elif self.tab == "lang":
            self._lang_tab()
        else:
            self._option_rows(self.tab)
        self.body.addStretch(1)
