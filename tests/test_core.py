import pytest

from owtune import apply_service as aps
from owtune import ow_config
from owtune.display_service import Monitor
from owtune.ow_config import ConfigError, IniDoc, read_snapshot, sha256
from owtune.recommender import Goal, build_plan, gpu_tier, suggest_hz

# 이 PC 실제 파일과 같은 형태(CRLF, 키 대소문자 무시 정렬)
PROFILE = {"priority": "balance", "target": 120}

SAMPLE = (
    '[GPU.6]\r\nGPUName = "NVIDIA GeForce RTX 4070 SUPER"\r\n\r\n'
    '[Render.13]\r\nFullScreenRefresh = "144"\r\nGFXPresetLevel = "3"\r\n'
    'ShaderQuality = "3"\r\nWindowedFullscreen = "1"\r\nWindowedRefresh = "120"\r\n'
    'WindowMode = "1"\r\n\r\n[Sound.3]\r\nLocalMicMute = "0"\r\n\r\n'
).encode()


@pytest.fixture(autouse=True)
def no_game(monkeypatch):
    monkeypatch.setattr(ow_config, "game_running", lambda: False)
    monkeypatch.setattr(aps, "game_running", lambda: False)


# ---------- INI 편집 ----------
def test_roundtrip_is_byte_identical():
    assert IniDoc(SAMPLE).to_bytes() == SAMPLE
    bom = b"\xef\xbb\xbf" + SAMPLE.replace(b"\r\n", b"\n")
    assert IniDoc(bom).to_bytes() == bom


def test_set_existing_changes_only_that_line():
    doc = IniDoc(SAMPLE)
    doc.set("Render.13", "GFXPresetLevel", "4")
    out = doc.to_bytes()
    assert out == SAMPLE.replace(b'GFXPresetLevel = "3"', b'GFXPresetLevel = "4"')


def test_insert_new_key_sorted_case_insensitive_with_crlf():
    doc = IniDoc(SAMPLE)
    doc.set("Render.13", "FrameRateCap", "144")
    doc.set("Render.13", "TextureDetail", "3")
    lines = doc.to_bytes().decode().split("\r\n")
    render = lines[lines.index("[Render.13]") + 1: lines.index("[Sound.3]") - 1]
    keys = [l.split(" = ")[0] for l in render]
    assert keys == sorted(keys, key=str.lower)
    assert 'FrameRateCap = "144"' in render and 'TextureDetail = "3"' in render
    assert b"\n" not in doc.to_bytes().replace(b"\r\n", b"")  # 줄바꿈이 섞이지 않음


def test_remove_key():
    doc = IniDoc(SAMPLE)
    doc.remove("Render.13", "ShaderQuality")
    assert b"ShaderQuality" not in doc.to_bytes()
    assert doc.get("Render.13", "WindowMode") == "1"


def test_duplicate_key_refused():
    bad = SAMPLE.replace(b'ShaderQuality = "3"', b'ShaderQuality = "3"\r\nShaderQuality = "1"')
    with pytest.raises(ConfigError):
        IniDoc(bad).set("Render.13", "ShaderQuality", "2")


def test_find_render_section_survives_version_bump():
    doc = IniDoc(SAMPLE.replace(b"Render.13", b"Render.14"))
    assert doc.find_section("Render.") == "Render.14"


def test_bad_value_refused():
    with pytest.raises(ConfigError):
        IniDoc(SAMPLE).set("Render.13", "X", 'a"b')


# ---------- 추천 ----------
def render_of(raw):
    doc = IniDoc(raw)
    return doc.values(doc.find_section("Render."))


MON = Monitor(r"\\.\DISPLAY2", "TFG32Q18V", "RTX", "HDMI", True, False, 2560, 1440, 60, 60.0,
              [60, 120, 144])


def test_gpu_tier_longest_match_and_unknown():
    assert gpu_tier("NVIDIA GeForce RTX 4070 SUPER") == "high"
    assert gpu_tier("NVIDIA GeForce RTX 4060 Ti") == "mid"
    assert gpu_tier("Some Future GPU 9000") is None


def test_suggest_hz():
    assert suggest_hz(MON, 120) == 120
    assert suggest_hz(MON, 100) == 120
    assert suggest_hz(MON, 240) == 144


def test_plan_sets_fps_cap_and_custom_mode():
    render = render_of(SAMPLE)
    plan = build_plan(render, Goal(target_fps=144, monitor=MON), "RTX 4070 SUPER", 12 << 30, set())
    w = plan.writes
    assert w["FrameRateCap"] == "144" and w["LimitToRefresh"] == "0"
    assert "WindowMode" not in w  # 화면 모드는 사용자가 고르지 않으면 유지
    assert "VerticalSyncEnabled" not in w  # 수직 동기화는 자동으로 안 바꿈


def test_plan_unknown_gpu_is_more_conservative():
    render = {}
    hi = build_plan(render, Goal(), "RTX 4070 SUPER", 12 << 30, set()).writes
    unk = build_plan(render, Goal(), "Mystery GPU", None, set()).writes
    assert int(unk["DirectionalShadowDetail"]) < int(hi["DirectionalShadowDetail"])
    assert int(unk["TextureDetail"]) <= 3  # VRAM 미확인 → 울트라 금지


def test_quiet_caps_fps_to_monitor_hz():
    plan = build_plan({}, Goal(target_fps=240, priority="quiet", monitor=MON), "RTX 4070", 12 << 30, set())
    assert plan.writes["FrameRateCap"] == "60"


def test_override_wins_and_mode_writes_multiple_keys():
    goal = Goal(mode="window", overrides={"shadow": "4"}, monitor=MON)
    w = build_plan(render_of(SAMPLE), goal, "RTX 4070", 12 << 30, set()).writes
    assert w["DirectionalShadowDetail"] == "4"
    assert w["WindowMode"] == "2" and w["WindowedFullscreen"] == "0"


def test_display_change_only_for_supported_rate():
    ok = build_plan({}, Goal(monitor=MON, apply_display=True, display_hz=144), None, None, set())
    bad = build_plan({}, Goal(monitor=MON, apply_display=True, display_hz=165), None, None, set())
    assert ok.display_change == (r"\\.\DISPLAY2", 60, 144)
    assert bad.display_change is None


# ---------- 적용·복구 ----------
@pytest.fixture
def env(tmp_path):
    ini = tmp_path / "Settings_v0.ini"
    ini.write_bytes(SAMPLE)
    return aps.Store(tmp_path / "app"), ini


def test_apply_backup_and_revert_restores_bytes(env):
    store, ini = env
    rec = aps.apply_writes(store, ini, sha256(SAMPLE), {"FrameRateCap": "144", "GFXPresetLevel": "4"}, PROFILE)
    snap = read_snapshot(ini)
    assert snap.render["FrameRateCap"] == "144" and snap.render["GFXPresetLevel"] == "4"
    assert (store.dir / "backups" / "first_original.ini").read_bytes() == SAMPLE
    assert rec["previous"] == {"FrameRateCap": None, "GFXPresetLevel": "3"}
    aps.revert_last(store, ini, snap.hash)
    assert ini.read_bytes() == SAMPLE
    assert store.last_apply is None


def test_stale_plan_refused(env):
    store, ini = env
    with pytest.raises(aps.StaleError):
        aps.apply_writes(store, ini, "old-hash", {"FrameRateCap": "144"}, PROFILE)
    assert ini.read_bytes() == SAMPLE


def test_game_running_refused(env, monkeypatch):
    store, ini = env
    monkeypatch.setattr(aps, "game_running", lambda: True)
    with pytest.raises(aps.ApplyError):
        aps.apply_writes(store, ini, sha256(SAMPLE), {"FrameRateCap": "144"}, PROFILE)
    assert ini.read_bytes() == SAMPLE


def test_reflection_after_game_resave(env):
    store, ini = env
    aps.apply_writes(store, ini, sha256(SAMPLE), {"FrameRateCap": "144", "TextureDetail": "3",
                                                  "GFXPresetLevel": "4"}, PROFILE)
    # 게임이 다시 저장: FrameRateCap 유지, TextureDetail 삭제, 프리셋 변경
    doc = IniDoc(ini.read_bytes())
    doc.remove("Render.13", "TextureDetail")
    doc.set("Render.13", "GFXPresetLevel", "5")
    ini.write_bytes(doc.to_bytes())
    snap = read_snapshot(ini)
    r = aps.check_reflection(store, snap.render, snap.hash)
    assert r.game_saved and r.kept == ["FrameRateCap"]
    assert r.removed == ["TextureDetail"] and r.changed == ["GFXPresetLevel"]
    assert "FrameRateCap" in store.confirmed


def test_revert_only_touches_written_keys(env):
    store, ini = env
    aps.apply_writes(store, ini, sha256(SAMPLE), {"FrameRateCap": "144"}, PROFILE)
    doc = IniDoc(ini.read_bytes())
    doc.set("Render.13", "ShaderQuality", "1")  # 게임 쪽에서 다른 키를 바꿈
    ini.write_bytes(doc.to_bytes())
    aps.revert_last(store, ini, sha256(ini.read_bytes()))
    snap = read_snapshot(ini)
    assert "FrameRateCap" not in snap.render and snap.render["ShaderQuality"] == "1"
