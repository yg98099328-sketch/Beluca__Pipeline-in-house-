"""
setup_pro - VFX Pipeline Preset & Shot Builder
UI: customtkinter 기반 프로 디자인
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import re
import os
from pathlib import Path
import subprocess
import sys

from setup_pro_common import (
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
    get_next_nuke_version,
    generate_nk_content,
    parse_shot_name,
)

# ── Design Tokens ─────────────────────────────────────────────────
BG          = "#1c1c1e"
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


class SetupProManager(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        super().__init__()
        self._init_fonts()

        self.title("setup_pro")
        self.geometry("1080x720")
        self.minsize(900, 600)
        self.configure(fg_color=BG)
        self.after(80, self._apply_win_chrome)

        # ── Data ──
        self.app_version = self._load_app_version()
        self.ocio_configs = load_ocio_configs_cache()
        self.presets      = load_presets()

        # ── State ──
        self._selected_preset: str  = ""
        self._preset_btns:     dict = {}
        self._last_nk_dir:     str  = ""

        # ── Variables ──
        self._init_vars()

        # ── UI ──
        self._build_ui()
        self._refresh_preset_list()

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
        self.F_BRAND = ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
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
        self.project_type_var         = tk.StringVar(value="OTT 시리즈")
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
            "(직접입력)": ("", ""),
            "FHD (1920x1080)": (1920, 1080), "HD (1280x720)": (1280, 720),
            "UHD (3840x2160)": (3840, 2160), "4K DCI (4096x2160)": (4096, 2160),
            "4K (3840x2070)": (3840, 2070),  "2K Scope (2048x858)": (2048, 858),
            "2K Cine (2048x1152)": (2048, 1152), "8K (7680x4320)": (7680, 4320),
        }

        # Shot Builder
        self.sb_server_root_var = tk.StringVar(value=_sb.get("server_root", r"W:\vfx\project_2026"))
        self.sb_project_code_var = tk.StringVar(value=_sb.get("project_code", ""))
        self.sb_preset_var       = tk.StringVar(value=_sb.get("preset", ""))
        self.sb_shot_name_var    = tk.StringVar(value="")

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
        ctk.CTkLabel(brand, text="setup_pro", font=self.F_BRAND, text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(brand, text="VFX Pipeline Tool", font=self.F_SMALL, text_color=TEXT_DIM).pack(anchor="w")

        # Divider
        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=(4, 12))

        # Nav
        nav = ctk.CTkFrame(sb, fg_color="transparent")
        nav.pack(fill="x", padx=8)

        self._nav_preset = self._nav_btn(nav, "  Preset Manager", lambda: self._show_page("preset"))
        self._nav_preset.pack(fill="x", pady=2)
        self._nav_shot = self._nav_btn(nav, "  Shot Builder", lambda: self._show_page("shot"))
        self._nav_shot.pack(fill="x", pady=2)

        # Footer
        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(side="bottom", fill="x", padx=12)
        footer = ctk.CTkFrame(sb, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=16, pady=12)
        ctk.CTkLabel(footer, text=f"v{self.app_version}", font=self.F_SMALL, text_color=TEXT_DIM).pack(anchor="w")

    def _nav_btn(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, anchor="w", height=42, corner_radius=8,
            fg_color="transparent", text_color=TEXT_DIM, hover_color=SELECT_BG,
            font=self.F_NAV, command=command,
        )

    def _show_page(self, page: str) -> None:
        for attr in ("_page_preset", "_page_shot"):
            p = getattr(self, attr, None)
            if p:
                p.pack_forget()

        # Nav highlight
        for btn, active in ((self._nav_preset, page == "preset"), (self._nav_shot, page == "shot")):
            btn.configure(
                fg_color=ACCENT if active else "transparent",
                text_color="#111111" if active else TEXT_DIM,
            )

        target = self._page_preset if page == "preset" else self._page_shot
        target.pack(fill="both", expand=True)

    # ── Pages ────────────────────────────────────────────────────────
    def _build_pages(self) -> None:
        self._page_preset = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_preset_page(self._page_preset)
        self._page_shot = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
        self._build_shot_page(self._page_shot)

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

        # Two-column layout
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self._build_form_col(body)
        self._build_list_col(body)

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
            scroll, values=["OTT 시리즈", "영화", "광고", "기타"],
            variable=self.project_type_var,
            fg_color=SELECT_BG, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOV, unselected_color=SELECT_BG,
            unselected_hover_color=HOVER, text_color=TEXT, font=self.F_SEG,
        )
        self.project_type_seg.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        r += 1

        label(r, "프로젝트 코드 *")
        entry(r, self.project_code_var, placeholder="예) SBS_030 (영문 대문자/숫자/_)")
        r += 1

        label(r, "FPS *")
        combo(r, self.fps_var, ["23.976", "24", "25", "29.97", "30", "50", "59.94", "60"])
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
        ctk.CTkEntry(wh, textvariable=self.plate_width_var, fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(wh, text="×", font=self.F_LABEL, text_color=TEXT_DIM).grid(row=0, column=1, padx=8)
        ctk.CTkEntry(wh, textvariable=self.plate_height_var, fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL).grid(row=0, column=2, sticky="ew")
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
        wcombo(wr, self.delivery_format_var, ["EXR 16bit", "EXR 32bit", "ProRes 422 HQ", "DNxHR HQX", "H264 MP4"]); wr += 1
        wlabel(wr, "Channels *")
        wcombo(wr, self.write_channels_var, self.write_channels_options); wr += 1
        wlabel(wr, "Datatype *")
        wcombo(wr, self.write_datatype_var, self.write_datatype_options); wr += 1
        wlabel(wr, "Compression *")
        wcombo(wr, self.write_compression_var, self.write_compression_options); wr += 1
        wlabel(wr, "Metadata *")
        wcombo(wr, self.write_metadata_var, self.write_metadata_options); wr += 1

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
            ff, text="변경", width=48, height=28,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_SMALL,
            command=self._browse_presets_dir,
        ).grid(row=1, column=1, padx=(4, 0))
        self.open_presets_btn = ctk.CTkButton(
            ff, text="열기", width=44, height=28, state="disabled",
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_SMALL,
            command=self._open_presets_folder,
        )
        self.open_presets_btn.grid(row=1, column=2, padx=(4, 0))

        # Divider + actions
        ctk.CTkFrame(panel, height=1, fg_color=BORDER).grid(row=5, column=0, sticky="ew", padx=12, pady=(12, 8))
        act = ctk.CTkFrame(panel, fg_color="transparent")
        act.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 16))
        ctk.CTkButton(
            act, text="프로그램 업데이트", height=38,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._update_self_and_restart,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            act, text="프리셋 저장", height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOV, text_color="#111111", font=self.F_BTN_EM,
            command=self._save_preset,
        ).pack(side="left")

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
        sep = lambda: (
            ctk.CTkFrame(card, height=1, fg_color=BORDER).grid(
                row=r, column=0, columnspan=2, sticky="ew", padx=16, pady=4))

        # STEP 1
        step_label(r, "STEP 1   서버 설정"); r += 1

        label(r, "서버 루트 경로 *")
        srv = ctk.CTkFrame(card, fg_color="transparent")
        srv.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        srv.columnconfigure(0, weight=1)
        ctk.CTkEntry(srv, textvariable=self.sb_server_root_var, fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT, font=self.F_LABEL).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            srv, text="찾아보기", width=80, height=32,
            fg_color=SELECT_BG, hover_color=HOVER, text_color=TEXT, font=self.F_BTN,
            command=self._sb_browse_server_root,
        ).grid(row=0, column=1, padx=(6, 0))
        r += 1

        label(r, "프로젝트 코드 *")
        entry(r, self.sb_project_code_var, placeholder="예) SBS_030")
        r += 1

        label(r, "프리셋 선택 *")
        self.sb_preset_combo = ctk.CTkComboBox(
            card, variable=self.sb_preset_var,
            values=sorted(self.presets.keys()) or [""],
            state="readonly",
            fg_color=INPUT_BG, border_color=BORDER, text_color=TEXT,
            button_color=BORDER, button_hover_color=SELECT_BG,
            dropdown_fg_color=PANEL_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SELECT_BG, font=self.F_LABEL,
            command=self._sb_on_preset_selected,
        )
        self.sb_preset_combo.grid(row=r, column=1, sticky="ew", padx=(0, 20), pady=(10, 2))
        r += 1
        ctk.CTkLabel(
            card, text="프리셋을 선택하면 프로젝트 코드가 자동 입력됩니다.",
            font=self.F_SMALL, text_color=TEXT_DIM, anchor="w",
        ).grid(row=r, column=1, sticky="w", padx=(0, 20), pady=(0, 4)); r += 1

        # Divider
        ctk.CTkFrame(card, height=1, fg_color=BORDER).grid(row=r, column=0, columnspan=2, sticky="ew", padx=16, pady=4); r += 1

        # STEP 2
        step_label(r, "STEP 2   샷 정보"); r += 1
        label(r, "샷 이름 *")
        shot_e = entry(r, self.sb_shot_name_var, placeholder="예) E107_S022_0080")
        shot_e.bind("<Return>", lambda e: self._sb_create_nk())
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
        self.sb_open_folder_btn.pack(side="left")

        # Divider
        ctk.CTkFrame(card, height=1, fg_color=BORDER).grid(row=r, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 4)); r += 1

        # STEP 3 — Log
        step_label(r, "STEP 3   실행 결과"); r += 1
        card.rowconfigure(r, weight=1)
        self.sb_log_text = ctk.CTkTextbox(
            card, fg_color=INPUT_BG, text_color=TEXT_DIM, font=self.F_MONO,
            state="disabled", corner_radius=8, border_color=BORDER, border_width=1,
        )
        self.sb_log_text.grid(row=r, column=0, columnspan=2, sticky="nsew", padx=16, pady=(0, 16))

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

    def _on_plate_choice_selected(self, choice: str = None) -> None:
        c = (choice or self.plate_format_choice_var.get() or "").strip()
        if not c or c == "(직접입력)":
            return
        wh = self.plate_preset_to_wh.get(c)
        if not wh:
            return
        w, h = wh
        if w and h:
            self.plate_width_var.set(str(w))
            self.plate_height_var.set(str(h))
            self.plate_format_name_var.set("")

    def _browse_ocio(self) -> None:
        selected = filedialog.askopenfilename(
            title="OCIO config 파일 선택",
            filetypes=[("OCIO config", "*.ocio"), ("All files", "*.*")],
        )
        if selected:
            self.ocio_path_var.set(selected)
            if selected not in self.ocio_configs:
                self.ocio_configs.append(selected)
                save_ocio_configs_cache(self.ocio_configs)
            self.ocio_combo.configure(values=self.ocio_configs)

    def _browse_presets_dir(self) -> None:
        selected = filedialog.askdirectory(title="프리셋 저장 폴더 선택")
        if not selected:
            return
        try:
            set_presets_dir(selected)
        except Exception as e:
            messagebox.showerror("setup_pro", f"프리셋 폴더 설정 실패: {e}")
            return
        self.presets_dir_var.set(selected)
        self.presets = load_presets()
        self._selected_preset = ""
        self._refresh_preset_list()

    def _open_presets_folder(self) -> None:
        d = (self.presets_dir_var.get() or "").strip()
        if not d:
            messagebox.showwarning("setup_pro", "프리셋 저장 폴더가 설정되지 않았습니다.")
            return
        try:
            os.startfile(d)
        except Exception as e:
            messagebox.showerror("setup_pro", f"폴더 열기 실패: {e}")

    def _collect_form(self) -> dict:
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
            messagebox.showerror("setup_pro", err)
            return
        self.presets[name] = data
        save_presets(self.presets)
        self._selected_preset = name
        self._refresh_preset_list()
        messagebox.showinfo(
            "setup_pro",
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
            messagebox.showwarning("setup_pro", "프리셋을 먼저 선택하세요.")
            return
        self._load_preset_to_form(name)

    def _delete_preset(self) -> None:
        name = self._get_selected_name()
        if not name:
            messagebox.showwarning("setup_pro", "프리셋을 먼저 선택하세요.")
            return
        if not messagebox.askyesno("setup_pro", f"'{name}' 프리셋을 삭제할까요?"):
            return
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
        self._load_preset_to_form(name)

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
        self.project_code_var.set(name)
        self.project_type_var.set(data.get("project_type", "OTT 시리즈"))
        self.delivery_format_var.set(data.get("delivery_format", "EXR 16bit"))
        self.fps_var.set(data.get("fps", "23.976"))
        self.plate_format_choice_var.set(data.get("plate_format_choice", "(직접입력)"))
        self.plate_format_name_var.set(data.get("plate_format_name", ""))
        self.plate_width_var.set(data.get("plate_width", "1920"))
        self.plate_height_var.set(data.get("plate_height", "1080"))
        self.ocio_path_var.set(data.get("ocio_path", ""))
        write_enabled = bool(data.get("write_enabled", True))
        self.write_open_var.set(write_enabled)
        if write_enabled:
            self.write_frame.grid()
        else:
            self.write_frame.grid_remove()
        self.write_channels_var.set(self._coerce(data.get("write_channels", ""), self.write_channels_options))
        self.write_datatype_var.set(self._coerce(data.get("write_datatype", ""), self.write_datatype_options))
        self.write_compression_var.set(self._coerce(data.get("write_compression", ""), self.write_compression_options))
        self.write_metadata_var.set(self._coerce(data.get("write_metadata", ""), self.write_metadata_options))
        tt = (data.get("write_transform_type", "") or "").strip().lower().replace("\\", "/").replace(" ", "")
        if tt in ("off", "input", "colorspace", "display/view"):
            self.write_transform_type_var.set(tt)
        self.write_out_colorspace_var.set(data.get("write_out_colorspace", data.get("write_colorspace", "")))
        self.write_output_display_var.set(data.get("write_output_display", "ACES"))
        self.write_output_view_var.set(data.get("write_output_view", "Rec.709"))
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
            messagebox.showerror("setup_pro", "build_exe.bat를 찾지 못했습니다.\nrelease 폴더 안에서 실행 중인지 확인하세요.")
            return
        release_dir = root_dir / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["cmd.exe", "/c", str(build_bat), "next"], cwd=str(root_dir), check=False)
        except Exception as e:
            messagebox.showerror("setup_pro", f"재빌드 실패: {e}")
            return
        next_exe = release_dir / "setup_pro_manager_next.exe"
        if not next_exe.exists():
            messagebox.showerror("setup_pro", "업데이트용 EXE를 생성하지 못했습니다.")
            return
        if not messagebox.askyesno("setup_pro", "업데이트가 완료되었습니다. 재실행할까요?"):
            return
        try:
            subprocess.Popen([str(next_exe)], cwd=str(release_dir), shell=False)
        except Exception as e:
            messagebox.showerror("setup_pro", f"재실행 실패: {e}")
            return
        os._exit(0)

    # ── Shot Builder Logic ───────────────────────────────────────────
    def _sb_on_preset_selected(self, value: str = None) -> None:
        name = (value or self.sb_preset_var.get()).strip()
        if name:
            self.sb_project_code_var.set(name)

    def _sb_browse_server_root(self) -> None:
        d = filedialog.askdirectory(title="서버 루트 경로 선택")
        if d:
            self.sb_server_root_var.set(d)

    def _sb_save_settings(self) -> None:
        save_shot_builder_settings({
            "server_root":  self.sb_server_root_var.get().strip(),
            "project_code": self.sb_project_code_var.get().strip().upper(),
            "preset":       self.sb_preset_var.get().strip(),
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
        server_root  = self.sb_server_root_var.get().strip()
        project_code = self.sb_project_code_var.get().strip().upper()
        shot_name    = self.sb_shot_name_var.get().strip().upper()
        preset_name  = self.sb_preset_var.get().strip()

        errors = []
        if not server_root:   errors.append("서버 루트 경로를 입력하세요.")
        if not project_code:  errors.append("프로젝트 코드를 입력하세요.")
        if not shot_name:     errors.append("샷 이름을 입력하세요.")
        if not preset_name:   errors.append("프리셋을 선택하세요.")
        if errors:
            messagebox.showerror("Shot Builder", "\n".join(errors))
            return

        if not re.match(r"^[A-Z0-9_]+$", project_code):
            messagebox.showerror("Shot Builder", "프로젝트 코드는 영문 대문자/숫자/_ 만 사용하세요.")
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
        self._sb_log(f"▶ NK 생성 시작: {shot_name}")
        self._sb_log(f"  프리셋: {preset_name}  |  FPS: {preset_data.get('fps')}  |  "
                     f"해상도: {preset_data.get('plate_width')}×{preset_data.get('plate_height')}")

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

        nuke_dir   = paths["nuke_dir"]
        nk_version = get_next_nuke_version(str(nuke_dir))
        self._sb_log(f"  NK 버전: {nk_version}")

        nk_ver_dir = nuke_dir / nk_version
        try:
            nk_ver_dir.mkdir(parents=True, exist_ok=True)
            self._sb_log(f"  폴더 생성: {nk_ver_dir}")
        except Exception as exc:
            messagebox.showerror("Shot Builder", f"폴더 생성 실패:\n{exc}")
            return

        nk_filename = f"{shot_name}_{nk_version}.nk"
        nk_filepath = nk_ver_dir / nk_filename

        if nk_filepath.exists():
            if not messagebox.askyesno("Shot Builder", f"파일이 이미 존재합니다:\n{nk_filename}\n덮어쓰시겠습니까?"):
                self._sb_log("취소되었습니다.")
                return

        try:
            content = generate_nk_content(preset_data, shot_name, paths, nk_version)
            nk_filepath.write_text(content, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Shot Builder", f"NK 파일 쓰기 실패:\n{exc}")
            return

        self._sb_log(f"\n✔ 완료!")
        self._sb_log(f"  파일:     {nk_filepath}")
        self._sb_log(f"  플레이트: {paths['plate_hi']}")
        self._sb_log(f"  편집본:   {paths['edit']}")
        self._sb_log(f"  렌더:     {paths['renders']}")

        self._last_nk_dir = str(nk_ver_dir)
        self.sb_open_folder_btn.configure(state="normal", text_color=TEXT)
        messagebox.showinfo("Shot Builder", f"NK 파일 생성 완료!\n\n{nk_filepath}")

    def _sb_open_folder(self) -> None:
        if self._last_nk_dir:
            try:
                os.startfile(self._last_nk_dir)
            except Exception as exc:
                messagebox.showerror("Shot Builder", f"폴더 열기 실패: {exc}")


if __name__ == "__main__":
    app = SetupProManager()
    app.mainloop()
