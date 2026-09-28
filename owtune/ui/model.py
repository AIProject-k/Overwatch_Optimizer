"""화면이 공유하는 상태. 탐지 결과·사용자 목표·계획을 들고 있고, 바뀌면 changed를 보낸다."""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from ..apply_service import Reflection, Store, check_reflection
from ..display_service import Monitor, list_monitors
from ..i18n import set_lang, t
from ..ow_config import ConfigError, ConfigSnapshot, default_settings_path, game_running, read_snapshot
from ..recommender import Goal, Plan, build_plan, suggest_hz
from ..system_probe import Gpu, HardwareSnapshot, pick_game_gpu, probe_hardware

POLL_MS = 2000


class _Relay(QObject):
    done = Signal(object)


_alive: set[_Relay] = set()  # 결과가 전달될 때까지 relay가 사라지지 않게 붙잡아 둔다


def run_bg(fn, cb) -> None:
    """fn을 작업 스레드에서 돌리고 결과(또는 예외)를 UI 스레드의 cb로 넘긴다."""
    relay = _Relay()
    _alive.add(relay)

    def deliver(res):
        _alive.discard(relay)
        cb(res)

    def work():
        try:
            res = fn()
        except Exception as e:  # UI에서 실패로 표시
            res = e
        relay.done.emit(res)

    relay.done.connect(deliver)
    threading.Thread(target=work, daemon=True).start()


class AppModel(QObject):
    changed = Signal()
    external_change = Signal()  # 앱 밖(게임 등)에서 설정 파일이 바뀜

    def __init__(self):
        super().__init__()
        self.store = Store()
        p = self.store.data.get("prefs", {})
        self.target: int = p.get("target", 120)
        self.custom_target: bool = p.get("custom", False)
        self.priority: str = p.get("priority", "balance")
        self.monitor_device: str | None = p.get("monitor")
        self.apply_display: bool = p.get("apply_display", False)
        self.overrides: dict[str, str] = p.get("overrides", {})
        self.lang: str = p.get("lang", "ko")
        set_lang(self.lang)
        self.mode: str | None = None  # 이번 계획에서만 쓰는 화면 모드 선택
        self.display_hz_manual: int | None = None

        self.path = default_settings_path()
        self.hw: HardwareSnapshot | None = None
        self.monitors: list[Monitor] = []
        self.snap: ConfigSnapshot | None = None
        self.config_error: str | None = None
        self.running = False
        self.reflection: Reflection | None = None
        self.loading = True
        self._sig = None
        self._tick = 0
        self.timer = QTimer(self, interval=POLL_MS, timeout=self.poll)

    # ---------------- 탐지 ----------------
    def load(self) -> None:
        self.loading = True
        self.changed.emit()
        run_bg(lambda: (probe_hardware(), list_monitors()), self._loaded)

    def _loaded(self, res) -> None:
        self.loading = False
        if isinstance(res, Exception):
            self.hw = HardwareSnapshot(None, None, None, errors=[str(res)])
        else:
            self.hw, self.monitors = res
        self.running = game_running()
        self.reread()
        self.timer.start()

    def reread(self) -> bool:
        """설정 파일을 다시 읽는다. 내용이 바뀌었으면 True."""
        old = self.snap.hash if self.snap else None
        try:
            st = os.stat(self.path)
            self._sig = (st.st_mtime_ns, st.st_size)
            self.snap = read_snapshot(self.path)
            self.config_error = None
            self.reflection = check_reflection(self.store, self.snap.render, self.snap.hash)
        except FileNotFoundError:
            self.snap, self._sig = None, None
            self.config_error = t("설정 파일 없음 · 게임을 한 번 실행한 뒤 다시 여세요")
        except (OSError, ConfigError) as e:
            self.snap = None
            self.config_error = t("설정 파일을 읽지 못함 · {e}", e=e)
        self.changed.emit()
        return old is not None and self.snap is not None and self.snap.hash != old

    def refresh_monitors(self) -> None:
        try:
            self.monitors = list_monitors()
        except Exception:
            pass
        self.changed.emit()

    def poll(self) -> None:
        """게임 실행 상태·파일 변경을 확인한다."""
        self._tick += 1
        try:
            st = os.stat(self.path)
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            sig = None
        if sig != self._sig and self.reread():
            self.external_change.emit()
        if self._tick % 5 == 0:  # Windows 설정에서 주사율을 바꾼 경우도 반영
            try:
                self.monitors = list_monitors()
            except Exception:
                pass
        running = game_running()
        if running != self.running or self._tick % 5 == 0:
            self.running = running
            self.changed.emit()

    # ---------------- 파생값 ----------------
    @property
    def monitor(self) -> Monitor | None:
        for m in self.monitors:
            if m.device == self.monitor_device:
                return m
        real = [m for m in self.monitors if not m.virtual]
        return real[0] if real else None

    @property
    def gpu(self) -> Gpu | None:
        if not self.hw:
            return None
        return pick_game_gpu(self.hw, self.snap.gpu_name if self.snap else None)

    @property
    def display_hz(self) -> int | None:
        m = self.monitor
        if m and self.display_hz_manual in m.rates:
            return self.display_hz_manual
        return suggest_hz(m, self.target)

    def goal(self) -> Goal:
        return Goal(self.target, self.priority, self.mode, self.monitor,
                    self.apply_display, self.display_hz, dict(self.overrides))

    def plan(self) -> Plan | None:
        if not self.snap:
            return None
        g = self.gpu
        return build_plan(self.snap.render, self.goal(), g.name if g else None,
                          g.vram_bytes if g else None, self.store.confirmed)

    # ---------------- 사용자 입력 ----------------
    def _save_prefs(self) -> None:
        self.store.data["prefs"] = {
            "target": self.target, "custom": self.custom_target, "priority": self.priority,
            "monitor": self.monitor_device, "apply_display": self.apply_display,
            "overrides": self.overrides, "lang": self.lang,
        }
        try:
            self.store.save()
        except OSError:
            pass
        self.changed.emit()

    def set_target(self, fps: int, custom: bool = False) -> None:
        self.target, self.custom_target = fps, custom
        self._save_prefs()

    def set_priority(self, pid: str) -> None:
        self.priority = pid
        self._save_prefs()

    def set_monitor(self, device: str) -> None:
        self.monitor_device, self.display_hz_manual = device, None
        self._save_prefs()

    def set_apply_display(self, on: bool) -> None:
        self.apply_display = on
        self._save_prefs()

    def set_display_hz(self, hz: int) -> None:
        self.display_hz_manual = hz
        self.changed.emit()

    def set_mode(self, mode_id: str, current: str | None) -> None:
        self.mode = None if mode_id == current else mode_id
        self.changed.emit()

    def set_override(self, opt_id: str, value: str | None) -> None:
        if value is None:
            self.overrides.pop(opt_id, None)
        else:
            self.overrides[opt_id] = value
        self._save_prefs()

    def set_language(self, code: str) -> None:
        """문구가 들어간 탐지 결과(모니터 이름·오류)도 새 언어로 다시 만든다."""
        self.lang = code
        set_lang(code)
        self._save_prefs()
        self.refresh_monitors()
        self.reread()

    def clear_overrides(self) -> None:
        self.overrides.clear()
        self._save_prefs()
