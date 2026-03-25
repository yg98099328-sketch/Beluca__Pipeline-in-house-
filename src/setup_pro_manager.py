"""
BELUCA Pipeline Engine (BPE) - VFX Pipeline Preset & Shot Builder
UI: customtkinter 기반 프로 디자인
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import re
import os
import json
import logging
import queue
import threading
from pathlib import Path
import subprocess
import sys
from typing import Optional

import shotgrid_client as sgc
from shotgrid_client import _dbg as _sg_dbg, _debug_9b9c60_log

from setup_pro_common import (
    APP_DIR,
    CACHE_DIR,
    find_latest_nk_path,
    load_presets,
    save_presets,
    get_presets_dir,
    set_presets_dir,
    load_nuke_formats_cache,
    load_colorspaces_cache,
    load_datatypes_cache,
    load_ocio_configs_cache,
    save_ocio_configs_cache,
    get_shot_builder_settings,
    save_shot_builder_settings,
    build_shot_paths,
    generate_nk_content,
    parse_shot_name,
    get_tools_settings,
    save_tools_settings,
    get_shotgrid_settings,
    save_shotgrid_settings,
    shotgrid_studio_config_path_resolved,
    parse_nk_file,
    save_preset_template,
    load_preset_template,
    delete_preset_template,
    _TEMPLATE_SAMPLE_SHOT_ROOT,
    _TEMPLATE_SAMPLE_SHOT_NAME,
)

logger = logging.getLogger(__name__)

try:
    from PIL import Image as PILImage  # noqa: F401 — CTkImage / 썸네일용
except ImportError:
    PILImage = None  # type: ignore[misc, assignment]


# ── Design Tokens ─────────────────────────────────────────────────
BG          = "#1c1c1e"
# ── Read Input Transform 카탈로그 (ACES 1.0.3 OCIO 기준) ──────────
READ_COLORSPACE_CATALOG: dict = {
    "Roles (Shortcuts)": [
        "scene_linear",
        "compositing_linear",
        "color_timing",
        "color_picking",
        "compositing_log",
        "data",
        "matte_paint",
        "reference",
        "rendering",
        "texture_paint",
        "default",
    ],
    "ACES": [
        "ACES - ACES2065-1",
        "ACES - ACEScc",
        "ACES - ACESproxy",
        "ACES - ACEScg",
        "ACES - log film scan (ADX10)",
        "ACES - log film scan (ADX16)",
    ],
    "Input - ADX": [
        "Input - ADX - ADX10",
        "Input - ADX - ADX16",
    ],
    "Input - ARRI": [
        "Input - ARRI - V3 LogC (EI160) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI200) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI250) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI320) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI400) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI500) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI640) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI800) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI1000) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI1280) - Wide Gamut",
        "Input - ARRI - V3 LogC (EI1600) - Wide Gamut",
    ],
    "Input - Canon": [
        "Input - Canon - Canon Log",
    ],
    "Input - GoPro": [
        "Input - GoPro - Protune Flat",
    ],
    "Input - Panasonic": [
        "Input - Panasonic - V-Log L",
    ],
    "Input - RED": [
        "Input - RED - REDlogFilm",
        "Input - RED - REDLog3G10",
    ],
    "Input - Sony": [
        "Input - Sony - S-Log1",
        "Input - Sony - S-Log2",
        "Input - Sony - S-Log3 - S-Gamut3",
        "Input - Sony - S-Log3 - S-Gamut3 Cine",
    ],
    "Output": [
        "Output - Rec.709",
        "Output - sRGB",
        "Output - P3-DCI",
        "Output - P3-D65",
        "Output - Rec.2020",
    ],
    "Utility - Linear": [
        "Utility - Linear - sRGB",
        "Utility - Linear - Rec.709",
        "Utility - Linear - Adobe RGB (1998)",
        "Utility - Linear - P3-D65",
        "Utility - Linear - P3-DCI",
        "Utility - Linear - Rec.2020",
    ],
    "Utility - Curve": [
        "Utility - Curve - Rec.709",
        "Utility - Curve - sRGB",
        "Utility - Curve - Gamma 1.8",
        "Utility - Curve - Gamma 2.2",
        "Utility - Curve - Gamma 2.4 (Rec.709)",
    ],
    "Utility - Texture": [
        "Utility - sRGB - Texture",
        "Utility - Gamma 1.8 - Rec.709 - Texture",
        "Utility - Gamma 2.2 - Rec.709 - Texture",
        "Utility - Gamma 2.2 - Apple iOS - Texture",
        "Utility - Gamma 2.2 - sRGB - Texture",
        "Utility - Gamma 2.4 - Rec.709 - Texture",
        "Utility - Gamma 2.6 - P3-DCI - Texture",
    ],
    "Utility - Other": [
        "Utility - Raw",
        "Utility - Log Film Scan (ADX10)",
        "Utility - Log Film Scan (ADX16)",
        "Utility - Black",
    ],
}
SIDEBAR_BG  = "#111114"
PANEL_BG    = "#252528"
INPUT_BG    = "#1c1c1e"
ACCENT      = "#f08a24"
ACCENT_HOV  = "#d97c1e"
TEXT        = "#f5f5f7"
TEXT_DIM    = "#86868b"
BORDER      = "#3a3a3c"
HOVER       = "#2c2c2e"
SELECT_BG   = "#3a3a3c"


def _make_dialog_fonts():
    return {
        "F_TITLE":  ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
        "F_HEAD":   ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        "F_LABEL":  ctk.CTkFont(family="Segoe UI", size=12),
        "F_SMALL":  ctk.CTkFont(family="Segoe UI", size=11),
        "F_MONO":   ctk.CTkFont(family="Consolas", size=10),
        "F_BTN":    ctk.CTkFont(family="Segoe UI", size=12),
        "F_BTN_EM": ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        "F_SUBHEAD":ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
    }


def _apply_dialog_chrome(win):
    try:
        import ctypes
        hwnd = win.winfo_id()
        for attr in (19, 20):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(ctypes.c_int(1)), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 35, ctypes.byref(ctypes.c_int(0x001e1c1c)), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
    except Exception:
        pass


def _ask_directory_modal(parent_win, *, title: str, initialdir: str = "") -> str:
    """
    Windows에서 CTkToplevel.grab_set() 상태로 tk 폴더 대화상자를 띄우면
    모달/부모 HWND가 꼬일 수 있어 grab 소유 창을 잠시 해제하고, 메인 앱을 parent로 넘깁니다.
    """
    grab_owner = None
    try:
        grab_owner = parent_win.grab_current()
    except tk.TclError:
        pass
    if grab_owner is not None:
        try:
            grab_owner.grab_release()
        except tk.TclError:
            grab_owner = None
    try:
        init = (initialdir or "").strip() or None
        kw = {"title": title, "parent": parent_win}
        if init:
            kw["initialdir"] = init
        return filedialog.askdirectory(**kw) or ""
    finally:
        if grab_owner is not None:
            try:
                if grab_owner.winfo_exists():
                    grab_owner.grab_set()
            except tk.TclError:
                pass


def _ask_file_modal(parent_win, *, title: str, filetypes=None, initialdir: str = "") -> str:
    """
    CTkToplevel.grab_set() 상태에서 askopenfilename 을 띄우면
    Windows 에서 파일 대화창 HWND/grab이 꼬여 먹통이 됩니다.
    grab 소유 창을 잠시 해제하고 파일 대화창을 표시한 뒤, 완료 후 grab을 복원합니다.
    _ask_directory_modal 과 동일한 패턴.
    """
    grab_owner = None
    try:
        grab_owner = parent_win.grab_current()
    except tk.TclError:
        pass
    if grab_owner is not None:
        try:
            grab_owner.grab_release()
        except tk.TclError:
            grab_owner = None
    try:
        kw: dict = {"title": title, "parent": parent_win}
        if filetypes:
            kw["filetypes"] = filetypes
        init = (initialdir or "").strip() or None
        if init:
            kw["initialdir"] = init
        return filedialog.askopenfilename(**kw) or ""
    finally:
        if grab_owner is not None:
            try:
                if grab_owner.winfo_exists():
                    grab_owner.grab_set()
            except tk.TclError:
                pass


class ShotBuilderNoticeDialog(ctk.CTkToplevel):
    """Shot Builder 전용 안내 다이얼로그 (다크 테마·앱과 동일한 스타일)."""

    def __init__(
        self,
        parent,
        *,
        title: str,
        headline: str,
        body: str,
        detail_path: str = "",
    ):
        super().__init__(parent)
        self._f = _make_dialog_fonts()
        self.title(title)
        h = 360 if detail_path else 260
        self.geometry(f"520x{h}")
        self.minsize(460, 240)
        self.configure(fg_color=BG)
        self.transient(parent)
        self.grab_set()
        self.after(80, lambda: _apply_dialog_chrome(self))

        f = self._f
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=22, pady=(20, 0))
        ctk.CTkLabel(
            hdr,
            text=headline,
            font=f["F_TITLE"],
            text_color=ACCENT,
            wraplength=460,
            justify="left",
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x", padx=14, pady=(12, 0))

        card = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=10)
        card.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        ctk.CTkLabel(
            card,
            text=body,
            font=f["F_SMALL"],
            text_color=TEXT,
            wraplength=440,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=14, pady=(14, 8))

        if detail_path:
            ctk.CTkLabel(
                card,
                text="경로",
                font=f["F_SUBHEAD"],
                text_color=TEXT_DIM,
                anchor="w",
            ).pack(anchor="w", padx=14, pady=(4, 2))
            tb = ctk.CTkTextbox(
                card,
                height=88,
                fg_color=INPUT_BG,
                text_color=TEXT_DIM,
                font=f["F_MONO"],
                border_color=BORDER,
                border_width=1,
                corner_radius=6,
                wrap="word",
            )
            tb.insert("1.0", detail_path)
            tb.configure(state="disabled")
            tb.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x", padx=14, pady=(8, 0))
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(12, 14))
        ctk.CTkButton(
            btn_row,
            text="확인",
            height=38,
            width=120,
            fg_color=ACCENT,
            hover_color=ACCENT_HOV,
            text_color="#111111",
            font=f["F_BTN_EM"],
            command=self.destroy,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.destroy)


class SetupProManager(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()

        # tkinterdnd2 DnD 지원 루트 패치
        # CTk는 일반 Tk 루트라 tkinterdnd2.TkinterDnD._require() 로 패치 필요
        try:
            from tkinterdnd2 import TkinterDnD as _TkDnD
            _TkDnD._require(self)  # type: ignore[attr-defined]
        except Exception:
            pass

        self._init_fonts()

        # ── Data (제목 표시줄에 버전 표기 전에 로드) ──
        self.app_version = self._load_app_version()
        self.title(f"BPE v{self.app_version}")
        self.geometry("1080x720")
        self.minsize(900, 600)
        self.configure(fg_color=BG)
        self.after(80, self._apply_win_chrome)
        self.ocio_configs = load_ocio_configs_cache()
        self.presets      = load_presets()

        # ── State ──
        self._selected_preset: str  = ""
        self._preset_btns:     dict = {}
        self._last_nk_dir:     str  = ""
        self._sg_project_rows: list = []
        self._sg_task_rows: list = []

        # ── Variables ──
        self._init_vars()

        # ── UI ──
        self._build_ui()
        self._refresh_preset_list()
        # Ctrl+S: 프리셋 저장 단축키
        self.bind_all("<Control-s>", lambda _e: self._save_preset())

    def _init_fonts(self) -> None:
        """CTkFont는 Tk 루트 생성 후에만 만들 수 있음 (PyInstaller/EXE 포함)."""
        self.F_TITLE = ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        self.F_HEAD = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.F_LABEL = ctk.CTkFont(family="Segoe UI", size=12)
        self.F_SMALL = ctk.CTkFont(family="Segoe UI", size=11)
        self.F_MONO = ctk.CTkFont(family="Consolas", size=10)
        self.F_NAV = ctk.CTkFont(family="Segoe UI", size=13)
        self.F_BTN = ctk.CTkFont(family="Segoe UI", size=12)
        self.F_BTN_EM = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.F_BRAND = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")
        self.F_SEG = ctk.CTkFont(family="Segoe UI", size=12)
        self.F_SUBHEAD = ctk.CTkFont(family="Segoe UI", size=11, weight="bold")

    # ─────────────────────────────── Window Chrome ──────────────────
    def _apply_win_chrome(self) -> None:
        """Windows 11: 다크 제목 표시줄 + 제목 표시줄 색상 + 둥근 모서리."""
        try:
            import ctypes
            hwnd = self.winfo_id()
            for attr in (19, 20):                             # dark titlebar (Win10+, Win11)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(ctypes.c_int(1)), 4)
            # 제목 표시줄 배경색 (BGR) — Win11 22H2+
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, ctypes.byref(ctypes.c_int(0x001e1c1c)), 4)
            # 둥근 모서리 — Win11
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception:
            pass

    # ─────────────────────────────── Version ────────────────────────
    def _load_app_version(self) -> str:
        candidates = []
        try:
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                candidates.append(Path(sys._MEIPASS) / "VERSION.txt")
        except Exception:
            pass
        _here = Path(__file__).resolve().parent
        candidates += [_here.parent / "VERSION.txt", _here / "VERSION.txt"]
        for p in candidates:
            try:
                if p.exists():
                    v = p.read_text(encoding="utf-8").strip()
                    if v:
                        return v
            except Exception:
                continue
        return "dev"

    # ─────────────────────────────── Variables ──────────────────────
    def _init_vars(self) -> None:
        _sb = get_shot_builder_settings()

        # Preset Manager
        self.project_type_var         = tk.StringVar(value="드라마(OTT)")
        self.project_code_var         = tk.StringVar()
        self.delivery_format_var      = tk.StringVar(value="EXR 16bit")
        self.fps_var                  = tk.StringVar(value="23.976")
        self.plate_format_choice_var  = tk.StringVar(value="(직접입력)")
        self.plate_format_name_var    = tk.StringVar()
        self.plate_width_var          = tk.StringVar(value="1920")
        self.plate_height_var         = tk.StringVar(value="1080")
        self.ocio_path_var            = tk.StringVar()
        self.write_open_var           = tk.BooleanVar(value=True)
        self.write_channels_var       = tk.StringVar(value="all")
        self.write_datatype_var       = tk.StringVar(value="16 bit half")
        self.write_compression_var    = tk.StringVar(value="PIZ Wavelet (32 scanlines)")
        self.write_metadata_var       = tk.StringVar(value="all metadata")
        self.write_transform_type_var = tk.StringVar(value="colorspace")
        self.write_out_colorspace_var = tk.StringVar(value="ACES - ACES2065-1")
        self.write_output_display_var = tk.StringVar(value="ACES")
        self.write_output_view_var    = tk.StringVar(value="Rec.709")
        self.presets_dir_var          = tk.StringVar(value=str(get_presets_dir()))
        # Read Input Transform
        self.read_input_transform_var = tk.StringVar(value="ACES - ACES2065-1")
        self.read_cs_cat_var          = tk.StringVar(value="ACES")
        self.nk_import_path_var       = tk.StringVar(value="")
        self.nk_import_preset_name_var = tk.StringVar(value="")

        # Option lists
        self.write_channels_options    = ["all", "rgb", "rgba", "depth", "forward", "backward", "motion", "none"]
        self.write_datatype_options    = ["16 bit half", "32 bit float", "integer"]
        self.write_compression_options = [
            "none", "ZIP (single line)", "ZIP (block of 16 scanlines)",
            "RLE", "PIZ Wavelet (32 scanlines)", "PXR24 (lossy)",
            "B44 (lossy)", "B44A (lossy)", "DWAA (lossy)", "DWAB (lossy)",
        ]
        self.write_metadata_options    = [
            "all metadata", "no metadata",
            "all metadata except input/time", "no metadata except input/time",
        ]
        self.write_transform_type_options = ["off", "display/view", "input", "colorspace"]
        self.plate_preset_to_wh = {
            "FHD (1920x1080)": (1920, 1080),
            "HD (1280x720)": (1280, 720),
            "UHD (3840x2160)": (3840, 2160),
            "4K DCI (4096x2160)": (4096, 2160),
            "4K (3840x2070)": (3840, 2070),
            "2K Scope (2048x858)": (2048, 858),
            "2K Cine (2048x1152)": (2048, 1152),
            "8K (7680x4320)": (7680, 4320),
            "(직접입력)": ("", ""),
        }
        self._plate_combo_applying = False
        self._plate_sync_after_id = None  # 가로·세로 입력 시 콤보 동기화용 after ID

        # Shot Builder
        self.sb_server_root_var    = tk.StringVar(value=_sb.get("server_root", ""))
        self.sb_preset_var         = tk.StringVar(value=_sb.get("preset", ""))
        self.sb_shot_name_var      = tk.StringVar(value="")

        # ShotGrid (API URL/Script/Key는 내장 자격 + settings.json 만 사용 — UI에서 편집 불가)
        _sg = get_shotgrid_settings()

        # Version 업로드용 변수
        self.sg_mov_path_var     = tk.StringVar(value="")  # 드롭된 MOV 경로
        self.sg_version_name_var = tk.StringVar(value="")  # Version Name
        self.sg_desc_var         = tk.StringVar(value="")  # Description
        self.sg_artist_var       = tk.StringVar(value="")  # Artist 입력 텍스트
        self.sg_artist_id        = None                    # 선택된 HumanUser id
        self.sg_artist_login     = None                    # 선택된 HumanUser login
        self.sg_link_var         = tk.StringVar(value="")  # Shot (Link) 표시
        self.sg_link_id          = None                    # 선택된 Shot id
        self.sg_task_input_var   = tk.StringVar(value="")  # Task 입력 텍스트
        self.sg_task_id          = None                    # 선택된 Task id
        self.sg_proj_label_var   = tk.StringVar(value="")  # Project 표시
        self.sg_proj_id          = None                    # Project id
        self.sg_status_value_var = tk.StringVar(value="")  # Status combo

        # 레거시 (API 저장 폼에서만 사용)
        self.sg_status_field_var = tk.StringVar(value=str(_sg.get("task_status_field", "") or ""))

        # 자동완성 디바운스 after ID
        self._sg_artist_after: str = ""
        self._sg_task_after: str = ""

        # 내 작업 샷 (My Shots)
        _sb_ms = get_shot_builder_settings()
        self.ms_assignee_var = tk.StringVar(
            value=str(_sb_ms.get("my_shots_last_human_name", "") or "")
        )
        self._ms_assignee_id: Optional[int] = _sb_ms.get("my_shots_last_human_user_id")
        if self._ms_assignee_id is not None:
            try:
                self._ms_assignee_id = int(self._ms_assignee_id)
            except (TypeError, ValueError):
                self._ms_assignee_id = None
        self._ms_user_after: str = ""
        self._ms_rows_data: list = []
        self._ms_row_widgets: list = []
        self._ms_thumb_refs: list = []
        # My Shots Dashboard 확장 변수
        self._ms_project_id: Optional[int] = None
        self.ms_project_var = tk.StringVar(value="-- 프로젝트 선택 --")
        self._ms_all_rows_data: list = []      # 전체 샷 데이터 (타일 필터 전)
        self._ms_status_filter: Optional[str] = None  # 현재 선택된 상태 타일
        self._ms_notes_data: list = []
        self._ms_note_widgets: list = []
        self._ms_status_tile_widgets: list = []
        self._ms_projects_cache: list = []     # 프로젝트 목록 캐시
        self._ms_last_note_shot_ids: list = []
        self._ms_thumb_workers_started: bool = False
        self._ms_thumb_gen: int = 0
        self._ms_shots_req_seq: int = 0
        self._ms_notes_req_seq: int = 0
        self._ms_projects_req_seq: int = 0
        self._ms_refresh_btn: Optional[ctk.CTkButton] = None

    # ─────────────────────────────── UI Build ───────────────────────
    def _build_ui(self) -> None:
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=SIDEBAR_BG)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Content area
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        self.content.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_pages()
        self._show_page("preset")

    # ── Sidebar ─────────────────────────────────────────────────────
    def _build_sidebar(self) -> None:
        sb = self.sidebar

        # Brand
        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(28, 12))
        ctk.CTkLabel(brand, text="BELUCA", font=self.F_BRAND, text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(brand, text="Pipeline Engine", font=self.F_SMALL, text_color=TEXT_DIM).pack(anchor="w")

        # Divider
        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=(4, 12))

        # Nav
        nav = ctk.CTkFrame(sb, fg_color="transparent")
        nav.pack(fill="x", padx=8)

        self._nav_preset = self._nav_btn(nav, "  Preset Manager", lambda: self._show_page("preset"))
        self._nav_preset.pack(fill="x", pady=2)
        self._nav_shot = self._nav_btn(nav, "  Shot Builder", lambda: self._show_page("shot"))
        self._nav_shot.pack(fill="x", pady=2)
        self._nav_my_shots = self._nav_btn(nav, "  My Tasks", lambda: self._show_page("my_shots"))
        self._nav_my_shots.pack(fill="x", pady=2)
        self._nav_sg = self._nav_btn(nav, "  Publish", lambda: self._show_page("shotgrid"))
        self._nav_sg.pack(fill="x", pady=2)
        self._nav_tools = self._nav_btn(nav, "  Tools", lambda: self._show_page("tools"))
        self._nav_tools.pack(fill="x", pady=2)

        # Footer
        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(side="bottom", fill="x", padx=12)
        footer = ctk.CTkFrame(sb, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=16, pady=12)
        ctk.CTkLabel(
            footer, text=f"BPE v{self.app_version}",
            font=self.F_SMALL, text_color=TEXT_DIM,
        ).pack(anchor="w")

    def _nav_btn(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, anchor="w", height=42, corner_radius=8,
            fg_color="transparent", text_color=TEXT_DIM, hover_color=SELECT_BG,
            font=self.F_NAV, command=command,
        )

    def _show_page(self, page: str) -> None:
        for attr in (
            "_page_preset",
            "_page_shot",
            "_page_my_shots",
            "_page_shotgrid",
            "_page_tools",
        ):
            p = getattr(self, attr, None)
            if p:
                p.pack_forget()

        # Nav highlight
        nav_map = {
            "preset": self._nav_preset,
            "shot":   self._nav_shot,
            "my_shots": self._nav_my_shots,
            "shotgrid": self._nav_sg,
            "tools":  self._nav_tools,
        }
        for name, btn in nav_map.items():
            active = (name == page)
            btn.configure(
                fg_color=ACCENT if active else "transparent",
                text_color="#111111" if active else TEXT_DIM,
            )

        page_map = {
            "preset": self._page_preset,
            "shot":   self._page_shot,
            "my_shots": self._page_my_shots,
            "shotgrid": self._page_shotgrid,
            "tools":  self._page_tools,
        }
        page_map[page].pack(fill="both", expand=True)

    # ── Pages ────────────────────────────────────────────────────────
    def _build_pages(self) -> None:
        self._page_preset = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_preset_page(self._page_preset)
        self._page_shot = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_shot_page(self._page_shot)
        self._page_my_shots = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_my_shots_page(self._page_my_shots)
        self._page_shotgrid = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_shotgrid_page(self._page_shotgrid)
        self._page_tools = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_tools_page(self._page_tools)

    # ────────────── PRESET MANAGER PAGE ────────────────────────────
    def _build_preset_page(self, parent) -> None:
        # Page header
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(24, 0))
        ctk.CTkLabel(hdr, text="Preset Manager", font=self.F_TITLE, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(
            hdr,
            text="프로젝트별 Nuke 세팅을 저장하고 팀과 공유하세요",
            font=self.F_SMALL, text_color=TEXT_DIM,
        ).pack(side="left", padx=(16, 0))

        # Two-column layout + 하단 노드 트리 편집 영역(팝업 없이 동일 기능)
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=0)

        self._build_form_col(body)
        self._build_list_col(body)
        self._build_node_tree_embed(body)

    # ── Form Column (left) ───────────────────────────────────────────
    def _build_form_col(self, parent) -> None:
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color=PANEL_BG, corner_radius=12,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SELECT_BG,
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        scroll.columnconfigure(1, weight=1)

        def section(row: int, text: str) -> None:
            ctk.CTkLabel(
                scroll, text=text, font=self.F_HEAD, text_color=TEXT, anchor="w",
            ).grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 0))
            ctk.CTkFrame(scroll, height=1, fg_color=BORDER).grid(
                row=row + 1, column=0, columnspan=2, sticky="ew", padx=20, pady=(6, 8),
            )

        def label(row: int, text: str) -> None:
            ctk.CTkLabel(scroll, text=text, font=self.F_LABEL, text_color=TEXT_DIM, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(20, 10), pady=(10, 2),
            )

        def combo(row: int, var: tk.StringVar, values: list, state: str = "readonly", cmd=None) -> ctk.CTkComboBox:
            kw = {}
            if cmd:
                kw["command"] = cmd
            cb = ctk.CTkComboBox(
                scroll, variable=var, values=values, state=state,
                fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
                button_color=BORDER, button_hover_color=SELECT_BG,
                dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
                dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
                **kw,
            )
            cb.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
            return cb

        def entry(row: int, var: tk.StringVar, placeholder: str = "", state: str = "normal") -> ctk.CTkEntry:
            kw = {"placeholder_text": placeholder} if placeholder else {}
            e = ctk.CTkEntry(
                scroll, textvariable=var, state=state,
                fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
                **kw,
            )
            e.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
            return e

        r = 0

        # ── PROJECT ──────────────────────────────────────────────
        section(r, "프로젝트 정보"); r += 2

        label(r, "프로젝트 타입 *")
        self.project_type_seg = ctk.CTkSegmentedButton(
            scroll, values=["드라마(OTT)", "영화", "광고", "기타"],
            variable=self.project_type_var,
            fg_color=SELECT_BG, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOV, unselected_color=SELECT_BG,
            unselected_hover_color=HOVER, text_color=TEXT, font=self.F_SEG,
        )
        self.project_type_seg.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        r += 1

        label(r, "프로젝트 코드 *")
        self.project_code_entry = entry(r, self.project_code_var, placeholder="예) SBS_030 (영문 대문자/숫자/_)")
        r += 1

        # 네이밍 컨벤션 안내
        ctk.CTkLabel(
            scroll,
            text="⚑  서버에 있는 프로젝트 폴더 이름과 반드시 똑같이 입력하세요.\n"
                 "    Shot Builder가 이 이름으로 서버 폴더를 찾아 NK를 생성합니다.",
            font=self.F_SMALL, text_color="#c08020", anchor="w", justify="left", wraplength=320,
        ).grid(row=r, column=1, sticky="w", padx=(0, 20), pady=(0, 10))
        r += 1

        label(r, "FPS *")
        self.fps_combo = combo(r, self.fps_var, ["23.976", "24", "25", "29.97", "30", "50", "59.94", "60"])
        r += 1

        label(r, "프로젝트 포맷 *")
        fmt_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        fmt_wrap.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        fmt_wrap.columnconfigure(0, weight=1)
        self.plate_choice_combo = ctk.CTkComboBox(
            fmt_wrap, variable=self.plate_format_choice_var,
            values=list(self.plate_preset_to_wh.keys()), state="readonly",
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
            command=self._on_plate_choice_selected,
        )
        self.plate_choice_combo.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        wh = ctk.CTkFrame(fmt_wrap, fg_color="transparent")
        wh.grid(row=1, column=0, columnspan=3, sticky="ew")
        wh.columnconfigure(0, weight=1); wh.columnconfigure(2, weight=1)
        self.plate_width_entry = ctk.CTkEntry(
            wh, textvariable=self.plate_width_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
        )
        self.plate_width_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(wh, text="×", font=self.F_LABEL, text_color=TEXT_DIM).grid(row=0, column=1, padx=8)
        self.plate_height_entry = ctk.CTkEntry(
            wh, textvariable=self.plate_height_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
        )
        self.plate_height_entry.grid(row=0, column=2, sticky="ew")
        for _e in (self.plate_width_entry, self.plate_height_entry):
            _e.bind("<FocusOut>", lambda _ev: self._sync_plate_choice_from_dimensions())
            _e.bind("<Return>", lambda _ev: self._sync_plate_choice_from_dimensions())
        self.plate_width_var.trace_add("write", lambda *_: self._schedule_plate_choice_sync())
        self.plate_height_var.trace_add("write", lambda *_: self._schedule_plate_choice_sync())
        r += 1

        label(r, "OCIO Config *")
        ocio_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        ocio_wrap.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        ocio_wrap.columnconfigure(0, weight=1)
        self.ocio_combo = ctk.CTkComboBox(
            ocio_wrap, variable=self.ocio_path_var,
            values=self.ocio_configs or [""], state="normal",
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
        )
        self.ocio_combo.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            ocio_wrap, text="찾아보기", width=80, height=32,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._browse_ocio,
        ).grid(row=0, column=1, padx=(6, 0))
        self.ocio_status_lbl = ctk.CTkLabel(
            ocio_wrap, text="", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        )
        self.ocio_status_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.ocio_path_var.trace_add("write", lambda *_: self._update_ocio_status())
        r += 1

        # ── READ INPUT TRANSFORM ────────────────────────────────
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).grid(
            row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 0)); r += 1
        read_hdr = ctk.CTkFrame(scroll, fg_color="transparent")
        read_hdr.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 4)); r += 1
        ctk.CTkLabel(read_hdr, text="Read Input Transform", font=self.F_HEAD, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(
            read_hdr, text="(Read 노드 colorspace)", font=self.F_SMALL, text_color=TEXT_DIM,
        ).pack(side="left", padx=(8, 0))

        read_wrap = ctk.CTkFrame(scroll, fg_color="transparent")
        read_wrap.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 4))
        read_wrap.columnconfigure(1, weight=1)
        r += 1

        ctk.CTkLabel(
            read_wrap, text="카테고리", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        self.read_cat_combo = ctk.CTkComboBox(
            read_wrap,
            variable=self.read_cs_cat_var,
            values=list(READ_COLORSPACE_CATALOG.keys()),
            state="readonly",
            width=200,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
            command=self._on_read_cs_cat_selected,
        )
        self.read_cat_combo.grid(row=0, column=1, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(
            read_wrap, text="Colorspace", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.read_cs_combo = ctk.CTkComboBox(
            read_wrap,
            variable=self.read_input_transform_var,
            values=READ_COLORSPACE_CATALOG.get("ACES", []),
            state="normal",
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
        )
        self.read_cs_combo.grid(row=1, column=1, sticky="ew")

        ctk.CTkLabel(
            scroll,
            text="  직접 입력도 가능합니다. OCIO 캐시가 있으면 Nuke의 실제 목록이 반영됩니다.",
            font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).grid(row=r, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 8))
        r += 1

        # ── WRITE ──────────────────────────────────────────────
        ctk.CTkFrame(scroll, height=1, fg_color=BORDER).grid(
            row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 0)); r += 1
        write_hdr = ctk.CTkFrame(scroll, fg_color="transparent")
        write_hdr.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 4)); r += 1
        ctk.CTkLabel(write_hdr, text="Write 설정", font=self.F_HEAD, text_color=TEXT).pack(side="left")
        self.write_toggle_cb = ctk.CTkCheckBox(
            write_hdr, text="사용", variable=self.write_open_var,
            command=self._toggle_write_frame,
            checkbox_width=20, checkbox_height=20,
            fg_color=ACCENT, hover_color=ACCENT_HOV, border_color=BORDER, text_color=TEXT_DIM,
            font=self.F_SMALL,
        )
        self.write_toggle_cb.pack(side="right")

        self.write_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self.write_frame.grid(row=r, column=0, columnspan=2, sticky="ew", padx=20)
        self.write_frame.columnconfigure(1, weight=1)
        r += 1

        def wlabel(wr: int, text: str) -> None:
            ctk.CTkLabel(
                self.write_frame, text=text, font=self.F_LABEL, text_color=TEXT_DIM, anchor="w",
            ).grid(row=wr, column=0, sticky="w", padx=(0, 10), pady=(8, 2))

        def wcombo(wr: int, var: tk.StringVar, values: list, state: str = "readonly", cmd=None) -> ctk.CTkComboBox:
            kw = {}
            if cmd:
                kw["command"] = cmd
            cb = ctk.CTkComboBox(
                self.write_frame, variable=var, values=values, state=state,
                fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
                button_color=BORDER, button_hover_color=SELECT_BG,
                dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
                dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
                **kw,
            )
            cb.grid(row=wr, column=1, sticky="ew", pady=(8, 2))
            return cb

        def wentry(wr: int, var: tk.StringVar) -> ctk.CTkEntry:
            e = ctk.CTkEntry(
                self.write_frame, textvariable=var,
                fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
            )
            e.grid(row=wr, column=1, sticky="ew", pady=(8, 2))
            return e

        wr = 0
        wlabel(wr, "납품 포맷 *")
        self.delivery_format_combo = wcombo(wr, self.delivery_format_var, ["EXR 16bit", "EXR 32bit", "ProRes 422 HQ", "DNxHR HQX", "H264 MP4"]); wr += 1
        wlabel(wr, "Channels *")
        self.write_channels_combo = wcombo(wr, self.write_channels_var, self.write_channels_options); wr += 1
        wlabel(wr, "Datatype *")
        self.write_datatype_combo = wcombo(wr, self.write_datatype_var, self.write_datatype_options); wr += 1
        wlabel(wr, "Compression *")
        self.write_compression_combo = wcombo(wr, self.write_compression_var, self.write_compression_options); wr += 1
        wlabel(wr, "Metadata *")
        self.write_metadata_combo = wcombo(wr, self.write_metadata_var, self.write_metadata_options); wr += 1

        ctk.CTkLabel(
            self.write_frame, text="Output Transform",
            font=self.F_SUBHEAD,
            text_color=ACCENT, anchor="w",
        ).grid(row=wr, column=0, columnspan=2, sticky="w", pady=(14, 2)); wr += 1

        wlabel(wr, "Transform Type *")
        self.write_transform_type_combo = wcombo(
            wr, self.write_transform_type_var, self.write_transform_type_options,
            cmd=lambda v: self._update_output_transform_fields(),
        ); wr += 1

        wlabel(wr, "Output Transform")
        self.write_out_cs_entry = wentry(wr, self.write_out_colorspace_var); wr += 1
        wlabel(wr, "Display")
        self.write_display_entry = wentry(wr, self.write_output_display_var); wr += 1
        wlabel(wr, "View")
        self.write_view_entry = wentry(wr, self.write_output_view_var); wr += 1

        # bottom padding
        ctk.CTkLabel(scroll, text="", height=12).grid(row=r + 1, column=0)

        if not self.write_open_var.get():
            self.write_frame.grid_remove()

        self._update_output_transform_fields()

    # ── List Column (right) ─────────────────────────────────────────
    def _build_list_col(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=12)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        # Header
        ph = ctk.CTkFrame(panel, fg_color="transparent")
        ph.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        ctk.CTkLabel(ph, text="저장된 프리셋", font=self.F_HEAD, text_color=TEXT).pack(side="left")

        # Preset list
        self.preset_scroll = ctk.CTkScrollableFrame(
            panel, fg_color=INPUT_BG, corner_radius=8,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SELECT_BG,
        )
        self.preset_scroll.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.preset_scroll.columnconfigure(0, weight=1)

        # Load / Delete
        ld = ctk.CTkFrame(panel, fg_color="transparent")
        ld.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkButton(
            ld, text="불러오기", height=32,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._load_selected,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            ld, text="삭제", height=32,
            fg_color=SELECT_BG, hover_color="#5a1010", text_color="#ff6b6b", font=self.F_BTN,
            command=self._delete_preset,
        ).pack(side="left")

        # Divider
        ctk.CTkFrame(panel, height=1, fg_color=BORDER).grid(row=3, column=0, sticky="ew", padx=12, pady=4)

        # Folder section
        ff = ctk.CTkFrame(panel, fg_color="transparent")
        ff.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 0))
        ff.columnconfigure(0, weight=1)
        ctk.CTkLabel(ff, text="프리셋 저장 폴더", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ctk.CTkEntry(
            ff, textvariable=self.presets_dir_var, state="readonly",
            fg_color=INPUT_BG, border_color=BORDER,
            text_color=TEXT_DIM, font=self.F_MONO,
        ).grid(row=1, column=0, sticky="ew")
        ctk.CTkButton(
            ff, text="변경", width=48, height=30,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_SMALL,
            command=self._browse_presets_dir,
        ).grid(row=1, column=1, padx=(4, 0))
        self.open_presets_btn = ctk.CTkButton(
            ff, text="열기", width=44, height=30, state="disabled",
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_SMALL,
            command=self._open_presets_folder,
        )
        self.open_presets_btn.grid(row=1, column=2, padx=(4, 0))

        # ── 액션 버튼 영역 ─────────────────────────────────────────
        ctk.CTkFrame(panel, height=1, fg_color=BORDER).grid(
            row=5, column=0, sticky="ew", padx=12, pady=(12, 8))

        act = ctk.CTkFrame(panel, fg_color="transparent")
        act.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkButton(
            act, text="프로그램 업데이트", height=38,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._update_self_and_restart,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            act, text="프리셋 저장", height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111", font=self.F_BTN_EM,
            command=self._save_preset,
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkFrame(panel, height=1, fg_color=BORDER).grid(
            row=7, column=0, sticky="ew", padx=12, pady=(4, 8))

        nt_hdr = ctk.CTkFrame(panel, fg_color="transparent")
        nt_hdr.grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 4))
        nt_hdr.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            nt_hdr, text="커스텀 노드 트리", font=self.F_SMALL,
            text_color=TEXT_DIM, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.node_tree_status_lbl = ctk.CTkLabel(
            nt_hdr, text="● 기본", font=self.F_SMALL, text_color=TEXT_DIM, anchor="e",
        )
        self.node_tree_status_lbl.grid(row=0, column=1, sticky="e")
        self.node_tree_btn = ctk.CTkButton(
            panel, text="노드 트리 편집 (하단 패널)", height=32,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT_DIM, font=self.F_BTN,
            state="disabled",
            command=self._open_node_tree_editor,
        )
        self.node_tree_btn.grid(row=9, column=0, sticky="ew", padx=12, pady=(0, 8))

        ctk.CTkFrame(panel, height=1, fg_color=BORDER).grid(
            row=10, column=0, sticky="ew", padx=12, pady=(4, 8))

        ctk.CTkLabel(
            panel, text="NK로 프리셋 가져오기", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).grid(row=11, column=0, sticky="w", padx=12, pady=(0, 2))
        ctk.CTkLabel(
            panel,
            text="분석 후 아래 카드에서 프리셋 이름을 입력·생성합니다.",
            font=self.F_SMALL, text_color="#5a5a5e", anchor="w", justify="left",
        ).grid(row=12, column=0, sticky="ew", padx=12, pady=(0, 6))
        nk_row = ctk.CTkFrame(panel, fg_color="transparent")
        nk_row.grid(row=13, column=0, sticky="ew", padx=12, pady=(0, 6))
        nk_row.columnconfigure(0, weight=1)
        self.nk_import_entry = ctk.CTkEntry(
            nk_row, textvariable=self.nk_import_path_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_MONO,
            placeholder_text="NK 파일 경로를 입력하거나 찾아보기...",
        )
        self.nk_import_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            nk_row, text="찾아보기", width=72, height=32,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_SMALL,
            command=self._browse_nk_import,
        ).grid(row=0, column=1)
        ctk.CTkButton(
            panel, text="NK 분석하기", height=34,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._import_nk_as_preset,
        ).grid(row=14, column=0, sticky="ew", padx=12, pady=(0, 6))

        self.nk_import_feedback_lbl = ctk.CTkLabel(
            panel, text="", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        )
        self.nk_import_feedback_lbl.grid(row=15, column=0, sticky="ew", padx=12, pady=(0, 4))

        self.nk_review_panel = ctk.CTkFrame(
            panel, fg_color=INPUT_BG, corner_radius=10, border_width=1, border_color=BORDER,
        )
        self._build_nk_import_review_shell(self.nk_review_panel)
        self._nk_pending_path = ""
        self._nk_pending_parsed = None

    # ────────────── NK 가져오기 인라인 패널 ─────────────────────────
    def _build_nk_import_review_shell(self, root: ctk.CTkFrame) -> None:
        root.columnconfigure(0, weight=1)
        ctk.CTkLabel(
            root, text="NK 분석 결과", font=self.F_SUBHEAD, text_color=ACCENT, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 0))
        self.nk_review_file_lbl = ctk.CTkLabel(
            root, text="", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        )
        self.nk_review_file_lbl.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 6))

        self.nk_review_rows_host = ctk.CTkScrollableFrame(
            root, fg_color=PANEL_BG, corner_radius=8, height=200,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SELECT_BG,
        )
        self.nk_review_rows_host.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))
        root.rowconfigure(2, weight=1)

        ctk.CTkFrame(root, height=1, fg_color=BORDER).grid(
            row=3, column=0, sticky="ew", padx=10, pady=(4, 0))

        nm = ctk.CTkFrame(root, fg_color="transparent")
        nm.grid(row=4, column=0, sticky="ew", padx=12, pady=(10, 4))
        nm.columnconfigure(1, weight=1)
        ctk.CTkLabel(
            nm, text="프리셋 이름 *", font=self.F_LABEL, text_color=TEXT, anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            nm, text="코드", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        self.nk_review_name_entry = ctk.CTkEntry(
            nm, textvariable=self.nk_import_preset_name_var,
            fg_color=PANEL_BG, border_color=BORDER, text_color=TEXT, font=self.F_MONO,
            placeholder_text="예) SBS_030",
        )
        self.nk_review_name_entry.grid(row=1, column=1, sticky="ew", pady=2)
        self.nk_review_name_hint = ctk.CTkLabel(
            nm, text="", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        )
        self.nk_review_name_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ctk.CTkLabel(
            nm,
            text="미감지 항목은 기본값으로 채워집니다. 왼쪽 폼에서 확인·수정 후 필요 시 「프리셋 저장」으로 다시 기록하세요.",
            font=self.F_SMALL, text_color="#5a5a5e", anchor="w", justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.nk_review_duplicate_lbl = ctk.CTkLabel(
            nm, text="", font=self.F_SMALL, text_color="#ffb74d", anchor="w", justify="left",
        )
        self.nk_review_duplicate_lbl.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self.nk_review_overwrite_bar = ctk.CTkFrame(root, fg_color="#3d2a1a", corner_radius=8)
        ctk.CTkLabel(
            self.nk_review_overwrite_bar,
            text="같은 이름의 프리셋이 이미 있습니다. 진행하면 기존 설정·커스텀 노드 트리 연동이 NK 기준으로 덮어써집니다.",
            font=self.F_SMALL, text_color="#ffcc80", anchor="w", justify="left",
        ).pack(side="left", padx=12, pady=10, fill="x", expand=True)
        ow_btns = ctk.CTkFrame(self.nk_review_overwrite_bar, fg_color="transparent")
        ow_btns.pack(side="right", padx=8, pady=6)
        ctk.CTkButton(
            ow_btns, text="취소", width=72, height=28, font=self.F_SMALL,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT,
            command=self._nk_import_hide_overwrite_bar,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            ow_btns, text="덮어쓰기", width=88, height=28, font=self.F_SMALL,
            fg_color="#c62828", hover_color="#e53935", text_color="#ffffff",
            command=self._confirm_nk_import_overwrite,
        ).pack(side="right")

        btn_row = ctk.CTkFrame(root, fg_color="transparent")
        btn_row.grid(row=6, column=0, sticky="ew", padx=12, pady=(12, 12))
        ctk.CTkButton(
            btn_row, text="분석 숨기기", height=32, width=100,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._hide_nk_import_review,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            btn_row, text="Enter로 생성", font=self.F_SMALL, text_color="#5a5a5e",
        ).pack(side="left", padx=(0, 8))
        self.nk_review_confirm_btn = ctk.CTkButton(
            btn_row, text="프리셋 생성", height=32,
            fg_color=SELECT_BG, hover_color=SELECT_BG, text_color=TEXT_DIM, font=self.F_BTN_EM,
            state="disabled", command=self._confirm_nk_import_from_panel,
        )
        self.nk_review_confirm_btn.pack(side="right")

        self.nk_review_overwrite_bar.grid(row=5, column=0, sticky="ew", padx=12, pady=(8, 0))
        self.nk_review_overwrite_bar.grid_remove()

        self.nk_review_name_entry.bind("<Return>", self._on_nk_import_name_return)

        self._nk_name_trace_id = self.nk_import_preset_name_var.trace_add(
            "write", lambda *_: self._update_nk_import_confirm_state())

    def _nk_import_hide_overwrite_bar(self) -> None:
        if hasattr(self, "nk_review_overwrite_bar"):
            self.nk_review_overwrite_bar.grid_remove()

    def _on_nk_import_name_return(self, _event=None):
        try:
            st = self.nk_review_confirm_btn.cget("state")
        except Exception:
            st = "disabled"
        if st == "normal":
            self._confirm_nk_import_from_panel()
        return "break"

    def _update_nk_import_confirm_state(self) -> None:
        if not hasattr(self, "nk_review_confirm_btn"):
            return
        self._nk_import_hide_overwrite_bar()
        raw = (self.nk_import_preset_name_var.get() or "").strip()
        up = raw.upper()
        valid = bool(raw) and bool(re.fullmatch(r"[A-Za-z0-9_]+", raw))
        dup = valid and up in getattr(self, "presets", {})
        if hasattr(self, "nk_review_duplicate_lbl"):
            if dup:
                self.nk_review_duplicate_lbl.configure(
                    text=f"⚠  '{up}' 프리셋이 이미 있습니다. 생성 시 기존 데이터가 교체됩니다.",
                )
            else:
                self.nk_review_duplicate_lbl.configure(text="")
        if valid:
            self.nk_review_confirm_btn.configure(
                state="normal",
                fg_color=ACCENT,
                hover_color=ACCENT_HOV,
                text_color="#111111",
                text="기존 프리셋 덮어쓰기" if dup else "프리셋 생성",
            )
            self.nk_review_name_hint.configure(
                text=f"✓  '{up}' 로 저장됩니다" + (" — 덮어쓰기 전에 한 번 더 확인합니다" if dup else ""),
                text_color="#ffb74d" if dup else "#4CAF50",
            )
            self.nk_review_name_entry.configure(border_color=("#ffb74d" if dup else ACCENT))
        else:
            self.nk_review_confirm_btn.configure(
                state="disabled",
                fg_color=SELECT_BG,
                hover_color=SELECT_BG,
                text_color=TEXT_DIM,
                text="프리셋 생성",
            )
            if raw and not re.fullmatch(r"[A-Za-z0-9_]+", raw):
                self.nk_review_name_hint.configure(
                    text="영문·숫자·_ 만 사용 (대소문자 무관, 저장 시 대문자로 통일)",
                    text_color="#CF6679",
                )
                self.nk_review_name_entry.configure(border_color="#CF6679")
            else:
                self.nk_review_name_hint.configure(
                    text="프리셋 코드를 입력하세요 (예: SBS_030)",
                    text_color=TEXT_DIM,
                )
                self.nk_review_name_entry.configure(border_color=BORDER)

    def _clear_nk_review_rows(self) -> None:
        if not hasattr(self, "nk_review_rows_host"):
            return
        for w in self.nk_review_rows_host.winfo_children():
            w.destroy()

    def _fmt_nk_ocio_name(self, p) -> str:
        if not p:
            return "미감지"
        try:
            return Path(p).name
        except Exception:
            return str(p)

    def _populate_nk_review_rows(self, d: dict) -> None:
        self._clear_nk_review_rows()
        host = self.nk_review_rows_host
        rows = [
            ("FPS",                  d.get("fps") or "미감지"),
            ("해상도",               f"{d.get('plate_width', '?')} × {d.get('plate_height', '?')}"
                                     if d.get("plate_width") and d.get("plate_height") else "미감지"),
            ("OCIO Config",          self._fmt_nk_ocio_name(d.get("ocio_path"))),
            ("Read Input Transform", d.get("read_input_transform") or "미감지"),
            ("납품 포맷",            d.get("delivery_format") or "미감지"),
            ("Channels",             d.get("write_channels") or "미감지"),
            ("Datatype",             d.get("write_datatype") or "미감지"),
            ("Compression",          d.get("write_compression") or "미감지"),
            ("Metadata",             d.get("write_metadata") or "미감지"),
            ("Transform Type",       d.get("write_transform_type") or "미감지"),
            ("Output Transform",     d.get("write_out_colorspace") or "미감지"),
            ("Display",              d.get("write_output_display") or "미감지"),
            ("View",                 d.get("write_output_view") or "미감지"),
        ]
        for label, value in rows:
            detected = value not in ("미감지", "? × ?")
            row = ctk.CTkFrame(host, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row, text=label, font=self.F_SMALL, text_color=TEXT_DIM, width=118, anchor="w",
            ).pack(side="left", padx=(4, 4))
            val_c = ACCENT if detected else "#555558"
            ctk.CTkLabel(
                row, text=str(value), font=self.F_SMALL, text_color=val_c,
                anchor="w", justify="left",
            ).pack(side="left", fill="x", expand=True)

    def _hide_nk_import_review(self, clear_feedback: bool = True) -> None:
        if hasattr(self, "nk_review_panel"):
            self.nk_review_panel.grid_remove()
        self._nk_pending_path = ""
        self._nk_pending_parsed = None
        self.nk_import_preset_name_var.set("")
        if clear_feedback and hasattr(self, "nk_import_feedback_lbl"):
            self.nk_import_feedback_lbl.configure(text="")

    def _show_nk_import_review(self, nk_path: str, parsed: dict) -> None:
        self._nk_pending_path = nk_path
        self._nk_pending_parsed = parsed
        self.nk_import_preset_name_var.set("")
        self.nk_review_file_lbl.configure(text=f"파일: {Path(nk_path).name}")
        self._populate_nk_review_rows(parsed)
        self.nk_review_panel.grid(row=16, column=0, sticky="nsew", padx=12, pady=(0, 14))
        self._update_nk_import_confirm_state()
        if hasattr(self, "nk_import_feedback_lbl"):
            self.nk_import_feedback_lbl.configure(
                text="✓  분석 완료 — 이름 입력 후 「프리셋 생성」",
                text_color=ACCENT,
            )
        try:
            self.nk_review_name_entry.focus_set()
        except Exception:
            pass

    def _confirm_nk_import_from_panel(self) -> None:
        if not self._nk_pending_parsed:
            return
        name = (self.nk_import_preset_name_var.get() or "").strip().upper()
        if not name or not re.fullmatch(r"[A-Z0-9_]+", name):
            return
        if name in self.presets:
            ow_gi = {}
            try:
                ow_gi = self.nk_review_overwrite_bar.grid_info()
            except tk.TclError:
                ow_gi = {}
            if not ow_gi:
                self.nk_review_overwrite_bar.grid(
                    row=5, column=0, sticky="ew", padx=12, pady=(8, 0))
                if hasattr(self, "nk_import_feedback_lbl"):
                    self.nk_import_feedback_lbl.configure(
                        text="덮어쓰기를 진행하려면 주황색 영역의 「덮어쓰기」를 누르세요.",
                        text_color="#ffb74d",
                    )
                return
            return
        self._nk_import_hide_overwrite_bar()
        self._on_nk_import_confirm(name, self._nk_pending_parsed)

    def _confirm_nk_import_overwrite(self) -> None:
        if not self._nk_pending_parsed:
            return
        name = (self.nk_import_preset_name_var.get() or "").strip().upper()
        if not name or not re.fullmatch(r"[A-Z0-9_]+", name):
            return
        self._nk_import_hide_overwrite_bar()
        self._on_nk_import_confirm(name, self._nk_pending_parsed)

    # ────────────── 노드 트리 인라인 패널 (Preset 페이지 하단) ───────
    def _build_node_tree_embed(self, body: ctk.CTkFrame) -> None:
        self.node_tree_embed = ctk.CTkFrame(body, fg_color=PANEL_BG, corner_radius=12)
        self.node_tree_embed.columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self.node_tree_embed, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 0))
        hdr.columnconfigure(0, weight=1)
        self.node_tree_editor_title = ctk.CTkLabel(
            hdr, text="커스텀 노드 트리", font=self.F_HEAD, text_color=TEXT, anchor="w",
        )
        self.node_tree_editor_title.grid(row=0, column=0, sticky="w")
        self.node_tree_editor_status_lbl = ctk.CTkLabel(
            hdr, text="", font=self.F_SMALL, text_color=TEXT_DIM, anchor="e",
        )
        self.node_tree_editor_status_lbl.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            hdr, text="패널 접기", width=88, height=30,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_SMALL,
            command=self._close_node_tree_editor,
        ).grid(row=0, column=2, padx=(12, 0))

        ctk.CTkFrame(self.node_tree_embed, height=1, fg_color=BORDER).grid(
            row=1, column=0, sticky="ew", padx=12, pady=(10, 0))

        info = ctk.CTkFrame(self.node_tree_embed, fg_color=INPUT_BG, corner_radius=8)
        info.grid(row=2, column=0, sticky="ew", padx=12, pady=(10, 0))
        self.node_tree_dirty_lbl_info = ctk.CTkLabel(
            info,
            text="",
            font=self.F_SMALL, text_color="#ffb74d", anchor="w", justify="left",
        )
        self.node_tree_dirty_lbl_info.pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            info,
            text="Nuke에서 노드 전체 선택(Ctrl+A) → 복사(Ctrl+C) 후 아래에 붙여넣기. "
                 "Shot Builder가 이 스크립트로 NK를 만듭니다.\n"
                 "※ 목록에서 다른 프리셋을 누르면 저장하지 않은 편집은 적용되지 않고 해당 프리셋 내용으로 바뀝니다.",
            font=self.F_SMALL, text_color=TEXT_DIM, justify="left", anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 4))
        ph_row = ctk.CTkFrame(info, fg_color="transparent")
        ph_row.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(
            ph_row, text="플레이스홀더 안내", height=26, width=140,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT_DIM, font=self.F_SMALL,
            command=self._toggle_node_tree_placeholder_help,
        ).pack(side="left")
        self.node_tree_ph_frame = ctk.CTkFrame(info, fg_color=PANEL_BG, corner_radius=6)
        self._node_tree_ph_visible = False
        tb = ctk.CTkTextbox(
            self.node_tree_ph_frame, height=168, fg_color=INPUT_BG, text_color=TEXT_DIM,
            font=self.F_MONO, border_color=BORDER, border_width=1, corner_radius=6,
            wrap="word",
        )
        ph_txt = (
            "템플릿 NK에 아래 문자열을 그대로 넣어두면, NK 생성 시 Shot Builder가\n"
            "서버 루트·프로젝트 코드·샷 이름으로 계산한 실제 값으로 바꿉니다.\n"
            "※ 아래 경로·샷명은 예시(고정 치환 키)일 뿐이며, 다른 프로젝트·다른 샷에도\n"
            "   동일하게 동작합니다.\n\n"
            "예시 샷 루트 (템플릿에 이렇게 적으면 → 생성 시 실제 샷 루트로 치환):\n"
            f"{_TEMPLATE_SAMPLE_SHOT_ROOT}\n\n"
            "예시 샷 이름 (템플릿에 이렇게 적으면 → 생성 시 입력한 샷 이름으로 치환):\n"
            f"{_TEMPLATE_SAMPLE_SHOT_NAME}\n"
        )
        tb.insert("1.0", ph_txt)
        tb.configure(state="disabled")
        tb.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(
            self.node_tree_embed, text="NK 스크립트", font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).grid(row=3, column=0, sticky="nw", padx=16, pady=(10, 2))
        self.node_tree_text_box = ctk.CTkTextbox(
            self.node_tree_embed, fg_color=INPUT_BG, text_color=TEXT, font=self.F_MONO,
            border_color=BORDER, border_width=1, corner_radius=8, wrap="none",
        )
        self.node_tree_text_box.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self.node_tree_embed.rowconfigure(4, weight=1)

        self.node_tree_unsaved_close_bar = ctk.CTkFrame(self.node_tree_embed, fg_color="#2a2540", corner_radius=8)
        ctk.CTkLabel(
            self.node_tree_unsaved_close_bar,
            text="저장하지 않은 변경이 있습니다. 어떻게 할까요?",
            font=self.F_SMALL, text_color="#d1c4e9", anchor="w", justify="left",
        ).pack(side="left", padx=12, pady=10, fill="x", expand=True)
        ucb = ctk.CTkFrame(self.node_tree_unsaved_close_bar, fg_color="transparent")
        ucb.pack(side="right", padx=8, pady=6)
        ctk.CTkButton(
            ucb, text="취소", width=72, height=28, font=self.F_SMALL,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT,
            command=self._node_tree_cancel_unsaved_close,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            ucb, text="버리고 닫기", width=96, height=28, font=self.F_SMALL,
            fg_color=SELECT_BG, hover_color="#5a1010", text_color="#ff8a80",
            command=self._node_tree_discard_and_close,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            ucb, text="저장 후 닫기", width=104, height=28, font=self.F_SMALL,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111",
            command=self._node_tree_save_and_close,
        ).pack(side="right")

        self.node_tree_clear_bar = ctk.CTkFrame(self.node_tree_embed, fg_color="#3a2020", corner_radius=8)
        ctk.CTkLabel(
            self.node_tree_clear_bar,
            text="기본 템플릿(shot_node_template.nk)으로 되돌릴까요? 커스텀 내용이 삭제됩니다.",
            font=self.F_SMALL, text_color="#ffccbc", anchor="w",
        ).pack(side="left", padx=12, pady=8)
        cf = ctk.CTkFrame(self.node_tree_clear_bar, fg_color="transparent")
        cf.pack(side="right", padx=8, pady=6)
        ctk.CTkButton(
            cf, text="아니오", width=72, height=28, font=self.F_SMALL,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT,
            command=self._node_tree_cancel_clear,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            cf, text="예", width=72, height=28, font=self.F_SMALL,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111",
            command=self._node_tree_do_clear,
        ).pack(side="right")

        btn_row = ctk.CTkFrame(self.node_tree_embed, fg_color="transparent")
        btn_row.grid(row=6, column=0, sticky="ew", padx=12, pady=(4, 14))
        ctk.CTkButton(
            btn_row, text="파일에서 불러오기", height=36,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._node_tree_load_from_file,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="기본 템플릿으로 초기화", height=36,
            fg_color=SELECT_BG, hover_color="#5a1010", text_color="#ff6b6b", font=self.F_BTN,
            command=self._node_tree_request_clear,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="저장", height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111", font=self.F_BTN_EM,
            command=self._node_tree_save_embedded,
        ).pack(side="right")
        ctk.CTkLabel(
            btn_row, text="편집 중 Ctrl+S → 이 템플릿만 저장", font=self.F_SMALL, text_color="#5a5a5e",
        ).pack(side="right", padx=(0, 12))

        self._node_tree_editing_preset = ""
        self._node_tree_baseline_content = ""
        self._node_tree_dirty = False
        self.node_tree_clear_bar.grid_remove()
        self.node_tree_unsaved_close_bar.grid_remove()
        self.node_tree_text_box.bind("<KeyRelease>", lambda _e: self._node_tree_recompute_dirty())
        try:
            self.node_tree_text_box.bind("<<Paste>>", lambda _e: self.after(80, self._node_tree_recompute_dirty))
        except tk.TclError:
            pass
        try:
            self.node_tree_text_box.bind("<Control-s>", self._node_tree_ctrl_s_save)
            self.node_tree_text_box.bind("<Control-S>", self._node_tree_ctrl_s_save)
        except Exception:
            pass

    def _node_tree_set_baseline_from_editor(self) -> None:
        if not hasattr(self, "node_tree_text_box"):
            return
        self._node_tree_baseline_content = self.node_tree_text_box.get("1.0", "end-1c")
        self._node_tree_dirty = False
        if hasattr(self, "node_tree_dirty_lbl_info"):
            self.node_tree_dirty_lbl_info.configure(text="")

    def _node_tree_recompute_dirty(self) -> None:
        if not getattr(self, "_node_tree_editing_preset", ""):
            return
        if not hasattr(self, "node_tree_text_box"):
            return
        cur = self.node_tree_text_box.get("1.0", "end-1c")
        self._node_tree_dirty = cur != self._node_tree_baseline_content
        if hasattr(self, "node_tree_dirty_lbl_info"):
            if self._node_tree_dirty:
                self.node_tree_dirty_lbl_info.configure(
                    text="● 저장되지 않은 변경이 있습니다. 「저장」 또는 Ctrl+S (이 패널에 포커스일 때만)",
                )
            else:
                self.node_tree_dirty_lbl_info.configure(text="")

    def _node_tree_ctrl_s_save(self, _event=None):
        if getattr(self, "_node_tree_editing_preset", ""):
            self._node_tree_save_embedded()
        return "break"

    def _node_tree_cancel_unsaved_close(self) -> None:
        self.node_tree_unsaved_close_bar.grid_remove()

    def _finalize_node_tree_close(self) -> None:
        self.node_tree_unsaved_close_bar.grid_remove()
        self.node_tree_clear_bar.grid_remove()
        body = self.node_tree_embed.master
        body.rowconfigure(1, weight=0)
        self.node_tree_embed.grid_remove()
        self._node_tree_editing_preset = ""
        self._node_tree_baseline_content = ""
        self._node_tree_dirty = False
        if hasattr(self, "node_tree_dirty_lbl_info"):
            self.node_tree_dirty_lbl_info.configure(text="")

    def _node_tree_discard_and_close(self) -> None:
        self.node_tree_unsaved_close_bar.grid_remove()
        self._finalize_node_tree_close()

    def _node_tree_save_and_close(self) -> None:
        was_dirty = getattr(self, "_node_tree_dirty", False)
        if not was_dirty:
            self.node_tree_unsaved_close_bar.grid_remove()
            self._finalize_node_tree_close()
            return
        self._node_tree_save_embedded()
        if not getattr(self, "_node_tree_dirty", False):
            self.node_tree_unsaved_close_bar.grid_remove()
            self._finalize_node_tree_close()

    def _toggle_node_tree_placeholder_help(self) -> None:
        self._node_tree_ph_visible = not self._node_tree_ph_visible
        if self._node_tree_ph_visible:
            self.node_tree_ph_frame.pack(fill="x", padx=8, pady=(0, 8))
        else:
            self.node_tree_ph_frame.pack_forget()

    def _node_tree_request_clear(self) -> None:
        self.node_tree_unsaved_close_bar.grid_remove()
        self.node_tree_clear_bar.grid(row=5, column=0, sticky="ew", padx=12, pady=(6, 0))

    def _node_tree_cancel_clear(self) -> None:
        self.node_tree_clear_bar.grid_remove()

    def _node_tree_do_clear(self) -> None:
        name = self._node_tree_editing_preset
        if not name:
            self.node_tree_clear_bar.grid_remove()
            return
        delete_preset_template(name)
        self.node_tree_text_box.delete("1.0", "end")
        self.node_tree_editor_status_lbl.configure(text="● 기본 템플릿 사용 중", text_color=TEXT_DIM)
        self.node_tree_clear_bar.grid_remove()
        self._node_tree_set_baseline_from_editor()
        self._update_node_tree_status()

    def _node_tree_load_from_file(self) -> None:
        path = _ask_file_modal(
            self,
            title="NK 파일 선택",
            filetypes=[("Nuke Script", "*.nk"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            self.node_tree_text_box.delete("1.0", "end")
            self.node_tree_text_box.insert("1.0", content)
            self.node_tree_editor_status_lbl.configure(text="파일에서 불러옴 (저장 시 프리셋에 적용)", text_color=ACCENT)
            self._node_tree_set_baseline_from_editor()
        except Exception as e:
            self.node_tree_editor_status_lbl.configure(text=f"읽기 실패: {e}", text_color="#e05252")

    def _node_tree_save_embedded(self) -> None:
        name = self._node_tree_editing_preset
        if not name:
            return
        content = self.node_tree_text_box.get("1.0", "end-1c").strip()
        if not content:
            self.node_tree_editor_status_lbl.configure(
                text="내용이 비어 있습니다. 붙여넣거나 파일을 불러오세요.",
                text_color="#e05252",
            )
            return
        try:
            save_preset_template(name, content)
        except Exception as e:
            self.node_tree_editor_status_lbl.configure(text=f"저장 실패: {e}", text_color="#e05252")
            return
        lines = len(content.splitlines())
        self.node_tree_editor_status_lbl.configure(
            text=f"✓ 저장 완료 ({lines}줄) — '{name}'",
            text_color=ACCENT,
        )
        self._node_tree_set_baseline_from_editor()
        self._update_node_tree_status()

    def _node_tree_load_template_for_preset(self, preset_name: str) -> None:
        self._node_tree_editing_preset = preset_name
        self.node_tree_text_box.delete("1.0", "end")
        content = load_preset_template(preset_name)
        if content:
            self.node_tree_text_box.insert("1.0", content)
            lines = len(content.splitlines())
            self.node_tree_editor_status_lbl.configure(
                text=f"✓ 커스텀 적용됨 ({lines}줄)", text_color=ACCENT)
        else:
            self.node_tree_editor_status_lbl.configure(
                text="● 기본 템플릿 사용 중 — 아래에 붙여넣고 저장하면 커스텀으로 전환",
                text_color=TEXT_DIM,
            )
        self.node_tree_editor_title.configure(text=f"커스텀 노드 트리 — {preset_name}")
        self.node_tree_clear_bar.grid_remove()
        self.node_tree_unsaved_close_bar.grid_remove()
        self._node_tree_ph_visible = False
        try:
            self.node_tree_ph_frame.pack_forget()
        except Exception:
            pass
        self._node_tree_set_baseline_from_editor()

    def _open_node_tree_editor(self) -> None:
        name = self._selected_preset
        if not name:
            messagebox.showwarning("BPE", "프리셋을 먼저 선택하세요.")
            return
        body = self.node_tree_embed.master
        body.rowconfigure(1, weight=2)
        self.node_tree_embed.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        self._node_tree_load_template_for_preset(name)
        self.after(50, lambda: self.node_tree_text_box.focus_set())

    def _close_node_tree_editor(self) -> None:
        self.node_tree_unsaved_close_bar.grid_remove()
        if getattr(self, "_node_tree_dirty", False):
            self.node_tree_clear_bar.grid_remove()
            self.node_tree_unsaved_close_bar.grid(
                row=5, column=0, sticky="ew", padx=12, pady=(6, 0))
            return
        self._finalize_node_tree_close()

    # ────────────── SHOT BUILDER PAGE ───────────────────────────────
    def _build_shot_page(self, parent) -> None:
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(24, 0))
        ctk.CTkLabel(hdr, text="Shot Builder", font=self.F_TITLE, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(
            hdr, text="샷 이름 하나로 NK 파일 + 경로 자동 생성",
            font=self.F_SMALL, text_color=TEXT_DIM,
        ).pack(side="left", padx=(16, 0))

        card = ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=12)
        card.pack(fill="both", expand=True, padx=20, pady=12)
        card.columnconfigure(0, minsize=140)
        card.columnconfigure(1, weight=1)

        def step_label(row: int, text: str) -> None:
            ctk.CTkLabel(
                card, text=text, font=self.F_SUBHEAD,
                text_color=ACCENT, anchor="w",
            ).grid(row=row, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 4))

        def label(row: int, text: str) -> None:
            ctk.CTkLabel(card, text=text, font=self.F_LABEL, text_color=TEXT_DIM, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(20, 10), pady=(10, 2))

        def entry(row: int, var: tk.StringVar, placeholder: str = "") -> ctk.CTkEntry:
            kw = {"placeholder_text": placeholder} if placeholder else {}
            e = ctk.CTkEntry(
                card, textvariable=var,
                fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
                **kw,
            )
            e.grid(row=row, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
            return e

        r = 0

        # STEP 1
        step_label(r, "STEP 1   서버 설정"); r += 1

        label(r, "서버 루트 경로 *")
        srv = ctk.CTkFrame(card, fg_color="transparent")
        srv.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        srv.columnconfigure(0, weight=1)
        self.sb_server_root_entry = ctk.CTkEntry(
            srv, textvariable=self.sb_server_root_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
        )
        self.sb_server_root_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            srv, text="찾아보기", width=80, height=32,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._sb_browse_server_root,
        ).grid(row=0, column=1, padx=(6, 0))
        r += 1

        # 서버 루트 경로 설명
        ctk.CTkLabel(
            card,
            text="서버에서 프로젝트 폴더들이 모여 있는 바로 위 폴더까지만 입력합니다.\n"
                 "예) 서버에 W:\\vfx\\project_2026\\SBS_030 폴더가 있다면\n"
                 "      → 여기에는  W:\\vfx\\project_2026  까지만 입력",
            font=self.F_SMALL, text_color=TEXT_DIM, anchor="w", justify="left",
        ).grid(row=r, column=1, sticky="w", padx=(0, 20), pady=(0, 6)); r += 1

        label(r, "프리셋 선택 *")
        self.sb_preset_combo = ctk.CTkComboBox(
            card, variable=self.sb_preset_var,
            values=sorted(self.presets.keys()) or [""],
            state="readonly",
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
        )
        self.sb_preset_combo.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        r += 1

        # 프리셋 = 프로젝트 코드 안내
        ctk.CTkLabel(
            card,
            text="프리셋 이름이 서버의 프로젝트 폴더명으로 사용됩니다.\n"
                 "Preset Manager에서 프리셋을 만들 때 서버 폴더명과 동일하게 지정해 주세요.",
            font=self.F_SMALL, text_color=TEXT_DIM, anchor="w", justify="left",
        ).grid(row=r, column=1, sticky="w", padx=(0, 20), pady=(0, 4)); r += 1

        # Divider
        ctk.CTkFrame(card, height=1, fg_color=BORDER).grid(row=r, column=0, columnspan=2, sticky="ew", padx=16, pady=4); r += 1

        # STEP 2
        step_label(r, "STEP 2   샷 정보"); r += 1
        label(r, "샷 이름 *")
        shot_e = entry(r, self.sb_shot_name_var, placeholder="예) E107_S012_0360")
        shot_e.bind("<Return>", lambda e: self._sb_create_nk())
        self.sb_shot_name_entry = shot_e
        self.sb_shot_name_var.trace_add("write", lambda *_: self._sb_update_path_preview())
        r += 1

        # Buttons
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=r, column=0, columnspan=2, sticky="w", padx=20, pady=(14, 4)); r += 1
        ctk.CTkButton(
            btns, text="NK 파일 생성", height=40,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111", font=self.F_BTN_EM,
            command=self._sb_create_nk,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btns, text="설정 저장", height=40,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._sb_save_settings,
        ).pack(side="left", padx=(0, 6))
        self.sb_open_folder_btn = ctk.CTkButton(
            btns, text="폴더 열기", height=40, state="disabled",
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT_DIM, font=self.F_BTN,
            command=self._sb_open_folder,
        )
        self.sb_open_folder_btn.pack(side="left", padx=(0, 6))

        # Divider
        ctk.CTkFrame(card, height=1, fg_color=BORDER).grid(row=r, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 4)); r += 1

        # STEP 3 — 실행 결과 로그
        step_label(r, "STEP 3   실행 결과"); r += 1
        card.rowconfigure(r, weight=1)

        self.sb_log_text = ctk.CTkTextbox(
            card, fg_color=INPUT_BG, text_color=TEXT_DIM, font=self.F_MONO,
            state="disabled", corner_radius=8, border_color=BORDER, border_width=1,
        )
        self.sb_log_text.grid(row=r, column=0, columnspan=2, sticky="nsew", padx=16, pady=(0, 16))

    # ────────────── SHOTGRID PAGE ───────────────────────────────────
    def _build_shotgrid_page(self, parent) -> None:
        # ── 헤더 ─────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(24, 0))
        ctk.CTkLabel(hdr, text="Publish", font=self.F_TITLE, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(
            hdr, text="Version 업로드  ·  MOV 드래그 앤 드롭",
            font=self.F_SMALL, text_color=TEXT_DIM,
        ).pack(side="left", padx=(16, 0))

        scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SELECT_BG,
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=(12, 8))
        scroll.columnconfigure(0, weight=1)

        # ── 연결 상태 배너 ───────────────────────────────────────────
        _sg_now = get_shotgrid_settings()
        _auto_creds = all(
            str(_sg_now.get(k, "") or "").strip()
            for k in ("base_url", "script_name", "script_key")
        )
        banner_color = "#1a3a1a" if _auto_creds else PANEL_BG
        banner_text  = (
            "✓  Beluca ShotGrid 자격 증명 내장됨 — 바로 업로드 가능"
            if _auto_creds else
            "⚠  ShotGrid 연결 정보를 찾을 수 없습니다. 관리자에게 문의하세요."
        )
        banner_color_txt = "#6fcf97" if _auto_creds else "#e0a060"
        ctk.CTkLabel(
            scroll, text=banner_text,
            font=self.F_SMALL, text_color=banner_color_txt,
            fg_color=banner_color, corner_radius=8, anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 12), ipady=8, ipadx=12)

        # ── MOV 드롭존 ───────────────────────────────────────────────
        drop_outer = ctk.CTkFrame(scroll, fg_color=PANEL_BG, corner_radius=10, border_width=2, border_color=BORDER)
        drop_outer.pack(fill="x", padx=4, pady=(0, 8))

        self._sg_drop_label = ctk.CTkLabel(
            drop_outer,
            text="MOV 파일을 여기에 드래그하거나  [파일 선택]  버튼을 누르세요\n(.mov / .mp4)",
            font=self.F_LABEL, text_color=TEXT_DIM, height=90, anchor="center", justify="center",
        )
        self._sg_drop_label.pack(fill="x", padx=12, pady=8)

        # tkinterdnd2 드래그 앤 드롭 등록 — 라벨 + 바깥 프레임 둘 다 등록
        for _dnd_widget in (self._sg_drop_label, drop_outer):
            try:
                _dnd_widget.drop_target_register("DND_Files")  # type: ignore[attr-defined]
                _dnd_widget.dnd_bind("<<Drop>>", self._sg_on_drop_event)  # type: ignore[attr-defined]
            except Exception:
                pass

        file_row = ctk.CTkFrame(drop_outer, fg_color="transparent")
        file_row.pack(fill="x", padx=12, pady=(0, 10))
        file_row.columnconfigure(0, weight=1)
        ctk.CTkEntry(
            file_row, textvariable=self.sg_mov_path_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_MONO,
            placeholder_text="파일 경로",
            state="readonly",
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            file_row, text="파일 선택", width=90, height=32,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._sg_browse_mov,
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            file_row, text="✕", width=32, height=32,
            fg_color=SELECT_BG, hover_color="#5a2020", text_color=TEXT, font=self.F_BTN,
            command=self._sg_clear_mov,
        ).grid(row=0, column=2, padx=(4, 0))

        # ── 폼 영역 ──────────────────────────────────────────────────
        form = ctk.CTkFrame(scroll, fg_color=PANEL_BG, corner_radius=10)
        form.pack(fill="x", padx=4, pady=(0, 8))
        form.columnconfigure(1, weight=1)

        def flbl(r: int, t: str) -> None:
            ctk.CTkLabel(
                form, text=t, font=self.F_LABEL, text_color=TEXT_DIM, anchor="w",
            ).grid(row=r, column=0, sticky="w", padx=(14, 10), pady=7)

        def fent(r: int, var: tk.StringVar, ph: str = "", readonly: bool = False) -> ctk.CTkEntry:
            e = ctk.CTkEntry(
                form, textvariable=var, fg_color=INPUT_BG, border_color=BORDER,
                text_color=TEXT, font=self.F_LABEL,
                placeholder_text=ph,
                state="readonly" if readonly else "normal",
            )
            e.grid(row=r, column=1, sticky="ew", padx=(0, 14), pady=7)
            return e

        fr = 0

        # Version Name — 참조 저장 (직접 업데이트용)
        flbl(fr, "Version Name")
        self._sg_version_name_entry = fent(fr, self.sg_version_name_var, ph="MOV 드롭 시 자동 채움")
        fr += 1

        # Description
        flbl(fr, "Description")
        self._sg_desc_entry = fent(fr, self.sg_desc_var, ph="수정 사항 또는 메모")
        fr += 1

        # Artist (자동완성)
        flbl(fr, "Artist")
        artist_wrap = ctk.CTkFrame(form, fg_color="transparent")
        artist_wrap.grid(row=fr, column=1, sticky="ew", padx=(0, 14), pady=7)
        artist_wrap.columnconfigure(0, weight=1)
        self._sg_artist_entry = ctk.CTkEntry(
            artist_wrap, textvariable=self.sg_artist_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
            placeholder_text="이름 또는 로그인 입력 (자동완성)",
        )
        self._sg_artist_entry.grid(row=0, column=0, sticky="ew")
        self._sg_artist_entry.bind("<KeyRelease>", self._sg_on_artist_keyrelease)
        self._sg_artist_id_label = ctk.CTkLabel(
            artist_wrap, text="", font=self.F_SMALL, text_color=ACCENT, anchor="w",
        )
        self._sg_artist_id_label.grid(row=1, column=0, sticky="w", pady=(1, 0))
        fr += 1

        # Link (Shot Builder 버튼 제거, "Link"로 라벨 변경)
        flbl(fr, "Link")
        link_wrap = ctk.CTkFrame(form, fg_color="transparent")
        link_wrap.grid(row=fr, column=1, sticky="ew", padx=(0, 14), pady=7)
        link_wrap.columnconfigure(0, weight=1)
        self._sg_link_entry = ctk.CTkEntry(
            link_wrap, textvariable=self.sg_link_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
            placeholder_text="MOV 드롭 시 자동 채움 또는 수동 입력",
        )
        self._sg_link_entry.grid(row=0, column=0, sticky="ew")
        self._sg_link_id_label = ctk.CTkLabel(
            link_wrap, text="", font=self.F_SMALL, text_color=ACCENT, anchor="w",
        )
        self._sg_link_id_label.grid(row=1, column=0, sticky="w", pady=(1, 0))
        fr += 1

        # Task (자동완성)
        flbl(fr, "Task")
        task_wrap = ctk.CTkFrame(form, fg_color="transparent")
        task_wrap.grid(row=fr, column=1, sticky="ew", padx=(0, 14), pady=7)
        task_wrap.columnconfigure(0, weight=1)
        self._sg_task_entry = ctk.CTkEntry(
            task_wrap, textvariable=self.sg_task_input_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL,
            placeholder_text="Task 이름 입력 (Shot 확정 후 자동완성)",
        )
        self._sg_task_entry.grid(row=0, column=0, sticky="ew")
        self._sg_task_entry.bind("<KeyRelease>", self._sg_on_task_keyrelease)
        self._sg_task_id_label = ctk.CTkLabel(
            task_wrap, text="", font=self.F_SMALL, text_color=ACCENT, anchor="w",
        )
        self._sg_task_id_label.grid(row=1, column=0, sticky="w", pady=(1, 0))
        fr += 1

        # Project (읽기전용, 자동채움) — 참조 저장
        flbl(fr, "Project")
        self._sg_proj_entry = fent(fr, self.sg_proj_label_var, ph="MOV 드롭 후 자동 채움", readonly=True)
        fr += 1

        # Status
        flbl(fr, "Status")
        _sg_status_values = sgc.merge_task_status_combo_options([])
        self.sg_status_combo = ctk.CTkComboBox(
            form, values=_sg_status_values,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
        )
        self.sg_status_combo.grid(row=fr, column=1, sticky="ew", padx=(0, 14), pady=7)
        self.sg_status_combo.set("(비움)")
        fr += 1

        # ── Create Version 버튼 ──────────────────────────────────────
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=(4, 4))
        self._sg_create_btn = ctk.CTkButton(
            btn_row, text="  Create Version  ", height=46,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111", font=self.F_BTN_EM,
            command=self._sg_create_version,
        )
        self._sg_create_btn.pack(side="left")
        ctk.CTkButton(
            btn_row, text="연결 테스트", height=46,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._sg_test_connection,
        ).pack(side="left", padx=(10, 0))
        # 업로드 진행 상태 표시 라벨
        self._sg_upload_status = ctk.CTkLabel(
            scroll, text="", font=self.F_LABEL, text_color=ACCENT, anchor="w",
        )
        self._sg_upload_status.pack(fill="x", padx=6, pady=(2, 0))
        prog_row = ctk.CTkFrame(scroll, fg_color="transparent")
        prog_row.pack(fill="x", padx=6, pady=(4, 0))
        prog_row.columnconfigure(0, weight=1)
        self._sg_upload_progress = ctk.CTkProgressBar(
            prog_row, height=12, fg_color=INPUT_BG, progress_color=ACCENT,
        )
        self._sg_upload_progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._sg_upload_progress.set(0)
        self._sg_upload_pct_label = ctk.CTkLabel(
            prog_row, text="0%", width=44, font=self.F_SMALL, text_color=TEXT_DIM,
        )
        self._sg_upload_pct_label.grid(row=0, column=1, sticky="e")
        self._sg_upload_prog_poll_token = 0

        # ── 로그 ─────────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="로그", font=self.F_SUBHEAD, text_color=ACCENT, anchor="w").pack(
            anchor="w", padx=4, pady=(12, 4))
        self.sg_log = ctk.CTkTextbox(
            scroll, height=140, fg_color=INPUT_BG, text_color=TEXT_DIM, font=self.F_MONO,
            state="disabled", corner_radius=8, border_color=BORDER, border_width=1,
        )
        self.sg_log.pack(fill="x", padx=4, pady=(0, 10))

    # ────────────── 내 작업 샷 (My Shots) ────────────────────────────
    def _build_my_shots_page(self, parent) -> None:
        # ── 헤더 ─────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(20, 0))
        ctk.CTkLabel(hdr, text="My Tasks", font=self.F_TITLE, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(
            hdr,
            text="ShotGrid Comp 배정 · 썸네일 · 작업 폴더 · NukeX 열기",
            font=self.F_SMALL, text_color=TEXT_DIM,
        ).pack(side="left", padx=(16, 0))

        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=20, pady=(10, 8))

        # ══════════════════════════════════════════════════════════════
        # [1단] 상단: 필터 컨트롤 + 상태 타일 대시보드
        # ══════════════════════════════════════════════════════════════
        top_panel = ctk.CTkFrame(outer, fg_color=PANEL_BG, corner_radius=10)
        top_panel.pack(fill="x", pady=(0, 6))

        # 1행: 필터 컨트롤 ─────────────────────────────────────────
        filter_row = ctk.CTkFrame(top_panel, fg_color="transparent")
        filter_row.pack(fill="x", padx=14, pady=(12, 6))

        # 프로젝트 콤보
        ctk.CTkLabel(
            filter_row, text="프로젝트", font=self.F_LABEL, text_color=TEXT_DIM,
        ).pack(side="left")
        self._ms_project_combo = ctk.CTkComboBox(
            filter_row,
            variable=self.ms_project_var,
            values=["-- 로딩 중 --"],
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG,
            font=self.F_LABEL, width=230,
            command=self._ms_on_project_select,
        )
        self._ms_project_combo.pack(side="left", padx=(8, 20))

        # 담당자 입력
        ctk.CTkLabel(
            filter_row, text="담당자", font=self.F_LABEL, text_color=TEXT_DIM,
        ).pack(side="left")
        self._ms_user_entry = ctk.CTkEntry(
            filter_row,
            textvariable=self.ms_assignee_var,
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            font=self.F_LABEL, width=170,
            placeholder_text="이름 입력 후 선택",
        )
        self._ms_user_entry.pack(side="left", padx=(8, 4))
        self._ms_user_entry.bind("<KeyRelease>", self._ms_on_user_keyrelease)

        self._ms_user_id_label = ctk.CTkLabel(
            filter_row, text="", font=self.F_SMALL, text_color=ACCENT, anchor="w",
        )
        self._ms_user_id_label.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            filter_row, text="나로 설정", width=76, height=28,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_SMALL,
            command=self._ms_guess_me,
        ).pack(side="left", padx=(0, 20))

        # 정렬 콤보
        ctk.CTkLabel(
            filter_row, text="정렬", font=self.F_LABEL, text_color=TEXT_DIM,
        ).pack(side="left")
        self.ms_sort_combo = ctk.CTkComboBox(
            filter_row, values=["샷 코드", "납기일", "상태"],
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG,
            font=self.F_LABEL, width=110,
            command=self._ms_on_sort_change,
        )
        self.ms_sort_combo.set("샷 코드")
        self.ms_sort_combo.pack(side="left", padx=(8, 20))

        # 조회 버튼
        self._ms_refresh_btn = ctk.CTkButton(
            filter_row, text="  조회  ", width=90, height=34,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111",
            font=self.F_BTN_EM, command=self._ms_refresh_all,
        )
        self._ms_refresh_btn.pack(side="left")

        # 2행: 상태 타일 (동적 생성) ──────────────────────────────
        self._ms_tile_row = ctk.CTkFrame(top_panel, fg_color="transparent")
        self._ms_tile_row.pack(fill="x", padx=14, pady=(2, 10))
        self._ms_tile_hint = ctk.CTkLabel(
            self._ms_tile_row,
            text="조회 버튼을 눌러 샷 목록을 불러오세요",
            font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        )
        self._ms_tile_hint.pack(side="left")

        # 로딩 표시
        self._ms_loading_label = ctk.CTkLabel(
            outer, text="", font=self.F_LABEL, text_color=ACCENT, anchor="w",
        )
        self._ms_loading_label.pack(fill="x", pady=(0, 2))

        # ══════════════════════════════════════════════════════════════
        # [2~3단] 샷 리스트 + 노트 — PanedWindow (세로 비율 드래그 조절)
        # ══════════════════════════════════════════════════════════════
        self._ms_paned = tk.PanedWindow(
            outer,
            orient=tk.VERTICAL,
            sashrelief=tk.FLAT,
            bg=BG,
            sashwidth=8,
            bd=0,
        )
        self._ms_paned.pack(fill="both", expand=True, pady=(4, 0))

        upper = tk.Frame(self._ms_paned, bg=BG)
        lower = tk.Frame(self._ms_paned, bg=BG)
        self._ms_paned.add(upper, stretch="always", minsize=220)
        self._ms_paned.add(lower, stretch="always", minsize=200)

        mid_panel = ctk.CTkFrame(upper, fg_color="transparent")
        mid_panel.pack(fill="both", expand=True)

        mid_hdr = ctk.CTkFrame(mid_panel, fg_color="transparent")
        mid_hdr.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            mid_hdr, text="  샷 목록", font=self.F_SUBHEAD,
            text_color=TEXT_DIM, anchor="w",
        ).pack(side="left")

        self._ms_list_host = ctk.CTkScrollableFrame(
            mid_panel, fg_color="transparent",
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SELECT_BG,
        )
        self._ms_list_host.pack(fill="both", expand=True)

        bot_panel = ctk.CTkFrame(lower, fg_color=PANEL_BG, corner_radius=10)
        bot_panel.pack(fill="both", expand=True, pady=(6, 0))

        bot_hdr = ctk.CTkFrame(bot_panel, fg_color="transparent")
        bot_hdr.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(
            bot_hdr, text="My Snapshot Note",
            font=self.F_HEAD, text_color=ACCENT, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            bot_hdr,
            text="최근 2주 코멘트 · 아래 구분선을 드래그해 영역 크기 조절",
            font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).pack(side="left", padx=(10, 0))
        ctk.CTkButton(
            bot_hdr,
            text="노트 새로고침",
            width=110,
            height=28,
            fg_color=SELECT_BG,
            hover_color=HOVER,
            text_color=TEXT,
            font=self.F_SMALL,
            command=self._ms_refresh_notes_clicked,
        ).pack(side="right", padx=(8, 0))

        note_col_hdr = ctk.CTkFrame(bot_panel, fg_color="transparent")
        note_col_hdr.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(
            note_col_hdr,
            text="프로젝트 · 작성자 · 대상 샷 · 시각",
            font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).pack(side="left")

        self._ms_note_host = ctk.CTkScrollableFrame(
            bot_panel, fg_color="transparent",
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SELECT_BG,
        )
        self._ms_note_host.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        # ── 페이지 진입 시 자동 초기화 ───────────────────────────
        if self._ms_assignee_id and (self.ms_assignee_var.get() or "").strip():
            self._ms_user_id_label.configure(text=f"✓ {self.ms_assignee_var.get()}")
        self._ms_ensure_thumb_workers()
        self.after(200, self._ms_load_projects)
        self.after(500, self._ms_set_paned_split)

    def _ms_set_paned_split(self) -> None:
        """초기 샷 목록 / 노트 패널 비율(약 62% / 38%)을 설정한다."""
        try:
            ph = int(self._ms_paned.winfo_height())
            if ph > 350:
                self._ms_paned.sash_place(0, 0, int(ph * 0.62))
        except Exception:
            pass

    def _ms_ensure_thumb_workers(self) -> None:
        """썸네일 다운로드용 고정 워커 스레드 4개 (스레드 폭발 방지)."""
        if self._ms_thumb_workers_started:
            return
        self._ms_thumb_workers_started = True
        self._ms_thumb_queue = queue.Queue()
        self._ms_thumb_result_queue = queue.Queue()
        for _ in range(4):
            threading.Thread(target=self._ms_thumb_worker_loop, daemon=True).start()
        self._ms_thumb_poll_tick()

    def _ms_thumb_worker_loop(self) -> None:
        while True:
            item = self._ms_thumb_queue.get()
            generation, shot_id, cache_path, label_widget, shot_code = item
            path_result: Optional[Path] = None
            try:
                cp = Path(cache_path)
                if cp.is_file() and cp.stat().st_size > 0:
                    path_result = cp
                else:
                    sg = sgc.get_default_sg()
                    ok = sgc.download_entity_thumbnail_to_path(
                        sg, "Shot", int(shot_id), cp
                    )
                    path_result = cp if ok else None
            except Exception:
                path_result = None
            try:
                self._ms_thumb_result_queue.put(
                    (generation, label_widget, path_result, shot_code)
                )
            except Exception:
                pass
            try:
                self._ms_thumb_queue.task_done()
            except Exception:
                pass

    def _ms_thumb_poll_tick(self) -> None:
        """워커가 넣은 썸네일 결과를 메인 스레드에서만 처리 (Tk after는 메인 전용)."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if not getattr(self, "_ms_thumb_workers_started", False):
            return
        try:
            while True:
                gen, lw, path_result, sc = self._ms_thumb_result_queue.get_nowait()
                if gen == self._ms_thumb_gen:
                    self._ms_thumb_on_main(lw, path_result, sc)
        except queue.Empty:
            pass
        except Exception as e:
            logger.debug("My Tasks thumb poll: %s", e)
        try:
            self.after(50, self._ms_thumb_poll_tick)
        except Exception:
            pass

    def _ms_thumb_on_main(
        self, label_widget, path: Optional[Path], shot_code: str
    ) -> None:
        try:
            if path is not None and path.is_file():
                if PILImage is not None:
                    self._ms_apply_thumb(label_widget, path)
                else:
                    short = ((shot_code or "?").strip()[:10] or "?")
                    label_widget.configure(
                        text=f"{short}\n(Pillow 없음)",
                        font=self.F_SMALL,
                        text_color=TEXT_DIM,
                    )
            else:
                label_widget.configure(
                    text="썸네일\n없음", font=self.F_SMALL, text_color=TEXT_DIM
                )
        except Exception:
            logger.debug("My Tasks thumbnail apply failed", exc_info=True)

    def _ms_refresh_notes_clicked(self) -> None:
        ids = list(getattr(self, "_ms_last_note_shot_ids", []) or [])
        if not ids:
            messagebox.showinfo(
                "My Tasks",
                "먼저 [조회]로 샷 목록을 불러오세요.",
            )
            return
        self._ms_refresh_notes(ids)

    def _ms_fill_user_entry(self, value: str) -> None:
        try:
            self._ms_user_entry.delete(0, "end")
            if value:
                self._ms_user_entry.insert(0, value)
        except Exception:
            self.ms_assignee_var.set(value or "")

    def _ms_save_assignee_prefs(self) -> None:
        sb = get_shot_builder_settings()
        sb["my_shots_last_human_user_id"] = self._ms_assignee_id
        sb["my_shots_last_human_name"] = (self.ms_assignee_var.get() or "").strip()
        save_shot_builder_settings(sb)

    def _ms_on_user_keyrelease(self, _event=None) -> None:
        if self._ms_user_after:
            try:
                self.after_cancel(self._ms_user_after)
            except Exception:
                pass
        self._ms_user_after = self.after(300, self._ms_user_autocomplete)

    def _ms_user_autocomplete(self) -> None:
        q = (self._ms_user_entry.get() or "").strip()
        if len(q) < 1:
            return

        def job():
            sg = sgc.get_default_sg()
            return sgc.search_human_users(sg, q)

        def done(kind, payload):
            if kind != "ok" or not payload:
                if kind != "ok":
                    logger.debug("My Tasks user autocomplete failed: %s", payload)
                return
            users = payload
            self._sg_show_autocomplete_popup(
                anchor=self._ms_user_entry,
                items=[
                    f"{u.get('name', '')}  ({u.get('login', '')})" for u in users
                ],
                on_select=lambda idx: self._ms_select_user(users[idx]),
            )

        self._sg_start_worker(job, done)

    def _ms_select_user(self, user: dict) -> None:
        name = user.get("name") or user.get("login") or ""
        uid = user.get("id")
        self._ms_assignee_id = int(uid) if uid is not None else None
        self.ms_assignee_var.set(name)
        self._ms_fill_user_entry(name)
        self._ms_user_id_label.configure(text=f"✓ {name}")
        self._ms_save_assignee_prefs()

    def _ms_guess_me(self) -> None:
        def job():
            sg = sgc.get_default_sg()
            return sgc.guess_human_user_for_me(sg)

        def done(kind, payload):
            if kind != "ok":
                messagebox.showerror("My Tasks", str(payload))
                return
            if not payload:
                messagebox.showinfo(
                    "My Tasks",
                    "로그인명으로 ShotGrid 사용자를 찾지 못했습니다.\n"
                    "담당자 칸에 이름을 입력해 자동완성으로 선택하세요.",
                )
                return
            self._ms_select_user(payload)

        self._sg_start_worker(job, done)

    def _ms_sort_rows(self, rows: list, mode: str) -> list:
        if not rows:
            return []
        mode = (mode or "").strip()
        if mode.startswith("납기"):
            def _due_key(rec: dict):
                d = rec.get("due_date")
                return (d is None, str(d or ""))

            return sorted(rows, key=_due_key)
        if mode.startswith("상태"):
            return sorted(
                rows,
                key=lambda r: (r.get("task_status") or "").lower(),
            )
        return sorted(
            rows,
            key=lambda r: (r.get("shot_code") or "").lower(),
        )

    def _ms_on_sort_change(self, _choice: Optional[str] = None) -> None:
        sort_mode = self.ms_sort_combo.get()
        # 전체 데이터와 현재 표시 데이터 모두 재정렬
        self._ms_all_rows_data = self._ms_sort_rows(self._ms_all_rows_data, sort_mode)
        self._ms_rows_data = self._ms_sort_rows(self._ms_rows_data, sort_mode)
        self._ms_render_rows()

    def _ms_set_refresh_busy(self, busy: bool) -> None:
        try:
            btn = getattr(self, "_ms_refresh_btn", None)
            if btn is None:
                return
            btn.configure(state="disabled" if busy else "normal")
        except Exception:
            pass

    def _ms_refresh_shots(self, *, on_complete=None) -> None:
        """샷 목록을 ShotGrid에서 로드한다. on_complete 콜백은 완료 후 호출된다."""
        if self._ms_assignee_id is None:
            messagebox.showwarning(
                "My Tasks",
                "담당자를 먼저 선택하세요.\n"
                "이름을 입력하면 자동완성이 뜨거나 [나로 설정]을 누르세요.",
            )
            return
        self._ms_shots_req_seq += 1
        req = self._ms_shots_req_seq
        self._ms_set_refresh_busy(True)
        self._ms_loading_label.configure(text="ShotGrid에서 샷 목록을 불러오는 중…")

        uid = int(self._ms_assignee_id)
        pid = self._ms_project_id  # None 이면 전체 프로젝트
        sg_cfg = get_shotgrid_settings()
        task_content = (sg_cfg.get("task_content") or "comp").strip()
        due_f = (sg_cfg.get("task_due_date_field") or "").strip() or None

        def job():
            sg = sgc.get_default_sg()
            st_field, _vals = sgc.list_task_status_values(sg)
            rows = sgc.list_comp_tasks_for_project_user(
                sg,
                pid,
                uid,
                task_content=task_content,
                status_filter=None,  # 상태 필터는 타일 클릭으로 클라이언트 측 처리
                status_field_name=st_field,
                due_date_field=due_f,
            )
            return rows

        def done(kind, payload):
            try:
                if req != self._ms_shots_req_seq:
                    return
                self._ms_loading_label.configure(text="")
                if kind != "ok":
                    messagebox.showerror("My Tasks", str(payload))
                    return
                rows = payload or []
                self._ms_all_rows_data = self._ms_sort_rows(
                    list(rows), self.ms_sort_combo.get()
                )
                # 타일 + 목록은 _ms_apply_status_filter 한 번으로 갱신 (중복 렌더 방지)
                self._ms_apply_status_filter(self._ms_status_filter)
                if on_complete:
                    on_complete(rows)
            finally:
                if req == self._ms_shots_req_seq:
                    self._ms_set_refresh_busy(False)

        self._sg_start_worker(job, done)

    def _ms_clear_row_widgets(self) -> None:
        self._ms_thumb_gen += 1
        for w in self._ms_row_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._ms_row_widgets.clear()
        self._ms_thumb_refs.clear()

    def _ms_render_rows(self) -> None:
        self._ms_clear_row_widgets()
        if not self._ms_rows_data:
            lab = ctk.CTkLabel(
                self._ms_list_host,
                text="배정된 Comp 샷이 없거나 아직 새로고침하지 않았습니다.",
                font=self.F_LABEL,
                text_color=TEXT_DIM,
            )
            lab.pack(anchor="w", padx=4, pady=8)
            self._ms_row_widgets.append(lab)
            return
        for rec in self._ms_rows_data:
            self._ms_add_row_card(rec)

    def _ms_add_row_card(self, rec: dict) -> None:
        card = ctk.CTkFrame(self._ms_list_host, fg_color=PANEL_BG, corner_radius=10)
        card.pack(fill="x", pady=6, padx=2)
        self._ms_row_widgets.append(card)
        # 썸네일 · 샷코드 · 상태 · 납기 · 프로젝트 · 디스크립션(확장) · 버튼
        card.columnconfigure(0, weight=0, minsize=175)
        card.columnconfigure(1, weight=0, minsize=170)
        card.columnconfigure(2, weight=0, minsize=90)
        card.columnconfigure(3, weight=0, minsize=100)
        card.columnconfigure(4, weight=0, minsize=120)
        card.columnconfigure(5, weight=1, minsize=160)
        card.columnconfigure(6, weight=0, minsize=155)

        thumb = ctk.CTkLabel(
            card,
            text="썸네일\n로딩",
            font=self.F_SMALL,
            text_color=TEXT_DIM,
            width=160,
            height=90,
            fg_color=INPUT_BG,
            corner_radius=6,
        )
        thumb.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10, sticky="nw")

        shot_code = (rec.get("shot_code") or "?").strip()
        ctk.CTkLabel(
            card,
            text="샷 코드",
            font=self.F_SMALL,
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=1, sticky="nw", padx=(4, 8), pady=(10, 2))
        ctk.CTkLabel(
            card,
            text=shot_code,
            font=self.F_HEAD,
            text_color=ACCENT,
            anchor="w",
        ).grid(row=1, column=1, sticky="nw", padx=(4, 8), pady=(0, 10))

        st = (rec.get("task_status") or "—").strip()
        ctk.CTkLabel(
            card,
            text="상태",
            font=self.F_SMALL,
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=2, sticky="nw", padx=(4, 8), pady=(10, 2))
        ctk.CTkLabel(
            card,
            text=st,
            font=self.F_LABEL,
            text_color=TEXT,
            anchor="w",
        ).grid(row=1, column=2, sticky="nw", padx=(4, 8), pady=(0, 10))

        due = rec.get("due_date")
        due_s = str(due).strip() if due else "—"
        ctk.CTkLabel(
            card,
            text="납기",
            font=self.F_SMALL,
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=3, sticky="nw", padx=(4, 8), pady=(10, 2))
        ctk.CTkLabel(
            card,
            text=due_s,
            font=self.F_LABEL,
            text_color=TEXT,
            anchor="w",
        ).grid(row=1, column=3, sticky="nw", padx=(4, 8), pady=(0, 10))

        proj = (rec.get("project_code") or rec.get("project_name") or "").strip() or "—"
        sg_ver = (rec.get("latest_version_code") or "").strip()
        proj_body = proj
        if sg_ver:
            proj_body = f"{proj}\nSG Ver: {sg_ver}"
        ctk.CTkLabel(
            card,
            text="프로젝트",
            font=self.F_SMALL,
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=4, sticky="nw", padx=(4, 8), pady=(10, 2))
        ctk.CTkLabel(
            card,
            text=proj_body,
            font=self.F_LABEL,
            text_color=TEXT_DIM,
            anchor="nw",
            justify="left",
        ).grid(row=1, column=4, sticky="nw", padx=(4, 8), pady=(0, 10))

        desc = (rec.get("shot_description") or "").strip() or "(디스크립션 없음)"
        desc_txt = desc[:500] + ("…" if len(desc) > 500 else "")
        ctk.CTkLabel(
            card,
            text="디스크립션",
            font=self.F_SMALL,
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=5, sticky="nw", padx=(4, 8), pady=(10, 2))
        ctk.CTkLabel(
            card,
            text=desc_txt,
            font=self.F_LABEL,
            text_color=TEXT,
            anchor="nw",
            justify="left",
            wraplength=280,
        ).grid(row=1, column=5, sticky="new", padx=(4, 8), pady=(0, 10))

        pcode = (
            (rec.get("project_code") or "").strip()
            or (rec.get("project_folder") or "").strip()
            or (rec.get("project_name") or "").strip()
        )
        btn_cell = ctk.CTkFrame(card, fg_color="transparent")
        btn_cell.grid(row=0, column=6, rowspan=2, sticky="ne", padx=(8, 10), pady=10)
        _mw, _mh = 145, 48
        ctk.CTkButton(
            btn_cell,
            text="작업 폴더",
            width=_mw,
            height=_mh,
            fg_color=SELECT_BG,
            hover_color=HOVER,
            text_color=TEXT,
            font=self.F_BTN,
            command=lambda sc=shot_code, pc=pcode: self._ms_open_work_folder(sc, pc),
        ).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            btn_cell,
            text="NukeX 열기",
            width=_mw,
            height=_mh,
            fg_color=SELECT_BG,
            hover_color=HOVER,
            text_color=TEXT,
            font=self.F_BTN,
            command=lambda sc=shot_code, pc=pcode: self._ms_open_latest_nk(sc, pc),
        ).pack(fill="x")

        sid = rec.get("shot_id")
        if sid is not None:
            self._ms_fetch_thumb_async(int(sid), thumb, shot_code)

    def _ms_fetch_thumb_async(self, shot_id: int, label_widget, shot_code: str) -> None:
        self._ms_ensure_thumb_workers()
        cache_dir = Path(CACHE_DIR) / "sg_thumbs"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            try:
                label_widget.configure(text="캐시\n오류", font=self.F_SMALL)
            except Exception:
                pass
            return
        cache_path = cache_dir / f"shot_{shot_id}.jpg"
        gen = self._ms_thumb_gen
        try:
            self._ms_thumb_queue.put(
                (gen, shot_id, cache_path, label_widget, shot_code)
            )
        except Exception:
            try:
                label_widget.configure(text="썸네일\n대기", font=self.F_SMALL)
            except Exception:
                pass

    def _ms_apply_thumb(self, label_widget, path: Path) -> None:
        if PILImage is None:
            return
        try:
            im = PILImage.open(path)
            im.thumbnail((240, 135))  # 원본 비율 유지하며 강제 축소
            im = im.convert("RGB")  # RGBA·P 모드 호환성 보장
            cimg = ctk.CTkImage(light_image=im, dark_image=im, size=(160, 90))
            label_widget.configure(image=cimg, text="")
            self._ms_thumb_refs.append(cimg)
        except Exception:
            try:
                label_widget.configure(text="썸네일\n오류")
            except Exception:
                pass

    def _ms_open_latest_nk(self, shot_code: str, project_code: str) -> None:
        root = (self.sb_server_root_var.get() or "").strip()
        sc = (shot_code or "").strip()
        pc = (project_code or "").strip()
        if not root:
            messagebox.showwarning(
                "My Tasks",
                "서버 루트가 비어 있습니다.\nShot Builder 페이지에서 서버 루트 경로를 설정하세요.",
            )
            return
        if not sc:
            messagebox.showwarning(
                "My Tasks",
                "샷 코드가 없어 NK 경로를 찾을 수 없습니다.",
            )
            return

        def job():
            return find_latest_nk_path(sc, pc, root)

        def done(kind, payload):
            if kind != "ok":
                messagebox.showerror("My Tasks", str(payload))
                return
            p = payload
            if p is None:
                messagebox.showinfo(
                    "My Tasks",
                    "해당 샷의 최신 .nk 파일을 찾을 수 없습니다.",
                )
                return
            try:
                os.startfile(str(p))  # noqa: S606 — Windows 기본 연결(Nuke)로 열기
            except OSError as e:
                messagebox.showerror(
                    "My Tasks",
                    f"파일을 열 수 없습니다:\n{p}\n\n{e}",
                )

        self._sg_start_worker(job, done)

    def _ms_open_work_folder(self, shot_code: str, project_code: str) -> None:
        """최신 .nk 가 있는 폴더를 탐색기로 연다 (파일 열기와 동일 탐색)."""
        root = (self.sb_server_root_var.get() or "").strip()
        sc = (shot_code or "").strip()
        pc = (project_code or "").strip()
        if not root:
            messagebox.showwarning(
                "My Tasks",
                "서버 루트가 비어 있습니다.\nShot Builder 페이지에서 서버 루트 경로를 설정하세요.",
            )
            return
        if not sc:
            messagebox.showwarning(
                "My Tasks",
                "샷 코드가 없어 작업 폴더를 찾을 수 없습니다.",
            )
            return

        def job():
            return find_latest_nk_path(sc, pc, root)

        def done(kind, payload):
            if kind != "ok":
                messagebox.showerror("My Tasks", str(payload))
                return
            p = payload
            if p is None:
                messagebox.showinfo(
                    "My Tasks",
                    "해당 샷의 최신 .nk 파일을 찾을 수 없어 폴더를 열 수 없습니다.",
                )
                return
            folder = p.parent
            try:
                os.startfile(str(folder))  # noqa: S606
            except OSError as e:
                messagebox.showerror(
                    "My Tasks",
                    f"폴더를 열 수 없습니다:\n{folder}\n\n{e}",
                )

        self._sg_start_worker(job, done)

    # ── My Shots: 프로젝트 로드 ───────────────────────────────────────
    def _ms_load_projects(self) -> None:
        """페이지 진입 시 ShotGrid에서 활성 프로젝트 목록을 콤보박스에 채운다."""
        try:
            self._ms_project_combo.configure(values=["-- 로딩 중 --"])
        except Exception:
            return

        self._ms_projects_req_seq += 1
        preq = self._ms_projects_req_seq

        def job():
            sg = sgc.get_default_sg()
            return sgc.list_active_projects(sg)

        def done(kind, payload):
            if preq != self._ms_projects_req_seq:
                return
            if kind != "ok" or not payload:
                if kind != "ok":
                    logger.warning("My Tasks project list failed: %s", payload)
                try:
                    self._ms_project_combo.configure(values=["-- 프로젝트 없음 --"])
                    self.ms_project_var.set("-- 프로젝트 없음 --")
                except Exception:
                    pass
                return
            projects = payload
            self._ms_projects_cache = projects
            labels = [
                f"{p.get('code') or p.get('name') or '?'}  ({p.get('name') or ''})"
                for p in projects
            ]
            labels.insert(0, "-- 전체 프로젝트 --")
            try:
                self._ms_project_combo.configure(values=labels)
                # 이전에 선택된 프로젝트가 있으면 복원
                if self._ms_project_id is not None:
                    for p in projects:
                        if p.get("id") == self._ms_project_id:
                            label = f"{p.get('code') or p.get('name') or '?'}  ({p.get('name') or ''})"
                            self.ms_project_var.set(label)
                            return
                self.ms_project_var.set("-- 전체 프로젝트 --")
            except Exception:
                pass

        self._sg_start_worker(job, done)

    def _ms_on_project_select(self, choice: str) -> None:
        """프로젝트 콤보박스 선택 시 project_id 업데이트."""
        if not choice or choice.startswith("--"):
            self._ms_project_id = None
            return
        for p in self._ms_projects_cache:
            label = f"{p.get('code') or p.get('name') or '?'}  ({p.get('name') or ''})"
            if label == choice:
                self._ms_project_id = p.get("id")
                return
        self._ms_project_id = None

    # ── My Shots: 전체 조회 (샷 + 노트) ─────────────────────────────
    def _ms_refresh_all(self) -> None:
        """조회 버튼 클릭 시 샷 목록과 노트를 순서대로 로드한다."""
        if self._ms_assignee_id is None:
            messagebox.showwarning(
                "My Tasks",
                "담당자를 먼저 선택하세요.\n"
                "이름을 입력하거나 [나로 설정]을 눌러 주세요.",
            )
            return
        # 상태 타일 필터 초기화
        self._ms_status_filter = None

        def after_shots_loaded(rows):
            shot_ids = [
                int(r.get("shot_id"))
                for r in (rows or [])
                if r.get("shot_id") is not None
            ]
            self._ms_last_note_shot_ids = shot_ids
            if shot_ids:
                self._ms_refresh_notes(shot_ids)
            else:
                self._ms_notes_data = []
                self._ms_render_notes()

        self._ms_refresh_shots(on_complete=after_shots_loaded)

    # ── My Shots: 상태 타일 대시보드 ────────────────────────────────
    def _ms_render_status_tiles(self, rows: list) -> None:
        """상태별 카운트를 집계해 타일 버튼을 동적으로 생성한다."""
        # 기존 타일 제거
        for w in self._ms_status_tile_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._ms_status_tile_widgets.clear()
        try:
            self._ms_tile_hint.pack_forget()
        except Exception:
            pass

        if not rows:
            try:
                self._ms_tile_hint.configure(text="조회된 샷이 없습니다.")
                self._ms_tile_hint.pack(side="left")
            except Exception:
                pass
            return

        # 상태별 카운트
        counts: dict = {}
        for rec in rows:
            st = (rec.get("task_status") or "—").strip()
            counts[st] = counts.get(st, 0) + 1

        total = len(rows)

        # "All" 타일 (첫 번째)
        all_tile = ctk.CTkButton(
            self._ms_tile_row,
            text=f"All  {total}",
            width=80, height=32, corner_radius=6,
            fg_color=ACCENT if self._ms_status_filter is None else SELECT_BG,
            hover_color=ACCENT_HOV if self._ms_status_filter is None else HOVER,
            text_color="#111111" if self._ms_status_filter is None else TEXT,
            font=self.F_SUBHEAD,
            command=lambda: self._ms_apply_status_filter(None),
        )
        all_tile.pack(side="left", padx=(0, 6))
        self._ms_status_tile_widgets.append(all_tile)

        # 상태별 타일
        for status, cnt in sorted(counts.items()):
            is_active = (self._ms_status_filter == status)
            tile = ctk.CTkButton(
                self._ms_tile_row,
                text=f"{status}  {cnt}",
                width=max(90, len(status) * 8 + 40),
                height=32, corner_radius=6,
                fg_color=ACCENT if is_active else SELECT_BG,
                hover_color=ACCENT_HOV if is_active else HOVER,
                text_color="#111111" if is_active else TEXT,
                font=self.F_SUBHEAD,
                command=lambda s=status: self._ms_apply_status_filter(s),
            )
            tile.pack(side="left", padx=(0, 6))
            self._ms_status_tile_widgets.append(tile)

    def _ms_apply_status_filter(self, status: Optional[str]) -> None:
        """상태 타일 클릭 시 샷 리스트를 필터링한다. status=None 이면 전체 표시."""
        self._ms_status_filter = status
        if status is None:
            self._ms_rows_data = list(self._ms_all_rows_data)
        else:
            self._ms_rows_data = [
                r for r in self._ms_all_rows_data
                if (r.get("task_status") or "").strip() == status
            ]
        # 타일 하이라이트 갱신
        self._ms_render_status_tiles(self._ms_all_rows_data)
        self._ms_render_rows()

    # ── My Shots: 노트 패널 ──────────────────────────────────────────
    def _ms_refresh_notes(self, shot_ids: list) -> None:
        """샷 ID 목록으로 노트를 ShotGrid에서 로드한다."""
        self._ms_notes_req_seq += 1
        nreq = self._ms_notes_req_seq
        self._ms_loading_label.configure(text="코멘트(Note)를 불러오는 중…")

        ids = [int(sid) for sid in shot_ids if sid is not None][:150]

        def job():
            sg = sgc.get_default_sg()
            return sgc.list_notes_for_shots(sg, ids)

        def done(kind, payload):
            if nreq != self._ms_notes_req_seq:
                return
            self._ms_loading_label.configure(text="")
            if kind != "ok":
                logger.warning("My Tasks notes load failed: %s", payload)
                return
            self._ms_notes_data = payload or []
            self._ms_render_notes()

        self._sg_start_worker(job, done)

    def _ms_clear_note_widgets(self) -> None:
        for w in self._ms_note_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._ms_note_widgets.clear()

    def _ms_render_notes(self) -> None:
        self._ms_clear_note_widgets()
        if not self._ms_notes_data:
            lab = ctk.CTkLabel(
                self._ms_note_host,
                text="코멘트가 없거나 아직 조회하지 않았습니다.",
                font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
            )
            lab.pack(anchor="w", padx=4, pady=6)
            self._ms_note_widgets.append(lab)
            return
        for rec in self._ms_notes_data:
            self._ms_add_note_row(rec)

    def _ms_add_note_row(self, rec: dict) -> None:
        wrap = ctk.CTkFrame(self._ms_note_host, fg_color="transparent")
        wrap.pack(fill="x", pady=(0, 4), padx=2)
        self._ms_note_widgets.append(wrap)

        row = ctk.CTkFrame(wrap, fg_color=HOVER, corner_radius=8)
        row.pack(fill="x")

        bar = ctk.CTkFrame(row, fg_color=ACCENT, width=4, corner_radius=0)
        bar.pack(side="left", fill="y", padx=(0, 10))
        bar.pack_propagate(False)

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", expand=True, pady=8, padx=(0, 10))

        proj_name = (rec.get("project_name") or "—").strip()
        author = (rec.get("author") or "—").strip()
        context = (rec.get("context") or "—").strip()
        ts = (rec.get("timestamp") or "—").strip()
        meta_line = f"{proj_name}  ·  {author}  ·  {context}  ·  {ts}"
        ctk.CTkLabel(
            inner,
            text=meta_line,
            font=self.F_LABEL,
            text_color=TEXT_DIM,
            anchor="w",
        ).pack(fill="x", anchor="w")

        raw = (rec.get("content") or rec.get("subject") or "—").strip()
        content = raw.replace("\n", " ").strip()
        ctk.CTkLabel(
            inner,
            text=content if content else "—",
            font=self.F_LABEL,
            text_color=TEXT,
            anchor="nw",
            justify="left",
            wraplength=720,
        ).pack(fill="x", anchor="w", pady=(6, 0))

        sep = ctk.CTkFrame(wrap, fg_color=BORDER, height=1)
        sep.pack(fill="x", pady=(8, 0))

    # ────────────── TOOLS PAGE ──────────────────────────────────────
    def _build_tools_page(self, parent) -> None:
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(24, 0))
        ctk.CTkLabel(hdr, text="Tools", font=self.F_TITLE, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(
            hdr, text="Nuke 편의기능 온/오프 관리",
            font=self.F_SMALL, text_color=TEXT_DIM,
        ).pack(side="left", padx=(16, 0))

        # 상단 안내 배너
        banner = ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=10)
        banner.pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkLabel(
            banner,
            text=(
                "Nuke 상단 메뉴에는 'Tools'가 아니라  setup_pro  가 보입니다.\n"
                "여기서 스위치를 켠 뒤, Nuke에서  setup_pro → BPE Tools → Reload Tool Hooks  를 "
                "한 번 실행해야 QC / Post-Render 훅이 적용됩니다.\n"
                "(상태 확인: setup_pro → BPE Tools → Show Tools Status)"
            ),
            font=self.F_SMALL, text_color=TEXT_DIM, justify="left", anchor="w",
        ).pack(padx=16, pady=10, anchor="w")

        scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SELECT_BG,
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=(8, 16))
        scroll.columnconfigure(0, weight=1)

        tools_cfg = get_tools_settings()

        self._tools_switches: dict = {}  # key → CTkSwitch

        def _tool_card(
            row: int,
            key: str,
            title: str,
            subtitle: str,
            detail: str,
        ) -> None:
            card = ctk.CTkFrame(scroll, fg_color=PANEL_BG, corner_radius=12)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
            card.columnconfigure(1, weight=1)

            enabled_init = tools_cfg.get(key, {}).get("enabled", False)
            sw_var = tk.BooleanVar(value=enabled_init)

            def _on_toggle(key=key, var=sw_var):
                cfg = get_tools_settings()
                if key not in cfg:
                    cfg[key] = {}
                cfg[key]["enabled"] = var.get()
                save_tools_settings(cfg)

            sw = ctk.CTkSwitch(
                card, text="", variable=sw_var, onvalue=True, offvalue=False,
                progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOV,
                fg_color=SELECT_BG, width=44,
                command=_on_toggle,
            )
            sw.grid(row=0, column=0, rowspan=2, padx=(16, 12), pady=14, sticky="ns")
            self._tools_switches[key] = sw

            ctk.CTkLabel(
                card, text=title, font=self.F_HEAD, text_color=TEXT, anchor="w",
            ).grid(row=0, column=1, sticky="w", padx=(0, 16), pady=(12, 0))

            ctk.CTkLabel(
                card, text=subtitle, font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
            ).grid(row=1, column=1, sticky="w", padx=(0, 16), pady=(0, 4))

            if detail:
                ctk.CTkLabel(
                    card, text=detail,
                    font=self.F_SMALL, text_color="#5a5a5e", anchor="w", justify="left",
                    wraplength=560,
                ).grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))

        r = 0
        _tool_card(
            r, "qc_checker",
            "QC Checker  —  렌더 전 자동 점검",
            "Write 렌더 시작 직전에 FPS / 해상도 / OCIO / 컬러스페이스 / 플레이트-편집본 길이 불일치를 팝업으로 알려줍니다.",
            "활성화 시: Nuke의 모든 Write 노드 렌더 직전에 체크리스트 팝업이 표시됩니다.\n"
            "프리셋이 설정된 NK라면 현재 설정과 프리셋 값의 차이를 비교해 경고합니다.",
        ); r += 1
        _tool_card(
            r, "post_render_viewer",
            "Post-Render Viewer  —  렌더 후 NK 자동 로드",
            "렌더 완료 후 Write 노드 출력 경로의 시퀀스를 Read 노드로 자동 생성하고 Viewer에 연결합니다.",
            "활성화 시: 렌더가 끝나면 'bpe_render_preview' Read 노드가 생성(또는 경로 갱신)되고 Viewer에 연결됩니다.\n"
            "기존 노드는 삭제/이동하지 않으며 Read 노드 추가만 수행합니다.",
        ); r += 1

    # ─────────────────────────────── Business Logic ──────────────────

    def _toggle_write_frame(self) -> None:
        if self.write_open_var.get():
            self.write_frame.grid()
        else:
            self.write_frame.grid_remove()

    def _update_output_transform_fields(self) -> None:
        t = (self.write_transform_type_var.get() or "").strip().lower().replace("\\", "/").replace(" ", "")
        if t == "colorspace":
            self.write_out_cs_entry.configure(state="normal")
            self.write_display_entry.configure(state="disabled")
            self.write_view_entry.configure(state="disabled")
        elif t == "display/view":
            self.write_out_cs_entry.configure(state="disabled")
            self.write_display_entry.configure(state="normal")
            self.write_view_entry.configure(state="normal")
        else:
            self.write_out_cs_entry.configure(state="disabled")
            self.write_display_entry.configure(state="disabled")
            self.write_view_entry.configure(state="disabled")

    def _on_read_cs_cat_selected(self, choice: str = None) -> None:
        cat = (choice or self.read_cs_cat_var.get()).strip()
        items = READ_COLORSPACE_CATALOG.get(cat, [])
        if hasattr(self, "read_cs_combo"):
            self.read_cs_combo.configure(values=items)
            if items and self.read_input_transform_var.get() not in items:
                self.read_input_transform_var.set(items[0])

    def _schedule_plate_choice_sync(self) -> None:
        """가로·세로 입력이 바뀔 때마다 짧게 묶어서 콤보를 (직접입력)으로 맞춤."""
        if self._plate_combo_applying:
            return
        jid = self._plate_sync_after_id
        if jid is not None:
            try:
                self.after_cancel(jid)
            except tk.TclError:
                pass
        self._plate_sync_after_id = self.after(50, self._run_plate_choice_sync)

    def _run_plate_choice_sync(self) -> None:
        self._plate_sync_after_id = None
        self._sync_plate_choice_from_dimensions()

    def _sync_plate_choice_from_dimensions(self) -> None:
        """가로·세로 값이 현재 선택된 프리셋과 다르면 (직접입력)으로 전환."""
        if self._plate_combo_applying:
            return
        try:
            w = int(float((self.plate_width_var.get() or "").strip()))
            h = int(float((self.plate_height_var.get() or "").strip()))
        except (ValueError, TypeError):
            return

        current = (self.plate_format_choice_var.get() or "").strip()
        preset = self.plate_preset_to_wh.get(current)
        if preset and preset[0] and preset[1]:
            if w == preset[0] and h == preset[1]:
                return  # 현재 프리셋 디멘션과 일치 → 변경 불필요
        elif current == "(직접입력)":
            return  # 이미 직접입력 상태 → 변경 불필요

        self._plate_combo_applying = True
        try:
            self.plate_format_choice_var.set("(직접입력)")
            if hasattr(self, "plate_choice_combo"):
                self.plate_choice_combo.set("(직접입력)")
            self.plate_format_name_var.set("")
        finally:
            self._plate_combo_applying = False

    def _on_plate_choice_selected(self, choice: str = None) -> None:
        c = (choice or self.plate_format_choice_var.get() or "").strip()
        if not c or c == "(직접입력)":
            return
        wh = self.plate_preset_to_wh.get(c)
        if not wh:
            return
        w, h = wh
        if w and h:
            self._plate_combo_applying = True
            try:
                self.plate_width_var.set(str(w))
                self.plate_height_var.set(str(h))
                self.plate_format_name_var.set("")
            finally:
                self._plate_combo_applying = False

    def _update_ocio_status(self) -> None:
        """OCIO 경로 입력 후 파일 존재 여부를 실시간 표시합니다."""
        if not hasattr(self, "ocio_status_lbl"):
            return
        p = (self.ocio_path_var.get() or "").strip()
        if not p:
            self.ocio_status_lbl.configure(text="", text_color=TEXT_DIM)
        elif os.path.isfile(p):
            self.ocio_status_lbl.configure(text="✓  파일 확인됨", text_color="#4CAF50")
        else:
            self.ocio_status_lbl.configure(text="⚠  파일을 찾을 수 없음", text_color="#e05252")

    def _browse_ocio(self) -> None:
        selected = filedialog.askopenfilename(
            title="OCIO config 파일 선택",
            parent=self,
            filetypes=[("OCIO config", "*.ocio"), ("All files", "*.*")],
        )
        if selected:
            self.ocio_path_var.set(selected)
            if selected not in self.ocio_configs:
                self.ocio_configs.append(selected)
                save_ocio_configs_cache(self.ocio_configs)
            self.ocio_combo.configure(values=self.ocio_configs)

    def _browse_presets_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="프리셋 저장 폴더 선택", parent=self)
        if not selected:
            return
        try:
            set_presets_dir(selected)
        except Exception as e:
            messagebox.showerror("BPE", f"프리셋 폴더 설정 실패: {e}")
            return
        self.presets_dir_var.set(selected)
        self.presets = load_presets()
        self._selected_preset = ""
        self._refresh_preset_list()

    def _open_presets_folder(self) -> None:
        d = (self.presets_dir_var.get() or "").strip()
        if not d:
            messagebox.showwarning("BPE", "프리셋 저장 폴더가 설정되지 않았습니다.")
            return
        try:
            os.startfile(d)
        except Exception as e:
            messagebox.showerror("BPE", f"폴더 열기 실패: {e}")

    def _collect_form(self) -> dict:
        self._sync_plate_choice_from_dimensions()
        return {
            "project_type":        self.project_type_var.get().strip(),
            "project_code":        self.project_code_var.get().strip().upper(),
            "delivery_format":     self.delivery_format_var.get().strip(),
            "fps":                 self.fps_var.get().strip(),
            "plate_format_choice": self.plate_format_choice_var.get().strip(),
            "plate_format_name":   self.plate_format_name_var.get().strip(),
            "plate_width":         self.plate_width_var.get().strip(),
            "plate_height":        self.plate_height_var.get().strip(),
            "ocio_path":           self.ocio_path_var.get().strip(),
            "write_enabled":       bool(self.write_open_var.get()),
            "write_channels":      self.write_channels_var.get().strip(),
            "write_datatype":      self.write_datatype_var.get().strip(),
            "write_compression":   self.write_compression_var.get().strip(),
            "write_metadata":      self.write_metadata_var.get().strip(),
            "write_transform_type": self.write_transform_type_var.get().strip(),
            "write_out_colorspace": self.write_out_colorspace_var.get().strip(),
            "write_output_display": self.write_output_display_var.get().strip(),
            "write_output_view":    self.write_output_view_var.get().strip(),
            "write_colorspace":     self.write_out_colorspace_var.get().strip(),
            "read_input_transform": self.read_input_transform_var.get().strip(),
        }

    def _validate_required(self, data: dict) -> str:
        missing = []
        if not data.get("project_type"):     missing.append("- 프로젝트 타입")
        if not data.get("project_code"):     missing.append("- 프로젝트 코드")
        if not data.get("fps"):              missing.append("- FPS")
        if not data.get("plate_width") or not data.get("plate_height"):
            missing.append("- 플레이트 사이즈")
        if not data.get("ocio_path"):        missing.append("- OCIO Config 파일")
        if bool(self.write_open_var.get()):
            if not data.get("delivery_format"):  missing.append("- 납품 포맷")
            if not data.get("write_channels"):   missing.append("- Channels")
            if not data.get("write_datatype"):   missing.append("- Datatype")
            if not data.get("write_compression"): missing.append("- Compression")
            if not data.get("write_metadata"):   missing.append("- Metadata")
            if not data.get("write_transform_type"): missing.append("- Transform Type")
            tt = (data.get("write_transform_type", "") or "").strip().lower()
            if tt == "colorspace" and not data.get("write_out_colorspace"):
                missing.append("- Output Transform")
            if tt == "display/view":
                if not data.get("write_output_display"): missing.append("- Display")
                if not data.get("write_output_view"):    missing.append("- View")
        if missing:
            return "필수값이 비어 있습니다:\n\n" + "\n".join(missing)
        if not re.fullmatch(r"[A-Z0-9_]+", data.get("project_code", "")):
            return "프로젝트 코드는 영문 대문자/숫자/_ 만 사용하세요.\n예) SBS_030, DRM_A01"
        try:
            float(data.get("fps", ""))
        except ValueError:
            return "FPS 값이 숫자가 아닙니다."
        if data.get("ocio_path") and not os.path.exists(data.get("ocio_path", "")):
            return "OCIO Config 경로가 존재하지 않습니다."
        try:
            w = int(float(data.get("plate_width", "")))
            h = int(float(data.get("plate_height", "")))
            if w <= 0 or h <= 0:
                return "플레이트 사이즈는 0보다 커야 합니다."
        except ValueError:
            return "플레이트 사이즈는 숫자여야 합니다."
        return ""

    def _save_preset(self) -> None:
        name = (self.project_code_var.get() or "").strip().upper()
        data = self._collect_form()
        err = self._validate_required(data)
        if err:
            messagebox.showerror("BPE", err)
            return
        self.presets[name] = data
        save_presets(self.presets)
        self._selected_preset = name
        self._refresh_preset_list()
        messagebox.showinfo(
            "BPE",
            f"저장 완료: {name}\n"
            f"타입: {data['project_type']}  |  "
            f"해상도: {data['plate_width']} × {data['plate_height']}  |  "
            f"FPS: {data['fps']}",
        )

    def _get_selected_name(self) -> str:
        return self._selected_preset

    def _load_selected(self) -> None:
        name = self._get_selected_name()
        if not name:
            messagebox.showwarning("BPE", "프리셋을 먼저 선택하세요.")
            return
        self._load_preset_to_form(name)

    def _delete_preset(self) -> None:
        name = self._get_selected_name()
        if not name:
            messagebox.showwarning("BPE", "프리셋을 먼저 선택하세요.")
            return
        has_custom = load_preset_template(name) is not None
        msg = f"'{name}' 프리셋을 삭제할까요?"
        if has_custom:
            msg += "\n(커스텀 노드 트리 파일도 함께 삭제됩니다)"
        if not messagebox.askyesno("BPE", msg):
            return
        delete_preset_template(name)
        self.presets.pop(name, None)
        self._selected_preset = ""
        save_presets(self.presets)
        self._refresh_preset_list()

    def _refresh_preset_list(self) -> None:
        if not hasattr(self, "preset_scroll"):
            return
        for w in self.preset_scroll.winfo_children():
            w.destroy()
        self._preset_btns.clear()

        for key in sorted(self.presets.keys()):
            is_sel = key == self._selected_preset
            btn = ctk.CTkButton(
                self.preset_scroll, text=key, anchor="w", height=36, corner_radius=6,
                fg_color=ACCENT if is_sel else "transparent",
                text_color="#111111" if is_sel else TEXT,
                hover_color=HOVER if not is_sel else ACCENT_HOV,
                font=self.F_BTN,
                command=lambda n=key: self._on_preset_click(n),
            )
            btn.pack(fill="x", padx=4, pady=2)
            self._preset_btns[key] = btn

        # Shot Builder combo
        if hasattr(self, "sb_preset_combo"):
            vals = sorted(self.presets.keys())
            self.sb_preset_combo.configure(values=vals if vals else [""])

        # Open folder btn
        if hasattr(self, "open_presets_btn"):
            self.open_presets_btn.configure(
                state="normal" if self._selected_preset else "disabled")

        if hasattr(self, "node_tree_btn"):
            has_sel = bool(self._selected_preset)
            self.node_tree_btn.configure(
                state="normal" if has_sel else "disabled",
                text_color=TEXT if has_sel else TEXT_DIM,
            )
        self._update_node_tree_status()

    def _on_preset_click(self, name: str) -> None:
        for n, btn in self._preset_btns.items():
            sel = n == name
            btn.configure(
                fg_color=ACCENT if sel else "transparent",
                text_color="#111111" if sel else TEXT,
                hover_color=ACCENT_HOV if sel else HOVER,
            )
        self._selected_preset = name
        if hasattr(self, "open_presets_btn"):
            self.open_presets_btn.configure(state="normal")
        if hasattr(self, "node_tree_btn"):
            self.node_tree_btn.configure(state="normal", text_color=TEXT)
        self._update_node_tree_status()
        self._load_preset_to_form(name)
        if hasattr(self, "node_tree_embed"):
            try:
                if self.node_tree_embed.grid_info():
                    self._node_tree_load_template_for_preset(name)
            except tk.TclError:
                pass

    def _update_node_tree_status(self) -> None:
        if not hasattr(self, "node_tree_status_lbl"):
            return
        name = self._selected_preset
        if not name:
            self.node_tree_status_lbl.configure(text="● 기본", text_color=TEXT_DIM)
            return
        tpl = load_preset_template(name)
        if tpl:
            lines = len(tpl.splitlines())
            self.node_tree_status_lbl.configure(
                text=f"✓ 커스텀 ({lines}줄)", text_color=ACCENT)
        else:
            self.node_tree_status_lbl.configure(text="● 기본", text_color=TEXT_DIM)

    def _nk_import_feedback(self, text: str, color=None) -> None:
        if not hasattr(self, "nk_import_feedback_lbl"):
            return
        self.nk_import_feedback_lbl.configure(
            text=text, text_color=color if color is not None else TEXT_DIM)

    def _browse_nk_import(self) -> None:
        init_dir = ""
        try:
            cur = (self.nk_import_path_var.get() or "").strip()
            if cur and os.path.isfile(cur):
                init_dir = os.path.dirname(cur)
            elif getattr(self, "_last_nk_dir", ""):
                init_dir = self._last_nk_dir
        except Exception:
            init_dir = ""
        path = _ask_file_modal(
            self,
            title="가져올 NK 파일 선택",
            filetypes=[("Nuke Script", "*.nk"), ("모든 파일", "*.*")],
            initialdir=init_dir,
        )
        if path:
            norm = os.path.normpath(path)
            self.nk_import_path_var.set(norm)
            self._last_nk_dir = os.path.dirname(norm)
            try:
                if hasattr(self, "nk_import_entry") and self.nk_import_entry.winfo_exists():
                    self.nk_import_entry.delete(0, "end")
                    self.nk_import_entry.insert(0, norm)
            except Exception:
                pass

    def _import_nk_as_preset(self) -> None:
        nk_path = (self.nk_import_path_var.get() or "").strip()
        if not nk_path and hasattr(self, "nk_import_entry"):
            try:
                nk_path = (self.nk_import_entry.get() or "").strip()
            except Exception:
                pass
        if not nk_path:
            self._nk_import_feedback(
                "NK 경로가 비어 있습니다. 입력하거나 「찾아보기」로 파일을 선택하세요.",
                "#e05252",
            )
            try:
                self.nk_import_entry.focus_set()
            except Exception:
                pass
            return
        nk_path = os.path.normpath(nk_path)
        if not os.path.isfile(nk_path):
            self._nk_import_feedback(f"파일을 찾을 수 없습니다: {nk_path}", "#e05252")
            return
        try:
            parsed = parse_nk_file(nk_path)
        except Exception as e:
            self._nk_import_feedback(f"NK 분석 실패: {e}", "#e05252")
            return
        self._show_nk_import_review(nk_path, parsed)

    def _on_nk_import_confirm(self, name: str, parsed: dict) -> None:
        """NK 분석 결과를 기본값으로 채워 프리셋으로 저장합니다."""
        full_data = {
            "project_type":         parsed.get("project_type", "드라마(OTT)"),
            "project_code":         name,
            "delivery_format":      parsed.get("delivery_format", "EXR 16bit"),
            "fps":                  parsed.get("fps", "23.976"),
            "plate_format_choice":  "(직접입력)",
            "plate_format_name":    "",
            "plate_width":          parsed.get("plate_width", "1920"),
            "plate_height":         parsed.get("plate_height", "1080"),
            "ocio_path":            parsed.get("ocio_path", ""),
            "write_enabled":        parsed.get("write_enabled", True),
            "write_channels":       parsed.get("write_channels", "all"),
            "write_datatype":       parsed.get("write_datatype", "16 bit half"),
            "write_compression":    parsed.get("write_compression", "PIZ Wavelet (32 scanlines)"),
            "write_metadata":       parsed.get("write_metadata", "all metadata"),
            "write_transform_type": parsed.get("write_transform_type", "colorspace"),
            "write_out_colorspace": parsed.get("write_out_colorspace", "ACES - ACES2065-1"),
            "write_output_display": parsed.get("write_output_display", "ACES"),
            "write_output_view":    parsed.get("write_output_view", "Rec.709"),
            "write_colorspace":     parsed.get(
                "write_colorspace",
                parsed.get("write_out_colorspace", "ACES - ACES2065-1"),
            ),
            "read_input_transform": parsed.get("read_input_transform", "ACES - ACES2065-1"),
        }
        self.presets[name] = full_data
        save_presets(self.presets)
        self._selected_preset = name
        self._refresh_preset_list()
        self._load_preset_to_form(name)
        self._hide_nk_import_review(clear_feedback=False)
        if hasattr(self, "nk_import_feedback_lbl"):
            self.nk_import_feedback_lbl.configure(
                text=f"✓ 프리셋 '{name}' 저장됨 — 왼쪽 폼에서 값을 확인·수정할 수 있습니다.",
                text_color="#4CAF50",
            )

    def _coerce(self, v: str, options: list) -> str:
        v = (v or "").strip()
        if not v:
            return options[0] if options else ""
        if v in options:
            return v
        for opt in options:
            if opt.lower() == v.lower():
                return opt
        return options[0] if options else v

    def _load_preset_to_form(self, name: str) -> None:
        data = self.presets.get(name, {})
        if not data:
            return

        # ── Project 정보 ────────────────────────────────────────────
        self.project_code_var.set(name)
        if hasattr(self, "project_code_entry"):
            self.project_code_entry.delete(0, "end")
            self.project_code_entry.insert(0, name)

        pt = data.get("project_type", "드라마(OTT)")
        if pt == "OTT 시리즈":
            pt = "드라마(OTT)"
        self.project_type_var.set(pt)

        fps_val = data.get("fps", "23.976")
        self.fps_var.set(fps_val)
        if hasattr(self, "fps_combo"):
            self.fps_combo.set(fps_val)

        # ── 플레이트 포맷 ────────────────────────────────────────────
        fmt_choice = data.get("plate_format_choice", "(직접입력)")
        plate_w = str(data.get("plate_width", "1920"))
        plate_h = str(data.get("plate_height", "1080"))
        self._plate_combo_applying = True
        try:
            self.plate_format_choice_var.set(fmt_choice)
            self.plate_format_name_var.set(data.get("plate_format_name", ""))
            self.plate_width_var.set(plate_w)
            self.plate_height_var.set(plate_h)
            if hasattr(self, "plate_choice_combo"):
                self.plate_choice_combo.set(fmt_choice)
            if hasattr(self, "plate_width_entry"):
                self.plate_width_entry.delete(0, "end")
                self.plate_width_entry.insert(0, plate_w)
            if hasattr(self, "plate_height_entry"):
                self.plate_height_entry.delete(0, "end")
                self.plate_height_entry.insert(0, plate_h)
        finally:
            self._plate_combo_applying = False

        # ── OCIO ────────────────────────────────────────────────────
        ocio_val = data.get("ocio_path", "")
        self.ocio_path_var.set(ocio_val)
        if hasattr(self, "ocio_combo"):
            self.ocio_combo.set(ocio_val)

        # ── Write 설정 ───────────────────────────────────────────────
        write_enabled = bool(data.get("write_enabled", True))
        self.write_open_var.set(write_enabled)
        if write_enabled:
            self.write_frame.grid()
        else:
            self.write_frame.grid_remove()

        delivery_val = data.get("delivery_format", "EXR 16bit")
        self.delivery_format_var.set(delivery_val)
        if hasattr(self, "delivery_format_combo"):
            self.delivery_format_combo.set(delivery_val)

        ch_val = self._coerce(data.get("write_channels", ""), self.write_channels_options)
        self.write_channels_var.set(ch_val)
        if hasattr(self, "write_channels_combo"):
            self.write_channels_combo.set(ch_val)

        dt_val = self._coerce(data.get("write_datatype", ""), self.write_datatype_options)
        self.write_datatype_var.set(dt_val)
        if hasattr(self, "write_datatype_combo"):
            self.write_datatype_combo.set(dt_val)

        comp_val = self._coerce(data.get("write_compression", ""), self.write_compression_options)
        self.write_compression_var.set(comp_val)
        if hasattr(self, "write_compression_combo"):
            self.write_compression_combo.set(comp_val)

        meta_val = self._coerce(data.get("write_metadata", ""), self.write_metadata_options)
        self.write_metadata_var.set(meta_val)
        if hasattr(self, "write_metadata_combo"):
            self.write_metadata_combo.set(meta_val)

        # ── Output Transform ────────────────────────────────────────
        tt = (data.get("write_transform_type", "") or "").strip().lower().replace("\\", "/").replace(" ", "")
        if tt not in ("off", "input", "colorspace", "display/view"):
            tt = "colorspace"
        self.write_transform_type_var.set(tt)
        if hasattr(self, "write_transform_type_combo"):
            self.write_transform_type_combo.set(tt)

        out_cs = data.get("write_out_colorspace", data.get("write_colorspace", ""))
        self.write_out_colorspace_var.set(out_cs)
        if hasattr(self, "write_out_cs_entry"):
            self.write_out_cs_entry.delete(0, "end")
            self.write_out_cs_entry.insert(0, out_cs)

        disp_val = data.get("write_output_display", "ACES")
        self.write_output_display_var.set(disp_val)
        if hasattr(self, "write_display_entry"):
            self.write_display_entry.delete(0, "end")
            self.write_display_entry.insert(0, disp_val)

        view_val = data.get("write_output_view", "Rec.709")
        self.write_output_view_var.set(view_val)
        if hasattr(self, "write_view_entry"):
            self.write_view_entry.delete(0, "end")
            self.write_view_entry.insert(0, view_val)

        # ── Read Input Transform ─────────────────────────────────────
        read_cs = data.get("read_input_transform", "ACES - ACES2065-1")
        self.read_input_transform_var.set(read_cs)
        if hasattr(self, "read_cs_combo"):
            self.read_cs_combo.set(read_cs)

        for cat, items in READ_COLORSPACE_CATALOG.items():
            if read_cs in items:
                self.read_cs_cat_var.set(cat)
                if hasattr(self, "read_cat_combo"):
                    self.read_cat_combo.set(cat)
                if hasattr(self, "read_cs_combo"):
                    self.read_cs_combo.configure(values=items)
                    self.read_cs_combo.set(read_cs)
                break

        self._update_output_transform_fields()

    # ── Self-Update ─────────────────────────────────────────────────
    def _find_project_root(self) -> Path:
        cur = Path(sys.executable).resolve().parent
        for _ in range(6):
            if (cur / "build_exe.bat").exists():
                return cur
            cur = cur.parent
        return Path(sys.executable).resolve().parent

    def _update_self_and_restart(self) -> None:
        root_dir = self._find_project_root()
        build_bat = root_dir / "build_exe.bat"
        if not build_bat.exists():
            messagebox.showerror("BPE", "build_exe.bat를 찾지 못했습니다.\nrelease 폴더 안에서 실행 중인지 확인하세요.")
            return
        release_dir = root_dir / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        try:
            _env = os.environ.copy()
            _env["NOPAUSE"] = "1"
            proc = subprocess.run(
                ["cmd.exe", "/c", str(build_bat), "next"],
                cwd=str(root_dir),
                check=False,
                env=_env,
            )
        except Exception as e:
            messagebox.showerror("BPE", f"재빌드 실패: {e}")
            return
        if proc.returncode != 0:
            messagebox.showerror(
                "BPE",
                "빌드가 실패했습니다.\n"
                "BPE_next.exe 가 실행 중이면 종료 후 다시 시도하거나,\n"
                "CMD에서 build_exe.bat next 를 직접 실행해 오류를 확인하세요.",
            )
            return
        # 스테이징 빌드: 실행 중인 BPE_next.exe 를 덮어쓸 수 없을 때
        # BPE_next_staging.exe 만 남음 → 항상 그 파일을 우선 실행
        staging_exe = release_dir / "BPE_next_staging.exe"
        next_exe = release_dir / "BPE_next.exe"
        if staging_exe.exists():
            launch = staging_exe
            restart_msg = (
                "업데이트 빌드가 완료되었습니다.\n"
                "현재 실행 중인 EXE를 바꿀 수 없어 새 파일로 재실행합니다.\n\n"
                "  BPE_next_staging.exe\n\n"
                "재실행할까요?"
            )
        elif next_exe.exists():
            launch = next_exe
            restart_msg = "업데이트가 완료되었습니다. 재실행할까요?"
        else:
            messagebox.showerror("BPE", "업데이트용 EXE를 찾을 수 없습니다.\nrelease 폴더를 확인하세요.")
            return
        if not messagebox.askyesno("BPE", restart_msg):
            return
        try:
            subprocess.Popen([str(launch)], cwd=str(release_dir), shell=False)
        except Exception as e:
            messagebox.showerror("BPE", f"재실행 실패: {e}")
            return
        self.destroy()
        sys.exit(0)

    # ── ShotGrid ─────────────────────────────────────────────────────

    def _sg_fill_entry(self, entry: ctk.CTkEntry, value: str) -> None:
        """CTkEntry의 placeholder 충돌을 우회하여 값을 직접 채웁니다."""
        try:
            was_readonly = str(entry.cget("state")) in ("readonly", "disabled")
            if was_readonly:
                entry.configure(state="normal")
            entry.delete(0, "end")
            if value:
                entry.insert(0, value)
            if was_readonly:
                entry.configure(state="readonly")
        except Exception:
            pass

    def _sg_log(self, msg: str) -> None:
        self.sg_log.configure(state="normal")
        self.sg_log.insert("end", msg + "\n")
        self.sg_log.see("end")
        self.sg_log.configure(state="disabled")

    def _sg_start_worker(self, fn, on_done) -> None:
        q: queue.Queue = queue.Queue()

        def work():
            try:
                q.put(("ok", fn()))
            except Exception as e:
                q.put(("err", e))

        def poll():
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                self.after(80, poll)
                return
            on_done(kind, payload)

        threading.Thread(target=work, daemon=True).start()
        self.after(80, poll)

    # ── 파일 드롭 / 선택 ──────────────────────────────────────────────

    def _sg_on_drop_event(self, event) -> None:
        """tkinterdnd2 Drop 이벤트 핸들러."""
        raw = (event.data or "").strip()
        # tkinterdnd2 는 여러 파일을 {path1} {path2} 형태로 전달할 수 있음
        if raw.startswith("{"):
            raw = raw[1:]
        if raw.endswith("}"):
            raw = raw[:-1]
        path = raw.split("} {")[0].strip()
        self._sg_on_file_drop(path)

    def _sg_on_file_drop(self, path: str) -> None:
        """MOV/MP4 파일이 드롭되거나 선택됐을 때 처리."""
        path = (path or "").strip().strip('"')
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext not in (".mov", ".mp4"):
            self._sg_log(f"⚠  지원하지 않는 형식: {ext}  (.mov / .mp4 만 가능)")
            self._sg_drop_label.configure(
                text=f"⚠  {ext} 은 지원하지 않습니다 (.mov / .mp4)", text_color="#e06060"
            )
            return

        self.sg_mov_path_var.set(path)
        filename = Path(path).name
        self._sg_drop_label.configure(
            text=f"✓  {filename}", text_color=ACCENT,
        )
        self._sg_log(f"파일 선택: {path}")
        # #region agent log
        try:
            _sz = os.path.getsize(path) if os.path.isfile(path) else -1
        except OSError:
            _sz = -1
        _debug_9b9c60_log(
            "H1",
            "setup_pro_manager.py:_sg_on_file_drop",
            "mov_selected",
            {
                "ext": ext,
                "is_file": os.path.isfile(path),
                "size_bytes": _sz,
            },
        )
        # #endregion

        # 파일명 자동 파싱 — CTkEntry placeholder 충돌 우회: StringVar + 직접 삽입 병행
        version_name = sgc.parse_version_name_from_filename(filename)
        self.sg_version_name_var.set(version_name)
        self._sg_fill_entry(self._sg_version_name_entry, version_name)

        # 파일명 우선, 못 찾으면 전체 경로(폴더 포함) 탐색
        shot_code = sgc.parse_shot_code_from_filename(path)
        if shot_code:
            self.sg_link_var.set(shot_code)
            self._sg_fill_entry(self._sg_link_entry, shot_code)
            self.sg_link_id = None
            self._sg_link_id_label.configure(text="")
            self._sg_log(f"샷 코드 파싱: {shot_code} — ShotGrid에서 샷/프로젝트 조회 중…")
            self._sg_start_worker(
                lambda sc=shot_code: self._sg_fetch_shot_by_code(sc),
                self._sg_on_shot_fetched,
            )
        else:
            self._sg_log(
                f"파일명에서 샷 코드를 찾지 못했습니다.\n"
                f"인식된 경로: {path}\n"
                "Link 필드에 샷 코드를 수동으로 입력하세요."
            )

    def _sg_fetch_shot_by_code(self, shot_code: str):
        """백그라운드에서 샷 코드로 Shot + Project + comp Task + 담당자 조회."""
        sg = sgc.get_default_sg()
        shot = sgc.find_shot_any_project(sg, shot_code)
        if not shot:
            return None
        comp_task, comp_assignee = sgc.get_comp_task_and_assignee(sg, shot["id"])
        return {
            "shot":           shot,
            "comp_task":      comp_task,
            "comp_assignee":  comp_assignee,
        }

    def _sg_on_shot_fetched(self, kind, payload) -> None:
        if kind != "ok":
            self._sg_log(f"[오류] 샷 조회 실패: {payload}")
            return
        if not payload:
            self._sg_log("ShotGrid에서 샷을 찾지 못했습니다 — Link 필드를 수동으로 확인하세요.")
            return

        # 신규 형식: dict with "shot"/"comp_task"/"comp_assignee" keys
        if isinstance(payload, dict) and "shot" in payload:
            shot           = payload.get("shot") or {}
            comp_task      = payload.get("comp_task")
            comp_assignee  = payload.get("comp_assignee")
        else:
            shot, comp_task, comp_assignee = payload, None, None

        if not shot:
            self._sg_log("ShotGrid에서 샷을 찾지 못했습니다.")
            return

        shot_id   = shot.get("id")
        shot_code = shot.get("code") or ""
        proj_info = shot.get("project") or {}
        proj_name = (proj_info.get("name") or "").strip()
        proj_id   = proj_info.get("id")

        # Link 업데이트
        self.sg_link_var.set(shot_code)
        self._sg_fill_entry(self._sg_link_entry, shot_code)
        self.sg_link_id = shot_id
        self._sg_link_id_label.configure(text=f"✓ {shot_code}")

        # Project 업데이트
        if proj_id:
            self.sg_proj_id = proj_id
            self.sg_proj_label_var.set(proj_name if proj_name else "")
            self._sg_fill_entry(self._sg_proj_entry, proj_name if proj_name else "")

        # comp Task 자동 채움
        if comp_task:
            task_id      = comp_task.get("id")
            task_content = (comp_task.get("content") or "comp").strip()
            self.sg_task_id = task_id
            self.sg_task_input_var.set(task_content)
            self._sg_fill_entry(self._sg_task_entry, task_content)
            self._sg_task_id_label.configure(text=f"✓ {task_content}")

        # comp 작업자 자동 채움 (어사인 되어 있을 때만)
        if comp_assignee:
            a_id    = comp_assignee.get("id")
            a_name  = (comp_assignee.get("name") or "").strip()
            a_login = (comp_assignee.get("login") or "").strip()
            # #region agent log
            _sg_dbg("H1/H2", "setup_pro_manager.py:_sg_on_shot_fetched", "comp_assignee_autofill",
                    {"a_id": a_id, "a_name": a_name, "a_login": a_login, "raw": comp_assignee})
            # #endregion
            if a_id and a_name:
                self.sg_artist_id    = a_id
                self.sg_artist_login = a_login
                self.sg_artist_var.set(a_name)
                self._sg_fill_entry(self._sg_artist_entry, a_name)
                self._sg_artist_id_label.configure(text=f"✓ {a_name}")

        msg = f"샷 확인: {shot_code} / 프로젝트: {proj_name or proj_id}"
        if comp_task:
            msg += f" / 태스크: {comp_task.get('content', 'comp')}"
        if comp_assignee:
            msg += f" / 작업자: {(comp_assignee.get('name') or '')}"
        self._sg_log(msg)

    def _sg_browse_mov(self) -> None:
        self.update_idletasks()
        init = (self.sg_mov_path_var.get() or "").strip()
        init_dir = os.path.dirname(init) if init and os.path.isfile(init) else ""
        try:
            p = filedialog.askopenfilename(
                title="MOV 파일 선택",
                initialdir=init_dir or None,
                filetypes=[("Video files", "*.mov *.mp4"), ("All files", "*.*")],
            )
        except TypeError:
            p = filedialog.askopenfilename(title="MOV 파일 선택")
        p = (p or "").strip()
        if not p:
            return
        self._sg_on_file_drop(p)

    def _sg_clear_mov(self) -> None:
        self.sg_mov_path_var.set("")
        self.sg_version_name_var.set("")
        self._sg_fill_entry(self._sg_version_name_entry, "")
        self.sg_link_var.set("")
        self._sg_fill_entry(self._sg_link_entry, "")
        self.sg_link_id = None
        self._sg_link_id_label.configure(text="")
        self.sg_proj_label_var.set("")
        self._sg_fill_entry(self._sg_proj_entry, "")
        self.sg_proj_id = None
        # Task 초기화
        self.sg_task_input_var.set("")
        self._sg_fill_entry(self._sg_task_entry, "")
        self.sg_task_id = None
        self._sg_task_id_label.configure(text="")
        # Artist 초기화
        self.sg_artist_var.set("")
        self._sg_fill_entry(self._sg_artist_entry, "")
        self.sg_artist_id    = None
        self.sg_artist_login = None
        self._sg_artist_id_label.configure(text="")
        # 업로드 상태 초기화
        try:
            self._sg_upload_status.configure(text="")
        except Exception:
            pass
        try:
            self._sg_upload_progress.set(0)
            self._sg_upload_pct_label.configure(text="0%")
        except Exception:
            pass
        self._sg_drop_label.configure(
            text="MOV 파일을 여기에 드래그하거나  [파일 선택]  버튼을 누르세요\n(.mov / .mp4)",
            text_color=TEXT_DIM,
        )
        self._sg_log("파일 선택 초기화.")

    # ── Shot Builder 동기화 ───────────────────────────────────────────

    def _sg_pull_shot_from_builder(self) -> None:
        s = (self.sb_shot_name_var.get() or "").strip()
        if not s:
            messagebox.showwarning("BPE", "Shot Builder에 샷 이름을 먼저 입력하세요.")
            return
        self.sg_link_var.set(s)
        self.sg_link_id = None
        self._sg_link_id_label.configure(text="")
        self._sg_log(f"Shot Builder에서 샷 코드 복사: {s}  — ShotGrid 조회 중…")
        self._sg_start_worker(
            lambda sc=s: self._sg_fetch_shot_by_code(sc),
            self._sg_on_shot_fetched,
        )

    # ── Artist 자동완성 ───────────────────────────────────────────────

    def _sg_on_artist_keyrelease(self, _event=None) -> None:
        if self._sg_artist_after:
            try:
                self.after_cancel(self._sg_artist_after)
            except Exception:
                pass
        self._sg_artist_after = self.after(300, self._sg_artist_autocomplete)

    def _sg_artist_autocomplete(self) -> None:
        q = (self._sg_artist_entry.get() or "").strip()
        if len(q) < 1:
            return

        def job():
            sg = sgc.get_default_sg()
            return sgc.search_human_users(sg, q)

        def done(kind, payload):
            if kind != "ok" or not payload:
                return
            users = payload
            self._sg_show_autocomplete_popup(
                anchor=self._sg_artist_entry,
                items=[f"{u.get('name', '')}  ({u.get('login', '')})" for u in users],
                on_select=lambda idx: self._sg_select_artist(users[idx]),
            )

        self._sg_start_worker(job, done)

    def _sg_select_artist(self, user: dict) -> None:
        name  = user.get("name") or user.get("login") or ""
        uid   = user.get("id")
        login = user.get("login") or ""
        self.sg_artist_var.set(name)
        self.sg_artist_id    = uid
        self.sg_artist_login = login
        self._sg_artist_id_label.configure(text=f"✓ {name}")
        self._sg_log(f"Artist 선택: {name}")
        # #region agent log
        _sg_dbg("H1/H2", "setup_pro_manager.py:_sg_select_artist", "artist_selected",
                {"uid": uid, "name": name, "login": login})
        # #endregion

    # ── Task 자동완성 ─────────────────────────────────────────────────

    def _sg_on_task_keyrelease(self, _event=None) -> None:
        if self._sg_task_after:
            try:
                self.after_cancel(self._sg_task_after)
            except Exception:
                pass
        self._sg_task_after = self.after(300, self._sg_task_autocomplete)

    def _sg_task_autocomplete(self) -> None:
        q = (self._sg_task_entry.get() or "").strip()
        shot_id = self.sg_link_id
        if shot_id is None:
            return

        def job():
            sg = sgc.get_default_sg()
            return sgc.search_tasks_for_shot(sg, shot_id, q)

        def done(kind, payload):
            if kind != "ok" or not payload:
                return
            tasks = payload
            self._sg_task_rows = []
            labels = []
            for t in tasks:
                tid     = t.get("id")
                content = (t.get("content") or "").strip() or "(content 없음)"
                proj    = (((t.get("project") or {}).get("name")) or "").strip()
                entity  = (((t.get("entity") or {}).get("name")) or "").strip()
                label   = f"{content}  {proj}" + (f" / {entity}" if entity else "")
                self._sg_task_rows.append({"id": tid, "label": label, "content": content})
                labels.append(label)
            self._sg_show_autocomplete_popup(
                anchor=self._sg_task_entry,
                items=labels,
                on_select=lambda idx: self._sg_select_task(self._sg_task_rows[idx]),
            )

        self._sg_start_worker(job, done)

    def _sg_select_task(self, row: dict) -> None:
        label   = row.get("label") or ""
        content = row.get("content") or label
        tid     = row.get("id")
        self.sg_task_input_var.set(content)
        self.sg_task_id = tid
        self._sg_task_id_label.configure(text=f"✓ {content}")
        self._sg_log(f"Task 선택: {content}")

    # ── 자동완성 팝업 ─────────────────────────────────────────────────

    def _sg_show_autocomplete_popup(self, anchor, items: list, on_select) -> None:
        """앵커 위젯 아래에 CTkToplevel 리스트박스 팝업을 표시합니다."""
        if not items:
            return

        # 기존 팝업 닫기
        existing = getattr(self, "_sg_autocomplete_popup", None)
        if existing is not None:
            try:
                existing.destroy()
            except Exception:
                pass
        self._sg_autocomplete_popup = None

        try:
            anchor.update_idletasks()
            x = anchor.winfo_rootx()
            y = anchor.winfo_rooty() + anchor.winfo_height() + 2
            # ScrollableFrame 안에서 winfo_width()가 과도하게 커질 수 있으므로 상한 고정
            w = min(max(anchor.winfo_width(), 260), 480)
            # 화면 오른쪽 밖으로 나가지 않도록 보정
            screen_w = self.winfo_screenwidth()
            if x + w > screen_w - 10:
                x = max(0, screen_w - w - 10)
        except Exception:
            return

        pop = ctk.CTkToplevel(self)
        pop.overrideredirect(True)
        pop.geometry(f"{w}x{min(len(items)*32+8, 220)}+{x}+{y}")
        pop.configure(fg_color=PANEL_BG)
        pop.attributes("-topmost", True)
        self._sg_autocomplete_popup = pop

        lb = tk.Listbox(
            pop, bg=PANEL_BG, fg=TEXT, selectbackground=SELECT_BG,
            highlightthickness=0, relief="flat", font=("Segoe UI", 11),
            activestyle="none",
        )
        lb.pack(fill="both", expand=True)
        for item in items:
            lb.insert("end", item)

        def select(idx: int) -> None:
            try:
                pop.destroy()
            except Exception:
                pass
            self._sg_autocomplete_popup = None
            on_select(idx)

        lb.bind("<ButtonRelease-1>", lambda e: select(lb.curselection()[0]) if lb.curselection() else None)
        lb.bind("<Return>", lambda e: select(lb.curselection()[0]) if lb.curselection() else None)

        def close_on_focus_out(*_a):
            # FocusOut이 ButtonRelease보다 먼저 오는 경우를 대비해 150ms 지연 후 닫음
            self.after(150, lambda: self._sg_close_autocomplete_popup())

        pop.bind("<FocusOut>", close_on_focus_out)
        pop.bind("<Escape>", lambda *_: self._sg_close_autocomplete_popup())

    def _sg_close_autocomplete_popup(self) -> None:
        existing = getattr(self, "_sg_autocomplete_popup", None)
        if existing is not None:
            try:
                existing.destroy()
            except Exception:
                pass
            self._sg_autocomplete_popup = None

    # ── 연결 테스트 ───────────────────────────────────────────────────

    def _sg_test_connection(self) -> None:
        self._sg_log("연결 테스트 중…")

        def job():
            sg = sgc.get_default_sg()
            return sgc.test_connection(sg)

        def done(kind, payload):
            if kind == "ok":
                self._sg_log(payload)
                messagebox.showinfo("Publish", payload)
            else:
                err = payload
                self._sg_log(f"[오류] {err}")
                messagebox.showerror("Publish", str(err))

        self._sg_start_worker(job, done)

    # ── Create Version ────────────────────────────────────────────────

    def _sg_estimate_upload_minutes(self, size_bytes: int) -> int:
        """대략적 업로드 소요(분). 네트워크·파일 형식에 따라 달라질 수 있음."""
        if size_bytes <= 0:
            return 3
        est = int(size_bytes / (12 * 1024 * 1024)) + 1
        return max(2, min(30, est))

    def _sg_create_version(self) -> None:
        mov_path     = (self.sg_mov_path_var.get() or "").strip()
        version_name = (self.sg_version_name_var.get() or "").strip()
        shot_id      = self.sg_link_id
        proj_id      = self.sg_proj_id

        if not mov_path:
            messagebox.showwarning("BPE", "MOV 파일을 먼저 선택하거나 드롭하세요.")
            return
        if not version_name:
            messagebox.showwarning("BPE", "Version Name이 비어 있습니다.")
            return
        if shot_id is None:
            messagebox.showwarning(
                "BPE",
                "Link(Shot)가 확인되지 않았습니다.\n파일명에 E###_S###_#### 패턴이 없으면 Shot Builder를 활용하거나,\nLink 필드에 입력 후 잠시 기다려 주세요.",
            )
            return
        if proj_id is None:
            messagebox.showwarning("BPE", "Project를 확인할 수 없습니다. 파일을 다시 드롭해 보세요.")
            return

        if self.sg_artist_id is None:
            messagebox.showwarning(
                "Publish",
                "Artist가 선택되지 않았습니다.\n\n"
                "웹 오버뷰에는 belucaAPI(스크립트)로 표시됩니다.\n"
                "자동완성 목록에서 아티스트를 선택한 뒤 업로드하는 것을 권장합니다.\n\n"
                "그래도 계속하려면 확인을 누르세요.",
            )

        task_id    = self.sg_task_id
        artist_id  = self.sg_artist_id
        artist_login = getattr(self, "sg_artist_login", None)
        # CTkEntry.get() 으로 직접 읽어야 textvariable 미반영 문제를 피함
        try:
            description = (self._sg_desc_entry.get() or "").strip()
        except Exception:
            description = (self.sg_desc_var.get() or "").strip()
        st_code    = sgc.parse_task_status_selection(self.sg_status_combo.get())
        # #region agent log
        _sg_dbg("H1/H2", "setup_pro_manager.py:_sg_create_version", "create_version_called",
                {"artist_id": artist_id, "artist_login": artist_login,
                 "artist_text": (self.sg_artist_var.get() or ""),
                 "mov_path": mov_path, "shot_id": shot_id, "proj_id": proj_id,
                 "task_id": task_id, "description": description})
        # #endregion

        self._sg_log(f"Version 생성 중: {version_name} …")

        try:
            _mov_sz = os.path.getsize(mov_path)
        except OSError:
            _mov_sz = 0
        est_min = self._sg_estimate_upload_minutes(_mov_sz)

        # 업로드 중 UI 상태 — 버튼 비활성화 + 진행 표시
        try:
            self._sg_create_btn.configure(state="disabled")
        except Exception:
            pass
        try:
            self._sg_upload_progress.set(0)
            self._sg_upload_pct_label.configure(text="0%")
        except Exception:
            pass
        try:
            self._sg_upload_status.configure(
                text=f"⏳  업로드 중… 영상 크기에 따라 약 {est_min}분 정도 걸릴 수 있습니다.",
                text_color="#e0c050",
            )
        except Exception:
            pass

        prog_q: queue.Queue = queue.Queue()
        self._sg_upload_prog_active = True

        def _poll_sg_upload_progress() -> None:
            if not getattr(self, "_sg_upload_prog_active", False):
                return
            try:
                while True:
                    frac = float(prog_q.get_nowait())
                    frac = max(0.0, min(1.0, frac))
                    try:
                        self._sg_upload_progress.set(frac)
                        self._sg_upload_pct_label.configure(text=f"{int(frac * 100)}%")
                    except Exception:
                        pass
            except queue.Empty:
                pass
            self.after(80, _poll_sg_upload_progress)

        _poll_sg_upload_progress()

        def _push_prog(frac: float) -> None:
            try:
                prog_q.put(float(frac))
            except Exception:
                pass

        # #region agent log
        _debug_9b9c60_log(
            "PRE",
            "setup_pro_manager.py:_sg_create_version",
            "worker_start",
            {
                "est_minutes_ui": est_min,
                "mov_size_bytes": _mov_sz,
                "artist_id": artist_id,
                "sudo_will_resolve": artist_id is not None,
            },
        )
        # #endregion

        def job():
            sg0 = sgc.get_default_sg()
            sudo_login: Optional[str] = None
            post_warn: Optional[str] = None
            if artist_id is not None:
                fb = (artist_login or "").strip() or None
                sudo_login = sgc.resolve_sudo_login(
                    sg0, int(artist_id), fallback_login=fb
                )
                if not sudo_login:
                    post_warn = (
                        "선택한 아티스트에 ShotGrid login/email이 없습니다. "
                        "오버뷰에는 스크립트(belucaAPI)로 표시될 수 있습니다. "
                        "관리자에게 HumanUser의 Login 필드 입력을 요청하세요."
                    )
            sg = sgc.get_shotgun_for_version_mutation(sudo_login)
            # #region agent log
            _debug_9b9c60_log(
                "H4",
                "setup_pro_manager.py:_sg_create_version",
                "before_create_version",
                {"using_sudo": bool((sudo_login or "").strip())},
            )
            # #endregion
            ver = sgc.create_version(
                sg,
                project_id=int(proj_id),
                shot_id=int(shot_id),
                task_id=int(task_id) if task_id is not None else None,
                version_name=version_name,
                description=description,
                artist_id=int(artist_id) if artist_id is not None else None,
                sg_status=st_code,
            )
            ver_id = ver["id"]
            # #region agent log
            _debug_9b9c60_log(
                "H2",
                "setup_pro_manager.py:_sg_create_version",
                "after_create_version",
                {"version_id": int(ver_id)},
            )
            # #endregion
            sgc.upload_movie_to_version(sg, ver_id, mov_path, progress_cb=_push_prog)
            # 썸네일 업로드 — MOV 첫 프레임 자동 추출 (ffmpeg 있을 때)
            try:
                sgc.upload_thumbnail_to_version(sg, ver_id, movie_path=mov_path)
            except Exception as thumb_e:
                logger.debug("Thumbnail upload skipped: %s", thumb_e)
            save_shotgrid_settings({"last_project_id": int(proj_id)})
            # #region agent log
            _sg_dbg(
                "sudo",
                "setup_pro_manager.py:_sg_create_version",
                "upload_done",
                {"artist_id": artist_id, "sudo_used": bool(sudo_login)},
                run_id="post-fix",
            )
            # #endregion
            return (ver_id, post_warn)

        def done(kind, payload):
            self._sg_upload_prog_active = False
            # 버튼 복원
            try:
                self._sg_create_btn.configure(state="normal")
            except Exception:
                pass
            if kind != "ok":
                self._sg_log(f"[오류] {payload}")
                try:
                    self._sg_upload_status.configure(
                        text=f"✗  업로드 실패: {payload}", text_color="#e06060"
                    )
                except Exception:
                    pass
                err_text = str(payload)
                if "sudo" in err_text.lower() or "permission" in err_text.lower():
                    err_text += (
                        "\n\n(힌트) 스크립트 belucaAPI 가 다른 사용자로 sudo 할 수 있는지 "
                        "ShotGrid 관리자(권한/스크립트 설정)를 확인하세요."
                    )
                try:
                    self._sg_upload_progress.set(0)
                    self._sg_upload_pct_label.configure(text="0%")
                except Exception:
                    pass
                messagebox.showerror("Publish", err_text)
                return
            ver_id, post_warn = payload
            if post_warn:
                self._sg_log(f"[알림] {post_warn}")
            self._sg_log(f"✓  Version 업로드 완료 — id={ver_id}  [{version_name}]")
            try:
                self._sg_upload_progress.set(1.0)
                self._sg_upload_pct_label.configure(text="100%")
            except Exception:
                pass
            try:
                self._sg_upload_status.configure(
                    text=f"✓  업로드 완료 — {version_name}  (id={ver_id})",
                    text_color=ACCENT,
                )
            except Exception:
                pass
            msg_ok = (
                f"Version 업로드 완료!\n\n"
                f"Version Name: {version_name}\nVersion id: {ver_id}"
            )
            if post_warn:
                msg_ok += f"\n\n알림:\n{post_warn}"
            messagebox.showinfo("Publish", msg_ok)

        self._sg_start_worker(job, done)

    # ── Shot Builder Logic ───────────────────────────────────────────
    def _sb_browse_server_root(self) -> None:
        """
        CTk + tk filedialog 조합에서 parent/grab 이 꼬이면 선택 경로가 비어 돌아오는 경우가 있어,
        parent 없이 폴더 대화상자를 띄우고 StringVar·Entry 양쪽에 반영합니다.
        """
        self.update_idletasks()
        self.update()
        init = (self.sb_server_root_var.get() or "").strip()
        if init and not os.path.isdir(init):
            init = ""
        try:
            d = filedialog.askdirectory(
                title="서버 루트 경로 선택",
                initialdir=init or None,
            )
        except TypeError:
            d = filedialog.askdirectory(title="서버 루트 경로 선택")
        d = (d or "").strip()
        if not d:
            return
        d = os.path.normpath(d)
        self.sb_server_root_var.set(d)
        try:
            ent = getattr(self, "sb_server_root_entry", None)
            if ent is not None and ent.winfo_exists():
                ent.delete(0, "end")
                ent.insert(0, d)
        except Exception:
            pass

    def _sb_update_path_preview(self) -> None:
        """샷 이름 입력 시 경로 미리보기를 업데이트합니다."""
        pass

    def _sb_save_settings(self) -> None:
        save_shot_builder_settings({
            "server_root": self.sb_server_root_var.get().strip(),
            "preset":      self.sb_preset_var.get().strip(),
        })
        self._sb_log("설정이 저장되었습니다.")

    def _sb_log(self, msg: str) -> None:
        self.sb_log_text.configure(state="normal")
        self.sb_log_text.insert("end", msg + "\n")
        self.sb_log_text.see("end")
        self.sb_log_text.configure(state="disabled")

    def _sb_clear_log(self) -> None:
        self.sb_log_text.configure(state="normal")
        self.sb_log_text.delete("1.0", "end")
        self.sb_log_text.configure(state="disabled")

    def _sb_create_nk(self) -> None:
        server_root = self.sb_server_root_var.get().strip()
        preset_name = self.sb_preset_var.get().strip()
        # 프리셋 이름 = 프로젝트 코드 = 서버 폴더명 (컨벤션)
        project_code = preset_name.upper()

        # StringVar 바인딩 미동작 대비: 위젯에서 직접 읽기
        shot_name = self.sb_shot_name_var.get().strip()
        if not shot_name and hasattr(self, "sb_shot_name_entry"):
            raw = self.sb_shot_name_entry.get().strip()
            placeholder = "예) E107_S012_0360"
            if raw and raw != placeholder:
                shot_name = raw
        shot_name = shot_name.upper()

        errors = []
        if not server_root:  errors.append("서버 루트 경로를 입력하세요.")
        if not preset_name:  errors.append("프리셋을 선택하세요.")
        if not shot_name:    errors.append("샷 이름을 입력하세요.")
        if errors:
            messagebox.showerror("Shot Builder", "\n".join(errors))
            return

        if not re.match(r"^[A-Z0-9_]+$", project_code):
            messagebox.showerror(
                "Shot Builder",
                f"프리셋 이름 '{project_code}'에 영문 대문자/숫자/_ 이외의 문자가 있습니다.\n"
                "Preset Manager에서 코드명을 수정하세요.",
            )
            return

        parsed = parse_shot_name(shot_name)
        if not parsed:
            messagebox.showerror("Shot Builder", f"샷 이름 형식이 올바르지 않습니다: {shot_name}\n예) E107_S022_0080")
            return

        preset_data = self.presets.get(preset_name)
        if not preset_data:
            messagebox.showerror("Shot Builder", f"프리셋 '{preset_name}'을 찾을 수 없습니다.")
            return

        self._sb_clear_log()
        self._sb_log("─" * 44)
        self._sb_log(f"▶ NK 생성 시작  {shot_name}")
        self._sb_log(f"  서버 루트: {server_root}")
        self._sb_log(f"  프리셋   : {preset_name}  (폴더명 = 프로젝트 코드)")
        self._sb_log(f"  FPS      : {preset_data.get('fps')}  |  "
                     f"해상도 : {preset_data.get('plate_width')}×{preset_data.get('plate_height')}")

        paths = build_shot_paths(server_root, project_code, shot_name)
        if not paths:
            messagebox.showerror("Shot Builder", "경로 생성에 실패했습니다.")
            return

        shot_root = paths["shot_root"]
        self._sb_log(f"  샷 루트: {shot_root}")

        if not shot_root.exists():
            if not messagebox.askyesno(
                "Shot Builder",
                f"서버에 해당 샷 폴더가 없습니다:\n{shot_root}\n\n폴더를 새로 생성하고 계속 진행하시겠습니까?",
            ):
                self._sb_log("취소되었습니다.")
                return

        nuke_dir = paths["nuke_dir"]
        # v002+ 는 Nuke에서 작업자가 버전업 — Shot Builder 는 항상 v001 만 생성
        nk_version = "v001"
        self._sb_log(f"  NK 버전: {nk_version} (고정)")

        nk_ver_dir = nuke_dir / nk_version
        nk_filename = f"{shot_name}_comp_{nk_version}.nk"
        nk_filepath = nk_ver_dir / nk_filename

        if nk_filepath.exists():
            self._sb_log("  생성 중단: 동일 이름 NK 가 이미 있습니다.")
            ShotBuilderNoticeDialog(
                self,
                title="Shot Builder — NK 이미 있음",
                headline="이미 NK 파일이 있습니다",
                body=(
                    "이 샷의 comp/devl/nuke/v001 폴더에\n"
                    f"「{nk_filename}」 파일이 이미 있습니다.\n\n"
                    "Shot Builder는 초기 NK(v001)만 만들어 주는 도구입니다.\n"
                    "추가 버전(v002 이후)은 Nuke에서 Save As / 버전업으로 진행해 주세요.\n\n"
                    "기존 파일을 덮어쓰지 않았습니다."
                ),
                detail_path=str(nk_filepath),
            )
            return

        try:
            nk_ver_dir.mkdir(parents=True, exist_ok=True)
            self._sb_log(f"  폴더 준비: {nk_ver_dir}")
        except Exception as exc:
            messagebox.showerror("Shot Builder", f"폴더 생성 실패:\n{exc}")
            return

        try:
            content, patch_warnings = generate_nk_content(preset_data, shot_name, paths, nk_version)
            nk_filepath.write_text(content, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Shot Builder", f"NK 파일 쓰기 실패:\n{exc}")
            return

        if patch_warnings:
            for w in patch_warnings:
                self._sb_log(w)

        self._sb_log(f"\n✔ 완료!")
        self._sb_log(f"  파일:     {nk_filepath}")
        self._sb_log(f"  플레이트: {paths['plate_hi']}")
        self._sb_log(f"  편집본:   {paths['edit']}")
        self._sb_log(f"  렌더:     {paths['renders']}")

        self._last_nk_dir = str(nk_ver_dir)
        self._last_nk_path = str(nk_filepath)
        self.sb_open_folder_btn.configure(state="normal", text_color=TEXT)

        # NK 생성 성공 시 서버 루트·프리셋 설정 자동 저장 (다음 실행 때 기억)
        save_shot_builder_settings({
            "server_root": server_root,
            "preset":      preset_name,
        })

        messagebox.showinfo("Shot Builder", f"NK 파일 생성 완료!\n\n{nk_filepath}")

    def _sb_open_folder(self) -> None:
        if self._last_nk_dir:
            try:
                os.startfile(self._last_nk_dir)
            except Exception as exc:
                messagebox.showerror("Shot Builder", f"폴더 열기 실패: {exc}")


class BPESplashScreen(tk.Toplevel):
    """
    BELUCA Pipeline Engine 스플래시 스크린.
    애니메이션(페이드인 + 진행 바 + 도트 인디케이터)을 포함합니다.
    """

    _STEPS = [
        "프리셋 데이터 불러오는 중...",
        "UI 컴포넌트 초기화 중...",
        "색상 관리 설정 확인 중...",
        "BELUCA Pipeline Engine 시작 중...",
    ]

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root)
        self._root = root
        self._alpha   = 0.0
        self._prog    = 0.0          # 0.0 ~ 1.0
        self._step_i  = 0
        self._dot_i   = 0
        self._done    = False

        W, H = 460, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - W) // 2
        y  = (sh - H) // 2

        self.overrideredirect(True)
        self.geometry(f"{W}x{H}+{x}+{y}")
        self.configure(bg="#1c1c1e")
        self.attributes("-alpha", 0.0)
        self.attributes("-topmost", True)
        self.lift()

        self._apply_shadow()
        self._build()
        self._fade_in()

    def _apply_shadow(self) -> None:
        try:
            import ctypes
            hwnd = self.winfo_id()
            # 둥근 모서리 (Win11)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception:
            pass

    def _build(self) -> None:
        W, H = 460, 280
        BG   = "#1c1c1e"
        ACC  = "#f08a24"
        DIM  = "#86868b"

        self._canvas = tk.Canvas(
            self, width=W, height=H, bg=BG, bd=0,
            highlightthickness=0, relief="flat",
        )
        self._canvas.pack(fill="both", expand=True)
        c = self._canvas

        # 배경 라운드 사각형 테두리
        c.create_rectangle(1, 1, W-1, H-1, outline="#3a3a3c", width=1)

        # ── 브랜드 (아이콘/사각형/B 마크 없음 — 텍스트 로딩 패널만) ──
        c.create_text(30, 38, text="BELUCA", anchor="w",
                      fill="#f5f5f7", font=("Segoe UI", 22, "bold"))
        c.create_text(30, 64, text="Pipeline Engine", anchor="w",
                      fill=DIM, font=("Segoe UI", 11))

        # 버전 (오른쪽 상단, VERSION.txt / EXE 번들과 연동)
        self._ver_lbl = c.create_text(W-20, 28, text="", anchor="e",
                                       fill=DIM, font=("Segoe UI", 10))

        # ── 구분선 ───────────────────────────────────────────────
        c.create_line(30, 90, W-30, 90, fill="#3a3a3c", width=1)

        # ── 슬로건 ───────────────────────────────────────────────
        c.create_text(W//2, 122, text="VFX Pipeline Preset & Shot Builder",
                      fill=DIM, font=("Segoe UI", 11), anchor="center")

        # ── 진행 바 배경 ─────────────────────────────────────────
        self._bar_x0, self._bar_y0 = 30, 168
        self._bar_x1, self._bar_y1 = W-30, 180
        c.create_rectangle(
            self._bar_x0, self._bar_y0,
            self._bar_x1, self._bar_y1,
            fill="#2c2c2e", outline="",
        )
        # 진행 바 채움
        self._bar_fill = c.create_rectangle(
            self._bar_x0, self._bar_y0,
            self._bar_x0, self._bar_y1,
            fill=ACC, outline="",
        )
        # 진행 바 끝단 하이라이트
        self._bar_cap = c.create_oval(
            self._bar_x0 - 4, self._bar_y0 - 2,
            self._bar_x0 + 4, self._bar_y1 + 2,
            fill=ACC, outline="",
        )

        # ── 상태 텍스트 ──────────────────────────────────────────
        self._status_id = c.create_text(
            30, 200, anchor="w", text=self._STEPS[0],
            fill=DIM, font=("Segoe UI", 10),
        )

        # ── 도트 애니메이션 ───────────────────────────────────────
        self._dots: list = []
        dot_y = H - 34
        for i in range(4):
            ox = W//2 - 24 + i * 16
            d = c.create_oval(ox, dot_y, ox+8, dot_y+8, fill="#3a3a3c", outline="")
            self._dots.append(d)

        # ── 저작권 ───────────────────────────────────────────────
        c.create_text(W//2, H-12, text="© 2025 BELUCA  |  All rights reserved",
                      fill="#3a3a3c", font=("Segoe UI", 8), anchor="center")

    # ── 페이드인 ─────────────────────────────────────────────────
    def _fade_in(self) -> None:
        self._alpha = min(self._alpha + 0.07, 1.0)
        self.attributes("-alpha", self._alpha)
        if self._alpha < 1.0:
            self.after(20, self._fade_in)
        else:
            self._animate()

    # ── 메인 애니메이션 루프 ─────────────────────────────────────
    def _animate(self) -> None:
        if self._done:
            return

        # 진행 바 업데이트
        self._prog = min(self._prog + 0.008, 1.0)
        x1 = self._bar_x0 + (self._bar_x1 - self._bar_x0) * self._prog
        self._canvas.coords(
            self._bar_fill,
            self._bar_x0, self._bar_y0, x1, self._bar_y1,
        )
        self._canvas.coords(
            self._bar_cap,
            x1 - 4, self._bar_y0 - 2, x1 + 4, self._bar_y1 + 2,
        )

        # 스텝 텍스트 업데이트
        step_th = int(self._prog * len(self._STEPS))
        step_th = min(step_th, len(self._STEPS) - 1)
        if step_th != self._step_i:
            self._step_i = step_th
            self._canvas.itemconfigure(
                self._status_id, text=self._STEPS[self._step_i])

        # 도트 애니메이션
        self._dot_i = (self._dot_i + 1) % (len(self._dots) * 4)
        for i, d in enumerate(self._dots):
            active = (self._dot_i // 4) == i
            self._canvas.itemconfigure(
                d, fill="#f08a24" if active else "#3a3a3c")

        if self._prog < 1.0:
            self.after(25, self._animate)
        else:
            self._canvas.itemconfigure(
                self._status_id, text="준비 완료!")
            self.after(350, self._finish)

    # ── 버전 텍스트 설정 (외부에서 호출) ────────────────────────
    def set_version(self, ver: str) -> None:
        self._canvas.itemconfigure(self._ver_lbl, text=f"v{ver}")

    # ── 페이드아웃 후 소멸 ───────────────────────────────────────
    def _finish(self) -> None:
        self._done = True
        self._fade_out()

    def _fade_out(self) -> None:
        self._alpha = max(self._alpha - 0.10, 0.0)
        self.attributes("-alpha", self._alpha)
        if self._alpha > 0.0:
            self.after(20, self._fade_out)
        else:
            self.destroy()


if __name__ == "__main__":
    import traceback
    import tempfile
    import os as _os

    def _bpe_crash_log(exc: BaseException) -> None:
        """윈도우 모드 EXE에서 크래시 트레이스백을 파일에 기록한다."""
        try:
            log_path = _os.path.join(tempfile.gettempdir(), "BPE_crash.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("BPE 크래시 로그\n")
                f.write("=" * 60 + "\n")
                traceback.print_exc(file=f)
            # messagebox 를 쓸 수 없는 경우를 대비해 tkinter 로 표시 시도
            try:
                import tkinter.messagebox as _mb
                _mb.showerror(
                    "BPE 시작 오류",
                    f"BPE 실행 중 오류가 발생했습니다.\n\n"
                    f"오류 내용은 아래 파일을 열어 확인하세요:\n{log_path}\n\n"
                    f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
        except Exception:
            pass

    try:
        # ── 투명 루트 창으로 Tk 초기화 (스플래시 표시 전에 필요) ──
        root = tk.Tk()
        root.withdraw()

        # ── 스플래시 스크린 표시 ───────────────────────────────────
        splash = BPESplashScreen(root)
        splash.update()

        # ── 메인 앱 생성 (스플래시 띄운 채 백그라운드 초기화) ─────
        app = SetupProManager()
        try:
            splash.set_version(app.app_version)
        except Exception:
            pass

        # 스플래시가 자연스럽게 사라질 때까지 짧게 대기 후 메인 창 표시
        def _show_main():
            try:
                if splash.winfo_exists():
                    app.after(200, _show_main)
                    return
            except Exception:
                pass
            root.destroy()          # 투명 루트 정리
            app.deiconify()         # 메인 창 표시
            app.lift()
            app.focus_force()

        # 최소 스플래시 시간 보장 (스플래시 자체 애니메이션: ~1.5초)
        app.withdraw()              # 메인은 스플래시 끝날 때까지 숨김
        app.after(200, _show_main)
        app.mainloop()

    except BaseException as _e:
        _bpe_crash_log(_e)
        raise
