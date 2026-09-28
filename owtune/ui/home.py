"""01 홈 — 사양 요약, 목표·우선순위, 권장 변경, 원클릭 적용."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QButtonGroup, QGridLayout, QHBoxLayout, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import theme as T
from .model import AppModel
from .widgets import Segmented, Toggle, badge, chip, clear, dot, frame, label
from ..i18n import t
from ..recommender import MODES, OPTION_BY_ID, PRIORITIES, TARGETS, current_mode, gpu_tier, mode_label

GB = 1024 ** 3


def hz_text(m) -> str:
    if m.exact_hz and abs(m.exact_hz - m.hz) >= 0.01:
        return f"{m.exact_hz:g}Hz"
    return f"{m.hz}Hz"


def priority_name(pid: str) -> str:
    return t(next(n for p, n, _ in PRIORITIES if p == pid))


def apply_title(rec: dict) -> str:
    p = rec.get("profile")
    if isinstance(p, dict):
        return t("{p} · 목표 {n} FPS", p=priority_name(p["priority"]), n=p["target"])
    return rec.get("title", "")


def facts(model: AppModel) -> list[tuple[str, str, bool]]:
    """(항목 원문, 값, 60 FPS 원인 후보인지). 항목은 표시할 때 t()로 번역. 홈·상세 설정이 같이 쓴다."""
    m, r = model.monitor, (model.snap.render if model.snap else {})
    opt = OPTION_BY_ID
    out = []
    if m:
        out.append(("Windows 활성 주사율", hz_text(m), m.hz <= 60))
        out.append(("지원 주사율", " / ".join(map(str, m.rates)) + "Hz" if m.rates else t("미확인"), False))
    else:
        out.append(("Windows 활성 주사율", t("미확인"), False))
    fm = r.get(opt["frame_mode"].key)
    out.append(("프레임 속도 방식", opt["frame_mode"].label(fm), fm == "1"))
    out.append(("게임 FPS 상한", opt["fps_cap"].label(r.get(opt["fps_cap"].key)), False))
    vs = r.get(opt["vsync"].key)
    out.append(("수직 동기화", opt["vsync"].label(vs), vs == "1"))
    wr = r.get("WindowedRefresh")
    out.append(("창 모드 주사율 저장값", t("{v} · Windows 값을 따라감", v=wr) if wr else t("기본값"), False))
    return out


class HomePage(QWidget):
    def __init__(self, model: AppModel, on_apply, on_restore):
        super().__init__()
        self.m = model
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        self.strip, self.strip_lay = frame("strip", QHBoxLayout, spacing=1)
        root.addWidget(self.strip)

        mid = QHBoxLayout()
        mid.setSpacing(16)
        root.addLayout(mid, 1)

        # ---- 왼쪽: 목표 ----
        left = QWidget()
        left.setFixedWidth(330)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(18)
        mid.addWidget(left)

        box = QVBoxLayout()
        box.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label(t("목표 FPS"), "h"))
        head.addStretch(1)
        head.addWidget(label(t("게임이 그리는 프레임 수"), "muted"))
        box.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.target_group = QButtonGroup(self)
        self.target_btns: dict[int, QPushButton] = {}
        for v in TARGETS:
            b = QPushButton(str(v))
            b.setObjectName("pick")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=v: self._pick_target(v))
            self.target_group.addButton(b)
            self.target_btns[v] = b
            row.addWidget(b)
        self.custom = QLineEdit()
        self.custom.setPlaceholderText(t("직접"))
        self.custom.setAlignment(Qt.AlignCenter)
        self.custom.setFixedWidth(72)
        self.custom.setValidator(QIntValidator(30, 600, self))
        self.custom.setToolTip(t("30~600 사이 숫자 입력 후 Enter"))
        self.custom.editingFinished.connect(self._custom_target)
        row.addWidget(self.custom)
        box.addLayout(row)
        ll.addLayout(box)

        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(label(t("우선순위"), "h"))
        grid = QGridLayout()
        grid.setSpacing(6)
        self.prio_group = QButtonGroup(self)
        self.prio_btns: dict[str, tuple[QPushButton, object]] = {}
        for i, (pid, name, desc) in enumerate(PRIORITIES):
            b = QPushButton()
            b.setObjectName("prio")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(64)
            bl = QVBoxLayout(b)
            bl.setContentsMargins(12, 9, 12, 9)
            bl.setSpacing(3)
            n = label(t(name))
            d = label(t(desc), "sub", wrap=True)
            d.setStyleSheet("font-size:11px;")
            for w in (n, d):
                w.setAttribute(Qt.WA_TransparentForMouseEvents)
                bl.addWidget(w)
            b.clicked.connect(lambda _=False, p=pid: self.m.set_priority(p))
            self.prio_group.addButton(b)
            self.prio_btns[pid] = (b, n)
            grid.addWidget(b, i // 2, i % 2)
        box.addLayout(grid)
        ll.addLayout(box)

        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(label(t("화면 모드"), "h"))
        self.mode_seg = Segmented()
        self.mode_seg.picked.connect(lambda v: self.m.set_mode(v, self._cur_mode()))
        box.addWidget(self.mode_seg)
        ll.addLayout(box)

        sep, _ = frame("cardHead")
        sep.setFixedHeight(1)
        ll.addWidget(sep)
        box = QVBoxLayout()
        box.setSpacing(4)
        head = QHBoxLayout()
        head.addWidget(label(t("화면 상태"), "h"))
        head.addStretch(1)
        head.addWidget(label(t("Hz와 FPS는 별개 값입니다"), "muted"))
        box.addLayout(head)
        self.facts_lay = QVBoxLayout()
        self.facts_lay.setSpacing(0)
        box.addLayout(self.facts_lay)
        ll.addLayout(box)
        ll.addStretch(1)

        # ---- 오른쪽: 권장 변경 ----
        card, cl = frame("card")
        mid.addWidget(card, 1)
        head, hl = frame("cardHead", QHBoxLayout, (18, 14, 18, 14), 12)
        hl.addWidget(label(t("권장 변경"), "h2"))
        self.count = label("", "sub")
        self.count.setTextFormat(Qt.RichText)
        hl.addWidget(self.count)
        hl.addStretch(1)
        self.conf_lay = QHBoxLayout()
        hl.addLayout(self.conf_lay)
        cl.addWidget(head)
        self.notes = QVBoxLayout()
        self.notes.setContentsMargins(18, 0, 18, 0)
        self.notes.setSpacing(6)
        cl.addLayout(self.notes)
        cols, col_l = frame("cardHead", QHBoxLayout, (18, 8, 18, 8), 12)
        for text, w in ((t("항목"), 140), (t("현재 → 권장"), 190), (t("이유"), 0), (t("근거"), 96)):
            lab = label(text, "key")
            if w:
                lab.setFixedWidth(w)
            col_l.addWidget(lab, 0 if w else 1)
        cl.addWidget(cols)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        self.rows = QVBoxLayout(body)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        scroll.setWidget(body)
        cl.addWidget(scroll, 1)

        foot, fl = frame("cardFoot", QHBoxLayout, (18, 14, 18, 14), 12)
        self.toggle = Toggle()
        self.toggle.clicked.connect(lambda on: self.m.set_apply_display(on))
        fl.addWidget(self.toggle)
        tx = QVBoxLayout()
        tx.setSpacing(1)
        self.toggle_title = label("")
        self.toggle_title.setStyleSheet("font-size:12px;")
        tx.addWidget(self.toggle_title)
        tx.addWidget(label(t("변경 후 15초 안에 ‘유지’를 눌러야 확정됩니다"), "muted"))
        fl.addLayout(tx)
        fl.addStretch(1)
        self.apply_btn = QPushButton(t("권장 설정 적용"))
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.clicked.connect(on_apply)
        fl.addWidget(self.apply_btn)
        cl.addWidget(foot)

        # ---- 하단: 마지막 적용 ----
        bar, bl = frame("bar", QHBoxLayout, (16, 10, 16, 10), 16)
        bl.addWidget(label(t("마지막 적용"), "key"))
        self.last_title = label("")
        self.last_title.setStyleSheet("font-size:12px;")
        bl.addWidget(self.last_title)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        bl.addLayout(self.chips)
        bl.addStretch(1)
        self.restore_btn = QPushButton()
        self.restore_btn.setObjectName("ghost")
        self.restore_btn.setCursor(Qt.PointingHandCursor)
        self.restore_btn.clicked.connect(on_restore)
        bl.addWidget(self.restore_btn)
        root.addWidget(bar)

        model.changed.connect(self.render)

    # ---------------- 입력 ----------------
    def _pick_target(self, v: int) -> None:
        self.custom.clear()
        self.m.set_target(v)

    def _custom_target(self) -> None:
        s = self.custom.text().strip()
        if s.isdigit() and 30 <= int(s) <= 600:
            self.m.set_target(int(s), custom=True)

    def _cur_mode(self) -> str | None:
        return current_mode(self.m.snap.render) if self.m.snap else None

    # ---------------- 그리기 ----------------
    def _summary(self) -> None:
        clear(self.strip_lay)
        m, hw, g = self.m, self.m.hw, self.m.gpu
        cells = []
        if m.loading or not hw:
            cells = [("CPU", t("확인 중…"), "", T.DIM)] * 3
        else:
            ram = t("RAM {n} GB", n=round(hw.ram_bytes / GB)) if hw.ram_bytes else t("RAM 미확인")
            os_text = t("{os} (빌드 {build})", os=hw.os_name, build=hw.os_build) if hw.os_name else t("OS 미확인")
            cells.append(("CPU", hw.cpu or t("미확인"), f"{ram} · {os_text}", T.OK if hw.cpu else T.WARN))
            if g:
                vram = t("VRAM {n} GB", n=round(g.vram_bytes / GB)) if g.vram_bytes else t("VRAM 미확인")
                drv = t("드라이버 {v}", v=g.driver or t("미확인"))
                cells.append(("GPU", g.name, f"{vram} · {drv}", T.OK if gpu_tier(g.name) else T.WARN))
            else:
                cells.append(("GPU", t("미확인"), t("그래픽 카드 정보를 읽지 못함"), T.WARN))
            mon = m.monitor
            if mon:
                role = t("주 모니터") if mon.primary else t("보조 모니터")
                conn = f" · {mon.connection}" if mon.connection else ""
                cells.append((t("모니터"), f"{mon.name} · {mon.width}×{mon.height}",
                              t("{hz} 활성", hz=hz_text(mon)) + f"{conn} · {role}", T.OK))
            else:
                cells.append((t("모니터"), t("미확인"), t("활성 모니터를 찾지 못함"), T.WARN))
        if m.config_error:
            game = (t("게임"), "Overwatch", m.config_error, T.WARN)
        elif m.running:
            game = (t("게임"), "Overwatch", t("실행 중 · 설정 쓰기 대기"), T.WARN)
        elif m.snap:
            game = (t("게임"), "Overwatch", t("설정 파일 확인됨 · 실행 안 됨"), T.OK)
        else:
            game = (t("게임"), "Overwatch", t("확인 중…"), T.DIM)
        cells.append(game)
        for k, v, sub, color in cells:
            cell, cl = frame("cell", margins=(16, 12, 16, 12), spacing=4)
            cl.addWidget(label(k, "key"))
            val = label(v, "value")
            val.setToolTip(v)
            val.setMinimumWidth(0)
            cl.addWidget(val)
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(dot(color))
            s = label(sub, "sub")
            s.setToolTip(sub)
            row.addWidget(s, 1)
            cl.addLayout(row)
            self.strip_lay.addWidget(cell, 1)

    def _row(self, r) -> QWidget:
        w, lay = frame("row", QHBoxLayout, (18, 8, 18, 8), 12)
        w.setMinimumHeight(40)
        name = label(r.name, wrap=True)
        name.setFixedWidth(140)
        name.setStyleSheet(f"font-size:13px;font-weight:500;color:{T.TEXT if r.changed else T.MUTED};")
        lay.addWidget(name)
        cr = QHBoxLayout()
        cr.setSpacing(8)
        cur = label(r.cur, "mono")
        cur.setStyleSheet(f"color:{T.SUB};")
        cr.addWidget(cur)
        arrow = label("→", "mono")
        arrow.setStyleSheet(f"color:{T.DIM};")
        cr.addWidget(arrow)
        rec = label(r.rec, "mono")
        rec.setStyleSheet(f"color:{T.ACCENT if r.changed else T.MUTED};font-weight:600;")
        cr.addWidget(rec)
        cr.addStretch(1)
        holder = QWidget()
        holder.setFixedWidth(190)
        holder.setLayout(cr)
        cr.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(holder)
        lay.addWidget(label(r.why, "sub", wrap=True), 1)
        bh = QHBoxLayout()
        bh.addStretch(1)
        bh.addWidget(badge(r.badge))
        bw = QWidget()
        bw.setFixedWidth(96)
        bw.setLayout(bh)
        bh.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(bw)
        return w

    def _note(self, html: str, warn: bool = False) -> QWidget:
        f, fl = frame("warnStrip" if warn else "row", QHBoxLayout, (12, 8, 12, 8))
        lab = label(html, wrap=True)
        lab.setTextFormat(Qt.RichText)
        if not warn:
            lab.setStyleSheet(f"color:{T.SUB};font-size:12px;")
        fl.addWidget(lab)
        return f

    def render(self) -> None:
        m = self.m
        self._summary()

        for v, b in self.target_btns.items():
            b.setChecked(not m.custom_target and m.target == v)
        if m.custom_target and not self.custom.hasFocus():
            self.custom.setText(str(m.target))
        self.custom.setProperty("active", m.custom_target)
        self.custom.style().polish(self.custom)
        for pid, (b, n) in self.prio_btns.items():
            on = pid == m.priority
            b.setChecked(on)
            n.setStyleSheet(f"font-size:13px;font-weight:600;color:{T.ACCENT if on else T.TEXT};")

        cur = self._cur_mode()
        self.mode_seg.set_items([(t(c["label"]), c["id"]) for c in MODES["choices"]],
                                m.mode or cur, current=cur, enabled=m.snap is not None)
        self.mode_seg.setToolTip(t("현재 파일 값: {mode} (WindowMode 대응은 커뮤니티 근거)", mode=mode_label(cur)))

        clear(self.facts_lay)
        flagged = False
        for k, v, warn in facts(m):
            row = QHBoxLayout()
            row.addWidget(label(t(k), "sub"))
            row.addStretch(1)
            val = label(v, "mono")
            val.setStyleSheet(f"color:{T.WARN if warn else T.TEXT};")
            row.addWidget(val)
            w = QWidget()
            w.setLayout(row)
            row.setContentsMargins(0, 3, 0, 3)
            self.facts_lay.addWidget(w)
            flagged |= warn
        if flagged:
            self.facts_lay.addWidget(label(t("노란 값은 FPS를 모니터 Hz에 묶을 수 있는 설정입니다."), "muted", wrap=True))

        plan = m.plan()
        clear(self.notes)
        clear(self.rows)
        clear(self.conf_lay)
        if m.loading:
            self.notes.addWidget(self._note(t("PC와 모니터를 확인하는 중…")))
        if m.config_error:
            self.notes.addWidget(self._note(
                f"<b style='color:{T.WARN}'>{t('설정 파일 확인 필요')}</b> · {m.config_error}", True))
        if m.running:
            self.notes.addWidget(self._note(
                f"<b style='color:{T.WARN}'>{t('게임 종료 후 적용')}</b> · "
                + t("게임을 강제 종료하지 않습니다. 게임을 끄면 설정 파일을 다시 읽고 계획을 갱신합니다."), True))
        if plan and plan.tier is None:
            self.notes.addWidget(self._note(
                f"<b style='color:{T.TEXT}'>{t('등급표에 없는 GPU')}</b> · "
                + t("보수적인 값을 제안합니다. 예상 FPS는 표시하지 않습니다.")))
        self.notes.setContentsMargins(*((18, 10, 18, 10) if self.notes.count() else (0, 0, 0, 0)))

        n_changed = plan.n_changed if plan else 0
        if plan:
            for r in sorted(plan.rows, key=lambda r: not r.changed):
                self.rows.addWidget(self._row(r))
            num = f"<span style='font-family:Consolas;color:{T.ACCENT}'>{n_changed}</span>"
            self.count.setText(t("{n}건 변경 · {k}건 유지", n=num, k=len(plan.rows) - n_changed))
            known = plan.tier is not None
            self.conf_lay.addWidget(chip(t("추천 신뢰도 보통 · 실측 전") if known else t("추천 신뢰도 낮음"),
                                         T.SUB if known else T.WARN))
        else:
            self.count.setText("")
        self.rows.addStretch(1)

        mon, hz = m.monitor, m.display_hz
        can_display = bool(mon and not mon.virtual and hz)
        self.toggle.setEnabled(can_display)
        self.toggle.setChecked(m.apply_display and can_display)
        if not can_display:
            self.toggle_title.setText(t("Windows 주사율 변경 · 지원 모드 미확인"))
        elif hz == mon.hz:
            self.toggle_title.setText(t("Windows 주사율도 변경 · 이미 {hz}Hz", hz=hz))
        else:
            self.toggle_title.setText(t("Windows 주사율도 변경")
                                      + f" · <span style='font-family:Consolas'>{mon.hz} → {hz}Hz</span>")

        text, enabled = t("권장 설정 적용"), True
        if m.loading or not plan:
            text, enabled = (t("설정 파일 확인 필요") if m.config_error else t("확인 중…")), False
        elif m.running:
            text, enabled = t("게임 종료 대기"), False
        elif n_changed == 0:
            text, enabled = t("변경할 항목 없음"), False
        self.apply_btn.setText(text)
        self.apply_btn.setEnabled(enabled)

        clear(self.chips)
        last, refl = m.store.last_apply, m.reflection
        if last:
            self.last_title.setText(f"{last['time']} · {apply_title(last)}")
            self.chips.addWidget(chip(t("저장 완료"), T.OK))
            if refl and refl.game_saved:
                total = len(last["written"])
                self.chips.addWidget(chip(t("게임 저장 후 유지 {n}/{total}", n=len(refl.kept), total=total), T.OK))
                if refl.removed:
                    c = chip(t("게임이 지움 {n}", n=len(refl.removed)), T.WARN)
                    c.setToolTip(t("기본값이라 기록하지 않았거나 게임이 인식하지 못한 키:") + "\n" + "\n".join(refl.removed))
                    self.chips.addWidget(c)
                if refl.changed:
                    c = chip(t("게임이 바꿈 {n}", n=len(refl.changed)), T.WARN)
                    c.setToolTip("\n".join(refl.changed))
                    self.chips.addWidget(c)
            else:
                c = chip(t("게임 반영 미확인"), T.SUB, "dashed")
                c.setToolTip(t("게임을 한 번 실행하고 끄면, 쓴 값이 남아 있는지 여기서 보여줍니다."))
                self.chips.addWidget(c)
            self.restore_btn.setText(t("이번 변경 취소"))
            self.restore_btn.show()
        else:
            self.last_title.setText(t("이 앱에서 적용한 기록 없음"))
            if m.store.first_original.exists():
                self.chips.addWidget(chip(t("최초 원본 백업 있음"), T.OK))
                self.restore_btn.setText(t("최초 원본으로 복구"))
                self.restore_btn.show()
            else:
                self.restore_btn.hide()
        self.restore_btn.setEnabled(not m.running and m.snap is not None)
