"""모니터 조회와 Windows 주사율 변경.

- 목록·지원 모드: EnumDisplayDevices / EnumDisplaySettings
- 모니터 실제 이름·연결 방식·정확한 주사율: QueryDisplayConfig (CCD API)
- 변경: ChangeDisplaySettingsEx (CDS_TEST로 먼저 검사)
- 복구: 앱과 별개인 감시 프로세스(run_guard)가 제한 시간 뒤 원래 모드로 되돌린다
"""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

import win32api
import win32con

from .i18n import t

KEEP_SECONDS = 15
GUARD_SECONDS = KEEP_SECONDS + 5  # 앱의 자체 되돌리기가 먼저 돌도록 조금 더 길게


class DisplayError(Exception):
    pass


@dataclass
class Monitor:
    device: str  # \\.\DISPLAY2 — 이름이 같은 모니터도 이 경로로 구분
    name: str
    adapter: str
    connection: str | None
    primary: bool
    virtual: bool
    width: int
    height: int
    hz: int  # Windows가 모드 목록에서 쓰는 정수 값
    exact_hz: float | None  # 119.998 같은 실제 값(조회 가능할 때만)
    rates: list[int] = field(default_factory=list)  # 현재 해상도에서 지원되는 주사율


# ---------------- CCD API (QueryDisplayConfig) ----------------
class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]


class _PATH_SOURCE(ctypes.Structure):
    _fields_ = [("adapterId", _LUID), ("id", ctypes.c_uint32),
                ("modeInfoIdx", ctypes.c_uint32), ("statusFlags", ctypes.c_uint32)]


class _PATH_TARGET(ctypes.Structure):
    _fields_ = [("adapterId", _LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                ("outputTechnology", ctypes.c_uint32), ("rotation", ctypes.c_uint32),
                ("scaling", ctypes.c_uint32), ("refreshRate", _RATIONAL),
                ("scanLineOrdering", ctypes.c_uint32), ("targetAvailable", wintypes.BOOL),
                ("statusFlags", ctypes.c_uint32)]


class _PATH_INFO(ctypes.Structure):
    _fields_ = [("sourceInfo", _PATH_SOURCE), ("targetInfo", _PATH_TARGET), ("flags", ctypes.c_uint32)]


class _MODE_INFO(ctypes.Structure):
    # 내용은 쓰지 않으므로 union 부분은 크기만 맞춘다(총 64바이트)
    _fields_ = [("infoType", ctypes.c_uint32), ("id", ctypes.c_uint32),
                ("adapterId", _LUID), ("_union", ctypes.c_uint64 * 6)]


class _INFO_HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32),
                ("adapterId", _LUID), ("id", ctypes.c_uint32)]


class _SOURCE_NAME(ctypes.Structure):
    _fields_ = [("header", _INFO_HEADER), ("viewGdiDeviceName", wintypes.WCHAR * 32)]


class _TARGET_NAME(ctypes.Structure):
    _fields_ = [("header", _INFO_HEADER), ("flags", ctypes.c_uint32),
                ("outputTechnology", ctypes.c_uint32), ("edidManufactureId", ctypes.c_uint16),
                ("edidProductCodeId", ctypes.c_uint16), ("connectorInstance", ctypes.c_uint32),
                ("monitorFriendlyDeviceName", wintypes.WCHAR * 64),
                ("monitorDevicePath", wintypes.WCHAR * 128)]


_QDC_ONLY_ACTIVE_PATHS = 0x2
_GET_SOURCE_NAME, _GET_TARGET_NAME = 1, 2
_TECH = {4: "DVI", 5: "HDMI", 10: "DisplayPort", 11: "DisplayPort(내장)",
         15: "Miracast", 16: "간접 연결", 17: "가상"}  # 표시할 때 t()로 번역


def _ccd_targets() -> dict[str, dict]:
    """GDI 장치 이름(\\\\.\\DISPLAYn) → {name, connection, exact_hz, virtual}."""
    user32 = ctypes.windll.user32
    n_paths, n_modes = ctypes.c_uint32(), ctypes.c_uint32()
    if user32.GetDisplayConfigBufferSizes(_QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_paths),
                                          ctypes.byref(n_modes)):
        return {}
    paths = (_PATH_INFO * n_paths.value)()
    modes = (_MODE_INFO * n_modes.value)()
    if user32.QueryDisplayConfig(_QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_paths), paths,
                                 ctypes.byref(n_modes), modes, None):
        return {}
    out: dict[str, dict] = {}
    for p in paths[: n_paths.value]:
        src = _SOURCE_NAME()
        src.header.type, src.header.size = _GET_SOURCE_NAME, ctypes.sizeof(_SOURCE_NAME)
        src.header.adapterId, src.header.id = p.sourceInfo.adapterId, p.sourceInfo.id
        tgt = _TARGET_NAME()
        tgt.header.type, tgt.header.size = _GET_TARGET_NAME, ctypes.sizeof(_TARGET_NAME)
        tgt.header.adapterId, tgt.header.id = p.targetInfo.adapterId, p.targetInfo.id
        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(src)) or \
                user32.DisplayConfigGetDeviceInfo(ctypes.byref(tgt)):
            continue
        rr = p.targetInfo.refreshRate
        tech = p.targetInfo.outputTechnology
        out[src.viewGdiDeviceName] = {
            "name": tgt.monitorFriendlyDeviceName or None,
            "connection": t(_TECH[tech]) if tech in _TECH else None,
            "exact_hz": round(rr.Numerator / rr.Denominator, 3) if rr.Denominator else None,
            "virtual": tech == 17,
        }
    return out


# ---------------- 목록 ----------------
def _supported_rates(device: str, width: int, height: int, bpp: int) -> list[int]:
    rates: set[int] = set()
    i = 0
    while True:
        try:
            dm = win32api.EnumDisplaySettings(device, i)
        except Exception:
            break
        i += 1
        if dm.PelsWidth == width and dm.PelsHeight == height and dm.BitsPerPel == bpp \
                and dm.DisplayFrequency > 1:
            rates.add(dm.DisplayFrequency)
    return sorted(rates)


def list_monitors() -> list[Monitor]:
    try:
        ccd = _ccd_targets()
    except Exception:
        ccd = {}
    monitors: list[Monitor] = []
    i = 0
    while True:
        try:
            d = win32api.EnumDisplayDevices(None, i)
        except Exception:
            break
        i += 1
        if not d.StateFlags & win32con.DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            continue
        try:
            cur = win32api.EnumDisplaySettings(d.DeviceName, win32con.ENUM_CURRENT_SETTINGS)
        except Exception:
            continue
        info = ccd.get(d.DeviceName, {})
        adapter = d.DeviceString
        virtual = info.get("virtual", False) or any(
            h in adapter.lower() for h in ("parsec", "virtual", "indirect"))
        monitors.append(Monitor(
            device=d.DeviceName,
            name=info.get("name") or t("모니터 {n}", n=d.DeviceName.rsplit("DISPLAY", 1)[-1]),
            adapter=adapter,
            connection=info.get("connection"),
            primary=bool(d.StateFlags & win32con.DISPLAY_DEVICE_PRIMARY_DEVICE),
            virtual=virtual,
            width=cur.PelsWidth, height=cur.PelsHeight, hz=cur.DisplayFrequency,
            exact_hz=info.get("exact_hz"),
            rates=_supported_rates(d.DeviceName, cur.PelsWidth, cur.PelsHeight, cur.BitsPerPel),
        ))
    monitors.sort(key=lambda m: (not m.primary, m.device))
    return monitors


# ---------------- 변경 ----------------
_DISP_MSG = {
    win32con.DISP_CHANGE_BADMODE: "지원하지 않는 모드",
    win32con.DISP_CHANGE_FAILED: "드라이버가 변경을 거부",
    win32con.DISP_CHANGE_RESTART: "재부팅이 필요한 변경",
    win32con.DISP_CHANGE_BADPARAM: "잘못된 설정값",
}


def set_refresh(device: str, hz: int) -> None:
    """현재 해상도를 유지한 채 주사율만 바꾼다. 사전 검사에 실패하면 아무것도 안 바꾼다."""
    dm = win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS)
    if dm.DisplayFrequency == hz:
        return
    dm.DisplayFrequency = hz
    dm.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT | win32con.DM_DISPLAYFREQUENCY
    r = win32api.ChangeDisplaySettingsEx(device, dm, win32con.CDS_TEST)
    if r != win32con.DISP_CHANGE_SUCCESSFUL:
        raise DisplayError(t("{hz}Hz 사전 검사 실패: {why}", hz=hz, why=t(_DISP_MSG.get(r, str(r)))))
    r = win32api.ChangeDisplaySettingsEx(device, dm, win32con.CDS_UPDATEREGISTRY)
    if r != win32con.DISP_CHANGE_SUCCESSFUL:
        raise DisplayError(t("{hz}Hz 적용 실패: {why}", hz=hz, why=t(_DISP_MSG.get(r, str(r)))))


def current_hz(device: str) -> int:
    return win32api.EnumDisplaySettings(device, win32con.ENUM_CURRENT_SETTINGS).DisplayFrequency


# ---------------- 복구 감시 프로세스 ----------------
def start_guard(device: str, original_hz: int, token: Path) -> None:
    """앱이 멈추거나 꺼져도 GUARD_SECONDS 뒤 원래 주사율로 되돌리는 별도 프로세스."""
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text("pending", encoding="utf-8")
    args = json.dumps({"device": device, "hz": original_hz, "token": str(token)})
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--guard", args]
    else:
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        cmd = [str(pyw if pyw.exists() else exe), "-m", "owtune", "--guard", args]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, creationflags=flags, close_fds=True, cwd=Path(__file__).resolve().parents[1])


def run_guard(args_json: str) -> None:
    a = json.loads(args_json)
    token = Path(a["token"])
    deadline = time.monotonic() + GUARD_SECONDS
    while time.monotonic() < deadline:
        try:
            if token.read_text(encoding="utf-8").strip() != "pending":
                return  # 앱이 '유지' 또는 '되돌리기'를 처리함
        except OSError:
            return
        time.sleep(0.5)
    try:
        set_refresh(a["device"], int(a["hz"]))
        token.write_text("reverted-by-guard", encoding="utf-8")
    except Exception as e:  # 모니터 분리 등: 성공으로 표시하지 않고 기록만 남긴다
        token.write_text(f"guard-failed: {e}", encoding="utf-8")
