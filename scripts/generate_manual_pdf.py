"""
BELUCA Pipeline Engine (setup_pro) — User Guide PDF
Professional VFX Studio Grade Design
"""
import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        Paragraph, Spacer, Table,
        TableStyle, HRFlowable, KeepTogether, PageBreak,
        FrameBreak, BaseDocTemplate, Frame, PageTemplate,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
    from reportlab.platypus.flowables import Flowable
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.graphics.shapes import (
        Drawing, Rect, Circle, String, Group, Line, Polygon,
    )
    from reportlab.graphics import renderPDF
except ImportError:
    print("pip install reportlab  then retry.")
    sys.exit(1)

# ── Output ────────────────────────────────────────────────────
OUT_DIR = Path(__file__).resolve().parent.parent / "docs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "BPE_manual.pdf"

PAGE_W, PAGE_H = A4
ML = MR = 2.0 * cm
MT = 1.4 * cm
MB = 1.6 * cm
CONTENT_W = PAGE_W - ML - MR

# ── Color System ──────────────────────────────────────────────
OR   = HexColor("#2D6A4F")   # dark green accent
OR2  = HexColor("#1B4332")   # dark green deep
OR_L = HexColor("#EBF5EF")   # green tint bg
BK   = HexColor("#0F0F11")   # near black
DK   = HexColor("#1C1C1E")   # dark
DK2  = HexColor("#2D2D30")   # dark mid
GY1  = HexColor("#F5F5F7")   # light gray
GY2  = HexColor("#E8E8ED")   # mid gray
GY3  = HexColor("#AEAEB2")   # dim gray
GY4  = HexColor("#636366")   # darker gray
WH   = white
GRN  = HexColor("#40916C")   # green (success)
GRN_L= HexColor("#D8F0E6")
BLU  = HexColor("#0A84FF")   # blue
BLU_L= HexColor("#E5F1FF")

# ── Fonts ─────────────────────────────────────────────────────
FN = "Helvetica"
FB = "Helvetica-Bold"
FM = "Courier"
FI = "Helvetica-Oblique"

for (alias, path) in [
    ("KR",  "C:/Windows/Fonts/malgun.ttf"),
    ("KRB", "C:/Windows/Fonts/malgunbd.ttf"),
]:
    try:
        pdfmetrics.registerFont(TTFont(alias, path))
        if alias == "KR":  FN = "KR"
        if alias == "KRB": FB = "KRB"
    except Exception:
        pass

# ── Style Factory ─────────────────────────────────────────────
def S(name="_", fontName=None, bold=False, size=10.5, leading=None,
      color=None, bg=None, align=TA_LEFT, spaceBefore=0, spaceAfter=4,
      leftIndent=0, rightIndent=0, borderPad=0) -> ParagraphStyle:
    fn = fontName or (FB if bold else FN)
    return ParagraphStyle(
        name,
        fontName=fn,
        fontSize=size,
        leading=leading or round(size * 1.55),
        textColor=color or DK2,
        backColor=bg,
        alignment=align,
        spaceBefore=spaceBefore,
        spaceAfter=spaceAfter,
        leftIndent=leftIndent,
        rightIndent=rightIndent,
        borderPad=borderPad,
    )

# Pre-built styles
s_h1     = S("h1",  bold=True, size=26, leading=36, color=BK, spaceAfter=6)
s_h2     = S("h2",  bold=True, size=15, leading=22, color=BK, spaceBefore=12, spaceAfter=5)
s_h3     = S("h3",  bold=True, size=11.5, leading=18, color=OR2, spaceBefore=8, spaceAfter=3)
s_body   = S("bd",  size=10.5, leading=18, color=DK2, spaceAfter=5)
s_body_j = S("bj",  size=10.5, leading=18, color=DK2, spaceAfter=5, align=TA_JUSTIFY)
s_sm     = S("sm",  size=9.5, leading=15, color=GY4)
s_label  = S("lb",  bold=True, size=9, leading=13, color=GY4)
s_cap    = S("cp",  size=8.5, leading=13, color=GY3, align=TA_CENTER, spaceAfter=8)
s_tip    = S("tp",  size=10, leading=16, color=HexColor("#1B5E20"), bg=GRN_L, borderPad=8, spaceAfter=6)
s_note   = S("nt",  size=10, leading=16, color=HexColor("#6D4C00"), bg=HexColor("#FFF8E1"), borderPad=8, spaceAfter=6)
s_code   = S("cd",  fontName=FM, size=9, leading=14, color=HexColor("#1A1A1C"), bg=GY1, borderPad=8, spaceAfter=6)
s_th     = S("th",  bold=True, size=9.5, leading=14, color=WH, align=TA_LEFT)
s_td     = S("td",  size=10, leading=14, color=DK2)
s_td_dim = S("tdd", size=9.5, leading=13, color=GY4)
s_toc_n  = S("tn",  bold=True, size=10, color=OR, spaceAfter=0)
s_toc_t  = S("tt",  size=11, color=DK2, spaceAfter=0)
s_toc_p  = S("tp2", size=10, color=GY3, align=TA_RIGHT, spaceAfter=0)
s_fq     = S("fq",  bold=True, size=11, leading=18, color=BK, spaceAfter=3)
s_fa     = S("fa",  size=10.5, leading=17, color=DK2, leftIndent=10, spaceAfter=14)
s_badge  = S("bg",  bold=True, size=9, leading=12, color=WH, align=TA_CENTER)

def sp(h=8):  return Spacer(1, h)

def div(color=GY2, t=0.5, sB=6, sA=8):
    return HRFlowable(width="100%", thickness=t, color=color,
                      spaceAfter=sA, spaceBefore=sB)

def tip(t):  return Paragraph(f"<b>TIP</b>\u2003{t}", s_tip)
def note(t): return Paragraph(f"<b>NOTE</b>\u2003{t}", s_note)
def code(t): return Paragraph(t, s_code)
def P(t, st=None): return Paragraph(t, st or s_body)


# ══════════════════════════════════════════════════════════════
# CUSTOM FLOWABLES — UI MOCKUPS & VISUAL ELEMENTS
# ══════════════════════════════════════════════════════════════

class UIWindow(Flowable):
    """Draws a simplified BPE application window mockup."""

    def __init__(self, width=None, height=180, highlight="preset"):
        super().__init__()
        self.w = width or CONTENT_W
        self.h = height
        self.highlight = highlight

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv
        w, h = self.w, self.h

        # ── Window frame ──────────────────────────────────────
        c.setFillColor(DK)
        c.roundRect(0, 0, w, h, 6, fill=1, stroke=0)

        # ── Title bar ─────────────────────────────────────────
        c.setFillColor(BK)
        c.roundRect(0, h - 28, w, 28, 6, fill=1, stroke=0)
        c.rect(0, h - 28, w, 14, fill=1, stroke=0)

        # Window buttons
        for i, col in enumerate([HexColor("#FF5F56"), HexColor("#FFBD2E"), HexColor("#27C93F")]):
            cx = 14 + i * 18
            c.setFillColor(col)
            c.circle(cx, h - 14, 5, fill=1, stroke=0)

        # Title text
        c.setFillColor(HexColor("#AAAAAA"))
        c.setFont(FB, 8.5)
        c.drawCentredString(w / 2, h - 18, "BELUCA Pipeline Engine")

        # ── Sidebar ───────────────────────────────────────────
        sb_w = w * 0.22
        c.setFillColor(HexColor("#111114"))
        c.rect(0, 0, sb_w, h - 28, fill=1, stroke=0)

        # Brand logo in sidebar
        c.setFillColor(OR)
        c.roundRect(10, h - 62, 20, 20, 3, fill=1, stroke=0)
        c.setFillColor(WH)
        c.setFont(FB, 10)
        c.drawCentredString(20, h - 55, "B")
        c.setFillColor(OR)
        c.setFont(FB, 10)
        c.drawString(36, h - 55, "BELUCA")
        c.setFillColor(HexColor("#666668"))
        c.setFont(FN, 7.5)
        c.drawString(36, h - 65, "Pipeline Engine")

        # Nav items
        nav_items = [
            ("Preset Manager", self.highlight == "preset"),
            ("Shot Builder",   self.highlight == "shot"),
        ]
        for i, (label, active) in enumerate(nav_items):
            ny = h - 95 - i * 34
            if active:
                c.setFillColor(OR)
                c.roundRect(6, ny - 6, sb_w - 12, 26, 4, fill=1, stroke=0)
                c.setFillColor(BK)
            else:
                c.setFillColor(HexColor("#555558"))
            c.setFont(FN, 8.5)
            c.drawString(16, ny + 4, label)

        # Version at bottom of sidebar
        c.setFillColor(HexColor("#3A3A3C"))
        c.setFont(FN, 7.5)
        c.drawString(12, 10, "v0.1.37")

        # ── Content area ──────────────────────────────────────
        cx0 = sb_w + 2
        cw = w - cx0 - 2

        if self.highlight == "preset":
            self._draw_preset_content(c, cx0, cw, h)
        elif self.highlight == "shot":
            self._draw_shot_content(c, cx0, cw, h)
        elif self.highlight == "import":
            self._draw_import_content(c, cx0, cw, h)

    def _form_row(self, c, x, y, w, label, value, accent=False):
        """Draws a label + input row."""
        c.setFillColor(HexColor("#555558"))
        c.setFont(FN, 7.5)
        c.drawString(x, y + 3, label)
        iw = w - 80
        c.setFillColor(HexColor("#252528"))
        c.roundRect(x + 75, y - 2, iw, 16, 2, fill=1, stroke=0)
        if accent:
            c.setFillColor(OR)
        else:
            c.setFillColor(HexColor("#AAAAAA"))
        c.setFont(FN, 7.5)
        c.drawString(x + 79, y + 2, str(value))

    def _draw_preset_content(self, c, x0, cw, h):
        # Page header
        c.setFillColor(HexColor("#252528"))
        c.rect(x0, h - 60, cw, 32, fill=1, stroke=0)
        c.setFillColor(OR)
        c.rect(x0, h - 60, 3, 32, fill=1, stroke=0)
        c.setFillColor(WH)
        c.setFont(FB, 10)
        c.drawString(x0 + 12, h - 50, "Preset Manager")
        c.setFillColor(HexColor("#666668"))
        c.setFont(FN, 7.5)
        c.drawString(x0 + 12, h - 62, "프로젝트 세팅을 저장하고 관리합니다")

        # Two-column layout
        fc_w = cw * 0.58  # form col
        lc_w = cw * 0.38  # list col
        lc_x = x0 + fc_w + 8

        # Form fields
        rows = [
            ("프로젝트 타입", "드라마 (OTT)"),
            ("프로젝트 코드", "SBS_030", ),
            ("FPS",          "23.976"),
            ("해상도",       "3840 × 2076"),
            ("OCIO Config",  "W:/config/aces.ocio"),
        ]
        for i, row in enumerate(rows):
            label = row[0]; val = row[1]
            accent = (i == 1)
            self._form_row(c, x0 + 8, h - 84 - i * 20, fc_w - 16, label, val, accent)

        # Save button
        c.setFillColor(OR)
        c.roundRect(x0 + 8, h - 195, fc_w - 16, 18, 3, fill=1, stroke=0)
        c.setFillColor(BK)
        c.setFont(FB, 8)
        c.drawCentredString(x0 + 8 + (fc_w - 16) / 2, h - 188, "프리셋 저장")

        # Preset list
        c.setFillColor(HexColor("#1C1C1E"))
        c.roundRect(lc_x, h - 60 - 148, lc_w, 148, 3, fill=1, stroke=0)
        c.setFillColor(HexColor("#555558"))
        c.setFont(FB, 7.5)
        c.drawString(lc_x + 8, h - 76, "저장된 프리셋")
        presets = ["SBS_030", "KBS_A12", "MBC_S01", "CJ_ENM"]
        for i, ps in enumerate(presets):
            py = h - 94 - i * 22
            if i == 0:
                c.setFillColor(OR)
                c.roundRect(lc_x + 4, py - 5, lc_w - 8, 20, 3, fill=1, stroke=0)
                c.setFillColor(BK)
            else:
                c.setFillColor(HexColor("#333336"))
                c.roundRect(lc_x + 4, py - 5, lc_w - 8, 20, 3, fill=1, stroke=0)
                c.setFillColor(HexColor("#CCCCCC"))
            c.setFont(FN, 8)
            c.drawString(lc_x + 12, py + 1, ps)

    def _draw_shot_content(self, c, x0, cw, h):
        c.setFillColor(HexColor("#252528"))
        c.rect(x0, h - 60, cw, 32, fill=1, stroke=0)
        c.setFillColor(OR)
        c.rect(x0, h - 60, 3, 32, fill=1, stroke=0)
        c.setFillColor(WH)
        c.setFont(FB, 10)
        c.drawString(x0 + 12, h - 50, "Shot Builder")
        c.setFillColor(HexColor("#666668"))
        c.setFont(FN, 7.5)
        c.drawString(x0 + 12, h - 62, "NK 파일을 자동으로 생성합니다")

        rows = [
            ("서버 루트",    r"W:\vfx\project_2026"),
            ("프로젝트 코드","SBS_030"),
            ("샷 이름",      "E107_S022_0080"),
            ("프리셋",       "SBS_030"),
        ]
        for i, (label, val) in enumerate(rows):
            self._form_row(c, x0 + 8, h - 84 - i * 22, cw - 16, label, val, i == 2)

        c.setFillColor(OR)
        c.roundRect(x0 + 8, h - 190, cw - 16, 20, 3, fill=1, stroke=0)
        c.setFillColor(BK)
        c.setFont(FB, 9)
        c.drawCentredString(x0 + 8 + (cw - 16) / 2, h - 182, "NK 생성")

        # Log area
        c.setFillColor(HexColor("#111114"))
        c.roundRect(x0 + 8, h - 214, cw - 16, 16, 2, fill=1, stroke=0)
        c.setFillColor(GRN)
        c.setFont(FM, 7)
        c.drawString(x0 + 12, h - 208, "✔  E107_S022_0080_comp_v001.nk 생성 완료")

    def _draw_import_content(self, c, x0, cw, h):
        # Import dialog mockup
        dw = cw * 0.85
        dh = h - 45
        dx = x0 + (cw - dw) / 2
        dy = (h - 28 - dh) / 2

        c.setFillColor(HexColor("#1C1C1E"))
        c.roundRect(dx, dy, dw, dh, 6, fill=1, stroke=0)
        c.setFillColor(HexColor("#252528"))
        c.roundRect(dx, dy + dh - 38, dw, 38, 6, fill=1, stroke=0)
        c.rect(dx, dy + dh - 24, dw, 24, fill=1, stroke=0)

        c.setFillColor(WH)
        c.setFont(FB, 10)
        c.drawString(dx + 12, dy + dh - 24, "NK 분석 결과 — 프리셋 생성")

        rows = [
            ("FPS", "23.976"),
            ("해상도", "3840 × 2076"),
            ("OCIO Config", "aces_1.0.3.ocio"),
            ("Read Transform", "ACES - ACES2065-1"),
            ("납품 포맷", "EXR 16bit"),
        ]
        c.setFillColor(HexColor("#252528"))
        c.roundRect(dx + 8, dy + dh - 130, dw - 16, 80, 3, fill=1, stroke=0)
        for i, (label, val) in enumerate(rows[:4]):
            ry = dy + dh - 62 - i * 16
            c.setFillColor(GY4)
            c.setFont(FN, 7.5)
            c.drawString(dx + 16, ry, label)
            c.setFillColor(OR)
            c.setFont(FB, 7.5)
            c.drawString(dx + 16 + 100, ry, val)

        # name input
        c.setFillColor(HexColor("#252528"))
        c.roundRect(dx + 8, dy + 40, dw - 16, 18, 2, fill=1, stroke=0)
        c.setFillColor(OR)
        c.setLineWidth(1)
        c.roundRect(dx + 8, dy + 40, dw - 16, 18, 2, fill=0, stroke=1)
        c.setFillColor(HexColor("#AAAAAA"))
        c.setFont(FN, 7.5)
        c.drawString(dx + 14, dy + 46, "프리셋 이름을 입력하세요...")

        # buttons
        c.setFillColor(HexColor("#3A3A3C"))
        c.roundRect(dx + 8, dy + 10, 60, 20, 3, fill=1, stroke=0)
        c.setFillColor(HexColor("#CCCCCC"))
        c.setFont(FN, 8)
        c.drawCentredString(dx + 38, dy + 17, "취소")
        c.setFillColor(OR)
        c.roundRect(dx + dw - 80, dy + 10, 68, 20, 3, fill=1, stroke=0)
        c.setFillColor(BK)
        c.setFont(FB, 8)
        c.drawCentredString(dx + dw - 46, dy + 17, "프리셋 생성")


class FeatureCard(Flowable):
    """Orange-accented feature card with icon, title, description."""

    def __init__(self, icon_char, title, desc, col_width=None):
        super().__init__()
        self.icon = icon_char
        self.title = title
        self.desc = desc
        self.w = col_width or CONTENT_W
        self.h = 90

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv
        w, h = self.w, self.h

        # Card bg
        c.setFillColor(GY1)
        c.roundRect(0, 0, w, h, 5, fill=1, stroke=0)

        # Left accent bar
        c.setFillColor(OR)
        c.roundRect(0, 0, 4, h, 2, fill=1, stroke=0)

        # Icon circle
        c.setFillColor(OR)
        c.circle(26, h - 26, 16, fill=1, stroke=0)
        c.setFillColor(WH)
        c.setFont(FB, 14)
        c.drawCentredString(26, h - 31, self.icon)

        # Title
        c.setFillColor(BK)
        c.setFont(FB, 11.5)
        c.drawString(52, h - 22, self.title)

        # Description - wrapped text manually
        c.setFillColor(DK2)
        c.setFont(FN, 9.5)
        lines = self._wrap_text(self.desc, w - 58, FN, 9.5)
        for i, line in enumerate(lines[:3]):
            c.drawString(52, h - 38 - i * 14, line)

    def _wrap_text(self, text, max_width, font, size):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if stringWidth(test, font, size) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines


class WorkflowArrow(Flowable):
    """Visual workflow steps connected with arrows."""

    def __init__(self, steps, width=None, height=70):
        super().__init__()
        self.steps = steps
        self.w = width or CONTENT_W
        self.h = height

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv
        n = len(self.steps)
        sw = self.w / n
        cy = self.h / 2

        for i, (num, label) in enumerate(self.steps):
            cx = sw * i + sw / 2

            # Circle
            c.setFillColor(OR)
            c.circle(cx, cy + 10, 16, fill=1, stroke=0)
            c.setFillColor(WH)
            c.setFont(FB, 12)
            c.drawCentredString(cx, cy + 5, str(num))

            # Label
            c.setFillColor(DK2)
            c.setFont(FN, 8.5)
            from reportlab.pdfbase.pdfmetrics import stringWidth
            tw = stringWidth(label, FN, 8.5)
            c.drawString(cx - tw / 2, cy - 12, label)

            # Arrow to next
            if i < n - 1:
                ax = cx + 16 + 4
                ax2 = cx + sw - 16 - 4
                mid = (ax + ax2) / 2
                c.setStrokeColor(OR)
                c.setLineWidth(1.5)
                c.line(ax, cy + 10, ax2, cy + 10)
                # arrowhead
                c.setFillColor(OR)
                p = c.beginPath()
                p.moveTo(ax2, cy + 10)
                p.lineTo(ax2 - 6, cy + 14)
                p.lineTo(ax2 - 6, cy + 6)
                p.close()
                c.drawPath(p, fill=1, stroke=0)


class PathDiagram(Flowable):
    """Draws the server folder structure diagram."""

    def __init__(self, width=None, height=160):
        super().__init__()
        self.w = width or CONTENT_W
        self.h = height

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv

        # Background
        c.setFillColor(GY1)
        c.roundRect(0, 0, self.w, self.h, 5, fill=1, stroke=0)

        lines = [
            (0,  False, "서버루트 / SBS_030 / 04_sq / E107 / E107_S022_0080 /"),
            (1,  False, "├─  comp / devl / nuke / v001 /"),
            (2,  True,  "│       ✦  E107_S022_0080_comp_v001.nk   ← 자동 생성"),
            (1,  False, "├─  plate / org / v001 / hi /"),
            (2,  True,  "│       ✦  E107_S022_0080_org_v001.####.exr   ← Read 노드 연결"),
            (1,  False, "└─  edit /"),
            (2,  True,  "        ✦  E107_S022_0080_edit.####.exr   ← Edit Read 연결"),
        ]

        for i, (indent, highlight, text) in enumerate(lines):
            y = self.h - 22 - i * 20
            x = 14 + indent * 16

            # 한글·기호 포함 시 Courier는 깨지므로 Malgun(KR) 계열 FN 사용
            if highlight:
                c.setFillColor(OR_L)
                c.roundRect(x - 4, y - 4, self.w - x - 10, 16, 2, fill=1, stroke=0)
                c.setFillColor(OR2)
            else:
                c.setFillColor(DK2)
            c.setFont(FN, 8.5)
            c.drawString(x, y, text)


class SplashMockup(Flowable):
    """Simplified splash screen mockup."""

    def __init__(self, width=None, height=140):
        super().__init__()
        self.w = width or CONTENT_W * 0.55
        self.h = height

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv
        w, h = self.w, self.h

        # Dark rounded window
        c.setFillColor(HexColor("#1C1C1E"))
        c.roundRect(0, 0, w, h, 8, fill=1, stroke=0)

        # Left orange bar
        c.setFillColor(OR)
        c.roundRect(0, 0, 5, h, 2, fill=1, stroke=0)

        # B logo circle
        cx, cy = w / 2, h - 40
        c.setFillColor(OR)
        c.circle(cx, cy, 22, fill=1, stroke=0)
        c.setFillColor(WH)
        c.setFont(FB, 20)
        c.drawCentredString(cx, cy - 7, "B")

        # Brand name
        c.setFillColor(WH)
        c.setFont(FB, 13)
        c.drawCentredString(cx, h - 75, "BELUCA")
        c.setFillColor(HexColor("#888888"))
        c.setFont(FN, 9)
        c.drawCentredString(cx, h - 88, "Pipeline Engine")

        # Progress bar bg
        bx = 24; bw = w - 48
        by = 24
        c.setFillColor(HexColor("#333336"))
        c.roundRect(bx, by + 8, bw, 6, 3, fill=1, stroke=0)
        # fill 70%
        c.setFillColor(OR)
        c.roundRect(bx, by + 8, bw * 0.7, 6, 3, fill=1, stroke=0)

        # Status text
        c.setFillColor(HexColor("#888888"))
        c.setFont(FN, 8)
        c.drawCentredString(cx, by, "UI 컴포넌트 초기화 중...")

        # Dots
        for i in range(4):
            dx = cx - 18 + i * 12
            col = OR if i == 2 else HexColor("#444446")
            c.setFillColor(col)
            c.circle(dx, by + 22, 3, fill=1, stroke=0)


class TOCMarker(Flowable):
    """목차(TableOfContents)용 보이지 않는 앵커 — 세로 배치·레이아웃에 영향 없음."""

    def __init__(self, level: int, title: str):
        super().__init__()
        self.level = level
        self.title = title

    def wrap(self, aw, ah):
        return (0, 0)

    def draw(self):
        pass


class ManualDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, TOCMarker):
            self.notify("TOCEntry", (flowable.level, flowable.title, self.page))


# ══════════════════════════════════════════════════════════════
# PAGE BACKGROUND
# ══════════════════════════════════════════════════════════════

def _on_page(canvas, doc):
    canvas.saveState()
    w, h = A4

    if doc.page == 1:
        # Cover: full dark
        canvas.setFillColor(BK)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        # Orange bottom strip
        canvas.setFillColor(OR)
        canvas.rect(0, 0, w, 5, fill=1, stroke=0)
        # Orange left bar
        canvas.setFillColor(OR)
        canvas.rect(0, 0, 8, h, fill=1, stroke=0)
        # Subtle grid lines decoration
        canvas.setStrokeColor(HexColor("#1E1E20"))
        canvas.setLineWidth(0.5)
        for gx in range(0, int(w), 30):
            canvas.line(gx, 0, gx, h)
        for gy in range(0, int(h), 30):
            canvas.line(0, gy, w, gy)
        canvas.restoreState()
        return

    # Normal pages — clean white
    canvas.setFillColor(WH)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Top header bar
    canvas.setFillColor(BK)
    canvas.rect(0, h - 1.1*cm, w, 1.1*cm, fill=1, stroke=0)
    canvas.setFillColor(OR)
    canvas.rect(0, h - 1.1*cm - 2.5, w, 2.5, fill=1, stroke=0)

    # Header text
    canvas.setFillColor(WH)
    canvas.setFont(FB, 8.5)
    canvas.drawString(ML, h - 0.73*cm, "BELUCA Pipeline Engine")
    canvas.setFillColor(GY3)
    canvas.setFont(FN, 8.5)
    canvas.drawRightString(w - MR, h - 0.73*cm, "User Guide")

    # Footer
    canvas.setFillColor(GY1)
    canvas.rect(0, 0, w, 1.05*cm, fill=1, stroke=0)
    canvas.setFillColor(OR)
    canvas.rect(0, 1.05*cm, w, 1.5, fill=1, stroke=0)

    if doc.page > 2:
        canvas.setFillColor(GY3)
        canvas.setFont(FN, 8)
        canvas.drawCentredString(w/2, 0.35*cm, f"{doc.page}")

    canvas.restoreState()


# ══════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════
def cover() -> list:
    S_COV = lambda **kw: ParagraphStyle("_cov", **kw)
    items = []
    items.append(sp(60))

    # Logo row
    logo_tbl = Table(
        [[
            Paragraph("<b>B</b>", ParagraphStyle("bl",
                fontName=FB, fontSize=32, leading=38, textColor=WH, alignment=TA_CENTER)),
            Paragraph("BELUCA", ParagraphStyle("bn",
                fontName=FB, fontSize=46, leading=56, textColor=OR, alignment=TA_LEFT)),
        ]],
        colWidths=[1.8*cm, 10*cm],
    )
    logo_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), OR),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (0, 0), 6),
        ("LEFTPADDING",   (1, 0), (1, 0), 14),
    ]))
    items.append(logo_tbl)
    items.append(sp(8))

    items.append(Paragraph("Pipeline Engine", ParagraphStyle("pe",
        fontName=FN, fontSize=16, leading=22, textColor=HexColor("#888888"),
        leftIndent=1.8*cm + 14)))
    items.append(sp(36))

    items.append(HRFlowable(width="100%", thickness=1, color=HexColor("#2E2E30"),
                            spaceBefore=0, spaceAfter=24))

    items.append(Paragraph("사용자 가이드", ParagraphStyle("cdoc",
        fontName=FB, fontSize=22, leading=30, textColor=WH)))
    items.append(sp(12))
    items.append(Paragraph(
        "Nuke 기반 VFX 파이프라인 도구 <b>setup_pro</b> (BELUCA Pipeline Engine).<br/>"
        "프리셋 관리·Shot Builder·NK 템플릿까지<br/>"
        "반복 세팅을 줄이고 컴포지팅 작업에 집중하세요.",
        ParagraphStyle("cdesc", fontName=FN, fontSize=13, leading=22,
                       textColor=HexColor("#AAAAAA"))))
    items.append(sp(48))

    # Meta info grid
    meta = Table(
        [
            [Paragraph("제품", ParagraphStyle("ml", fontName=FB, fontSize=9, textColor=OR)),
             Paragraph("setup_pro · BELUCA Pipeline Engine (BPE)", ParagraphStyle("mv", fontName=FN, fontSize=10, textColor=HexColor("#CCCCCC")))],
            [Paragraph("대상", ParagraphStyle("ml", fontName=FB, fontSize=9, textColor=OR)),
             Paragraph("VFX 컴포지터 · 파이프라인 담당자", ParagraphStyle("mv", fontName=FN, fontSize=10, textColor=HexColor("#CCCCCC")))],
            [Paragraph("플랫폼", ParagraphStyle("ml", fontName=FB, fontSize=9, textColor=OR)),
             Paragraph("Windows 10 / 11  ·  Nuke 13 – 15", ParagraphStyle("mv", fontName=FN, fontSize=10, textColor=HexColor("#CCCCCC")))],
        ],
        colWidths=[2.0*cm, 10*cm],
    )
    meta.setStyle(TableStyle([
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBEFORE",  (0, 0), (0, -1), 2, OR),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
    ]))
    items.append(meta)
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SECTION HEADER helper (목차 앵커 포함)
# ══════════════════════════════════════════════════════════════
def sec_hdr(num, title, toc_entry=None) -> list:
    entry = toc_entry if toc_entry else f"{num}  {title}"
    hdr = Table(
        [[
            Paragraph(num, ParagraphStyle("sn", fontName=FB, fontSize=16,
                                          leading=20, textColor=WH, alignment=TA_CENTER,
                                          wordWrap=None)),
            Paragraph(title, ParagraphStyle("st", fontName=FB, fontSize=16,
                                            leading=24, textColor=WH)),
        ]],
        colWidths=[1.6*cm, CONTENT_W - 1.8*cm],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BK),
        ("BACKGROUND",    (0, 0), (0, 0),   OR2),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (0, 0),    4),
        ("RIGHTPADDING",  (0, 0), (0, 0),    4),
        ("LEFTPADDING",   (1, 0), (1, 0),   16),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",     (0, 0), (-1, -1),  3, OR),
    ]))
    return [TOCMarker(0, entry), hdr, sp(14)]


def info_tbl(headers, rows, col_w=None) -> Table:
    uw = CONTENT_W
    if col_w is None:
        w = uw / len(headers)
        col_w = [w] * len(headers)
    data = [[Paragraph(h, s_th) for h in headers]]
    for i, row in enumerate(rows):
        data.append([Paragraph(str(c), s_td) for c in row])
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), BK),
        ("TOPPADDING",     (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING",  (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WH, GY1]),
        ("TOPPADDING",     (0, 1), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 1), (-1, -1), 7),
        ("LEFTPADDING",    (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 10),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",           (0, 0), (-1, -1), 0.4, GY2),
        ("LINEBELOW",      (0, 0), (-1, 0), 2, OR),
    ]))
    return t


def steps(*items_list) -> list:
    out = []
    for num, text in items_list:
        row = Table(
            [[
                Paragraph(str(num), ParagraphStyle("stn",
                    fontName=FB, fontSize=11, leading=14, textColor=WH, alignment=TA_CENTER)),
                Paragraph(text, s_body),
            ]],
            colWidths=[0.72*cm, CONTENT_W - 0.9*cm],
        )
        row.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (0, 0), OR),
            ("BACKGROUND",     (1, 0), (1, 0), GY1),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 6),
            ("LEFTPADDING",    (0, 0), (0, 0), 4),
            ("LEFTPADDING",    (1, 0), (1, 0), 12),
        ]))
        out.append(row)
        out.append(sp(4))
    return out


# ══════════════════════════════════════════════════════════════
# SEC 1 — What is BPE
# ══════════════════════════════════════════════════════════════
def sec1() -> list:
    items = sec_hdr("01", "BELUCA Pipeline Engine · setup_pro 란?")

    items.append(P(
        "<b>BELUCA Pipeline Engine(BPE)</b>는 데스크톱 앱과 Nuke 연동 스크립트를 묶은 "
        "제품 이름이며, 메뉴·문서에서는 <b>setup_pro</b>로 표기되는 경우가 많습니다. "
        "Nuke 기반 VFX 스튜디오를 위한 <b>프로젝트 세팅·샷 NK 자동화 도구</b>로, "
        "Root(FPS·해상도·OCIO)·Write·샷 폴더 규칙을 한 번 정해 두면 "
        "팀 전체가 같은 기준으로 작업할 수 있습니다.", s_body_j))
    items.append(sp(8))

    # Feature cards 2x2
    features = [
        ("⚙", "Preset Manager",
         "Save plate size FPS OCIO Write as named presets. Point the preset folder to a team share so everyone loads the same settings."),
        ("⚡", "Shot Builder",
         "Enter shot name and preset to emit a versioned NK under comp/devl/nuke with Reads and Writes wired to your server layout."),
        ("📁", "NK 가져오기",
         "Analyze an existing NK to extract FPS format OCIO and Write options then save as a new preset without retyping."),
        ("🎬", "Nuke setup_pro 메뉴",
         "From the Nuke menubar open the panel apply a preset in one click. Optional BPE Tools submenu for hooks and QC helpers."),
    ]
    for f in features:
        items.append(FeatureCard(f[0], f[1], f[2], col_width=CONTENT_W))
        items.append(sp(6))

    items.append(sp(6))
    items.append(P("<b>데이터가 저장되는 위치 (요약)</b>", s_h2))
    items.append(info_tbl(
        ["항목", "기본 위치", "설명"],
        [
            ["프리셋 JSON", "~/.setup_pro/presets.json 또는 지정 폴더", "Preset Manager에서 [변경]으로 경로 지정 가능"],
            ["Shot Builder 설정", "~/.setup_pro/shot_builder.json", "서버 루트·마지막 입력 값 등"],
            ["Nuke 연동 파일", "~/.nuke/ 및 배포 폴더의 .py", "install_to_nuke.bat이 복사·menu.py에 hook 추가"],
        ],
        col_w=[3.2 * cm, 6.2 * cm, CONTENT_W - 9.6 * cm],
    ))
    items.append(sp(8))
    items.append(P("<b>BPE가 해결하는 문제</b>", s_h2))
    items.append(info_tbl(
        ["기존 작업 방식", "BPE 사용 시"],
        [
            ["매 샷마다 Root 해상도·FPS 수동 입력",        "프리셋 하나로 즉시 적용"],
            ["Write 노드 설정을 노드마다 반복",             "프리셋의 Write 설정이 자동으로 구성"],
            ["NK 파일을 폴더 규칙에 맞게 수동 저장",       "Shot Builder가 규칙 경로에 자동 생성"],
            ["새 멤버 온보딩 시 세팅 설명 반복",           "공유 프리셋 폴더만 맞추면 동일 환경"],
        ],
        col_w=[CONTENT_W * 0.48, CONTENT_W * 0.52],
    ))
    items.append(PageBreak())
    items.append(P("<b>권장 워크플로 요약</b>", s_h2))
    items.append(P(
        "1) 파이프라인 담당자가 BPE 앱으로 <b>프리셋</b>을 만들고 저장 폴더를 "
        "팀 서버(또는 공유 볼륨)로 둡니다. "
        "2) 각 아티스트 PC에서 <b>install_to_nuke.bat</b>을 한 번 실행해 Nuke에 연동합니다. "
        "3) Nuke에서는 <b>setup_pro</b> 메뉴에서 패널을 열고 동일 프리셋 폴더를 가리킨 뒤 적용합니다. "
        "4) 샷 작업 시작 시 Shot Builder로 <b>v001 NK</b>를 만들고 Nuke에서 연 후 작업합니다.", s_body_j))
    items.append(sp(6))
    items.append(note(
        "이 매뉴얼은 기능별로 한 장 이상을 배정해 두었습니다. "
        "처음 사용자는 02장(설치·실행)과 03장(팀 서버 연동)을 순서대로 읽는 것을 권장합니다."
    ))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 2 — 시작하기
# ══════════════════════════════════════════════════════════════
def sec2() -> list:
    items = sec_hdr("02", "시작하기 — 설치·실행·필수 환경")

    items.append(P(
        "이 장에서는 <b>배포 폴더 준비</b>, <b>데스크톱 앱 실행</b>, "
        "<b>Nuke 연동(install_to_nuke)</b>까지를 처음 보는 사용자도 따라 할 수 있게 "
        "단계별로 설명합니다. 팀 단위 배포는 다음 장(03)을 함께 참고하세요.", s_body_j))
    items.append(sp(8))

    # Splash screen mockup on the right, text on the left
    splash_w = CONTENT_W * 0.44
    txt_w = CONTENT_W * 0.50

    splash = SplashMockup(width=splash_w, height=140)
    layout = Table(
        [[splash, Paragraph("", s_sm)]],
        colWidths=[splash_w, txt_w],
    )
    layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 16),
    ]))
    items.append(layout)

    items.append(P("<b>1) 시스템 요구 사항</b>", s_h2))
    items.append(info_tbl(
        ["항목", "내용"],
        [
            ["OS", "Windows 10 / 11 (64bit) 권장"],
            ["Nuke", "스튜디오에서 사용 중인 버전 (문서 기준 13–15 호환 목표)"],
            ["네트워크", "프리셋·플레이트가 NAS/SAN에 있을 경우 해당 드라이브 매핑 후 실행"],
            ["Python", "BPE 배포 EXE는 내장 런타임 사용 — 별도 Python 설치 불필요"],
        ],
        col_w=[3.5 * cm, CONTENT_W - 3.5 * cm],
    ))
    items.append(sp(8))

    items.append(P("<b>2) 배포 패키지 받기</b>", s_h2))
    items.append(P(
        "빌드 산출물은 보통 <b>release 폴더 전체</b>를 zip으로 묶어 배포합니다. "
        "압축을 풀 때 <b>하위 파일이 빠지지 않도록</b> 전체를 한 폴더에 유지하세요. "
        "특히 <b>install_to_nuke.bat</b>과 같은 디렉터리에 "
        "<b>install_setup_pro_menu.ps1</b>, Nuke용 <b>.py</b> 파일들이 있어야 "
        "설치 스크립트가 정상 동작합니다.", s_body_j))
    items.append(sp(6))
    items.append(info_tbl(
        ["파일·폴더", "역할"],
        [
            ["setup_pro_manager.exe (또는 BPE EXE)", "프리셋·Shot Builder GUI"],
            ["실행.bat", "EXE 실행을 돕는 배치(배포본에 포함된 경우)"],
            ["install_to_nuke.bat", "Nuke 사용자 폴더에 모듈 복사 + menu.py hook"],
            ["nuke_setup_pro.py, setup_pro_common.py 등", "Nuke에서 import 되는 스크립트"],
        ],
        col_w=[5.5 * cm, CONTENT_W - 5.5 * cm],
    ))
    items.append(sp(8))

    items.append(P("<b>3) BPE 앱 실행</b>", s_h2))
    items.append(P(
        "EXE는 <b>Python이 내장</b>된 단독 실행 파일입니다. "
        "탐색기에서 더블클릭하면 스플래시(로딩) 후 메인 창이 열립니다.", s_body))
    items += steps(
        ("1", "배포 ZIP을 원하는 위치에 압축 해제합니다."),
        ("2", "폴더 안의 <b>setup_pro_manager.exe</b> 또는 <b>실행.bat</b>을 더블클릭합니다."),
        ("3", "Windows가 처음 실행을 확인할 때는 <b>추가 정보 → 실행</b>으로 진행하면 됩니다 (내부 배포 EXE에서 흔한 절차입니다)."),
        ("4", "왼쪽 사이드바에서 <b>Preset Manager</b> / <b>Shot Builder</b> 탭을 전환합니다."),
    )
    items.append(sp(4))
    items.append(tip("첫 실행 후 프리셋 저장 폴더를 아직 지정하지 않았다면, Preset Manager 오른쪽 패널 상단 [변경]으로 팀이 합의한 경로를 먼저 잡는 것이 좋습니다."))
    items.append(PageBreak())

    items.append(P("<b>4) Nuke 연동 — install_to_nuke.bat</b>", s_h2))
    items.append(P(
        "Nuke 메뉴에 <b>setup_pro</b>를 올리려면 <b>각 작업자 PC마다 한 번</b> "
        "설치 배치를 실행합니다. 기존 <b>~/.nuke/menu.py</b>를 통째로 덮어쓰지 않고 "
        "맨 아래에 <b>import hook만 추가</b>하는 방식이므로, TD가 커스텀한 menu.py가 "
        "있어도 충돌 가능성을 줄였습니다.", s_body_j))
    items.append(sp(4))
    items += steps(
        ("1", "배포 폴더에서 <b>install_to_nuke.bat</b>을 더블클릭합니다."),
        ("2", "콘솔 창에 오류 없이 완료 메시지가 나오는지 확인합니다."),
        ("3", "Nuke를 <b>완전히 종료</b>했다가 다시 실행합니다."),
        ("4", "상단 메뉴에 <b>setup_pro</b>가 보이면 성공입니다."),
    )
    items.append(sp(6))
    items.append(code(
        "PowerShell 실행이 막힌 PC에서는 .nuke\\menu.py 맨 아래에 다음을 수동으로 추가할 수 있습니다:<br/>"
        "<br/>"
        "try:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;import nuke_setup_pro<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;nuke_setup_pro.add_setup_pro_menu()<br/>"
        "except Exception:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;pass"
    ))
    items.append(sp(6))
    items.append(P(
        "설치 직후 Nuke에서 <b>setup_pro → 캐시 새로 고침</b>을 한 번 실행해 두면 "
        "Write/포맷 관련 목록이 안정적으로 채워지는 경우가 많습니다.", s_body))
    items.append(sp(8))
    items.append(note("가상 PC·렌더 노드 등 Nuke를 띄우지 않는 머신에는 install_to_nuke가 필요 없을 수 있습니다. 실제 컴포짓 워크스테이션 위주로 설치하세요."))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 3 — 팀 서버 연동
# ══════════════════════════════════════════════════════════════
def sec_team() -> list:
    items = sec_hdr("03", "팀 서버 연동 — 전 작업자가 같은 기준으로 쓰기")

    items.append(P(
        "BPE의 효과는 <b>한 명이 만든 프리셋과 폴더 규칙을 팀 전체가 동일하게 참조</b>할 때 "
        "최대가 됩니다. 이 장에서는 공유 볼륨에 무엇을 두고, 각 PC에서 무엇을 맞추면 "
        "되는지 <b>운영 관점</b>에서 정리합니다.", s_body_j))
    items.append(sp(8))

    items.append(P("<b>1) 프리셋 저장 폴더를 서버로 통일</b>", s_h2))
    items.append(P(
        "Preset Manager 오른쪽의 <b>프리셋 저장 폴더</b>는 JSON 파일이 생성되는 위치입니다. "
        "여기를 <b>팀 읽기·쓰기 가능한 네트워크 경로</b>(예: <b>W:\\pipeline\\setup_pro_presets</b>)로 "
        "지정하면, 모든 아티스트가 같은 프리셋 목록을 봅니다.", s_body_j))
    items += steps(
        ("1", "서버에 전용 폴더를 만들고 팀 권한(읽기/쓰기)을 부여합니다."),
        ("2", "파이프라인 담당 PC에서 BPE [변경]으로 그 경로를 선택합니다."),
        ("3", "프리셋을 저장하면 해당 폴더에 데이터가 기록됩니다."),
        ("4", "다른 PC의 BPE에서도 <b>동일 경로</b>를 [변경]으로 지정합니다."),
    )
    items.append(sp(6))
    items.append(tip("경로는 반드시 UNC(\\\\server\\share\\...) 또는 모두가 동일한 드라이브 문자로 매핑된 경로로 통일하세요. 한 PC만 다른 문자 드라이브를 쓰면 파일을 찾지 못합니다."))
    items.append(PageBreak())

    items.append(P("<b>2) Shot Builder 입력값(서버 루트) 공유</b>", s_h2))
    items.append(P(
        "Shot Builder 탭의 <b>서버 루트</b>는 샷 트리가 시작되는 상위 경로입니다. "
        "팀에서 합의한 루트를 문서화해 두고, 신규 인력 온보딩 시 그대로 입력하도록 하면 "
        "경로 오류를 줄일 수 있습니다. 마지막 입력 값은 로컬 설정 파일에 기억될 수 있으므로, "
        "프로젝트가 바뀔 때마다 값을 다시 확인하는 습관을 권장합니다.", s_body_j))
    items.append(sp(8))

    items.append(P("<b>3) Nuke 패널의 프리셋 폴더</b>", s_h2))
    items.append(P(
        "Nuke에서 <b>setup_pro → 프리셋 적용</b>으로 연 패널에도 프리셋 폴더 경로가 있습니다. "
        "여기가 BPE 앱과 <b>어긋나면</b> 목록이 다르게 보입니다. "
        "팀 정책으로 “<b>항상 서버의 이 경로만 쓴다</b>”고 정하면 운영이 단순해집니다.", s_body))
    items.append(sp(8))

    items.append(P("<b>4) 배포물 버전 맞추기</b>", s_h2))
    items.append(P(
        "Nuke 쪽 <b>nuke_setup_pro.py</b>와 데스크톱 앱 빌드는 <b>같은 릴리스</b>를 쓰는 것이 안전합니다. "
        "업데이트 시에는 배포 zip을 통째로 교체하고, 팀원에게 <b>install_to_nuke.bat 재실행</b>을 "
        "안내하세요(스크립트가 갱신되므로).", s_body_j))
    items.append(sp(8))

    items.append(P("<b>5) 권한·백업</b>", s_h2))
    items.append(info_tbl(
        ["운영 항목", "권장"],
        [
            ["프리셋 폴더 권한", "리드·파이프라인 TD는 쓰기, 일반 컴포지터는 읽기만으로도 운영 가능(정책에 따라 조정)"],
            ["백업", "프리셋 JSON과 커스텀 노드 트리(프리셋별)는 프로젝트 자산으로 주기적 백업"],
            ["샷 NK", "Shot Builder는 v001 생성에 집중 — 이후 버전은 Nuke Save As로 관리"],
        ],
        col_w=[4.0 * cm, CONTENT_W - 4.0 * cm],
    ))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 4 — Preset Manager
# ══════════════════════════════════════════════════════════════
def sec3() -> list:
    items = sec_hdr("04", "Preset Manager — 프리셋 생성·편집·목록 관리")

    items.append(P(
        "프리셋은 BPE의 중심 데이터입니다. <b>FPS·Root 해상도·OCIO 경로·Read/Write 성격</b>을 "
        "한 이름(프로젝트 코드) 아래에 묶어 두고, Nuke에서는 패널에서 골라 <b>한 번에 적용</b>합니다. "
        "이 장에서는 화면의 각 칸이 무엇을 의미하는지, 저장·불러오기·삭제 흐름을 상세히 설명합니다.", s_body_j))
    items.append(sp(8))

    # Full UI mockup
    items.append(UIWindow(width=CONTENT_W, height=200, highlight="preset"))
    items.append(P("▲ Preset Manager — 왼쪽 스크롤 폼에 값 입력, 오른쪽에서 프리셋 목록·폴더·NK 가져오기", s_cap))
    items.append(sp(8))

    items.append(P("<b>필드별 설명 (처음 사용자용)</b>", s_h2))
    items.append(info_tbl(
        ["항목", "설명", "예시 / 주의"],
        [
            ["프로젝트 타입", "OTT/영화/광고 등 분류(팀 내부 기준)", "목록에서 선택"],
            ["프로젝트 코드", "프리셋 ID. Shot Builder·서버 폴더명과 맞출 때가 많음", "SBS_030 — 서버 프로젝트 폴더와 동일 권장"],
            ["FPS", "Root fps에 대응", "23.976 / 24 / 25"],
            ["해상도", "플레이트 기준 가로×세로", "프리셋 목록 또는 직접 입력"],
            ["OCIO Config", ".ocio 파일 절대 경로", "네트워크 경로 가능 — 파일 존재 여부 확인"],
            ["Read Input Transform", "첫 Read colorspace 후보", "Nuke OCIO 캐시와 연동"],
            ["Write 사용", "체크 시 납품 Write 관련 칸 활성", "끄면 Write 자동 생성 생략 가능"],
            ["납품 포맷 / Datatype / Compression", "EXR·MOV 등과 비트·압축", "프로젝트 납품 스펙에 맞출 것"],
            ["Output Transform", "colorspace 단일 지정 또는 display+view", "프로젝트 컬러 정책 준수"],
        ],
        col_w=[3.6 * cm, 5.8 * cm, CONTENT_W - 9.6 * cm],
    ))
    items.append(PageBreak())

    items.append(P("<b>저장·불러오기·삭제 절차</b>", s_h2))
    items += steps(
        ("1", "오른쪽 <b>프리셋 저장 폴더</b>가 의도한 경로인지 [변경]으로 확인합니다."),
        ("2", "왼쪽 폼을 채운 뒤 <b>프리셋 저장</b>을 누릅니다 — 목록에 코드가 나타납니다."),
        ("3", "기존 프리셋을 고치려면 목록에서 선택 후 <b>불러오기</b>로 폼에 올리고 수정·다시 저장합니다."),
        ("4", "더 이상 쓰지 않는 프리셋은 <b>삭제</b>로 제거합니다(팀 정책에 따라 권한 제한 권장)."),
    )
    items.append(sp(6))
    items.append(P("<b>커스텀 노드 트리 / NK 가져오기와의 관계</b>", s_h3))
    items.append(P(
        "같은 화면 오른쪽 아래에서 <b>커스텀 노드 트리</b> 편집 창을 열거나, "
        "<b>NK로 프리셋 가져오기</b>로 기존 스크립트를 분석해 새 프리셋을 만들 수 있습니다. "
        "자세한 동작은 이 매뉴얼 06·07장을 참고하세요.", s_body))
    items.append(sp(6))
    items.append(tip("프로젝트 코드는 서버 상 프로젝트 폴더 이름과 반드시 같게 두는 것이 Shot Builder 경로 생성과 일치해 실수가 적습니다."))
    items.append(sp(6))
    items.append(note("프리셋 JSON은 텍스트입니다. Git 등으로 버전 관리하면 변경 이력 추적에 유리합니다."))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 5 — Shot Builder
# ══════════════════════════════════════════════════════════════
def sec4() -> list:
    items = sec_hdr("05", "Shot Builder — 샷 NK 자동 생성")

    items.append(P(
        "Shot Builder는 <b>서버 루트 + 프로젝트 코드 + 샷 이름 + 프리셋</b> 네 가지를 입력하면 "
        "합의된 폴더 규칙 아래 <b>comp/devl/nuke/v001</b>에 "
        "<b>{샷이름}_comp_v001.nk</b>를 만들어 줍니다. "
        "템플릿(기본 또는 커스텀 노드 트리)에 따라 Read·Write 경로 문자열이 채워지므로 "
        "컴포지터는 파일을 연 뒤 바로 작업을 시작할 수 있습니다.", s_body_j))
    items.append(sp(8))

    # Workflow
    items.append(WorkflowArrow([
        ("1", "서버 루트"),
        ("2", "샷 이름"),
        ("3", "프리셋"),
        ("4", "NK 생성"),
        ("5", "Nuke에서 열기"),
    ], width=CONTENT_W, height=72))
    items.append(sp(8))

    # Shot Builder UI mockup
    items.append(UIWindow(width=CONTENT_W, height=190, highlight="shot"))
    items.append(P("▲ Shot Builder — 서버 루트·프로젝트 코드·샷 이름·프리셋 입력 후 NK 생성", s_cap))
    items.append(sp(8))

    items.append(P("<b>샷 이름 형식 (중요)</b>", s_h2))
    items.append(P(
        "내부적으로 <b>에피소드 접두 + 언더스코어 구분</b>을 사용합니다. "
        "예: <b>E107_S022_0080</b> → 에피소드 폴더 <b>E107</b>, 샷 폴더 전체 이름이 파일명 접두와 맞아야 합니다. "
        "규칙이 다르면 <b>build_shot_paths</b> 단계에서 실패하거나 잘못된 경로가 될 수 있으니 "
        "파이프라인 문서와 반드시 일치시키세요.", s_body_j))
    items.append(sp(8))

    items.append(P("<b>생성되는 서버 경로 구조</b>", s_h2))
    items.append(PathDiagram(width=CONTENT_W, height=155))
    items.append(P("▲ 예시 트리 — 실제 루트·프로젝트 코드·샷명은 입력값에 따라 바뀝니다", s_cap))
    items.append(PageBreak())

    items.append(P("<b>필드 입력 가이드</b>", s_h2))
    items.append(info_tbl(
        ["필드", "역할"],
        [
            ["서버 루트", "프로젝트 상위 볼륨(예: W:/vfx/project_2026) — 팀에서 고정값으로 문서화 권장"],
            ["프로젝트 코드", "서버의 프로젝트 폴더명과 동일해야 경로가 맞음"],
            ["샷 이름", "대문자 정규화됨 — 위 형식 준수"],
            ["프리셋", "Preset Manager에 저장된 코드 선택 — 커스텀 노드 트리가 있으면 해당 템플릿 사용"],
        ],
        col_w=[3.8 * cm, CONTENT_W - 3.8 * cm],
    ))
    items.append(sp(8))

    items.append(P("<b>생성 규칙 (덮어쓰기 방지)</b>", s_h2))
    items.append(info_tbl(
        ["상황", "BPE 동작"],
        [
            ["v001 NK가 없음",            "정상 생성"],
            ["v001 폴더만 있고 NK 없음",  "폴더 유지, NK만 생성"],
            ["v001 NK가 이미 있음",       "생성하지 않고 안내 — 기존 작업 보호"],
            ["샷 폴더가 없음",            "생성 여부를 사용자에게 확인"],
        ],
        col_w=[CONTENT_W * 0.42, CONTENT_W * 0.58],
    ))
    items.append(sp(4))
    items.append(note("v002 이상은 Nuke <b>File → Save As</b>로만 올리세요. Shot Builder는 의도적으로 v001만 담당합니다."))
    items.append(sp(6))
    items.append(tip("로그 영역에 출력되는 경로를 항상 한 번 읽어 보세요. 생성 직후 경로 오타를 잡는 데 도움이 됩니다."))
    items.append(PageBreak())

    items.append(P("<b>Nuke 패널 vs Shot Builder — 둘 다 쓰되, 새 샷은 Shot Builder가 더 효율적입니다</b>", s_h2))
    items.append(P(
        "<b>Nuke의 setup_pro 패널</b>은 이미 연 스크립트에 프리셋을 골라 "
        "Root·Write 기준을 맞출 때 빠르고 편합니다. "
        "<b>Shot Builder</b>는 그와 <b>다른 강점</b>이 있습니다. "
        "같은 프리셋을 공유하더라도, <b>새 샷의 첫 NK</b>를 만들 때는 Shot Builder를 쓰는 편이 "
        "실수가 적고 속도·일관성 면에서 이득이 큽니다.", s_body_j))
    items.append(sp(6))
    items.append(info_tbl(
        ["작업 상황", "이렇게 쓰면 좋습니다"],
        [
            ["열려 있는 nk에서 FPS·OCIO·Write만 맞추고 싶다", "Nuke → setup_pro → 프리셋 적용 패널"],
            ["새 샷의 v001 nk를 규칙 경로에 만들고 Read·Write까지 연결하고 싶다", "BPE 앱 → Shot Builder (같은 프리셋 선택)"],
            ["템플릿·플레이스홀더로 경로를 자동 치환하고 싶다", "Shot Builder (프리셋의 커스텀 노드 트리 반영)"],
        ],
        col_w=[5.4 * cm, CONTENT_W - 5.4 * cm],
    ))
    items.append(sp(8))
    items.append(P("<b>Shot Builder를 쓰면 좋은 이유 (요약)</b>", s_h3))
    items += steps(
        ("1", "<b>저장 위치를 고민할 필요가 거의 없습니다.</b> 팀이 정한 서버 트리(comp/devl/nuke/v001)에 맞춰 파일이 생깁니다."),
        ("2", "<b>경로 오타·폴더 빠뜨림이 줄어듭니다.</b> 샷 이름과 프리셋만 맞으면 플레이트·편집·렌더 경로 문자열이 한 번에 정리됩니다."),
        ("3", "<b>시작점이 항상 같은 형태입니다.</b> 신규 인력도 “Shot Builder → Nuke에서 열기” 흐름만 익히면 됩니다."),
        ("4", "<b>기존 v001을 지키는 설계</b>와 맞물려, 실수로 덮어쓰는 일 없이 안전하게 시작할 수 있습니다."),
        ("5", "<b>패널 적용과 충돌하지 않습니다.</b> 생성된 nk를 연 뒤, 필요하면 패널로 미세 조정하면 됩니다."),
    )
    items.append(sp(6))
    items.append(tip(
        "요약하면, <b>패널 = 지금 열린 씬에 세팅 반영</b>, "
        "<b>Shot Builder = 새 샷 파일을 규칙대로 “한 번에” 준비</b>입니다. "
        "프리셋 하나로 두 워크플로 모두 커버할 수 있어 팀 운영이 단순해집니다."
    ))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 6 — NK Import
# ══════════════════════════════════════════════════════════════
def sec5() -> list:
    items = sec_hdr("06", "NK 가져오기 — 기존 스크립트에서 프리셋 추출")

    items.append(P(
        "검증된 마스터 .nk가 이미 있다면, 그 파일을 분석해 "
        "<b>FPS·Root 포맷·OCIO·Read colorspace·Write 계열 설정</b>을 뽑아 "
        "새 프리셋으로 저장할 수 있습니다. "
        "시즌2처럼 전 시즌 스크립트를 복제해 미세 조정만 하는 워크플로에 특히 유리합니다.", s_body_j))
    items.append(sp(8))

    # Import dialog mockup
    import_mock = UIWindow(width=CONTENT_W * 0.55, height=195, highlight="import")
    steps_txt = Table(
        [[
            import_mock,
            Table(
                [[P("<b>사용 방법 (상세)</b>", s_h3)]] +
                [[P(t, s_body)] for t in [
                    "1. Preset Manager 오른쪽 아래 <b>NK로 프리셋 가져오기</b> 영역을 엽니다.",
                    "2. 경로 입력란에 nk를 쓰거나 <b>찾아보기</b>로 선택합니다.",
                    "3. <b>NK 분석하기</b>를 누르면 하단 카드에 감지된 값이 채워집니다.",
                    "4. 누락 항목은 카드 안내에 따라 왼쪽 폼에서 보완합니다.",
                    "5. <b>프리셋 이름</b>을 입력하고 <b>프리셋 생성</b> 또는 Enter로 확정합니다.",
                    "6. 동일 이름이 있으면 덮어쓰기 경고를 읽고 결정합니다.",
                ]],
                colWidths=[CONTENT_W * 0.44],
            ),
        ]],
        colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45],
    )
    steps_txt.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 16),
    ]))
    items.append(steps_txt)
    items.append(P("▲ NK 분석 결과 팝업 — 이름 입력 후 프리셋 생성", s_cap))
    items.append(sp(10))

    items.append(P("<b>자동 감지 항목</b>", s_h2))
    items.append(info_tbl(
        ["항목", "감지", "설명"],
        [
            ["FPS",                        "✅ 자동", "Root 블록 추출"],
            ["해상도 (가로 × 세로)",        "✅ 자동", "Root format 추출"],
            ["OCIO Config 경로",           "✅ 자동", "따옴표·중괄호 포맷 모두 지원"],
            ["Read Input Transform",       "✅ 자동", "첫 번째 Read 노드 colorspace"],
            ["납품 포맷 (EXR/MOV)",         "✅ 자동", "Write file_type 분석"],
            ["Channels / Datatype / Compression", "✅ 자동", "Write 노드에서 추출"],
            ["Output Transform",           "✅ 자동", "colorspace 또는 display/view"],
        ],
        col_w=[5.2*cm, 2.0*cm, CONTENT_W - 7.4*cm],
    ))
    items.append(sp(4))
    items.append(note("미감지 항목은 기본값으로 채워집니다. 생성 후 반드시 Preset Manager 폼에서 검토·저장하세요."))
    items.append(PageBreak())
    items.append(P("<b>추출 실패 시 점검</b>", s_h2))
    items.append(P(
        "Root 블록이 비정형이거나 OCIO knob이 비어 있으면 일부 필드가 비어 있을 수 있습니다. "
        "이 경우 수동으로 값을 채운 뒤 프리셋 저장하면 이후 Shot Builder·Nuke 적용에는 동일하게 사용됩니다.", s_body_j))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 7 — Custom Node Tree
# ══════════════════════════════════════════════════════════════
def sec6() -> list:
    items = sec_hdr("07", "커스텀 노드 트리 — 프리셋별 NK 템플릿")

    items.append(P(
        "기본적으로 Shot Builder는 공통 템플릿(shot_node_template.nk)을 사용합니다. "
        "커스텀 노드 트리 기능을 사용하면 "
        "<b>프리셋마다 완전히 다른 노드 구성</b>을 지정할 수 있습니다. "
        "프리셋별로 그레인·컬러 그레이딩·마스킹 등 기본 구성을 다르게 설정하세요.", s_body_j))
    items.append(sp(10))

    items.append(P("<b>설정 방법</b>", s_h2))
    items += steps(
        ("1", "Preset Manager 오른쪽 패널에서 프리셋을 선택합니다."),
        ("2", "[커스텀 노드 트리] 버튼을 클릭해 편집 창을 엽니다."),
        ("3", "Nuke에서 원하는 노드 구성을 만들고 Ctrl+A → Ctrl+C 로 복사합니다."),
        ("4", "편집 창의 텍스트 영역에 붙여넣고 [저장]을 클릭합니다."),
    )
    items.append(sp(10))

    items.append(P("<b>경로 자동 치환</b>", s_h2))
    items.append(P(
        "커스텀 템플릿 안에 샘플 경로와 샷 이름이 있으면 "
        "Shot Builder 실행 시 실제 경로로 <b>자동 교체</b>됩니다.", s_body))
    items.append(sp(4))
    items.append(code(
        "템플릿 안의 샘플 경로:  W:/vfx/project_2026/SBS_030/04_sq/E107/E107_S022_0080<br/>"
        "→ Shot Builder 실행 시:  W:/vfx/project_2026/SBS_030/04_sq/E107/E107_S100_0030<br/>"
        "<br/>"
        "템플릿 안의 샘플 이름:  E107_S022_0080<br/>"
        "→ Shot Builder 실행 시:  E107_S100_0030"
    ))
    items.append(tip("편집 창에서 <b>플레이스홀더 안내</b>를 열면 템플릿에 넣어야 할 <b>예시 샷 루트·예시 샷 이름</b> 문자열을 확인할 수 있습니다. 다른 프로젝트·샷에도 동일 문자열만 맞추면 자동 치환됩니다."))
    items.append(sp(10))

    items.append(P("<b>우선순위</b>", s_h2))
    items.append(info_tbl(
        ["상태", "Shot Builder 동작"],
        [
            ["커스텀 노드 트리 없음", "shot_node_template.nk (기본 템플릿) 사용"],
            ["커스텀 노드 트리 있음", "해당 프리셋의 커스텀 템플릿 우선 사용"],
        ],
        col_w=[CONTENT_W * 0.4, CONTENT_W * 0.6],
    ))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 8 — Nuke 패널
# ══════════════════════════════════════════════════════════════
def sec7() -> list:
    items = sec_hdr("08", "Nuke — setup_pro 메뉴·패널·BPE Tools")

    items.append(P(
        "Nuke 상단 메뉴 <b>setup_pro</b>에서 패널을 열어 프리셋을 고르면 "
        "Root(FPS·format·OCIO)와 <b>setup_pro_write</b> 계열 Write 구성이 "
        "<b>한 번에 적용</b>됩니다. 메뉴 이름은 제품 내부 코드명과 동일하게 유지되어 "
        "TD 문서·로그와 대응하기 쉽습니다.", s_body_j))
    items.append(sp(8))

    items.append(P("<b>메뉴 구성 (실제 스크립트 기준)</b>", s_h2))
    items.append(info_tbl(
        ["메뉴 항목", "설명"],
        [
            ["프리셋 적용 (FPS · 해상도 · OCIO · Write 세팅)", "패널을 열어 프리셋 선택 후 적용"],
            ["캐시 새로 고침 (Write / 포맷 목록 갱신)", "colorspace/datatype 목록이 비었을 때 먼저 실행"],
            ["BPE Tools → QC · Post-Render 상태 확인", "훅·렌더 관련 상태 점검(환경에 따라 사용)"],
            ["BPE Tools → Tool Hooks 다시 불러오기", "데스크톱 앱에서 저장한 훅 설정을 Nuke에 재로드"],
            ["Tool Hooks 다시 불러오기", "상위 메뉴 단축 항목(동일 동작)"],
        ],
        col_w=[6.2 * cm, CONTENT_W - 6.2 * cm],
    ))
    items.append(sp(8))

    items.append(P("<b>패널에서 할 일 (단계)</b>", s_h2))
    items += steps(
        ("1", "Nuke에서 <b>setup_pro → 프리셋 적용 …</b>을 선택합니다."),
        ("2", "패널이 열리면 <b>프리셋 폴더</b>가 팀 공유 경로인지 확인합니다."),
        ("3", "목록에서 프리셋을 고르고 적용(Apply) 동작을 실행합니다."),
        ("4", "콘솔/메시지에 실패 항목이 있으면 내용을 캡처해 파이프라인에 전달합니다."),
    )
    items.append(sp(10))

    items.append(P("<b>적용 시 주로 바뀌는 Nuke 항목</b>", s_h2))
    items.append(info_tbl(
        ["Nuke 항목", "적용 내용"],
        [
            ["Root → fps",              "프리셋의 FPS 값"],
            ["Root → format",           "프리셋 해상도로 포맷 등록 후 설정"],
            ["Root → OCIO Config",      "프리셋의 .ocio 파일 경로"],
            ["Write → file_type",       "EXR / MOV 납품 포맷"],
            ["Write → channels",        "all / rgb / rgba 출력 채널"],
            ["Write → datatype",        "16 bit half / 32 bit float"],
            ["Write → compression",     "PIZ Wavelet 등 압축 방식"],
            ["Write → colorspace / display/view", "Output Transform 설정"],
        ],
        col_w=[CONTENT_W * 0.42, CONTENT_W * 0.58],
    ))
    items.append(sp(8))
    items.append(tip(
        "Nuke 버전마다 knob 이름이 다를 수 있습니다. "
        "nuke_setup_pro.py는 <b>여러 후보 knob</b>을 순서대로 시도해 호환 범위를 넓혔습니다."
    ))
    items.append(note(
        "목록이 비어 있으면 <b>setup_pro → 캐시 새로 고침</b>을 실행한 뒤 패널을 다시 열어보세요."
    ))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 9 — 보안·안전 설계
# ══════════════════════════════════════════════════════════════
def sec_security() -> list:
    items = sec_hdr("09", "안심하고 쓰는 BPE — 안전하고 투명한 설계")

    items.append(P(
        "BPE(setup_pro)는 <b>스튜디오 안에서 믿고 쓸 수 있도록</b> 만들어졌습니다. "
        "데이터는 <b>팀이 정한 폴더 안에서만</b> 오가고, 동작은 <b>예측 가능하게</b> 열려 있습니다. "
        "이 장에서는 그래서 <b>왜 안전하다고 말할 수 있는지</b>, "
        "그리고 <b>프리셋 파일(JSON)</b>이 무엇인지까지 편하게 정리합니다.", s_body_j))
    items.append(sp(8))

    items.append(P("<b>참고: JSON이란? (주석처럼 읽어 주세요)</b>", s_h3))
    items.append(P(
        "<b>JSON</b>(제이슨)은 설정·목록을 담는 <b>표준 텍스트 형식</b>입니다. "
        "바이너리가 아니라 <b>메모장으로도 열어볼 수 있는 글자 파일</b>이라, "
        "“안에 뭐가 들었는지” 팀이 그대로 확인할 수 있습니다. "
        "BPE의 프리셋도 이런 JSON(또는 팀이 지정한 폴더 안의 JSON)으로 저장되어 "
        "<b>백업·버전 관리(Git 등)</b>와도 잘 맞습니다.", s_body_j))
    items.append(sp(4))
    items.append(code(
        "간단 예시 — 이름과 값이 쌍으로 적힌 텍스트입니다:<br/>"
        "{ \"project_code\": \"SBS_030\", \"fps\": \"23.976\" }<br/>"
        "<br/>"
        "→ 프로그램이 읽기 쉽고, 사람도 열어서 검토하기 좋은 형태입니다."
    ))
    items.append(sp(8))

    items.append(P("<b>1) 데이터는 스튜디오 안, 지정한 경로 안에서만</b>", s_h2))
    items.append(P(
        "BPE는 <b>사내 PC와 NAS</b>처럼 여러분이 이미 쓰는 저장소를 전제로 합니다. "
        "프리셋·Shot Builder 설정·생성된 NK는 모두 <b>사용자가 선택한 경로</b>에 기록됩니다. "
        "<b>클라우드로 자동 업로드하거나 숨은 전송을 하는 구조가 아닙니다</b> — "
        "그래서 팀 IT 정책과 함께 쓰기에 <b>예측 가능하고 안심할 수 있는</b> 구조입니다.", s_body_j))
    items.append(sp(6))
    items.append(info_tbl(
        ["항목", "BPE가 지향하는 안전한 방식"],
        [
            ["프리셋", "팀 공유 폴더의 JSON — 권한만 맞추면 접근·백업이 명확합니다"],
            ["OCIO 등 경로", "로컬·NAS에서 파일 존재를 확인하는 방식으로 연결합니다"],
            ["Nuke 메뉴 연동", "menu.py에는 짧은 try/import만 추가되어, 연동이 비활성화되어도 Nuke는 정상 기동됩니다"],
        ],
        col_w=[3.6 * cm, CONTENT_W - 3.6 * cm],
    ))
    items.append(PageBreak())

    items.append(P("<b>2) 서버 작업물을 소중히 지키는 Shot Builder</b>", s_h2))
    items.append(P(
        "Shot Builder는 <b>이미 있는 v001 NK를 덮어쓰지 않습니다</b>. "
        "파일이 있으면 멈추고 알려 주어, <b>진행 중인 작업을 보호</b>합니다. "
        "샷 폴더가 없을 때도 <b>한 번 확인</b>하고 진행할 수 있어, "
        "의도와 다른 대량 생성 없이 <b>차분하게 운영</b>할 수 있습니다.", s_body_j))
    items.append(sp(8))

    items.append(P("<b>3) NK는 검증된 템플릿에서 출발합니다</b>", s_h2))
    items.append(P(
        "샷 NK는 <b>팀이 검토한 템플릿</b>(기본 shot_node_template 또는 커스텀 노드 트리)을 바탕으로 "
        "필요한 경로·노드 설정을 채워 넣습니다. "
        "Nuke 쪽 프리셋 적용도 <b>여러 버전에 맞춰 준비된 knob 후보</b>를 순서대로 시도하고, "
        "결과는 <b>메시지와 콘솔 출력</b>으로 남겨 <b>투명하게 확인</b>할 수 있게 했습니다.", s_body_j))
    items.append(sp(6))
    items.append(tip(
        "템플릿 NK를 Git 등으로 관리하면 “무엇이 언제 바뀌었는지”가 한눈에 들어와, "
        "팀 전체가 <b>더 안전하고 자신 있게</b> 배포할 수 있습니다."
    ))
    items.append(PageBreak())

    items.append(P("<b>4) 함께하면 더 든든한 운영 팁</b>", s_h2))
    items.append(P(
        "BPE 자체가 <b>안전하게 설계</b>되어 있을 뿐 아니라, "
        "스튜디오의 좋은 습관과 만나면 <b>더욱 안심</b>할 수 있습니다.", s_body_j))
    items.append(sp(4))
    items.append(info_tbl(
        ["협력 포인트", "이렇게 하면 더 좋습니다"],
        [
            ["프리셋 관리", "TD·리드가 JSON을 관리하고, 컴포지터는 동일 폴더를 읽기만 — 역할이 분명해집니다"],
            ["배포", "내부에서 공인한 zip만 배포하면 설치 경로가 항상 깨끗합니다"],
            ["IT 협력", "사내 코드 서명·백신 예외는 IT와 협의해 표준 PC 이미지에 맞추면 더 매끈합니다"],
            ["이력", "프리셋 JSON을 Git 등으로 보관하면 변경 이력이 남아 감사·인수인계에 유리합니다"],
        ],
        col_w=[3.8 * cm, CONTENT_W - 3.8 * cm],
    ))
    items.append(sp(8))
    items.append(P(
        "<b>한 줄로</b> — BPE는 <b>투명한 저장 방식</b>, <b>예측 가능한 파일 생성</b>, "
        "<b>검증 가능한 템플릿</b>을 바탕으로, 스튜디오가 <b>안심하고 매일 쓸 수 있는</b> 도구가 되도록 "
        "다듬어 왔습니다.", s_body_j))
    items.append(PageBreak())
    return items


# ══════════════════════════════════════════════════════════════
# SEC 10 — FAQ
# ══════════════════════════════════════════════════════════════
def sec8() -> list:
    items = sec_hdr("10", "FAQ · 문제 해결 · 업데이트")

    faqs = [
        ("Q.  Python이 없는 PC에서도 BPE 앱이 실행되나요?",
         "네. 배포 EXE는 내장 런타임을 사용하므로 별도 Python 설치가 필요 없습니다."),

        ("Q.  Windows SmartScreen / Defender가 막습니다.",
         "내부 빌드는 코드 서명이 없을 수 있습니다. IT 정책에 따라 예외를 요청하거나, "
         "'추가 정보 → 실행'으로 진행하세요."),

        ("Q.  Nuke 메뉴에 setup_pro가 안 보여요.",
         "install_to_nuke.bat을 배포 폴더에서 다시 실행했는지, Nuke를 완전히 재시작했는지 확인하세요. "
         "menu.py 수동 연동 예시는 매뉴얼 02장을 참고하세요."),

        ("Q.  컬러스페이스 / Datatype 목록이 비어 있어요.",
         "Nuke에서 setup_pro → 캐시 새로 고침을 실행한 뒤, 프리셋 적용 패널을 다시 여세요. "
         "BPE 앱도 Nuke가 설치된 PC에서 실행하면 목록이 채워지는 경우가 많습니다."),

        ("Q.  프리셋 목록이 동료와 다릅니다.",
         "Preset Manager와 Nuke 패널 모두에서 <b>프리셋 저장 폴더 경로</b>가 동일한지(드라이브 문자 포함) 확인하세요."),

        ("Q.  Shot Builder가 NK를 만들지 않고 막아요.",
         "이미 v001 NK가 있으면 <b>의도적으로 건너뜁니다</b>. "
         "샷 경로·프로젝트 코드·샷 이름 형식이 파이프라인 문서와 일치하는지도 확인하세요."),

        ("Q.  플레이트 Read 경로가 틀립니다.",
         "서버 트리가 plate/org/v001/hi/ 규칙과 맞는지 확인하세요. "
         "다르면 커스텀 노드 트리로 Read file 경로 패턴을 팀에 맞게 수정합니다."),

        ("Q.  NK 가져오기 후 값이 비어 있습니다.",
         "Root/Write 블록이 비표준이면 자동 추출이 실패할 수 있습니다. "
         "폼에서 수동 입력 후 프리셋 저장하면 이후에는 동일하게 사용 가능합니다."),

        ("Q.  업데이트 후에도 Nuke가 옛 동작을 합니다.",
         "배포 zip 전체를 교체하고 install_to_nuke.bat을 다시 실행해 스크립트를 덮어쓰세요. "
         "필요 시 setup_pro → Tool Hooks 다시 불러오기를 누릅니다."),

        ("Q.  보안·안전 관련 설명 자료가 필요합니다.",
         "매뉴얼 09장「안심하고 쓰는 BPE」를 인용하고, 프리셋 폴더 ACL·백업 정책을 팀 표준 문서에 덧붙이면 됩니다."),
    ]

    for q, a in faqs:
        block = KeepTogether([
            Paragraph(q, s_fq),
            Paragraph(a, s_fa),
            HRFlowable(width="100%", thickness=0.5, color=GY2,
                       spaceBefore=0, spaceAfter=6),
        ])
        items.append(block)

    items.append(sp(20))
    items.append(HRFlowable(width="100%", thickness=2, color=OR, spaceAfter=10))
    items.append(Paragraph(
        "BELUCA Pipeline Engine · setup_pro · 사용자 가이드",
        ParagraphStyle("ft", fontName=FN, fontSize=8.5, textColor=GY3, alignment=TA_CENTER)
    ))
    return items


# ══════════════════════════════════════════════════════════════
# BUILD (자동 목차 — multiBuild)
# ══════════════════════════════════════════════════════════════
def build():
    frame_h = PAGE_H - (MT + 1.1 * cm) - (MB + 1.05 * cm)
    doc = ManualDocTemplate(
        str(OUT_FILE),
        pagesize=A4,
        leftMargin=ML,
        rightMargin=MR,
        topMargin=MT + 1.1 * cm,
        bottomMargin=MB + 1.05 * cm,
        title="BELUCA Pipeline Engine / setup_pro User Guide",
        author="BELUCA",
        subject="BPE Manual",
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="main",
                frames=[Frame(ML, MB + 1.05 * cm, CONTENT_W, frame_h, id="normal")],
                onPage=_on_page,
                pagesize=A4,
            )
        ]
    )

    toc_flow = TableOfContents()
    toc_flow.levelStyles = [
        ParagraphStyle(
            name="TOC1",
            fontName=FN,
            fontSize=10.5,
            leading=14,
            leftIndent=18,
            firstLineIndent=-18,
            spaceBefore=4,
            spaceAfter=2,
            textColor=BK,
        ),
    ]

    story = []
    story += cover()
    story.append(sp(4))
    story.append(
        Paragraph(
            "목  차",
            ParagraphStyle(
                "thtoc",
                fontName=FB,
                fontSize=22,
                leading=30,
                textColor=BK,
                spaceAfter=6,
            ),
        )
    )
    story.append(
        HRFlowable(width="100%", thickness=2.5, color=OR, spaceAfter=14, spaceBefore=4)
    )
    story.append(toc_flow)
    story.append(PageBreak())
    story += sec1()
    story += sec2()
    story += sec_team()
    story += sec3()
    story += sec4()
    story += sec5()
    story += sec6()
    story += sec7()
    story += sec_security()
    story += sec8()

    doc.multiBuild(story, canvasmaker=rl_canvas.Canvas)
    print(f"PDF saved: {OUT_FILE}")


if __name__ == "__main__":
    build()
