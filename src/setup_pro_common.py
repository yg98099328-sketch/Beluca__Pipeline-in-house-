import json
import os
import re
from collections import deque
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """
    임시 파일에 쓴 뒤 os.replace 로 교체합니다.
    네트워크/공유 폴더에서 presets.json 등이 쓰기 도중 깨지는 것을 줄입니다.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as fp:
            fp.write(text)
        os.replace(str(tmp_path), str(path))
    except BaseException:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


# 캐시는 항상 기본 폴더에 둡니다.
APP_DIR = Path.home() / ".setup_pro"
CACHE_DIR = APP_DIR / "cache"

# presets.json만 사용자가 지정한 폴더로 옮길 수 있게 합니다.
SETTINGS_FILE = APP_DIR / "settings.json"


FORMAT_CACHE_FILE = CACHE_DIR / "nuke_formats.json"
COLORSPACE_CACHE_FILE = CACHE_DIR / "nuke_colorspaces.json"
DATATYPE_CACHE_FILE = CACHE_DIR / "nuke_write_datatypes.json"

OCIO_CONFIG_CACHE_FILE = CACHE_DIR / "ocio_configs.json"
SHOT_BUILDER_FILE = APP_DIR / "shot_builder.json"


def _load_settings() -> Dict[str, Any]:
    try:
        if not SETTINGS_FILE.exists():
            return {}
        raw = SETTINGS_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def get_presets_dir() -> Path:
    """
    presets.json 저장/로드 폴더를 반환합니다.
    기본값: ~/.setup_pro
    """
    settings = _load_settings()
    p = settings.get("presets_dir")
    if isinstance(p, str) and p.strip():
        return Path(p.strip())
    return APP_DIR


def _save_settings(data: Dict[str, Any]) -> None:
    """settings.json 전체를 안전하게 저장합니다."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        SETTINGS_FILE,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


def set_presets_dir(path_str: str) -> None:
    """
    presets.json 저장 폴더를 설정합니다.
    기존 settings.json 내 다른 키(tools 등)는 보존합니다.
    """
    path = Path(path_str).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)

    settings = _load_settings()
    settings["presets_dir"] = str(path)
    _save_settings(settings)


def _preset_file() -> Path:
    return get_presets_dir() / "presets.json"


def ensure_store() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # presets 폴더는 설정에 의해 달라질 수 있습니다.
    presets_dir = get_presets_dir()
    presets_dir.mkdir(parents=True, exist_ok=True)
    preset_file = _preset_file()
    if not preset_file.exists():
        _atomic_write_text(preset_file, "{}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_presets() -> Dict[str, Any]:
    ensure_store()
    preset_file = _preset_file()
    for _ in range(12):
        try:
            raw = preset_file.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            return {}
        except json.JSONDecodeError:
            # 다른 PC가 저장 중일 때 빈/불완전 파일이 잠깐 보일 수 있음
            time.sleep(0.04)
        except (OSError, PermissionError):
            time.sleep(0.04)
    return {}


def save_presets(data: Dict[str, Any]) -> None:
    ensure_store()
    preset_file = _preset_file()
    _atomic_write_text(
        preset_file,
        json.dumps(data, ensure_ascii=False, indent=2),
    )


# ─────────────────────────────────────────────
# 프리셋별 커스텀 NK 템플릿
# ─────────────────────────────────────────────


def get_preset_template_path(preset_name: str) -> Path:
    """프리셋별 커스텀 NK 템플릿 파일 경로를 반환합니다."""
    return get_presets_dir() / f"{preset_name}_template.nk"


def save_preset_template(preset_name: str, content: str) -> None:
    """프리셋 커스텀 NK 템플릿을 파일로 저장합니다."""
    ensure_store()
    path = get_preset_template_path(preset_name)
    _atomic_write_text(path, content)


def load_preset_template(preset_name: str) -> Optional[str]:
    """프리셋 커스텀 NK 템플릿을 읽습니다. 파일이 없으면 None 반환."""
    path = get_preset_template_path(preset_name)
    if path.exists():
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None
    return None


def delete_preset_template(preset_name: str) -> None:
    """프리셋 커스텀 NK 템플릿 파일을 삭제합니다."""
    path = get_preset_template_path(preset_name)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def parse_nk_file(nk_path: str) -> Dict[str, Any]:
    """
    NK 파일에서 프리셋으로 쓸 수 있는 설정을 추출합니다.
    중첩 {} 및 {value} 형식을 올바르게 처리합니다.

    Returns:
        감지된 설정 dict (없는 항목은 포함되지 않음)
    """
    try:
        content = Path(nk_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise ValueError(f"NK 파일을 읽지 못했습니다: {e}") from e

    result: Dict[str, Any] = {}

    def _get_knob(text: str, knob: str) -> Optional[str]:
        """
        knob "value", knob {value}, knob value 세 형식을 모두 지원.
        Nuke 버전에 따라 같은 knob이 다른 형식으로 저장될 수 있음.
        """
        m = re.search(rf'(?:^|\s){re.escape(knob)} "([^"]*)"', text, re.MULTILINE)
        if m:
            return m.group(1)
        m = re.search(rf'(?:^|\s){re.escape(knob)} \{{([^}}]*)\}}', text, re.MULTILINE)
        if m:
            return m.group(1)
        m = re.search(rf'(?:^|\s){re.escape(knob)} ([^\s"{{][^\s]*)', text, re.MULTILINE)
        if m:
            return m.group(1)
        return None

    def _extract_all_blocks(node_type: str) -> list:
        """중첩 {} 깊이를 추적해 지정 노드 타입의 블록 내부 텍스트를 추출."""
        blocks = []
        pattern = re.compile(
            rf'(?:^|\n){re.escape(node_type)} \{{', re.MULTILINE)
        for m in pattern.finditer(content):
            start = m.end()
            depth = 1
            i = start
            while i < len(content) and depth > 0:
                ch = content[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                i += 1
            if depth == 0:
                blocks.append(content[start : i - 1])
        return blocks

    def _find_named_block(node_type: str, node_name: str) -> Optional[str]:
        name_re = re.compile(
            rf'(?:^|\s)name {re.escape(node_name)}\s*(?:\n|$)', re.MULTILINE)
        for block in _extract_all_blocks(node_type):
            if name_re.search(block):
                return block
        return None

    root_blocks = _extract_all_blocks("Root")
    rb = root_blocks[0] if root_blocks else None
    if rb:
        fps = _get_knob(rb, "fps")
        if fps:
            result["fps"] = fps
        for pat in (r'format "(\d+) (\d+)', r'format \{(\d+) (\d+)'):
            fmt_m = re.search(pat, rb)
            if fmt_m:
                result["plate_width"] = fmt_m.group(1)
                result["plate_height"] = fmt_m.group(2)
                break
        ocio = _get_knob(rb, "customOCIOConfigPath")
        if ocio:
            result["ocio_path"] = ocio.replace("\\\\", "\\").strip()

    wb = (
        _find_named_block("Write", "Write2")
        or _find_named_block("Write", "setup_pro_write")
    )
    if not wb:
        all_writes = _extract_all_blocks("Write")
        wb = all_writes[0] if all_writes else None
    if wb:
        result["write_enabled"] = True
        for knob, key in [
            ("channels", "write_channels"),
            ("datatype", "write_datatype"),
            ("compression", "write_compression"),
            ("metadata", "write_metadata"),
        ]:
            v = _get_knob(wb, knob)
            if v:
                result[key] = v
        file_type = _get_knob(wb, "file_type")
        if file_type == "exr":
            dt = (result.get("write_datatype") or "").lower()
            result["delivery_format"] = (
                "EXR 32bit" if ("32" in dt or "float" in dt) else "EXR 16bit"
            )
        elif file_type in ("mov", "mp4"):
            result["delivery_format"] = "ProRes 422 HQ"
        ocio_cs = _get_knob(wb, "ocioColorspace")
        colorspace = _get_knob(wb, "colorspace")
        display = _get_knob(wb, "display")
        view = _get_knob(wb, "view")
        if ocio_cs:
            result["write_out_colorspace"] = ocio_cs
            result["write_colorspace"] = ocio_cs
        elif colorspace:
            result["write_out_colorspace"] = colorspace
            result["write_colorspace"] = colorspace
        if display:
            result["write_output_display"] = display
        if view:
            result["write_output_view"] = view
        if ocio_cs or (colorspace and colorspace not in ("scene_linear", "")):
            result["write_transform_type"] = "colorspace"
        elif display and view:
            result["write_transform_type"] = "display/view"

    rb_read = (
        _find_named_block("Read", "Read4")
        or _find_named_block("Read", "Read_Plate")
        or _find_named_block("Read", "Read5")
    )
    if not rb_read:
        all_reads = _extract_all_blocks("Read")
        rb_read = all_reads[0] if all_reads else None
    if rb_read:
        cs = _get_knob(rb_read, "colorspace")
        if cs:
            result["read_input_transform"] = cs

    return result


def _read_json_file(path: Path, default):
    try:
        if not path.exists():
            return default
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return default
        data = json.loads(raw)
        return data
    except Exception:
        return default


def _write_json_file(path: Path, data) -> None:
    ensure_store()
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def load_nuke_formats_cache() -> Dict[str, Any]:
    data = _read_json_file(FORMAT_CACHE_FILE, default={})
    return data if isinstance(data, dict) else {}


def save_nuke_formats_cache(data: Dict[str, Any]) -> None:
    _write_json_file(FORMAT_CACHE_FILE, data)


def load_colorspaces_cache() -> list:
    data = _read_json_file(COLORSPACE_CACHE_FILE, default=[])
    return data if isinstance(data, list) else []


def save_colorspaces_cache(data: list) -> None:
    _write_json_file(COLORSPACE_CACHE_FILE, data)


def load_datatypes_cache() -> list:
    data = _read_json_file(DATATYPE_CACHE_FILE, default=[])
    return data if isinstance(data, list) else []


def save_datatypes_cache(data: list) -> None:
    _write_json_file(DATATYPE_CACHE_FILE, data)


def load_ocio_configs_cache() -> list:
    data = _read_json_file(OCIO_CONFIG_CACHE_FILE, default=[])
    return data if isinstance(data, list) else []


def save_ocio_configs_cache(data: list) -> None:
    _write_json_file(OCIO_CONFIG_CACHE_FILE, data)


# ─────────────────────────────────────────────
# Shot Builder
# ─────────────────────────────────────────────

def get_shot_builder_settings() -> Dict[str, Any]:
    data = _read_json_file(SHOT_BUILDER_FILE, default={})
    return data if isinstance(data, dict) else {}


def save_shot_builder_settings(data: Dict[str, Any]) -> None:
    ensure_store()
    _write_json_file(SHOT_BUILDER_FILE, data)


# ─────────────────────────────────────────────
# Tools 설정 (settings.json의 "tools" 키)
# ─────────────────────────────────────────────

_DEFAULT_TOOLS: Dict[str, Any] = {
    "qc_checker":        {"enabled": False},
    "post_render_viewer": {"enabled": False},
}


def get_tools_settings() -> Dict[str, Any]:
    """
    settings.json 의 "tools" 섹션을 반환합니다.
    없는 키는 기본값으로 보완합니다.
    """
    settings = _load_settings()
    tools = settings.get("tools")
    if not isinstance(tools, dict):
        tools = {}
    merged: Dict[str, Any] = {}
    for key, default_val in _DEFAULT_TOOLS.items():
        entry = tools.get(key)
        if isinstance(entry, dict):
            merged[key] = {**default_val, **entry}
        else:
            merged[key] = dict(default_val)
    return merged


def save_tools_settings(tools_data: Dict[str, Any]) -> None:
    """
    settings.json 의 "tools" 섹션만 업데이트합니다.
    나머지 키(presets_dir 등)는 보존합니다.
    """
    settings = _load_settings()
    settings["tools"] = tools_data
    _save_settings(settings)


# ─────────────────────────────────────────────
# ShotGrid (settings.json의 "shotgrid" 키)
# ─────────────────────────────────────────────

_DEFAULT_SHOTGRID: Dict[str, Any] = {
    "base_url":            "https://beluca.shotgrid.autodesk.com",
    "script_name":         "belucaAPI",
    "script_key":          "dnolt2flVfbdoehoknpfp)bbc",
    "published_file_type": "Image Sequence",
    "task_content":        "comp",
    "task_due_date_field": "",
    "task_status_field":   "",
    "last_project_id":     None,
}


def _shotgrid_studio_json_candidates() -> list:
    """사내 자동 설정 파일 후보 (앞에서부터 존재·유효한 첫 파일 사용)."""
    paths: list = []
    env_path = os.environ.get("BPE_SHOTGRID_STUDIO_JSON", "").strip()
    if env_path:
        paths.append(Path(env_path).expanduser())
    try:
        if getattr(sys, "frozen", False):
            paths.append(Path(sys.executable).resolve().parent / "shotgrid_studio.json")
    except Exception:
        pass
    paths.append(APP_DIR / "shotgrid_studio.json")
    try:
        paths.append(Path(__file__).resolve().parent.parent / "shotgrid_studio.json")
    except Exception:
        pass
    return paths


def load_shotgrid_studio_dict() -> Dict[str, Any]:
    """
    shotgrid_studio.json 을 읽습니다.
    한 번만 채워 두면 URL/스크립트/키를 매번 입력하지 않아도 됩니다.
    """
    for path in _shotgrid_studio_json_candidates():
        try:
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                continue
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {}


def shotgrid_studio_config_path_resolved() -> Optional[Path]:
    """자격 정보가 하나라도 있는 studio 파일 경로 (없으면 None)."""
    for path in _shotgrid_studio_json_candidates():
        try:
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                continue
            data = json.loads(raw)
            if not isinstance(data, dict):
                continue
            if any(
                str(data.get(k, "") or "").strip()
                for k in ("base_url", "script_name", "script_key")
            ):
                return path.resolve()
        except Exception:
            continue
    return None


def get_shotgrid_settings() -> Dict[str, Any]:
    """
    shotgrid 설정 병합 순서:
      1) 기본값
      2) shotgrid_studio.json (EXE 옆 / ~/.setup_pro / 저장소 루트 / BPE_SHOTGRID_STUDIO_JSON)
      3) settings.json 의 shotgrid (비어 있지 않은 항목만 덮어씀, script_key 빈 문자열은 무시)
      4) 환경 변수 BPE_SHOTGRID_BASE_URL / SCRIPT_NAME / SCRIPT_KEY (최우선)
    """
    merged: Dict[str, Any] = {**_DEFAULT_SHOTGRID}

    studio = load_shotgrid_studio_dict()
    for k, v in studio.items():
        if k not in merged:
            continue
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        merged[k] = v

    settings = _load_settings()
    raw = settings.get("shotgrid")
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k == "script_key" and isinstance(v, str) and not v.strip():
                continue
            if v is None:
                continue
            if isinstance(v, str) and not v.strip() and k != "last_project_id":
                continue
            merged[k] = v

    url = os.environ.get("BPE_SHOTGRID_BASE_URL", "").strip()
    if url:
        merged["base_url"] = url
    sn = os.environ.get("BPE_SHOTGRID_SCRIPT_NAME", "").strip()
    if sn:
        merged["script_name"] = sn
    sk = os.environ.get("BPE_SHOTGRID_SCRIPT_KEY", "").strip()
    if sk:
        merged["script_key"] = sk

    return merged


def save_shotgrid_settings(partial: Dict[str, Any]) -> None:
    """
    shotgrid 설정만 병합 저장합니다. 나머지 settings 키는 보존합니다.
    partial 에 포함되지 않은 키는 기존 값 유지.
    """
    settings = _load_settings()
    cur = settings.get("shotgrid")
    if not isinstance(cur, dict):
        cur = {}
    for k, v in partial.items():
        if k == "script_key" and isinstance(v, str) and not v.strip():
            continue
        cur[k] = v
    settings["shotgrid"] = {**_DEFAULT_SHOTGRID, **cur}
    _save_settings(settings)


def parse_shot_name(shot_name: str) -> Optional[Dict[str, str]]:
    """
    샷 이름에서 에피소드 폴더명을 추출합니다.
    예) E107_S022_0080 → {ep: 'E107', full: 'E107_S022_0080'}
    서버 경로: 04_sq / EP / SHOT_NAME
    """
    s = (shot_name or "").strip().upper()
    if not s:
        return None
    parts = s.split("_")
    if len(parts) < 2:
        return None
    return {"ep": parts[0], "full": s}


def build_shot_paths(
    server_root: str, project_code: str, shot_name: str
) -> Optional[Dict[str, Path]]:
    """
    샷의 서버 경로 딕셔너리를 반환합니다.
    구조: server_root / project_code / 04_sq / EP / shot_name / ...
    shot_name을 파싱할 수 없으면 None 반환.
    """
    parsed = parse_shot_name(shot_name)
    if not parsed:
        return None
    shot_root = (
        Path(server_root) / project_code / "04_sq" / parsed["ep"] / parsed["full"]
    )
    nuke_dir = shot_root / "comp" / "devl" / "nuke"
    return {
        "shot_root": shot_root,
        "nuke_dir": nuke_dir,
        "plate_hi": shot_root / "plate" / "org" / "v001" / "hi",
        "edit": shot_root / "edit",
        "renders": shot_root / "comp" / "devl" / "renders",
        "element": shot_root / "comp" / "devl" / "element",
    }


_NK_VERSION_RE = re.compile(r"[vV](\d+)")


def _nk_is_junk_file(path: Path) -> bool:
    name = path.name
    low = name.lower()
    if "~" in name:
        return True
    if ".autosave" in low or low.endswith(".nk.autosave"):
        return True
    if "autosave" in low:
        return True
    return False


def _find_shot_root_heuristic(
    server_root: str, project_code: str, shot_name: str, *, max_depth: int = 10
) -> Optional[Path]:
    """
    parse_shot_name/build_shot_paths 가 실패할 때,
    server_root/project_code 아래에서 샷 폴더명(디렉터리)이 shot_name 과 일치하는 경로를 BFS 로 탐색합니다.
    """
    sr = Path(server_root).expanduser()
    pc = (project_code or "").strip()
    needle = (shot_name or "").strip()
    if not needle:
        return None
    # 프로젝트 코드가 없거나 해당 경로가 없으면 서버 루트 전체에서 BFS (예: project_2026/SBS_030)
    if pc:
        base = sr / pc
        if not base.is_dir():
            base = sr
    else:
        base = sr
    if not base.is_dir():
        return None
    nlow = needle.lower()

    q: deque[Tuple[Path, int]] = deque([(base, 0)])
    seen: set = set()
    while q:
        p, depth = q.popleft()
        try:
            rp = p.resolve()
        except OSError:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        try:
            if p.name.lower() == nlow:
                return p
        except OSError:
            continue
        if depth >= max_depth:
            continue
        try:
            for ch in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                if ch.is_dir():
                    q.append((ch, depth + 1))
        except OSError:
            continue
    return None


def _nk_search_roots_from_shot_root(shot_root: Path) -> List[Path]:
    roots: List[Path] = []
    for rel in (
        shot_root / "comp" / "devl" / "nuke",
        shot_root / "comp",
        shot_root / "comp" / "devl",
        shot_root / "comp" / "devl" / "nuke",
        shot_root / "work",
        shot_root / "scripts",
    ):
        try:
            p = Path(rel).resolve()
            if p.is_dir():
                roots.append(p)
        except OSError:
            continue
    if not roots:
        try:
            roots = [shot_root.resolve()]
        except OSError:
            pass
    return roots


def find_latest_nk_path(
    shot_name: str, project_code: str, server_root: str
) -> Optional[Path]:
    """
    샷 폴더 하위(comp/nuke/work 등)에서 최신 .nk 경로를 읽기 전용으로 탐색합니다.
    버전 접미사(v###)가 있으면 최대 버전, 없으면 수정 시각 기준 최신 파일을 고릅니다.
    build_shot_paths 가 실패하면 프로젝트 루트 아래에서 샷 폴더명을 휴리스틱으로 찾습니다.
    """
    sn = (shot_name or "").strip()
    pc = (project_code or "").strip()
    sr = (server_root or "").strip()
    if not sn or not sr:
        return None

    shot_root: Optional[Path] = None
    if pc:
        bp = build_shot_paths(sr, pc, sn)
        if bp:
            cand = bp["shot_root"]
            try:
                if cand.exists():
                    shot_root = cand
            except OSError:
                shot_root = None
    if shot_root is None:
        shot_root = _find_shot_root_heuristic(sr, pc, sn)
    if shot_root is None:
        return None

    roots = _nk_search_roots_from_shot_root(shot_root)
    if not roots:
        return None

    seen: set = set()
    nk_files: List[Path] = []
    for root in roots:
        try:
            for p in root.rglob("*.nk"):
                if not p.is_file():
                    continue
                if _nk_is_junk_file(p):
                    continue
                try:
                    rp = p.resolve()
                except OSError:
                    rp = p
                if rp in seen:
                    continue
                seen.add(rp)
                nk_files.append(p)
        except OSError:
            continue

    if not nk_files:
        return None

    needle = sn.lower()
    matched = [
        p
        for p in nk_files
        if needle in p.stem.lower() or needle in p.name.lower()
    ]
    pool = matched if matched else nk_files

    def _sort_key(p: Path) -> Tuple[int, float]:
        try:
            name_nums = [int(m.group(1)) for m in _NK_VERSION_RE.finditer(p.name)]
            parent_nums = [
                int(m.group(1)) for m in _NK_VERSION_RE.finditer(p.parent.name)
            ]
            merged = name_nums + parent_nums
            vmax = max(merged) if merged else -1
            mt = os.path.getmtime(p)
        except OSError:
            vmax, mt = -1, 0.0
        return (vmax, mt)

    return max(pool, key=_sort_key)


def find_latest_nk_and_open(
    shot_name: str, project_code: str, server_root: str
) -> Optional[Path]:
    """find_latest_nk_path 를 호출하고, 파일을 찾으면 Windows 기본 앱(Nuke)으로 열어줍니다.
    열기에 성공하면 Path 반환, 파일을 찾지 못하면 None 반환.
    이 함수는 100% 읽기 전용입니다 — 파일을 생성·변경·삭제하지 않습니다.
    """
    path = find_latest_nk_path(shot_name, project_code, server_root)
    if path is None:
        return None
    try:
        os.startfile(str(path))  # noqa: S606 — Windows 전용
    except Exception:
        pass
    return path


# 템플릿에 박혀 있던 예시 샷 루트(경로·샷명 치환용)
_TEMPLATE_SAMPLE_SHOT_ROOT = (
    "W:/vfx/project_2026/SBS_030/04_sq/E107/E107_S022_0080"
)
_TEMPLATE_SAMPLE_SHOT_NAME = "E107_S022_0080"


def _to_nk_path(p: Any) -> str:
    return str(p).replace("\\", "/")


def _nk_escape_quotes(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _find_blocks_with_positions(content: str, node_type: str) -> list:
    """
    NK 파일에서 지정 노드 타입의 블록을 중첩 {} 깊이 추적으로 찾습니다.
    Returns list of (start, end, inner):
      start: content 내 'NodeType {' 시작 인덱스
      end:   닫는 '}' 다음 인덱스
      inner: { 와 } 사이 텍스트 (앞뒤 \n 포함)
    """
    results = []
    pattern = re.compile(rf'(?:^|\n)({re.escape(node_type)} \{{)', re.MULTILINE)
    for m in pattern.finditer(content):
        group_start = m.start(1)  # 'NodeType {' 시작 위치
        inner_start = m.end()
        depth = 1
        i = inner_start
        while i < len(content) and depth > 0:
            ch = content[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
            i += 1
        if depth == 0:
            results.append((group_start, i, content[inner_start:i - 1]))
    return results


def _replace_knob_in_block(inner: str, knob_name: str, new_value: str) -> str:
    """
    블록 inner 텍스트에서 특정 knob 값을 교체합니다.
    따옴표 / 중괄호 / 토큰 세 가지 NK 형식을 모두 처리합니다.
    knob이 없으면 inner를 그대로 반환합니다.
    """
    escaped = _nk_escape_quotes(new_value)
    kn = re.escape(knob_name)

    # 형식 1: ' knob "value"'
    result, n = re.subn(
        rf'^( {kn} )"[^"]*"',
        rf'\1"{escaped}"',
        inner,
        flags=re.MULTILINE,
    )
    if n:
        return result

    # 형식 2: ' knob {value}'
    result, n = re.subn(
        rf'^( {kn} )\{{[^}}]*\}}',
        rf'\1"{escaped}"',
        inner,
        flags=re.MULTILINE,
    )
    if n:
        return result

    # 형식 3: ' knob token' (공백 없는 단순 값)
    result, n = re.subn(
        rf'^( {kn} )([^\s"{{][^\s]*)',
        rf'\1"{escaped}"',
        inner,
        flags=re.MULTILINE,
    )
    if n:
        return result

    return inner


def get_shot_node_template_path() -> Optional[Path]:
    """PyInstaller(onefile) 또는 개발 폴더에서 shot_node_template.nk 를 찾습니다."""
    candidates: list[Path] = []
    try:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "shot_node_template.nk")
    except Exception:
        pass
    candidates.append(Path(__file__).resolve().parent / "shot_node_template.nk")
    for p in candidates:
        if p.exists():
            return p
    return None


def _preset_datatype_string(preset_data: Dict[str, Any]) -> str:
    dt_raw = preset_data.get("write_datatype", "16 bit half") or "16 bit half"
    if "32" in dt_raw:
        return "32 bit float"
    if "integer" in dt_raw.lower():
        return "8 bit fixed"
    return "16 bit half"


def _preset_first_part(preset_data: Dict[str, Any]) -> str:
    ch = (preset_data.get("write_channels") or "all").strip().lower()
    if ch == "rgb":
        return "rgb"
    return "rgba"


def _patch_read_colorspace(body: str, colorspace: str) -> str:
    """Read 노드(Read4, Read5 등)의 colorspace를 프리셋 input transform으로 교체.
    블록 기반으로 knob 순서와 무관하게 정확하게 교체합니다.
    블록 추출에 실패하면 기존 정규식으로 폴백합니다.
    """
    if not colorspace:
        return body

    blocks = _find_blocks_with_positions(body, "Read")
    if not blocks:
        # 폴백: 기존 정규식 (colorspace 가 name 바로 앞에 있는 경우)
        escaped_cs = _nk_escape_quotes(colorspace)
        return re.sub(
            r'( colorspace )"[^"]*"\n( name Read[\w\d_]+\n)',
            rf'\1"{escaped_cs}"\n\2',
            body,
        )

    result = body
    # 역순으로 처리해 앞쪽 블록의 위치 인덱스를 유지합니다
    for start, end, inner in reversed(blocks):
        # name 이 Read\w+ 패턴인 블록만 대상으로 합니다
        if not re.search(r'(?m)^ name Read[\w\d_]+\s*$', inner):
            continue
        new_inner = _replace_knob_in_block(inner, "colorspace", colorspace)
        if new_inner != inner:
            result = result[:start] + f"Read {{{new_inner}}}" + result[end:]

    return result


def _patch_write2_from_preset(body: str, preset_data: Dict[str, Any]) -> Tuple[str, bool]:
    """메인 EXR Write2 노드에 프리셋 compression/metadata/datatype/channels/OCIO 반영.
    블록 기반으로 Write2를 찾아 개별 knob을 교체한 뒤 나머지(xpos/ypos 등)는 보존합니다.
    블록 추출 실패 시 기존 정규식으로 폴백합니다.
    Returns (new_body, success) — success=False 면 패치가 적용되지 않은 것.
    """
    comp_raw = preset_data.get("write_compression", "PIZ Wavelet (32 scanlines)") or ""
    meta_raw = preset_data.get("write_metadata", "all metadata") or ""
    datatype_val = _preset_datatype_string(preset_data)
    first_part = _preset_first_part(preset_data)

    tt = (
        (preset_data.get("write_transform_type") or "colorspace")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("\\", "/")
    )
    out_cs = _nk_escape_quotes(
        preset_data.get("write_out_colorspace", "ACES - ACES2065-1")
        or "ACES - ACES2065-1"
    )
    disp = (preset_data.get("write_output_display", "ACES") or "ACES").strip()
    view = (preset_data.get("write_output_view", "Rec.709") or "Rec.709").strip()

    def _knob_line_token(val: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_.+-]+", val):
            return val
        return f'"{_nk_escape_quotes(val)}"'

    if tt == "colorspace":
        cs_value = out_cs
        ocio_value = out_cs
    elif tt == "display/view":
        cs_value = "scene_linear"
        ocio_value = out_cs
    else:
        cs_value = "scene_linear"
        ocio_value = "ACES - ACEScg"

    # ── 공통 출력 줄 생성 ────────────────────────────────────────────
    if tt == "colorspace":
        cs_line = f' colorspace "{out_cs}"'
        ocio_line = f' ocioColorspace "{out_cs}"'
    elif tt == "display/view":
        cs_line = " colorspace scene_linear"
        ocio_line = f' ocioColorspace "{out_cs}"'
    else:
        cs_line = " colorspace scene_linear"
        ocio_line = ' ocioColorspace "ACES - ACEScg"'

    disp_line = f" display {_knob_line_token(disp)}"
    view_line = f" view {_knob_line_token(view)}"

    # ── 1차: 블록 기반 (Write2 블록을 찾아 중간 섹션을 재구성) ──────
    write_blocks = _find_blocks_with_positions(body, "Write")
    write2 = None
    for blk in write_blocks:
        blk_start, blk_end, inner = blk
        if re.search(r'(?m)^ name Write2\s*$', inner):
            write2 = blk
            break

    if write2 is not None:
        blk_start, blk_end, inner = write2

        # 보존할 줄 추출
        file_m = re.search(r'(?m)^( file (?:"[^"]*"|\{[^}]*\}|\S+))', inner)
        file_line = (file_m.group(1) + '\n') if file_m else ' file placeholder.####.exr\n'

        autocrop_m = re.search(r'(?m)^( autocrop [^\n]+)', inner)
        autocrop_line = (autocrop_m.group(1) + '\n') if autocrop_m else ' autocrop true\n'

        ver_m = re.search(r'(?m)^( version \d+)', inner)
        ver_line = (ver_m.group(1) + '\n') if ver_m else ' version 1\n'

        inputs_m = re.search(r'(?m)^( inputs \d+)', inner)
        inputs_line = (inputs_m.group(1) + '\n') if inputs_m else ''

        # name Write2 이후 내용 보존 (xpos/ypos/selected 등)
        after_m = re.search(r'(?m)^ name Write2\s*\n([\s\S]*)', inner)
        after_name = after_m.group(1) if after_m else ''

        new_inner = (
            '\n'
            + inputs_line
            + file_line
            + ' file_type exr\n'
            + autocrop_line
            + f' compression "{_nk_escape_quotes(comp_raw)}"\n'
            + f' metadata "{_nk_escape_quotes(meta_raw)}"\n'
            + f' datatype "{_nk_escape_quotes(datatype_val)}"\n'
            + f' first_part {first_part}\n'
            + cs_line + '\n'
            + ver_line
            + ocio_line + '\n'
            + disp_line + '\n'
            + view_line + '\n'
            + ' name Write2\n'
            + after_name
        )
        new_body = body[:blk_start] + f"Write {{{new_inner}}}" + body[blk_end:]
        return new_body, True

    # ── 2차 폴백: 기존 정규식 (현재 템플릿 구조에 맞는 패턴) ──────────

    pattern = re.compile(
        r'(Write \{\n file "[^"]+"\n file_type exr\n autocrop true\n)'
        r'(?P<pre>(?:(?! name Write2\n).)*?)'
        r' name Write2\n',
        re.MULTILINE | re.DOTALL,
    )

    def repl(m: re.Match) -> str:
        head = m.group(1)
        pre_text = m.group("pre")
        ver_m = re.search(r' version (\d+)\n', pre_text)
        ver_line = f" version {ver_m.group(1)}\n" if ver_m else " version 1\n"
        return (
            head
            + f' compression "{_nk_escape_quotes(comp_raw)}"\n'
            + f' metadata "{_nk_escape_quotes(meta_raw)}"\n'
            + f' datatype "{_nk_escape_quotes(datatype_val)}"\n'
            + f" first_part {first_part}\n"
            + cs_line + "\n"
            + ver_line
            + ocio_line + "\n"
            + disp_line + "\n"
            + view_line + "\n name Write2\n"
        )

    new_body, n = pattern.subn(repl, body, count=1)
    return (new_body, True) if n else (body, False)


def _patch_eo7_mov_write(body: str, preset_data: Dict[str, Any]) -> Tuple[str, bool]:
    """프리뷰용 mov Write(eo7Write1)의 display/view/ocioColorspace 를 프리셋에 맞춤.
    1차: 정확한 문자열 매칭 → 2차: 정규식 → 3차: 블록 기반
    Returns (new_body, success) — success=False 면 패치가 적용되지 않은 것.
    """
    tt = (
        (preset_data.get("write_transform_type") or "colorspace")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("\\", "/")
    )
    out_cs = _nk_escape_quotes(
        preset_data.get("write_out_colorspace", "ACES - ACES2065-1")
        or "ACES - ACES2065-1"
    )
    disp = (preset_data.get("write_output_display", "ACES") or "ACES").strip()
    view = (preset_data.get("write_output_view", "Rec.709") or "Rec.709").strip()

    def _knob_line_token(val: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_.+-]+", val):
            return val
        return f'"{_nk_escape_quotes(val)}"'

    if tt == "colorspace":
        ocio_value = (preset_data.get("write_out_colorspace", "ACES - ACEScg") or "ACES - ACEScg").strip()
    else:
        ocio_value = "ACES - ACEScg"

    ocio_line = f' ocioColorspace "{_nk_escape_quotes(ocio_value)}"'
    disp_tok = _knob_line_token(disp)
    view_tok = _knob_line_token(view)

    new_tail_lines = (
        f"{ocio_line}\n"
        f" display {disp_tok}\n"
        f" view {view_tok}\n"
        " name eo7Write1\n"
    )

    # ── 1차: 정확한 문자열 매칭 (현재 템플릿 기본값에 최적화) ──────────
    old_tail = (
        ' ocioColorspace "ACES - ACEScg"\n'
        " display ACES\n"
        " view Rec.709\n"
        " name eo7Write1\n"
    )
    if old_tail in body:
        return body.replace(old_tail, new_tail_lines, 1), True

    # ── 2차: 정규식 폴백 ─────────────────────────────────────────────
    eo7_pattern = re.compile(
        r'( ocioColorspace "[^"]*"\n'
        r' display [^\n]+\n'
        r' view [^\n]+\n'
        r' name eo7Write1\n)',
        re.MULTILINE,
    )
    new_body, n = eo7_pattern.subn(new_tail_lines, body, count=1)
    if n:
        return new_body, True

    # ── 3차: 블록 기반 ──────────────────────────────────────────────
    write_blocks = _find_blocks_with_positions(body, "Write")
    eo7 = None
    for blk in write_blocks:
        blk_start, blk_end, inner = blk
        if re.search(r'(?m)^ name eo7Write1\s*$', inner):
            eo7 = blk
            break

    if eo7 is None:
        return body, False

    blk_start, blk_end, inner = eo7
    new_inner = _replace_knob_in_block(inner, "ocioColorspace", ocio_value)
    new_inner = _replace_knob_in_block(new_inner, "display", disp)
    new_inner = _replace_knob_in_block(new_inner, "view", view)
    new_body = body[:blk_start] + f"Write {{{new_inner}}}" + body[blk_end:]
    return new_body, True


def _patch_viewer_fps(body: str, fps: str) -> str:
    return re.sub(
        r"(Viewer \{\n frame_range [^\n]+\n fps )([\d.]+)",
        rf"\g<1>{fps}",
        body,
        count=1,
    )


def _generate_nk_minimal(
    preset_data: Dict[str, Any],
    shot_name: str,
    paths: Dict[str, Path],
    nk_version: str,
) -> str:
    """템플릿이 없을 때 사용하는 최소 .nk (폴백)."""
    fps = preset_data.get("fps", "23.976")
    width = int(float(preset_data.get("plate_width", 1920)))
    height = int(float(preset_data.get("plate_height", 1080)))
    ocio_path = (preset_data.get("ocio_path", "") or "").replace("\\", "/")
    format_name = f"SP_{width}x{height}"
    plate_file = f"{_to_nk_path(paths['plate_hi'])}/{shot_name}.####.exr"
    edit_file = f"{_to_nk_path(paths['edit'])}/{shot_name}_edit.####.exr"
    delivery_fmt = (preset_data.get("delivery_format", "EXR 16bit") or "EXR 16bit").upper()
    if "EXR" in delivery_fmt:
        write_file_type, write_ext = "exr", "exr"
    elif "PRORES" in delivery_fmt or "DNXHR" in delivery_fmt:
        write_file_type, write_ext = "mov", "mov"
    else:
        write_file_type, write_ext = "exr", "exr"
    write_file = (
        f"{_to_nk_path(paths['renders'])}/{shot_name}_comp_{nk_version}.####.{write_ext}"
    )
    channels = preset_data.get("write_channels", "all") or "all"
    datatype_val = _preset_datatype_string(preset_data)
    comp_raw = preset_data.get("write_compression", "PIZ Wavelet (32 scanlines)") or ""
    comp_map = {
        "none": "none",
        "ZIP (single line)": "Zip (1 scanline)",
        "ZIP (block of 16 scanlines)": "Zip (16 scanlines)",
        "RLE": "RLE",
        "PIZ Wavelet (32 scanlines)": "PIZ Wavelet",
        "PXR24 (lossy)": "PXR24 (lossy)",
        "B44 (lossy)": "B44 (lossy)",
        "B44A (lossy)": "B44A (lossy)",
        "DWAA (lossy)": "DWAA (lossy)",
        "DWAB (lossy)": "DWAB (lossy)",
    }
    comp_val = comp_map.get(comp_raw, "PIZ Wavelet")
    metadata_raw = preset_data.get("write_metadata", "all metadata") or "all metadata"
    fmt_str = f"{width} {height} 0 0 {width} {height} 1 {format_name}"
    # .nk 스크립트에는 addFormat 이 유효한 명령이 아님(Nuke API 전용) → Root.format 만 사용
    lines = [
        "set cut_paste_input [stack 0]",
        "version 14.1 v4",
        "Root {",
        " inputs 0",
        f" fps {fps}",
        f' format "{fmt_str}"',
        *([" colorManagement OCIO",
           " OCIO_config custom",
           f' customOCIOConfigPath "{ocio_path}"'] if ocio_path else []),
        "}",
        "Read {",
        " inputs 0",
        " file_type exr",
        f" file {plate_file}",
        f" colorspace {(preset_data.get('read_input_transform') or 'scene_linear').strip()}",
        " name Read_Plate",
        " xpos -300",
        " ypos -400",
        "}",
        "set cut_paste_input [stack 0]",
        "Viewer {",
        " inputs 1",
        " name Viewer1",
        " xpos -300",
        " ypos -300",
        "}",
        "push $cut_paste_input",
        "Write {",
        " inputs 1",
        f" file {write_file}",
        f" file_type {write_file_type}",
        f" channels {channels}",
        f' datatype "{datatype_val}"',
        f' compression "{comp_val}"',
        f' metadata "{metadata_raw}"',
        " name setup_pro_write",
        " xpos -300",
        " ypos -200",
        "}",
        "Read {",
        " inputs 0",
        " file_type exr",
        f" file {edit_file}",
        " colorspace scene_linear",
        " name Read_Edit",
        " xpos 100",
        " ypos -400",
        "}",
        "",
    ]
    return "\n".join(lines)


def generate_nk_content(
    preset_data: Dict[str, Any],
    shot_name: str,
    paths: Dict[str, Path],
    nk_version: str,
) -> Tuple[str, list]:
    """
    shot_node_template.nk(팀 기본 노드 트리) + Root(프리셋) + 경로·Write·Viewer 패치.
    템플릿이 없으면 최소 그래프로 폴백합니다.
    Returns (nk_content, warnings) — warnings 는 패치 실패 등 알림 문자열 리스트.
    """
    warnings: list = []

    preset_name = (preset_data.get("project_code") or "").strip().upper()
    custom_body = load_preset_template(preset_name) if preset_name else None
    if custom_body:
        body = custom_body
    else:
        tpl_path = get_shot_node_template_path()
        if tpl_path is None:
            return _generate_nk_minimal(preset_data, shot_name, paths, nk_version), [
                "⚠ shot_node_template.nk 를 찾지 못해 최소 NK로 생성되었습니다."
            ]
        body = tpl_path.read_text(encoding="utf-8", errors="replace")

    shot_root_norm = _to_nk_path(paths["shot_root"])
    body = body.replace(_TEMPLATE_SAMPLE_SHOT_ROOT, shot_root_norm)
    body = body.replace(_TEMPLATE_SAMPLE_SHOT_ROOT.replace("/", "\\"), shot_root_norm)
    body = body.replace(_TEMPLATE_SAMPLE_SHOT_NAME, shot_name)
    # 과거 버그로 생성된 NK의 오타 경로 보정
    body = body.replace("/palte/", "/plate/")
    body = body.replace("\\palte\\", "\\plate\\")

    # Viewer NDISender 등에 박힌 comp 버전 폴더(v001)를 실제 nk_version 으로
    body = re.sub(
        rf"(monitorOutNDISenderName \"NukeX - {re.escape(shot_name)}_comp_)v\d+",
        rf"\g<1>{nk_version}",
        body,
        count=1,
    )

    fps = str(preset_data.get("fps", "23.976"))
    width = int(float(preset_data.get("plate_width", 1920)))
    height = int(float(preset_data.get("plate_height", 1080)))
    ocio_path = _nk_escape_quotes(
        (preset_data.get("ocio_path", "") or "").replace("\\", "/")
    )
    format_name = f"SP_{width}x{height}"
    fmt_str = f"{width} {height} 0 0 {width} {height} 1 {format_name}"

    # Read 노드 format 교체: "plate" 이름 포맷 전체 교체 (Read4, Read5, Read_Edit 등)
    body = re.sub(
        r'format "\d+ \d+ \d+ \d+ \d+ \d+ \d+ plate"',
        f'format "{width} {height} 0 0 {width} {height} 1 plate"',
        body,
    )

    # Reformat/Crop box 사이즈 교체 (템플릿에 박힌 고정 해상도)
    body = re.sub(
        r" box_width \d+\n box_height \d+",
        f" box_width {width}\n box_height {height}",
        body,
        count=1,
    )

    # Read 노드 input transform 패치
    read_cs = (preset_data.get("read_input_transform", "") or "").strip()
    if read_cs:
        body = _patch_read_colorspace(body, read_cs)

    body, w2_ok = _patch_write2_from_preset(body, preset_data)
    if not w2_ok:
        warnings.append(
            "⚠ Write2 노드 패치 실패: 템플릿 포맷이 변경되었을 수 있습니다.\n"
            "  Write 설정(compression/datatype/colorspace)이 적용되지 않았습니다."
        )

    body, eo7_ok = _patch_eo7_mov_write(body, preset_data)
    if not eo7_ok:
        warnings.append(
            "⚠ eo7Write1 MOV 노드 패치 실패: display/view 설정이 적용되지 않았습니다."
        )

    body = _patch_viewer_fps(body, fps)

    # addFormat 은 .nk 로드 시 인식되지 않음 → Root 블록의 format 만 설정
    root_block = (
        "Root {\n"
        " inputs 0\n"
        f" fps {fps}\n"
        f' format "{fmt_str}"\n'
        " colorManagement OCIO\n"
        " OCIO_config custom\n"
        f' customOCIOConfigPath "{ocio_path}"\n'
        "}\n"
    )

    # 'version X.Y vZ' 행 다음에 Root 블록을 삽입합니다.
    # 이렇게 하면 두 번째 Root 블록이 템플릿의 Root보다 나중에 적용되어
    # FPS / 해상도 / OCIO 설정을 올바르게 오버라이드합니다.
    ver_m = re.search(r'^version [\d.]+ v\d+\s*$', body, re.MULTILINE)
    if ver_m:
        insert_pos = ver_m.end()
        if insert_pos < len(body) and body[insert_pos] == '\n':
            insert_pos += 1
    else:
        # version 행이 없으면 두 번째 줄 뒤에 삽입 (기존 동작 유지)
        second_nl = body.find("\n", body.find("\n") + 1)
        insert_pos = (second_nl + 1) if second_nl != -1 else 0

    return body[:insert_pos] + root_block + body[insert_pos:], warnings
