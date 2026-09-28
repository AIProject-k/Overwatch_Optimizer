"""PC 사양 조회. 읽지 못한 값은 None으로 남기고 추측으로 채우지 않는다."""
from __future__ import annotations

import winreg
from dataclasses import dataclass, field

import psutil

_GPU_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
_VIRTUAL_HINTS = ("parsec", "virtual", "basic display", "remote", "indirect")


@dataclass
class Gpu:
    name: str
    driver: str | None
    vram_bytes: int | None
    virtual: bool


@dataclass
class HardwareSnapshot:
    cpu: str | None
    ram_bytes: int | None
    os_name: str | None  # 'Windows 11'
    os_build: int | None = None
    gpus: list[Gpu] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _reg(root, path: str, name: str):
    with winreg.OpenKey(root, path) as k:
        return winreg.QueryValueEx(k, name)[0]


def _read_gpus() -> list[Gpu]:
    gpus: list[Gpu] = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _GPU_CLASS) as base:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(base, i)
            except OSError:
                break
            i += 1
            if not sub.isdigit():
                continue
            path = f"{_GPU_CLASS}\\{sub}"
            try:
                name = _reg(winreg.HKEY_LOCAL_MACHINE, path, "DriverDesc")
            except OSError:
                continue
            driver = vram = None
            try:
                driver = _reg(winreg.HKEY_LOCAL_MACHINE, path, "DriverVersion")
            except OSError:
                pass
            try:
                vram = int(_reg(winreg.HKEY_LOCAL_MACHINE, path, "HardwareInformation.qwMemorySize"))
            except (OSError, ValueError, TypeError):
                pass
            virtual = any(h in name.lower() for h in _VIRTUAL_HINTS)
            gpus.append(Gpu(name, driver, vram, virtual))
    return gpus


def probe_hardware() -> HardwareSnapshot:
    snap = HardwareSnapshot(None, None, None)
    try:
        snap.cpu = " ".join(_reg(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                                 "ProcessorNameString").split())
    except OSError:
        snap.errors.append("CPU")
    try:
        snap.ram_bytes = psutil.virtual_memory().total
    except Exception:
        snap.errors.append("RAM")
    try:
        nt = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        build = int(_reg(winreg.HKEY_LOCAL_MACHINE, nt, "CurrentBuild"))
        # 윈도우 11도 ProductName은 'Windows 10'으로 남아 있어 빌드 번호로 구분
        snap.os_name = f"Windows {'11' if build >= 22000 else '10'}"
        snap.os_build = build
    except (OSError, ValueError):
        snap.errors.append("OS")
    try:
        snap.gpus = _read_gpus()
    except OSError:
        snap.errors.append("GPU")
    return snap


def pick_game_gpu(hw: HardwareSnapshot, game_gpu_name: str | None) -> Gpu | None:
    """게임 설정 파일에 기록된 GPU를 우선, 없으면 VRAM이 가장 큰 실제 GPU."""
    if game_gpu_name:
        for g in hw.gpus:
            if g.name.strip().lower() == game_gpu_name.strip().lower():
                return g
    real = [g for g in hw.gpus if not g.virtual]
    if not real:
        return None
    return max(real, key=lambda g: g.vram_bytes or 0)
