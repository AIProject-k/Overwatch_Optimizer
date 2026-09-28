"""메인 창: 왼쪽 메뉴(홈·상세 설정) + 적용·복구·화면 변경 흐름."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QHBoxLayout, QMainWindow,
                               QPushButton, QStackedWidget, QWidget)

from . import theme as T
from .home import HomePage
from .model import AppModel
from .settings_page import SettingsPage
from .widgets import ConfirmDialog, KeepDialog, Toast, frame, label
from .. import __version__
from ..apply_service import (APP_DIR, ApplyError, StaleError, apply_writes, restore_first_original,
                             revert_last)
from ..display_service import KEEP_SECONDS, set_refresh, start_guard
from ..i18n import t
from ..recommender import OPTIONS_DATA

GUARD_TOKEN = APP_DIR / "display_guard.token"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1280, 820)
        self.setMinimumSize(1140, 740)
        self.m = AppModel()
        self.m.external_change.connect(
            lambda: self.toast.show_msg(t("설정 파일이 앱 밖에서 바뀌어 다시 읽고 계획을 갱신했습니다")))
        self._build(page=0)
        self.m.load()

    def _build(self, page: int, tab: str = "display") -> None:
        """화면 전체를 현재 언어로 만든다. 언어를 바꾸면 다시 부른다."""
        old = self.centralWidget()
        if old is not None:
            self.m.changed.disconnect(self.home.render)
            self.m.changed.disconnect(self.settings.render)
            old.deleteLater()
        self.setWindowTitle(t("OW Tune — 오버워치 그래픽·성능 최적화"))

        root = QWidget()
        root.setObjectName("root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        nav, nl = frame("nav", margins=(10, 16, 10, 16), spacing=2)
        nav.setFixedWidth(200)
        brand = QHBoxLayout()
        brand.setContentsMargins(12, 0, 0, 14)
        mark = QWidget()
        mark.setFixedSize(12, 12)
        mark.setStyleSheet(f"border:2px solid {T.ACCENT};border-radius:2px;")
        brand.addWidget(mark)
        brand.addSpacing(6)
        name = label("OW Tune")
        name.setStyleSheet("font-size:13px;font-weight:700;")
        brand.addWidget(name)
        brand.addStretch(1)
        nl.addLayout(brand)
        self.stack = QStackedWidget()
        self.home = HomePage(self.m, self.apply, self.restore)
        self.settings = SettingsPage(self.m, self.change_display_only, self.set_language, tab)
        group = QButtonGroup(root)
        for i, (k, text) in enumerate((("01", t("홈")), ("02", t("상세 설정")))):
            b = QPushButton(f"{k}    {text}")
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setChecked(i == page)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self.stack.setCurrentIndex(i))
            group.addButton(b)
            nl.addWidget(b)
        nl.addStretch(1)
        foot = label(t("v{ver} · 규칙 데이터 {rules}", ver=__version__, rules=OPTIONS_DATA["version"])
                     + "\n" + t("모든 기록은 이 PC에만 저장됩니다."))
        foot.setObjectName("navFoot")
        foot.setWordWrap(True)
        nl.addWidget(foot)
        lay.addWidget(nav)

        self.stack.addWidget(self.home)
        self.stack.addWidget(self.settings)
        self.stack.setCurrentIndex(page)
        lay.addWidget(self.stack, 1)
        self.toast = Toast(root)
        self.setCentralWidget(root)
        self.home.render()
        self.settings.render()

    def set_language(self, code: str) -> None:
        self.m.set_language(code)
        self._build(page=1, tab="lang")

    # ---------------- 화면 주사율 ----------------
    def _display(self, device: str, old: int, new: int) -> tuple[bool, str]:
        """주사율을 바꾸고 15초 유지 확인. (유지됨, 메시지)"""
        mon = next((x for x in self.m.monitors if x.device == device), None)
        name = mon.name if mon else device
        try:
            start_guard(device, old, GUARD_TOKEN)
        except Exception as e:
            return False, t("복구 감시를 시작하지 못해 화면을 바꾸지 않았습니다 · {e}", e=e)
        try:
            set_refresh(device, new)
        except Exception as e:
            GUARD_TOKEN.write_text("failed", encoding="utf-8")
            return False, t("주사율을 바꾸지 못했습니다 · {e}", e=e)
        kept = KeepDialog(self, name, new, KEEP_SECONDS).exec() == QDialog.Accepted
        if kept:
            GUARD_TOKEN.write_text("keep", encoding="utf-8")
            return True, t("{name} {hz}Hz 유지", name=name, hz=new)
        try:
            set_refresh(device, old)
            GUARD_TOKEN.write_text("reverted", encoding="utf-8")
            return False, t("{hz}Hz로 되돌렸습니다", hz=old)
        except Exception as e:  # 토큰을 그대로 두면 감시 프로세스가 다시 시도한다
            return False, t("되돌리기 실패 · 복구 감시가 곧 다시 시도합니다 ({e})", e=e)

    def change_display_only(self, device: str, old: int, new: int) -> None:
        _, msg = self._display(device, old, new)
        self.m.set_display_hz(new)
        self.m.refresh_monitors()
        self.toast.show_msg(msg)

    # ---------------- 원클릭 적용 ----------------
    def apply(self) -> None:
        m = self.m
        plan, snap = m.plan(), m.snap
        if not plan or not snap:
            return
        written = None
        if plan.writes:
            try:
                written = apply_writes(m.store, m.path, snap.hash, plan.writes,
                                       {"priority": m.priority, "target": m.target})
            except StaleError as e:
                m.reread()
                self.toast.show_msg(str(e))
                return
            except (ApplyError, OSError) as e:
                m.reread()
                self.toast.show_msg(t("적용하지 않았습니다 · {e}", e=e))
                return
            m.mode = None
            m.reread()

        msg = t("저장했습니다. 게임을 실행해 반영 여부를 확인하세요") if written else ""
        if plan.display_change:
            kept, dmsg = self._display(*plan.display_change)
            m.refresh_monitors()
            if not kept:
                if written:  # 화면 변경이 취소·실패하면 이번에 바꾼 게임 설정도 되돌린다
                    try:
                        revert_last(m.store, m.path, m.snap.hash)
                        dmsg += " · " + t("이번에 바꾼 게임 설정도 되돌렸습니다")
                    except (ApplyError, OSError) as e:
                        dmsg += " · " + t("게임 설정은 되돌리지 못함(부분 적용): {e}", e=e)
                    m.reread()
                self.toast.show_msg(dmsg, 5000)
                return
            msg = (msg + " · " if msg else "") + dmsg
        self.toast.show_msg(msg, 4500)

    # ---------------- 복구 ----------------
    def restore(self) -> None:
        m = self.m
        if not m.snap:
            return
        last = m.store.last_apply
        if last:
            dlg = ConfirmDialog(self, t("이번 변경 취소"),
                                [(t("기준"), t("직전 적용 전")), (t("대상 시점"), last["time"]),
                                 (t("범위"), t("이번에 바꾼 게임 설정 키 {n}개만", n=len(last["written"])))],
                                t("게임이 그사이 저장한 다른 설정은 그대로 둡니다. Windows 주사율은 바뀌지 않습니다."),
                                t("되돌리기"))
            if dlg.exec() != QDialog.Accepted:
                return
            try:
                drifted = revert_last(m.store, m.path, m.snap.hash)
            except (ApplyError, OSError) as e:
                m.reread()
                self.toast.show_msg(t("되돌리지 않았습니다 · {e}", e=e))
                return
            m.reread()
            extra = " · " + t("그사이 게임이 바꾼 값 {n}개도 이전 값으로", n=drifted) if drifted else ""
            self.toast.show_msg(t("이번 변경을 되돌렸습니다") + extra)
            return
        dlg = ConfirmDialog(self, t("최초 원본으로 복구"),
                            [(t("기준"), t("이 앱이 처음 쓰기 전 파일")), (t("범위"), t("게임 설정 파일 전체 교체"))],
                            t("그 뒤 게임에서 바꾼 설정도 모두 최초 상태로 돌아갑니다."), t("복구"))
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            restore_first_original(m.store, m.path, m.snap.hash)
            self.toast.show_msg(t("최초 원본으로 복구했습니다"))
        except (ApplyError, OSError) as e:
            self.toast.show_msg(t("복구하지 않았습니다 · {e}", e=e))
        m.reread()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OW Tune")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(T.QSS)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / "data" / "icon.ico")))
    w = MainWindow()
    w.show()
    return app.exec()
