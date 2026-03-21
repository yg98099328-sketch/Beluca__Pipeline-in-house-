import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


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


def set_presets_dir(path_str: str) -> None:
    """
    presets.json 저장 폴더를 설정합니다.
    """
    path = Path(path_str).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)

    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps({"presets_dir": str(path)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _preset_file() -> Path:
    return get_presets_dir() / "presets.json"


def ensure_store() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    # presets 폴더는 설정에 의해 달라질 수 있습니다.
    presets_dir = get_presets_dir()
    presets_dir.mkdir(parents=True, exist_ok=True)
    preset_file = _preset_file()
    if not preset_file.exists():
        preset_file.write_text("{}", encoding="utf-8")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_presets() -> Dict[str, Any]:
    ensure_store()
    preset_file = _preset_file()
    raw = preset_file.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


def save_presets(data: Dict[str, Any]) -> None:
    ensure_store()
    preset_file = _preset_file()
    preset_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def get_next_nuke_version(nuke_dir: str) -> str:
    """
    nuke_dir 내 v001, v002 ... 폴더를 스캔하여 다음 버전 문자열을 반환합니다.
    폴더가 없으면 'v001' 반환.
    """
    nuke_path = Path(nuke_dir)
    if not nuke_path.exists():
        return "v001"
    existing: list[int] = []
    for d in nuke_path.iterdir():
        if d.is_dir() and re.match(r"^v\d+$", d.name, re.IGNORECASE):
            try:
                existing.append(int(d.name[1:]))
            except ValueError:
                pass
    if not existing:
        return "v001"
    return f"v{max(existing) + 1:03d}"


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
        "plate_hi": shot_root / "palte" / "org" / "v001" / "hi",
        "edit": shot_root / "edit",
        "renders": shot_root / "comp" / "devl" / "renders",
        "element": shot_root / "comp" / "devl" / "element",
    }


# 템플릿에 박혀 있던 예시 샷 루트(경로·샷명 치환용)
_TEMPLATE_SAMPLE_SHOT_ROOT = (
    "W:/vfx/project_2026/SBS_030/04_sq/E107/E107_S022_0080"
)
_TEMPLATE_SAMPLE_SHOT_NAME = "E107_S022_0080"


def _to_nk_path(p: Any) -> str:
    return str(p).replace("\\", "/")


def _nk_escape_quotes(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


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


def _patch_write2_from_preset(body: str, preset_data: Dict[str, Any]) -> str:
    """메인 EXR Write2 노드에 프리셋 compression/metadata/datatype/channels/OCIO 반영."""
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

    pattern = re.compile(
        r'(Write \{\n file "[^"]+"\n file_type exr\n autocrop true\n)'
        r' compression "[^"]*"\n'
        r' metadata "[^"]*"\n'
        r' first_part \w+\n'
        r' colorspace "[^"]*"\n'
        r' version \d+\n'
        r' ocioColorspace "[^"]*"\n'
        r' display [^\n]+\n'
        r' view [^\n]+\n'
        r' name Write2\n',
        re.MULTILINE,
    )

    def repl(m: re.Match) -> str:
        head = m.group(1)
        return (
            head
            + f' compression "{_nk_escape_quotes(comp_raw)}"\n'
            + f' metadata "{_nk_escape_quotes(meta_raw)}"\n'
            + f' datatype "{_nk_escape_quotes(datatype_val)}"\n'
            + f" first_part {first_part}\n"
            + cs_line
            + "\n version 17\n"
            + ocio_line
            + "\n"
            + disp_line
            + "\n"
            + view_line
            + "\n name Write2\n"
        )

    new_body, n = pattern.subn(repl, body, count=1)
    return new_body if n else body


def _patch_eo7_mov_write(body: str, preset_data: Dict[str, Any]) -> str:
    """프리뷰용 mov Write(eo7Write1)의 display/view/ocioColorspace 를 프리셋에 맞춤."""
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
        ocio_line = f' ocioColorspace "{out_cs}"'
    else:
        ocio_line = ' ocioColorspace "ACES - ACEScg"'

    disp_tok = _knob_line_token(disp)
    view_tok = _knob_line_token(view)

    old_tail = (
        ' ocioColorspace "ACES - ACEScg"\n'
        " display ACES\n"
        " view Rec.709\n"
        " name eo7Write1\n"
    )
    new_tail = (
        f"{ocio_line}\n"
        f" display {disp_tok}\n"
        f" view {view_tok}\n"
        " name eo7Write1\n"
    )
    if old_tail in body:
        return body.replace(old_tail, new_tail, 1)
    return body


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
    lines = [
        f'addFormat "{fmt_str}"',
        "Root {",
        " inputs 0",
        f" fps {fps}",
        f' format "{fmt_str}"',
        " colorManagement OCIO",
        " OCIO_config custom",
        f' customOCIOConfigPath "{ocio_path}"',
        "}",
        "Read {",
        " inputs 0",
        " file_type exr",
        f" file {plate_file}",
        " colorspace scene_linear",
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
) -> str:
    """
    shot_node_template.nk(팀 기본 노드 트리) + Root(프리셋) + 경로·Write·Viewer 패치.
    템플릿이 없으면 최소 그래프로 폴백합니다.
    """
    tpl_path = get_shot_node_template_path()
    if tpl_path is None:
        return _generate_nk_minimal(preset_data, shot_name, paths, nk_version)

    body = tpl_path.read_text(encoding="utf-8", errors="replace")

    shot_root_norm = _to_nk_path(paths["shot_root"])
    body = body.replace(_TEMPLATE_SAMPLE_SHOT_ROOT, shot_root_norm)
    body = body.replace(_TEMPLATE_SAMPLE_SHOT_ROOT.replace("/", "\\"), shot_root_norm)
    body = body.replace("/plate/", "/palte/")
    body = body.replace("\\plate\\", "\\palte\\")
    body = body.replace(_TEMPLATE_SAMPLE_SHOT_NAME, shot_name)

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

    old_read_fmt = 'format "3840 2076 0 0 3840 2076 1 plate"'
    new_read_fmt = f'format "{width} {height} 0 0 {width} {height} 1 plate"'
    body = body.replace(old_read_fmt, new_read_fmt)

    body = re.sub(
        r" box_width 3840\n box_height 2076",
        f" box_width {width}\n box_height {height}",
        body,
        count=1,
    )

    body = _patch_write2_from_preset(body, preset_data)
    body = _patch_eo7_mov_write(body, preset_data)
    body = _patch_viewer_fps(body, fps)

    root_block = (
        f'addFormat "{fmt_str}"\n'
        "Root {\n"
        " inputs 0\n"
        f" fps {fps}\n"
        f' format "{fmt_str}"\n'
        " colorManagement OCIO\n"
        " OCIO_config custom\n"
        f' customOCIOConfigPath "{ocio_path}"\n'
        "}\n"
    )

    second_nl = body.find("\n", body.find("\n") + 1)
    if second_nl == -1:
        return root_block + body
    head = body[: second_nl + 1]
    rest = body[second_nl + 1 :]
    return head + root_block + rest
