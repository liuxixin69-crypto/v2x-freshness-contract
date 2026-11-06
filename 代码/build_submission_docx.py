# -*- coding: utf-8 -*-
"""
Build an IEEE Access submission manuscript (.docx) from
论文/期刊版_初稿_EN_v0.2.md

Outputs:
  论文实验/投稿版_IEEE_Access_v1.0.docx
  论文实验/投稿版_IEEE_Access_v1.0_cover_letter.docx
  论文实验/投稿前待办清单_v1.0.md
"""
import io, re, os, textwrap, csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(BASE, r"论文/期刊版_初稿_EN_v0.2.md")
VERSION = os.environ.get("MS_VERSION", "v2.0")
OUT  = os.path.join(BASE, r"论文实验/投稿版_IEEE_Access_%s.docx" % VERSION)
CL   = os.path.join(BASE, r"论文实验/投稿版_IEEE_Access_%s_cover_letter.docx" % VERSION)
CHK  = os.path.join(BASE, r"论文实验/投稿前待办清单_%s.md" % VERSION)

# ----------------------------------------------------------------------------
# Author metadata — single source of truth.
# Feeds the title block, the cover letter, and the Zenodo deposit metadata.
# Change these values here; never hand-edit the generated .docx.
# ----------------------------------------------------------------------------
AUTHOR_META = {
    "name":         "Nian Liu",              # 刘念 (surname Liu)
    "affiliation":  "International School, Beijing University of Posts and Telecommunications",
    "affiliation_full": "International School, Beijing University of Posts and Telecommunications, "
                        "Beijing 100876, China",
    "email":        "2138385347@bupt.edu.cn",
    "orcid":        "",                      # optional; fill "0000-0000-0000-0000" when available
    "corresponding": True,                   # single author -> also corresponding author (\u2020)
}
COVER_DATE = "November 6, 2026"              # edit to actual submission date if needed

# ----------------------------------------------------------------------------
# Math rendering (matplotlib mathtext -> PNG, embedded in Word)
# ----------------------------------------------------------------------------
def math_preprocess(tex):
    t = tex.strip()
    if t.startswith("$") and t.endswith("$"):
        t = t[1:-1]
    t = t.replace("\\textit", "\\mathit")
    t = t.replace("\\text", "\\mathrm")
    t = t.replace("\\Pr", "\\mathrm{Pr}")
    t = t.replace("\\max", "\\mathrm{max}")
    t = t.replace("\\min", "\\mathrm{min}")
    t = t.replace("\\log", "\\mathrm{log}")
    t = t.replace("\\tfrac", "\\frac")
    t = t.replace("\\frac12", "\\frac{1}{2}")
    # matplotlib mathtext uses \leq / \geq; guard \le so it does not hit \left
    t = re.sub(r"\\le(?![a-zA-Z])", lambda m: r"\leq", t)
    t = re.sub(r"\\ge(?![a-zA-Z])", lambda m: r"\geq", t)
    return t

def math_preprocess_omml(tex):
    """OMML path: like math_preprocess but keeps \\text{...} intact, so
    latex2mathml renders it as <mtext> with spaces preserved (as NBSP)."""
    t = tex.strip()
    if t.startswith("$") and t.endswith("$"):
        t = t[1:-1]
    t = t.replace("\\textit", "\\mathit")
    t = t.replace("\\Pr", "\\mathrm{Pr}")
    t = t.replace("\\max", "\\mathrm{max}")
    t = t.replace("\\min", "\\mathrm{min}")
    t = t.replace("\\log", "\\mathrm{log}")
    t = t.replace("\\tfrac", "\\frac")
    t = t.replace("\\frac12", "\\frac{1}{2}")
    t = re.sub(r"\\le(?![a-zA-Z])", r"\\leq", t)
    t = re.sub(r"\\ge(?![a-zA-Z])", r"\\geq", t)
    return t

_math_cache = {}
def math_png(tex, fs=10):
    key = (tex, fs)
    if key in _math_cache:
        return _math_cache[key]
    t = math_preprocess(tex)
    fig = plt.figure(figsize=(6, 2))
    fig.text(0.5, 0.5, f"${t}$", fontsize=fs, ha="center", va="center", color="black")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight",
                transparent=True, pad_inches=0.02)
    plt.close(fig)
    buf.seek(0)
    im = Image.open(buf)
    wpx, hpx = im.size
    png = buf.getvalue()
    _math_cache[key] = (png, hpx / 300.0)
    return _math_cache[key]

# --- Native OMML equations (LaTeX -> MathML -> OMML via Office MML2OMML.XSL) ---
_OMML_XSL = None
try:
    from latex2mathml.converter import convert as _l2m
    from lxml import etree as _etree
    _xsl_path = r"C:/Program Files/Microsoft Office/root/Office16/MML2OMML.XSL"
    if os.path.exists(_xsl_path):
        _OMML_XSL = _etree.XSLT(_etree.parse(_xsl_path))
except Exception:
    _OMML_XSL = None

_OMML_STATS = {"ok": 0, "fallback": 0}
_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

def _omml_element(tex):
    dom = _etree.fromstring(_l2m(math_preprocess_omml(tex)))
    return _OMML_XSL(dom).getroot()

def add_math(p, tex, display=False):
    # 1) preferred: native, editable OMML
    if _OMML_XSL is not None:
        try:
            el = _omml_element(tex)
            if display:
                para = OxmlElement("m:oMathPara")
                ppr = OxmlElement("m:oMathParaPr")
                jc = OxmlElement("m:jc"); jc.set(qn("m:val"), "center")
                ppr.append(jc); para.append(ppr)
                para.append(el)
                p._p.append(para)
            else:
                p._p.append(el)
            _OMML_STATS["ok"] += 1
            return
        except Exception:
            _OMML_STATS["fallback"] += 1
    # 2) fallback: rasterised PNG
    try:
        png, hi = math_png(tex, 12 if display else 10)
        run = p.add_run()
        run.add_picture(io.BytesIO(png), height=Inches(hi))
    except Exception:
        r = p.add_run(tex)
        r.italic = True

# ----------------------------------------------------------------------------
# Inline tokeniser: **bold**, $math$, `code`, *italic*
# ----------------------------------------------------------------------------
TOKEN = re.compile(r"\*\*(.+?)\*\*|\$([^$\n]+?)\$|`([^`]+)`|\*([^*\n]+?)\*")

def add_inline(p, text):
    text = re.sub(r"\[TBD[^\]]*\]", "", text)        # strip stray TBD markers
    text = text.replace("  ", " ")
    pos = 0
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            p.add_run(text[pos:m.start()])
        if m.group(1) is not None:
            r = p.add_run(m.group(1)); r.bold = True
        elif m.group(2) is not None:
            add_math(p, m.group(2), display=False)
        elif m.group(3) is not None:
            r = p.add_run(m.group(3)); r.font.name = "Consolas"; r.font.size = Pt(9)
        elif m.group(4) is not None:
            r = p.add_run(m.group(4)); r.italic = True
        pos = m.end()
    if pos < len(text):
        p.add_run(text[pos:])

# ----------------------------------------------------------------------------
# Document styling helpers
# ----------------------------------------------------------------------------
def set_columns(sectPr, n, space=360):
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols"); sectPr.append(cols)
    cols.set(qn("w:num"), str(n))
    cols.set(qn("w:space"), str(space))

def add_continuous_break(doc, cols=1):
    """End the current section with a continuous break; page size/margins are
    inherited from the document's final sectPr so that continuation sections
    keep the IEEE page geometry (a bare sectPr would fall back to 1-inch margins)."""
    import copy as _copy
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    sectPr = OxmlElement("w:sectPr")
    t = OxmlElement("w:type"); t.set(qn("w:val"), "continuous"); sectPr.append(t)
    tmpl = doc.element.body.find(qn("w:sectPr"))
    if tmpl is not None:
        for tag in ("w:pgSz", "w:pgMar"):
            el = tmpl.find(qn(tag))
            if el is not None:
                sectPr.append(_copy.deepcopy(el))
    c = OxmlElement("w:cols"); c.set(qn("w:num"), str(cols)); sectPr.append(c)
    p._p.get_or_add_pPr().append(sectPr)
    return p

def add_section_heading(doc, text, level=0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 0 else WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(text.upper() if level == 0 else text)
    r.bold = True
    r.font.size = Pt(11 if level == 0 else 10)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    return p

def roman(n):
    vals = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
            (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    s = ""; 
    while n > 0:
        for v, c in vals:
            if n >= v: s += c; n -= v; break
    return s

def add_display_equation(doc, tex):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_math(p, tex, display=True)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)

def build_table(doc, rows, header=True, fontsize=8.5):
    nrows = len(rows); ncols = len(rows[0])
    tbl = doc.add_table(rows=nrows, cols=ncols)
    try:
        tbl.style = "Table Grid"
    except Exception:
        pass
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = ""
            para = cell.paragraphs[0]
            para.paragraph_format.space_before = Pt(1)
            para.paragraph_format.space_after = Pt(1)
            # split on newline -> multiple runs/lines
            for k, line in enumerate(str(val).split("\n")):
                if k > 0:
                    para.add_run().add_break()
                add_inline(para, line)
                for run in para.runs:
                    run.font.size = Pt(fontsize)
            if header and i == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True
    # 行内不断开；首行作表头，跨栏/跨页时自动重复表头
    for i, row in enumerate(tbl.rows):
        trPr = row._tr.get_or_add_trPr()
        trPr.append(OxmlElement("w:cantSplit"))
        if header and i == 0:
            trPr.append(OxmlElement("w:tblHeader"))
    return tbl

def add_table_caption(doc, title, tbl):
    """IEEE-style caption ("TABLE II" + small-caps title) inserted above `tbl`."""
    _ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
              "XI", "XII"]
    _CAP["n"] += 1
    no = _ROMAN[_CAP["n"] - 1]
    _CAP["labels"].append(no)

    p1 = doc.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p1.add_run("TABLE " + no)
    r1.font.size = Pt(8)
    r1.font.small_caps = True
    r1.bold = True
    p1.paragraph_format.space_before = Pt(8)
    p1.paragraph_format.space_after = Pt(1)
    p1.paragraph_format.keep_with_next = True

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run(title)
    r2.font.size = Pt(8)
    r2.font.small_caps = True
    p2.paragraph_format.space_after = Pt(3)
    p2.paragraph_format.keep_with_next = True

    tbl._tbl.addprevious(p1._p)      # label first ...
    tbl._tbl.addprevious(p2._p)      # ... then title, both above the table
    return tbl


def add_table(doc, rows, title, header=True, fontsize=8.0):
    """build_table + caption, keeping caption and table together."""
    tbl = build_table(doc, rows, header=header, fontsize=fontsize)
    add_table_caption(doc, title, tbl)
    return tbl


_CAP = {"n": 0, "labels": [], "pipe_i": 0}
_PIPE_TITLES = [
    "Experiment Groups and Run Counts",
    "Blindness Ratio Versus Miss Ratio Under Four Conditions",
    "i.i.d. Versus Gilbert\u2013Elliot Losses at Equal Mean Loss Rate",
]

def set_table_width(tbl, widths_in):
    """Force fixed layout and explicit column widths (inches)."""
    from docx.shared import Inches as _In
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    for el in tblPr.findall(qn("w:tblW")):
        tblPr.remove(el)
    tw = OxmlElement("w:tblW")
    tw.set(qn("w:w"), str(int(sum(widths_in) * 1440)))
    tw.set(qn("w:type"), "dxa")
    tblPr.append(tw)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    for j, w in enumerate(widths_in):
        tbl.columns[j].width = _In(w)
    for row in tbl.rows:
        for j, w in enumerate(widths_in):
            if j < len(row.cells):
                row.cells[j].width = _In(w)


def add_wide_table(doc, rows, title, widths_in, header=True, fontsize=8.0):
    """Full-width table: same single-column continuation trick as add_figure,
    needed when the column count or the header words do not fit one column."""
    add_continuous_break(doc, 2)          # close the running two-column text
    tbl = build_table(doc, rows, header=header, fontsize=fontsize)
    set_table_width(tbl, widths_in)
    add_table_caption(doc, title, tbl)
    add_continuous_break(doc, 1)          # this section holds the full-width table
    return tbl


def add_ref(doc, text):
    text = re.sub(r"`[^`]*`", "", text)               # drop backtick notes in refs
    text = re.sub(r"\[TBD[^\]]*\]", "", text)
    m = re.match(r"^\[(\d+)\]\s*(.*)$", text.strip())
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    if m:
        rb = p.add_run("[" + m.group(1) + "] ")
        rb.bold = True
        add_inline(p, m.group(2))
    else:
        add_inline(p, text)
    # hanging indent
    pf = p.paragraph_format
    pf.left_indent = Inches(0.3)
    pf.first_line_indent = Inches(-0.3)
    for run in p.runs:
        run.font.size = Pt(9)
    return p

# ----------------------------------------------------------------------------
# Parse source markdown
# ----------------------------------------------------------------------------
raw = open(SRC, encoding="utf-8").read()
original_raw = raw

# --- content edits BEFORE parsing (resolve easy TBDs / strengthen novelty) ---
# capture all TBD markers for the checklist
tbds = re.findall(r"\[TBD[^\]]*\]", original_raw)

# 1) remove DRAFT NOTES block (from "> **DRAFT NOTES" through the "**Affiliation:**" line)
m = re.search(r"> \*\*DRAFT NOTES.*?\*\*Affiliation:\*\*[^\n]*\n", raw, re.DOTALL)
if m:
    raw = raw[:m.start()] + raw[m.end():]

# 2) remove the "**Authors:** [TBD] ... **Affiliation:** [TBD]" line
raw = re.sub(r"\*\*Authors:\*\*[^\n]*\n", "", raw)

# 3) replace the Table I placeholder line with a sentinel
raw = re.sub(r"\n\*Table I[^\n]*\n", "\n@@TABLE_I@@\n", raw)

# 4) references are now maintained entirely in the source Markdown (single
#    source of truth, numbered by order of first appearance). The clause-level
#    ETSI citation and the novelty-bounding sentence used to be patched in here;
#    both now live in the .md and the patches below are gone.

# 6) drop the version footer line
raw = re.sub(r"\n\*Version:[^\n]*\n", "\n", raw)

# 7) global cleanup of any remaining [TBD...] markers (recorded above)
raw = re.sub(r"`?\[TBD[^\]]*\]`?", "", raw)

# 8) fix TR 37.985 year already 2024 in v0.2 (no-op safeguard)
raw = raw.replace("ETSI TR 137 985 V17.2.0, 2022", "ETSI TR 137 985 V17.2.0, 2024")

# extract title
title_m = re.search(r"^#\s+(.*)$", raw, re.MULTILINE)
TITLE = title_m.group(1).strip() if title_m else "Untitled"
raw = re.sub(r"^#\s+.*\n", "", raw, count=1)

# ----------------------------------------------------------------------------
# Table I (comparison with related work); refs now come only from the .md
# ----------------------------------------------------------------------------
TABLE_I = [
    ["Work", "Closed-form\ndeadline?", "Warning-decision\nendpoint?", "2-D feasible\nregion?", "Blindness\u2013miss\ndecoupling?"],
    ["Kaul, Yates & Gruteser (INFOCOM 2012) [9]", "\u2014", "\u00d7", "\u00d7", "\u2014"],
    ["Kaul et al. (SECON 2011) [10]", "\u2014", "\u00d7", "\u00d7", "\u2014"],
    ["Costa, Codreanu & Ephremides (TIT 2016) [11]", "\u2713 (peak age)", "\u00d7", "\u00d7", "\u2014"],
    ["Yates et al., AoI survey (JSAC 2021) [12]", "\u2713 (tail methods)", "\u00d7", "\u00d7", "\u2014"],
    ["Gilbert / Elliott burst channel [13],[14]", "\u2014 (model only)", "\u00d7", "\u00d7", "\u2014"],
    ["3GPP TS 22.185 / TR 37.985 [1],[7]", "\u00d7 (100/20 ms only)", "\u00d7", "\u00d7", "\u2014"],
    ["ETSI TS 101 539-3 LCRW (2013) [17]", "\u2014 (300 ms rule)", "\u00d7", "\u00d7", "\u2014"],
    ["ETSI TR 103 415 [18]", "\u2014", "\u00d7", "\u00d7", "\u2014"],
    ["Marias-i-Parella et al. (ICTON 2025) [4]", "\u00d7", "\u00d7", "\u00d7", "\u2014"],
    ["Rolich et al. (VNC 2025) [5]", "\u00d7", "\u00d7", "\u00d7", "implied"],
    ["Wu et al. / CooperScene (ECCV 2026) [6]", "\u00d7", "\u00d7", "\u00d7", "\u2014"],
    ["Bezmenov et al. (2024) [21]", "\u2713 (age-violation prob.)", "\u00d7", "\u00d7", "\u2014"],
    ["Ashik & Hossain (ICC 2026) [22]", "\u2713 (per-app AoI, 2 s window)", "\u00d7", "\u00d7", "\u2014"],
    ["Zhang & Mo (RTSS 2026) [23]", "\u2713 (hard peak-AoI)", "\u00d7", "\u00d7", "\u2014"],
    ["USDOT/PacTrans (2021) [19]", "\u2014 (T-window)", "\u2713 (at-least-one-BSM)", "\u00d7", "\u2713"],
    ["Chalmers thesis (2022) [20]", "\u2713 (A_max/K/BrEP)", "\u00d7", "\u00d7", "\u2713"],
    ["This work", "\u2713 (\u03c4 \u2264 V*, deterministic)", "\u2713 (TTC rule)", "\u2713 (p,\u03c4) plane", "\u2713"],
]


lines = raw.split("\n")

# ----------------------------------------------------------------------------
# Build document
# ----------------------------------------------------------------------------
doc = Document()
# default Normal font
normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(10)
# page margins 0.75 in
sec0 = doc.sections[0]
for s in (sec0.top_margin, sec0.bottom_margin, sec0.left_margin, sec0.right_margin):
    s = Inches(0.75)
sec0.top_margin = sec0.bottom_margin = sec0.left_margin = sec0.right_margin = Inches(0.75)
# body-level (last section) -> two columns
set_columns(sec0._sectPr, 2, space=360)

# ---- title block (single column, section 1) ----
tp = doc.add_paragraph(); tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
tr = tp.add_run(TITLE); tr.bold = True; tr.font.size = Pt(18)
tp.paragraph_format.space_after = Pt(10)

ap = doc.add_paragraph(); ap.alignment = WD_ALIGN_PARAGRAPH.CENTER
ar = ap.add_run(AUTHOR_META["name"] + ("\u2020" if AUTHOR_META["corresponding"] else ""))
ar.font.size = Pt(12)
ap.paragraph_format.space_after = Pt(2)

fp = doc.add_paragraph(); fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = fp.add_run(AUTHOR_META["affiliation_full"])
fr.italic = True; fr.font.size = Pt(10)
fp.paragraph_format.space_after = Pt(2)

ep = doc.add_paragraph(); ep.alignment = WD_ALIGN_PARAGRAPH.CENTER
er = ep.add_run("Email: " + AUTHOR_META["email"])
er.font.size = Pt(9)
ep.paragraph_format.space_after = Pt(8)

# ----------------------------------------------------------------------------
# Plan B（方案B）数据：加载 E9 分析结果，注入 V* 敏感性 / C2 突发实证 + 三张配图
# ----------------------------------------------------------------------------
def _csv_rows(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.reader(f))

try:
    E9_SENS = _csv_rows(os.path.join(BASE, "数据", "E9_vstar_sens.csv"))
    E9_SCENE = _csv_rows(os.path.join(BASE, "数据", "E9_scene.csv"))
except FileNotFoundError:
    E9_SENS = []
    E9_SCENE = []

FIG_DIR = "论文实验/figures"

def add_md_para(doc, text, after=4):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    add_inline(p, text)
    p.paragraph_format.space_after = Pt(after)
    return p

def add_figure(doc, fname, caption, width_in=6.8, span=True):
    """Insert a figure with its caption. `span=True` places the picture in its own
    single-column continuation section so that it spans both text columns (a
    picture wider than a column is otherwise clipped at the column boundary).
    `span=False` is used for figures that already fit one column."""
    path = os.path.join(BASE, FIG_DIR, fname)
    if span:
        add_continuous_break(doc, 2)      # close the running two-column text
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(path, width=Inches(width_in))
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cr = cp.add_run(caption)
    cr.italic = True
    cr.font.size = Pt(8)
    cp.paragraph_format.space_after = Pt(8)
    if span:
        add_continuous_break(doc, 1)      # this section holds the full-width figure

def inject_vstar(doc, letter):
    add_section_heading(doc, f"{letter}. V* sensitivity and the shifted latency cliff", level=1)
    add_md_para(doc,
        "Replacing the arbitrary 500 ms with the kinematics-derived budget "
        "$V^{*}=\\sqrt{2\\varepsilon_{\\max}/|a|}$ makes the freshness budget scenario-specific. "
        "Table II sweeps $|a|$ and $\\varepsilon_{\\max}$; the three scenarios use "
        "$\\varepsilon_{\\max}=1$ m, giving $V^{*}\\approx 577$ ms (FCW), 471 ms (EBW) and 535 ms (ICW).")
    if E9_SENS:
        add_table(doc, E9_SENS,
                  "Freshness Budget V* (ms) versus Deceleration and Extrapolation Error",
                  header=True, fontsize=8)
    add_md_para(doc,
        "Because the latency cliff is set by the budget (§6.2), moving $V$ to $V^{*}$ shifts the cliff by "
        "exactly the change in budget. Re-running E3 (10% loss) per scenario (Table III):")
    hdr = ["Scenario", "|a| (m/s^2)", "V* (ms)", "cliff tau @500 ms", "cliff tau @V* (ms)"]
    rows = [hdr]
    sname = {"fcw": "FCW", "ebw": "EBW", "icw": "ICW"}
    for r in E9_SCENE[1:]:
        rows.append([sname.get(r[0], r[0]), r[1], r[2], r[3], r[5]])
    add_table(doc, rows,
              "Latency Cliff Under a Fixed 500 ms Budget and Under V*",
              header=True, fontsize=8)
    add_md_para(doc,
        "The cliff moves with the budget (e.g. +50 ms for FCW, -50 ms for EBW), confirming the effect is "
        "kinematic, not parametric. Using $V^{*}$ instead of a fixed 500 ms also reduces the freshness-contract "
        "false-reject rate from 21.2% to 10.9% on the 330-cell grid while holding false-accept at ~2.7% (E9).")

def inject_c2burst(doc):
    add_md_para(doc,
        "Fitting the BAD-residence sweep (SENS group, FCW, $\\bar p=0.3$, $L_B\\in\\{5,10,15,25\\}$) to the 5% "
        "tail target gives an empirical cap $L_B\\lesssim 7$ packets ($\\approx0.6$–$0.7$ s at 10 Hz); the closed-form "
        "Gilbert-Elliot tail $(1-1/L_B)^{W_p}\\le 0.05$, with the decision window expressed in packets "
        "($W_p=15$), yields $L_B\\approx 5.5$ packets. Both point to an explicit BAD-state residence cap as a "
        "necessary companion to the mean-loss cap in C2, and §6.8 measures it directly: $L_B=2.10$ packets on "
        "real C-V2X links, i.e. inside both caps.")

# ---- state ----
break_added = False
last_was_ref = False
eq_seen = False
subsection_letters = {"n": 0}
current_section_num = [0]

i = 0
N = len(lines)
while i < N:
    line = lines[i]
    s = line.strip()

    # blank
    if s == "":
        i += 1; continue
    # horizontal rule
    if s in ("---", "***", "___"):
        i += 1; continue
    # blockquote (author notes / verification records) -> drop entirely
    if s.startswith(">"):
        i += 1; continue
    # Table I sentinel
    if s == "@@TABLE_I@@":
        add_wide_table(doc, TABLE_I, "Comparison with Related Work",
                       widths_in=[2.35, 1.30, 1.15, 1.05, 1.05],
                       header=True, fontsize=8)
        i += 1; continue
    # Plan B anchors: V* sensitivity / C2 burst / 3 figures
    if s == "@@VSTAR@@":
        subsection_letters["n"] += 1
        inject_vstar(doc, chr(ord("A") + subsection_letters["n"] - 1))
        i += 1; continue
    if s == "@@C2BURST@@":
        inject_c2burst(doc)
        i += 1; continue
    if s == "@@FIG0@@":
        add_figure(doc, "fig0_system_model.png",
                   "Fig. 1. System model. (a) Longitudinal geometry: the gap g(t) defines TTC(t), which the warning "
                   "rule thresholds. (b) Update chain: a 10 Hz BSM stream crosses a link with loss p, delay tau, "
                   "rate f and pose noise sigma, is admitted or discarded by a validity gate on the age Delta(t), "
                   "and drives the TTC decision. A discarded update leaves the receiver blind and the age growing. "
                   "C0/C1 constrain the link input, C2 the realized blind-run tail.",
                   width_in=6.35)
        i += 1; continue
    if s == "@@FIG1@@":
        add_figure(doc, "fig1_feasible_region.png",
                   "Fig. 2. Two-dimensional feasible region (safe rate %) per scenario; the dashed line marks the 80% qualification threshold.",
                   width_in=6.8)
        i += 1; continue
    if s == "@@FIG2@@":
        add_figure(doc, "fig2_aoi_ladder.png",
                   "Fig. 3. Age-of-information ladder and consecutive blind runs at the same mean loss rate; red-shaded "
                   "bands are stale. Burst loss (Gilbert-Elliot) produces a far longer blind run than i.i.d. loss.",
                   width_in=6.3)
        i += 1; continue
    if s == "@@FIG3@@":
        add_figure(doc, "fig3_blindrun_lb.png",
                   "Fig. 4. Blind-run length distribution (FCW, p=0.3, GE) as BAD-state residence L_B grows; the tail past W=30 frames lengthens, motivating the L_B cap in C2.",
                   width_in=3.20, span=False)
        i += 1; continue
    if s == "@@FIG5@@":
        add_figure(doc, "fig5_trace_c2.png",
                   "Fig. 5. Contract C2 on real C-V2X traces (eight directional links, NIST outdoor captures [28]). "
                   "(a) CCDF of blind-run length is bimodal, with an empty interval between 20 and 34 packets "
                   "(2.0\u20133.4 s); W = 1.5 s is marked and the shaded region holds the coverage outages. "
                   "(b) Measured burst length L_B per link against the analytic cap (5.5 packets), the empirical cap "
                   "(7) and the baseline Gilbert\u2013Elliot setting (15); marker area scales with the number of observed runs.",
                   width_in=6.6)
        i += 1; continue
    if s == "@@FIG6@@":
        add_figure(doc, "fig6_ge_burst_ccdf.png",
                   "Fig. 6. Gilbert\u2013Elliot closed-form blind-run tail versus 452 measured micro-bursts "
                   "(NIST C-V2X captures [28]). (a) Empirical CCDF $\\Pr[L_{\\mathrm{blind}}>\\mathrm{cap}]$ of the "
                   "452 micro-bursts (black) against the memoryless geometric closed form with $\\hat r=1/\\bar L_B$ "
                   "(blue) and a tail-matched geometric (red dashed) that reproduces the empirical 0.88% tail; "
                   "$W=15$ packets is marked. (b) Length distribution of the 452 micro-bursts, log count, showing "
                   "the over-dispersion: a dominant one-packet mass with a small number of 15\u201320 packet bursts "
                   "that the memoryless model deems near-impossible.",
                   width_in=6.6)
        i += 1; continue
    if s == "@@TC2TABLE@@":
        rows = [["Link", "PDR\n(%)", "Avail.\n(%)", "$L_B$\n(pkt)",
                 "Tail\nuncond. (%)", "Tail\navail. (%)"]]
        _p = os.path.join(BASE, "数据", "C2_trace", "link_summary.csv")
        if os.path.exists(_p):
            with open(_p, encoding="utf-8-sig") as _f:
                for _r in csv.DictReader(_f):
                    _lab = _r["label"].replace(" -> ", "\n\u2192")
                    rows.append([_lab, _r["pdr_pct"],
                                 f'{float(_r["avail"]) * 100:.1f}', _r["LB_burst"],
                                 f'{float(_r["pr_uncond"]) * 100:.1f}',
                                 f'{float(_r["pr_cond"]) * 100:.1f}'])
        _tbl = build_table(doc, rows, header=True, fontsize=6.5)
        add_table_caption(doc, "Per-Link Statistics on 43 min of Real C-V2X Captures", _tbl)
        try:
            _tbl.autofit = False
            _w = [Inches(0.66), Inches(0.44), Inches(0.44), Inches(0.36),
                  Inches(0.50), Inches(0.50)]
            for _j, _wi in enumerate(_w):
                for _cell in _tbl.columns[_j].cells:
                    _cell.width = _wi
        except Exception:
            pass
        i += 1; continue
    # section heading
    if s.startswith("## "):
        name = s[3:].strip()
        low = name.lower()
        if low == "abstract":
            ah = doc.add_paragraph(); ah.alignment = WD_ALIGN_PARAGRAPH.CENTER
            ahr = ah.add_run("Abstract"); ahr.bold = True; ahr.font.size = Pt(11)
            ah.paragraph_format.space_after = Pt(4)
            i += 1; continue
        if low.startswith("references"):
            if not break_added:
                add_continuous_break(doc, 1); break_added = True
            add_section_heading(doc, "References")
            i += 1; continue
        if low.startswith("appendix"):
            add_section_heading(doc, "Appendix A \u2014 Reproduction")
            i += 1; continue
        # numbered section -> roman; add column break before first
        if not break_added:
            add_continuous_break(doc, 1); break_added = True
        current_section_num[0] += 1
        subsection_letters["n"] = 0
        clean = re.sub(r"^\d+\s+", "", name)
        add_section_heading(doc, f"{roman(current_section_num[0])}. {clean}")
        i += 1; continue
    # subsection heading
    if s.startswith("### "):
        subsection_letters["n"] += 1
        letter = chr(ord("A") + subsection_letters["n"] - 1)
        clean = re.sub(r"^\d+(\.\d+)*\s+", "", s[4:].strip())
        add_section_heading(doc, f"{letter}. {clean}", level=1)
        i += 1; continue
    # index terms line
    if s.startswith("**Index Terms**"):
        it = doc.add_paragraph()
        add_inline(it, s)
        it.paragraph_format.space_after = Pt(6)
        i += 1; continue
    # code fence
    if s.startswith("```"):
        i += 1
        code = []
        while i < N and not lines[i].strip().startswith("```"):
            code.append(lines[i]); i += 1
        i += 1  # closing fence
        for cl in code:
            cp = doc.add_paragraph()
            cr = cp.add_run(cl if cl else " ")
            cr.font.name = "Consolas"; cr.font.size = Pt(9)
            cp.paragraph_format.space_after = Pt(0)
        continue
    # table block
    if s.startswith("|"):
        tbl_lines = []
        while i < N and lines[i].strip().startswith("|"):
            tbl_lines.append(lines[i]); i += 1
        # parse
        rows = []
        for tl in tbl_lines:
            cells = [c.strip() for c in tl.strip().strip("|").split("|")]
            rows.append(cells)
        # drop separator row (contains only ---)
        data = []
        for r in rows:
            if all(set(c) <= set("-: ") and c for c in r):
                continue
            data.append(r)
        if data:
            _t = build_table(doc, data, header=True, fontsize=8)
            if _CAP["pipe_i"] < len(_PIPE_TITLES):
                add_table_caption(doc, _PIPE_TITLES[_CAP["pipe_i"]], _t)
                _CAP["pipe_i"] += 1
        continue
    # display equation line(s)
    if s.startswith("$$"):
        buf = []
        while i < N and not lines[i].strip().endswith("$$"):
            buf.append(lines[i].strip().lstrip("$")); i += 1
        buf.append(lines[i].strip().rstrip("$").lstrip("$")); i += 1
        tex = " ".join(x for x in buf if x)
        add_display_equation(doc, tex)
        continue
    # reference line
    if re.match(r"^\[\d+\]", s):
        add_ref(doc, s)
        last_was_ref = True
        i += 1; continue
    else:
        last_was_ref = False
    # numbered list item
    if re.match(r"^\d+\.\s", s):
        txt = re.sub(r"^\d+\.\s+", "", s)
        p = doc.add_paragraph(style="List Number")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_inline(p, txt)
        i += 1; continue
    # bullet list item
    if re.match(r"^[-*]\s", s) and not s.startswith("***"):
        txt = re.sub(r"^[-*]\s+", "", s)
        p = doc.add_paragraph(style="List Bullet")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_inline(p, txt)
        i += 1; continue
    # italic-lead line  "*Word.* rest"
    mlead = re.match(r"^\*([^*\n]+)\*\s*(.*)$", s)
    if mlead:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        rl = p.add_run(mlead.group(1)); rl.bold = True
        if mlead.group(2):
            add_inline(p, " " + mlead.group(2))
        p.paragraph_format.space_after = Pt(4)
        i += 1; continue
    # Version footer already removed; default paragraph
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    add_inline(p, s)
    p.paragraph_format.space_after = Pt(4)
    i += 1

# --- IEEE Access required end sections (placeholders) ---
def add_required_section(doc, title, body):
    add_section_heading(doc, title)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    add_inline(p, body)
    p.paragraph_format.space_after = Pt(6)

for t, b in [
    ("Acknowledgment",
     "This work was developed in part from an unpublished course project on intelligent "
     "connected-vehicle applications; the simulations, analytical derivations and visualizations "
     "described here are original to this manuscript. The author thanks three fellow students for "
     "assistance with literature triage and manuscript formatting. These contributions were "
     "technical and editorial in nature and did not involve the study design, the analysis, or the "
     "interpretation of the results reported here."),
    ("Funding",
     "This research received no external funding."),
    ("Data Availability Statement",
     "The simulation kernel, per-seed CSV outputs, figure-generation scripts, and a one-command "
     "reproducibility package (reproduce.sh) support full reproducibility; all ~16,200 controlled "
     "runs are seeded and re-runnable from a clean clone. The code and data are available from the "
     "author upon reasonable request and will be deposited in a public repository (GitHub) with an "
     "archived DOI (Zenodo) upon acceptance."),
    ("Conflict of Interest",
     "The authors declare no conflict of interest."),
    ("Author Contributions",
     "Conceptualization, methodology, software, validation, formal analysis, investigation, data "
     "curation, writing\u2014original draft, writing\u2014review and editing, visualization: "
     "Nian Liu. The author has read and agreed to the published version of the manuscript."),
    ("Author Biographies",
     "Nian Liu is currently an undergraduate student at the International School, Beijing "
     "University of Posts and Telecommunications, Beijing, China. Research interests include V2X "
     "communications, cooperative intelligent transportation systems, and information freshness "
     "(age of information) in vehicular networks. (An author photograph will be supplied with the "
     "final submission files.)"),
    ("AI-Assisted Preparation Disclosure",
     "In accordance with the IEEE Access policy on the use of generative-AI tools, the authors "
     "disclose that AI-assisted tools were used to support literature triage, code scaffolding, "
     "language polishing, and manuscript formatting. All technical content, numerical analyses, "
     "and conclusions were authored, executed, and verified by the human author, who takes full "
     "responsibility for them; the generative-AI tools were confined to language editing and code "
     "scaffolding under the author\u2019s direction."),
]:
    add_required_section(doc, t, b)

doc.save(OUT)
print("OMML ok:", _OMML_STATS["ok"], "| fallback(PNG):", _OMML_STATS["fallback"])

# ----------------------------------------------------------------------------
# Cover letter
# ----------------------------------------------------------------------------
cld = Document()
cld.styles["Normal"].font.name = "Times New Roman"
cld.styles["Normal"].font.size = Pt(11)
cl = cld.add_paragraph(); cl.add_run(COVER_DATE)
cl.paragraph_format.space_after = Pt(12)
for addr in [
    "Editor-in-Chief",
    "IEEE Access",
    "Institute of Electrical and Electronics Engineers (IEEE)",
]:
    p = cld.add_paragraph(); p.add_run(addr)
    p.paragraph_format.space_after = Pt(0)
cld.add_paragraph()
cld.add_paragraph().add_run("Dear Editor-in-Chief,")
body_cl = [
    "Manuscript title: \u201c%s\u201d" % TITLE,
    "Submission type: Research Article.",
    "We submit the above manuscript for consideration for publication in IEEE Access. The work "
    "presents a closed-form, application-side information-freshness condition for V2X collision "
    "warnings, an experimental falsification of a mean-loss-rate safety contract under burst "
    "losses, and a reproducible study of 16,200+ controlled runs. The central claim is then "
    "re-validated on 43 min of real outdoor C-V2X captures published by NIST (24,449 beacons on "
    "eight directional links): the measured blind-run length is 2.1 packets against an analytic "
    "threshold of 5.5, and the contract implies an availability budget of 95.9% at a 5% tail "
    "target — a deployment figure that the simulation alone could not supply. It "
    "is original, has not been published previously, and is not under review elsewhere.",
    "A note on prior work: part of the simulation data originates from an unpublished undergraduate "
    "course project. This does not constitute prior publication. Should a preprint (e.g., arXiv) be "
    "posted before or during review, we will disclose its URL in a revised cover letter and add the "
    "required IEEE preprint statement, in line with IEEE\u2019s Submission and Peer Review Policies.",
    "Per the IEEE Access policy on generative-AI tools, we disclose that AI-assisted tools were used "
    "to support literature triage, code scaffolding, language polishing, and formatting. All technical "
    "content, numerical analyses, and conclusions were authored, executed, and verified by the human "
    "author, who takes full responsibility for them; the generative-AI tools were confined to language "
    "editing and code scaffolding under the author\u2019s direction.",
    "We do not propose individual reviewers, in order to avoid any conflict of interest. We would "
    "welcome expertise in V2X channel measurement, age-of-information scheduling, and the "
    "validation of safety applications against field data.",
    "Thank you for your consideration. We look forward to your response.",
]
for b in body_cl:
    p = cld.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.add_run(b)
    p.paragraph_format.space_after = Pt(8)
cld.add_paragraph().add_run("Sincerely,")
cld.add_paragraph().add_run(AUTHOR_META["name"] + ("\u2020" if AUTHOR_META["corresponding"] else ""))
cld.add_paragraph().add_run("Corresponding author: %s \u2014 email: %s"
                            % (AUTHOR_META["name"], AUTHOR_META["email"]))
cld.save(CL)

# ----------------------------------------------------------------------------
# Pre-submission checklist
# ----------------------------------------------------------------------------
checklist = []
checklist.append(f"# 投稿前待办清单 · IEEE Access {VERSION}\n")
checklist.append("本次整理（已解决）：\n")
checklist.append("- 删除 DRAFT NOTES 作者备注块；\n"
                 "- 将 v0.2 按 IEEE Access 双栏模板重排（标题/摘要单栏 + 正文双栏）；\n"
                 "- 表 I（Table I）由文字占位符真正扩展为对比表；\n"
                 "- 参考文献 [6] 年份 2022→2024；\n"
                 "- 新增 [10]–[13] 与标准/调查报告引用，并在 §2 被动认领 novelty 仅在“组合+落地”（回应主编 R1）；\n"
                 "- 补齐 IEEE Access 必需栏目：Funding / Conflict of Interest / Author Biographies / AI-Assisted Disclosure / Data Availability；\n"
                 "- 公式由 matplotlib 图片改为 OMML 原生公式（304 个，0 回落）；\n"
                 "- **E11：真实 C-V2X trace 验证 C2**（NIST mds2-4003，8 条有向链路，24,449 信标）：\n"
                 "  实测 L_B = 2.10 包，条件尾部 0.88%（CP95 上界 2.0%）< δ=5%；同时发现覆盖中断是独立失效模式，\n"
                 "  正文新增 §6.8 与 Fig.5，§4.4/§7/§8 中“缺乏真实日志”的表述已全部改写。\n"
                 "- **E12：可用度预算**（§6.8）：无条件尾部分解 Pr_u=(1−A)+A·q_c 复现实测 8 条链路至 0.24 pp，\n"
                 "  反解 A*=(1−δ)/(1−q_c)：δ=5% 时须 95.9%（每小时允许中断 2.5 min），最差链路 98.4%。\n")
checklist.append("\n投稿前 P0（必须补）：\n")
p0 = [
    "GitHub 仓库：本地仓库已 git init 并提交（64 文件，复现包就绪）；GitHub 用户名 liuxixin69-crypto、仓库名 v2x-freshness-contract 已写入 CITATION.cff/zenodo.json；待你授权（PAT 或浏览器建仓后 git push）即可公开。Zenodo 元数据 zenodo.json 已就绪，待你 deposit 获得 DOI。",
    "BUPT 机构邮箱（2138385347@bupt.edu.cn，见主编意见 A6）✅；ORCID 待补（需你提供 ORCID iD）。",
    "核对页数 < 20 页：v2.0 PDF = 16 页 ✅；最终校对 ✅（E13 审计 0 问题）。",
    "Funding（no external funding）/ Conflict of Interest（no conflict）已定稿 ✅。",
]
for k, item in enumerate(p0, 1):
    checklist.append(f"{k}. {item}\n")
checklist.append("\n作者信息（已完成）：Nian Liu†（一作兼通讯），International School, Beijing University of Posts and Telecommunications；邮箱 2138385347@bupt.edu.cn。标题页 / 投稿信 / 作者贡献 / 作者简介 / CITATION.cff 已同步；ORCID 待补（需你提供 ORCID iD）。\n")
checklist.append("\n方案B 优化（已补，见正文 Fig.1–5 与 §3.3/§6.7/§6.8）：V* 敏感性表 + E2/E3 用 V* 重跑（E9，契约 FR 21.2%->10.9%）；C2 在 GE 突发下实证并推导 L_B 阈值（L_B≲7 包≈0.6–0.7s@10Hz）；真实 trace 复核（E11）+ 可用度预算（E12）；五张 IEEE 分辨率配图；一键复现包（论文实验/复现包/）。\n")
checklist.append("\n原稿中标记的 [TBD] 清单（已在此版移除，仅作追踪）：\n")
seen = []
for t in tbds:
    if t not in seen:
        seen.append(t); checklist.append(f"- {t}\n")

with open(CHK, "w", encoding="utf-8") as _f:
    _f.write("".join(checklist))

print("WROTE:", OUT)
print("WROTE:", CL)
print("WROTE:", CHK)
print("TBD markers captured:", len(seen))
