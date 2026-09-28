"""오버워치 Settings_v0.ini 찾기·읽기·최소 변경 편집.

파일 전체를 재직렬화하지 않고, 바꿀 줄만 고친다.
BOM·줄바꿈(CRLF)·다른 섹션·공백은 그대로 둔다.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psutil

from .i18n import t

GAME_PROCESS_NAMES = {"overwatch.exe"}
SETTINGS_FILE_NAME = "Settings_v0.ini"

_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_KEY_RE = re.compile(r'^(\s*)([A-Za-z0-9_.]+)(\s*=\s*)"([^"]*)"(\s*)$')
_BOM = b"\xef\xbb\xbf"


class ConfigError(Exception):
    """파일 구조가 모호하거나 예상과 달라 자동 편집을 멈춰야 할 때."""


def documents_dir() -> Path:
    """OneDrive 이동·폴더 리디렉션을 반영한 실제 문서 폴더."""
    try:
        from win32com.shell import shell, shellcon

        return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Documents))
    except Exception:
        return Path.home() / "Documents"


def default_settings_path() -> Path:
    if os.environ.get("OWTUNE_SETTINGS"):  # 테스트용: 실제 게임 파일 대신 사본을 쓸 때
        return Path(os.environ["OWTUNE_SETTINGS"])
    return documents_dir() / "Overwatch" / "Settings" / SETTINGS_FILE_NAME


def game_running() -> bool:
    for p in psutil.process_iter(["name"]):
        name = (p.info.get("name") or "").lower()
        if name in GAME_PROCESS_NAMES:
            return True
    return False


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass
class _Section:
    name: str
    header: int  # 헤더 줄 번호
    end: int  # 다음 섹션 헤더 줄 번호(또는 파일 끝)
    keys: dict[str, list[int]]  # 키 → 줄 번호들


class IniDoc:
    """줄 단위로 들고 있다가 필요한 줄만 바꾸는 INI 문서."""

    def __init__(self, raw: bytes):
        self.bom = raw.startswith(_BOM)
        text = raw[len(_BOM):] if self.bom else raw
        try:
            decoded = text.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ConfigError(t("설정 파일을 UTF-8로 읽을 수 없습니다")) from e
        self.newline = "\r\n" if "\r\n" in decoded else "\n"
        self.trailing_newline = decoded.endswith(self.newline)
        body = decoded[: -len(self.newline)] if self.trailing_newline else decoded
        self.lines: list[str] = body.split(self.newline) if body else []

    # ---- 구조 파악 ----
    def _sections(self) -> list[_Section]:
        out: list[_Section] = []
        for i, line in enumerate(self.lines):
            m = _SECTION_RE.match(line)
            if m:
                if out:
                    out[-1].end = i
                out.append(_Section(m.group(1), i, len(self.lines), {}))
            elif out:
                km = _KEY_RE.match(line)
                if km:
                    out[-1].keys.setdefault(km.group(2), []).append(i)
        return out

    def _section(self, name: str) -> _Section:
        found = [s for s in self._sections() if s.name == name]
        if not found:
            raise ConfigError(t("[{name}] 섹션이 없습니다", name=name))
        if len(found) > 1:
            raise ConfigError(t("[{name}] 섹션이 여러 개라 자동 편집을 멈춥니다", name=name))
        sec = found[0]
        dup = [k for k, idx in sec.keys.items() if len(idx) > 1]
        if dup:
            raise ConfigError(t("중복 키({keys})가 있어 자동 편집을 멈춥니다", keys=", ".join(dup)))
        return sec

    def section_names(self) -> list[str]:
        return [s.name for s in self._sections()]

    def find_section(self, prefix: str) -> str:
        """'Render.' 처럼 버전 번호가 붙는 섹션을 찾는다. 패치로 번호가 바뀌어도 동작."""
        names = [n for n in self.section_names() if n.startswith(prefix)]
        if len(names) != 1:
            raise ConfigError(t("'{prefix}*' 섹션을 하나로 특정할 수 없습니다 ({n}개)", prefix=prefix, n=len(names)))
        return names[0]

    def values(self, section: str) -> dict[str, str]:
        sec = self._section(section)
        return {k: _KEY_RE.match(self.lines[idx[0]]).group(4) for k, idx in sec.keys.items()}

    def get(self, section: str, key: str) -> str | None:
        return self.values(section).get(key)

    # ---- 편집 ----
    def set(self, section: str, key: str, value: str) -> None:
        if '"' in value or "\n" in value or "\r" in value:
            raise ConfigError(t("허용되지 않는 값입니다: {value}", value=repr(value)))
        sec = self._section(section)
        if key in sec.keys:
            i = sec.keys[key][0]
            m = _KEY_RE.match(self.lines[i])
            self.lines[i] = f'{m.group(1)}{key}{m.group(3)}"{value}"{m.group(5)}'
            return
        # 게임은 키를 대소문자 무시 정렬로 저장한다 → 같은 규칙으로 끼워 넣는다
        key_lines = sorted(i for idx in sec.keys.values() for i in idx)
        insert_at = sec.header + 1
        for i in key_lines:
            if _KEY_RE.match(self.lines[i]).group(2).lower() < key.lower():
                insert_at = i + 1
        self.lines.insert(insert_at, f'{key} = "{value}"')

    def remove(self, section: str, key: str) -> None:
        sec = self._section(section)
        if key in sec.keys:
            del self.lines[sec.keys[key][0]]

    def to_bytes(self) -> bytes:
        text = self.newline.join(self.lines)
        if self.trailing_newline:
            text += self.newline
        data = text.encode("utf-8")
        return _BOM + data if self.bom else data


@dataclass
class ConfigSnapshot:
    path: Path
    raw: bytes
    hash: str
    doc: IniDoc
    render_section: str
    render: dict[str, str]  # [Render.*] 키 → 값
    gpu_name: str | None  # 게임이 기록한 사용 GPU


def read_snapshot(path: Path) -> ConfigSnapshot:
    raw = path.read_bytes()
    doc = IniDoc(raw)
    render_section = doc.find_section("Render.")
    gpu_name = None
    try:
        gpu_name = doc.get(doc.find_section("GPU."), "GPUName")
    except ConfigError:
        pass
    return ConfigSnapshot(path, raw, sha256(raw), doc, render_section,
                          doc.values(render_section), gpu_name)
