"""여러 화면에서 쓰는 작은 위젯들."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QDialog, QFrame, QHBoxLayout,
                               QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from . import theme as T
from ..i18n import t


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    lab.setWordWrap(wrap)
    return lab


def frame(name: str, layout_cls=QVBoxLayout, margins=(0, 0, 0, 0), spacing=0) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName(name)
    lay = layout_cls(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return f, lay


def clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


def dot(color: str, size: int = 6) -> QLabel:
    d = QLabel()
    d.setFixedSize(size, size)
    d.setStyleSheet(f"background:{color};border-radius:{size // 2}px;")
    return d


def chip(text: str, color: str, style: str = "solid") -> QLabel:
    c = QLabel(text)
    c.setStyleSheet(f"color:{color};border:1px {style} {color};border-radius:3px;"
                    f"padding:1px 7px;font-size:11px;")
    return c


def badge(kind: str) -> QLabel:
    text, color, style, tip = T.BADGES[kind]
    b = chip(t(text), color, style)
    b.setStyleSheet(b.styleSheet() + "font-size:10px;padding:1px 6px;")
    b.setToolTip(t(tip))
    return b


class SegButton(QPushButton):
    """세그먼트 버튼. cur=True면 아래에 '현재 파일 값' 점을 그린다."""

    def __init__(self, text: str, cur: bool = False):
        super().__init__(text)
        self.setObjectName("segBtn")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.cur = cur

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.cur:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.ON_ACCENT if self.isChecked() and self.property("accent") else T.SUB))
            p.drawEllipse(QRectF(self.width() / 2 - 2, self.height() - 8, 4, 4))


class Segmented(QFrame):
    picked = Signal(str)

    def __init__(self, accent: bool = False):
        super().__init__()
        self.setObjectName("seg")
        self.accent = accent
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(3, 3, 3, 3)
        self.lay.setSpacing(3)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

    def set_items(self, items: list[tuple[str, str]], selected: str | None,
                  current: str | None = None, enabled: bool = True) -> None:
        for b in self.group.buttons():
            self.group.removeButton(b)
        clear(self.lay)
        self.setProperty("dots", current is not None)
        self.style().polish(self)
        for text, value in items:
            b = SegButton(text, cur=current is not None and value == current)
            b.setProperty("accent", self.accent)
            b.setChecked(value == selected)
            b.setEnabled(enabled)
            b.clicked.connect(lambda _=False, v=value: self.picked.emit(v))
            self.group.addButton(b)
            self.lay.addWidget(b)


class Toggle(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(34, 18)

    def sizeHint(self):
        return QSize(34, 18)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        on = self.isChecked()
        track = T.ACCENT if on else T.LINE3
        if not self.isEnabled():
            track = T.LINE2
        p.setBrush(QColor(track))
        p.drawRoundedRect(QRectF(0, 0, 34, 18), 9, 9)
        p.setBrush(QColor(T.ON_ACCENT if on else T.SUB))
        p.drawEllipse(QRectF(18 if on else 2, 2, 14, 14))


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.hide()
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_msg(self, text: str, ms: int = 3200) -> None:
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 84)  # 하단 '마지막 적용' 줄 위
        self.raise_()
        self.show()
        self.timer.start(ms)


class _Dialog(QDialog):
    def __init__(self, parent, width: int):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setFixedWidth(width)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 24, 24, 24)
        self.lay.setSpacing(14)

    def buttons(self, cancel: str, ok: str, primary: bool = True) -> tuple[QPushButton, QPushButton]:
        row = QHBoxLayout()
        row.addStretch(1)
        c, o = QPushButton(cancel), QPushButton(ok)
        c.setObjectName("ghost")
        o.setObjectName("primary" if primary else "ghost")
        o.setMinimumHeight(36)
        c.setMinimumHeight(36)
        for b in (c, o):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        self.lay.addLayout(row)
        return c, o


class ConfirmDialog(_Dialog):
    def __init__(self, parent, title: str, rows: list[tuple[str, str]], body: str, ok: str):
        super().__init__(parent, 460)
        self.lay.addWidget(label(title, "h2"))
        box, bl = frame("card", margins=(14, 12, 14, 12), spacing=8)
        for k, v in rows:
            r = QHBoxLayout()
            r.addWidget(label(k, "muted"))
            r.addStretch(1)
            r.addWidget(label(v, "sub"))
            bl.addLayout(r)
        self.lay.addWidget(box)
        self.lay.addWidget(label(body, "sub", wrap=True))
        c, o = self.buttons(t("취소"), ok)
        c.clicked.connect(self.reject)
        o.clicked.connect(self.accept)


class KeepDialog(_Dialog):
    """화면 변경 뒤 15초 안에 '유지'를 누르지 않으면 되돌린다(검은 화면 대비)."""

    def __init__(self, parent, monitor: str, hz: int, seconds: int):
        super().__init__(parent, 440)
        self.left = self.total = seconds
        head = QHBoxLayout()
        head.addWidget(label(t("화면이 정상으로 보이나요?"), "h2"))
        head.addStretch(1)
        self.count = label(str(seconds))
        self.count.setStyleSheet(f"font-family:{T.MONO};font-size:28px;font-weight:600;color:{T.ACCENT};")
        head.addWidget(self.count)
        self.lay.addLayout(head)
        self.msg = label("", "sub", wrap=True)
        self.lay.addWidget(self.msg)
        self.bar = QProgressBar()
        self.bar.setRange(0, seconds)
        self.bar.setTextVisible(False)
        self.lay.addWidget(self.bar)
        c, o = self.buttons(t("되돌리기"), t("유지"))
        c.clicked.connect(self.reject)
        o.clicked.connect(self.accept)
        self.monitor, self.hz = monitor, hz
        self.timer = QTimer(self, interval=1000, timeout=self._tick)
        self._render()
        self.timer.start()

    def _render(self):
        self.count.setText(str(self.left))
        self.bar.setValue(self.left)
        self.msg.setText(t("{monitor}이(가) {hz}Hz로 바뀌었습니다. 응답이 없으면 {left}초 뒤 "
                           "이전 주사율과 이번에 바꾼 게임 설정으로 되돌립니다.",
                           monitor=self.monitor, hz=self.hz, left=self.left))

    def _tick(self):
        self.left -= 1
        if self.left <= 0:
            self.timer.stop()
            self.reject()
        else:
            self._render()
