"""백업 → 충돌 검사 → 임시 파일 작성·재파싱 → 교체 → 재읽기.

UI·추천 모듈은 파일을 직접 쓰지 않고 여기를 거친다.
백업은 화면 없이 조용히 남기고, 홈의 '이전 설정으로 복구'에만 쓴다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .i18n import t
from .ow_config import ConfigError, ConfigSnapshot, IniDoc, game_running, read_snapshot, sha256

APP_DIR = Path(os.environ.get("OWTUNE_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OWTune")
KEEP_BACKUPS = 10


class ApplyError(Exception):
    pass


class StaleError(ApplyError):
    """계획을 만든 뒤 파일이 바뀜 → 오래된 계획을 적용하지 않는다."""


# ---------------- 앱 상태(state.json) ----------------
class Store:
    def __init__(self, app_dir: Path = APP_DIR):
        self.dir = app_dir
        self.file = app_dir / "state.json"
        try:
            self.data: dict = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.file)

    @property
    def confirmed(self) -> set[str]:
        return set(self.data.get("confirmed", []))

    @property
    def last_apply(self) -> dict | None:
        return self.data.get("last_apply")

    @property
    def first_original(self) -> Path:
        return self.dir / "backups" / "first_original.ini"


# ---------------- 내부 단계 ----------------
def _backup(store: Store, raw: bytes) -> Path:
    bdir = store.dir / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    if not store.first_original.exists():  # 최초 원본은 항상 보존
        store.first_original.write_bytes(raw)
    path = bdir / f"Settings_v0_{datetime.now():%Y%m%d-%H%M%S-%f}.ini"
    path.write_bytes(raw)
    if path.read_bytes() != raw:
        raise ApplyError(t("백업 확인 실패 · 적용하지 않았습니다"))
    for old in sorted(bdir.glob("Settings_v0_*.ini"))[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    return path


def _prepare(path: Path, expected_hash: str,
             edits: dict[str, str | None]) -> tuple[ConfigSnapshot, bytes]:
    """edits(키 → 새 값, None이면 줄 삭제)를 반영한 새 파일 내용을 만든다. 아직 쓰지 않음."""
    if game_running():
        raise ApplyError(t("게임 실행 중에는 설정 파일을 쓰지 않습니다"))
    try:
        snap = read_snapshot(path)
        if snap.hash != expected_hash:
            raise StaleError(t("설정 파일이 바뀌어 계획을 새로 만들었습니다. 다시 확인해 주세요"))
        for k, v in edits.items():
            if v is None:
                snap.doc.remove(snap.render_section, k)
            else:
                snap.doc.set(snap.render_section, k, v)
    except (OSError, ConfigError) as e:
        raise ApplyError(str(e)) from e
    return snap, snap.doc.to_bytes()


def _safe_write(path: Path, expected_hash: str, new: bytes, section: str,
                expect: dict[str, str | None]) -> None:
    tmp = path.with_name(path.name + ".owtune-tmp")
    tmp.write_bytes(new)
    try:
        check = IniDoc(tmp.read_bytes()).values(section)
        if any(check.get(k) != v for k, v in expect.items()):
            raise ApplyError(t("임시 파일 재파싱 결과가 계획과 다릅니다"))
        if game_running():
            raise ApplyError(t("게임이 실행돼 적용을 멈췄습니다"))
        if sha256(path.read_bytes()) != expected_hash:
            raise StaleError(t("적용 직전 설정 파일이 바뀌었습니다"))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    after = IniDoc(path.read_bytes()).values(section)
    if any(after.get(k) != v for k, v in expect.items()):
        raise ApplyError(t("저장 후 다시 읽은 값이 계획과 다릅니다"))


# ---------------- 공개 기능 ----------------
def apply_writes(store: Store, path: Path, expected_hash: str, writes: dict[str, str],
                 profile: dict) -> dict:
    """계획의 키들을 쓰고 적용 기록(last_apply)을 남긴다."""
    snap, new = _prepare(path, expected_hash, writes)
    if new == snap.raw:
        raise ApplyError(t("이미 같은 값이라 쓰지 않았습니다"))
    backup = _backup(store, snap.raw)
    _safe_write(path, expected_hash, new, snap.render_section, writes)
    rec = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "profile": profile,  # {"priority": ..., "target": ...}
        "written": writes,
        "previous": {k: snap.render.get(k) for k in writes},
        "hash_after": sha256(path.read_bytes()),
        "backup": str(backup),
    }
    store.data["last_apply"] = rec
    store.save()
    return rec


def revert_last(store: Store, path: Path, expected_hash: str) -> int:
    """마지막 적용에서 바꾼 키만 이전 값으로 되돌린다. 게임이 그사이 바꾼 다른 키는 건드리지 않는다.
    반환: 적용 뒤 게임·외부에서 값이 바뀌어 있던 키 수."""
    last = store.last_apply
    if not last:
        raise ApplyError(t("되돌릴 적용 기록이 없습니다"))
    snap, new = _prepare(path, expected_hash, last["previous"])
    drifted = sum(snap.render.get(k) != v for k, v in last["written"].items())
    if new != snap.raw:
        _backup(store, snap.raw)
        _safe_write(path, expected_hash, new, snap.render_section, last["previous"])
    store.data.pop("last_apply", None)
    store.save()
    return drifted


def restore_first_original(store: Store, path: Path, expected_hash: str) -> None:
    """앱이 처음 쓰기 전의 파일 전체로 되돌린다(적용 기록이 없을 때의 비상 복구)."""
    if not store.first_original.exists():
        raise ApplyError(t("최초 원본 백업이 없습니다"))
    snap, _ = _prepare(path, expected_hash, {})
    original = store.first_original.read_bytes()
    if original == snap.raw:
        raise ApplyError(t("이미 최초 원본과 같습니다"))
    _backup(store, snap.raw)
    _safe_write(path, expected_hash, original, snap.render_section, {})


# ---------------- 게임 반영 확인 ----------------
@dataclass
class Reflection:
    game_saved: bool  # 적용 뒤 게임이 파일을 다시 저장했는지
    kept: list[str]
    changed: list[str]
    removed: list[str]


def check_reflection(store: Store, render: dict[str, str], current_hash: str) -> Reflection | None:
    """적용 뒤 게임이 파일을 다시 저장했다면, 쓴 값이 살아남았는지 비교한다.
    살아남은 키는 '이 PC에서 유지 확인'으로 기록한다(게임 UI와의 대응까지 증명하진 않음)."""
    last = store.last_apply
    if not last:
        return None
    if current_hash == last["hash_after"]:
        return Reflection(False, [], [], [])
    kept, changed, removed = [], [], []
    for k, v in last["written"].items():
        now = render.get(k)
        (kept if now == v else removed if now is None else changed).append(k)
    if kept and not set(kept) <= store.confirmed:
        store.data["confirmed"] = sorted(store.confirmed | set(kept))
        store.save()
    return Reflection(True, kept, changed, removed)
