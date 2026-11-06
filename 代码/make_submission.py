# -*- coding: utf-8 -*-
"""
生成「可提交」的期末材料包。

做三件事：
  1. 把期末论文里已回官方 PDF 核实的 3GPP 引用改成正式条目（主库同步）；
  2. 把 Markdown 论文转成规范排版的 .docx 与打印用 .html（后者由 Edge 转 PDF）；
  3. 组装只含交付物的目录，并写提交清单。

运行： python 代码/make_submission.py     （在项目根目录）
依赖： python-docx
"""
import os, re, shutil, html as htmllib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "提交包", "期末汇报_提交包_20261105")
SRC_MD = os.path.join(ROOT, "论文", "期末论文_v1.md")

# ---------- 1. 主库：核实过的 3GPP 引用改成正式条目 ----------
md = open(SRC_MD, encoding="utf-8").read()
reps = [
 ("3GPP TS 22.185 对 V2V 业务规定端到端最大时延 100 ms，并对预碰撞感知给出 20 ms 的建议值 `[待核]`。",
  "3GPP TS 22.185 的 [R-5.2.1-001] 规定 V2V/V2P 端到端最大时延 100 ms，[R-5.2.1-002] 对预碰撞感知给出 20 ms 建议值；[R-5.2.4-001] 还要求通信范围足以给出约 4 s 的驾驶员反应时间——这条正是本文用「预警提前量」而非单纯投递率评价安全性的标准依据。"),
 ("每 UE 每秒最多 10 条消息 `[待核]`。",
  "每 UE 每秒最多 10 条消息（[R-5.2.3-001]）。条文号与数值已回 ETSI 官方 PDF（ETSI TS 122 185 V15.0.0）核实。"),
 ("[3] 3GPP. TS 22.185: Enhancement of 3GPP support for V2X scenarios[S]. `[待核：版本号与条款号]`",
  "[3] 3GPP. TS 22.185 V15.0.0: Service requirements for V2X services (Release 15)[S]. ETSI TS 122 185, 2018. 条文 [R-5.2.1-001/002]、[R-5.2.3-001]、[R-5.2.4-001]."),
]
for old, new in reps:
    if md.count(old) == 1:
        md = md.replace(old, new)
    elif new in md:
        pass  # 已写入，允许重复运行
    else:
        raise RuntimeError("3GPP 引用锚点缺失: " + old[:30])
open(SRC_MD, "w", encoding="utf-8").write(md)
print("[1/3] 3GPP 引用已回官方条文核实并写入主库")

# ---------- 2. 提交版正文清洗 ----------
body = md
# 内部使用说明不进提交正文
body = re.sub(r"^> \*\*使用说明（不进正文）\*\*.*\n", "", body, flags=re.M)
# 提交版去掉内部 [待核] 标记（未核实条目清单写在提交清单里）
body = re.sub(r"`\[待核[^\]]*\]`", "", body)
body = re.sub(r"\[待核\]", "", body)
# 版本记录不是论文正文内容，移除整节
body = re.sub(r"\n### 版本记录\n[\s\S]*?$", "\n", body)

def latex_to_text(s):
    """把行内/块级 LaTeX 转成可读的 Unicode 文本（避免提交版出现源码）。"""
    m = {
        r"\tau": "τ", r"\varepsilon": "ε", r"\Delta": "Δ", r"\le": "≤", r"\ge": "≥",
        r"\times": "×", r"\approx": "≈", r"\sum": "Σ", r"\mathbb{E}": "E",
        r"\min": "min", r"\max": "max", r"\quad": " ", r"\,": " ", r"\;": " ",
        r"\frac": "", r"\left": "", r"\right": "", r"\ge": "≥", r"\sim": "~",
        r"\mathbb{P}": "P", r"\cdot": "·", r"\infty": "∞", r"\epsilon": "ε",
    }
    for k, v in m.items():
        s = s.replace(k, v)
    s = re.sub(r"\\(?:mathbf|mathrm|text)\{([^}]*)\}", r"\1", s)
    s = re.sub(r"_\{([^}]*)\}", r"_\1", s)
    s = re.sub(r"\^\{([^}]*)\}", r"^\1", s)
    s = s.replace("{", "").replace("}", "").replace("$", "").replace("&", "")
    return s.strip()

def inline(s):
    """markdown 行内标记 -> [(text, bold, code)]"""
    s = latex_to_text(s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = s.replace("`", "")
    return s

# ---------- 3. 解析成块 ----------
def parse(text):
    lines = text.split("\n")
    blocks, i = [], 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip():
            i += 1; continue
        if ln.strip() == "---":
            i += 1; continue
        if ln.startswith("$$") and ln.count("$$") >= 2:
            blocks.append(("formula", latex_to_text(ln.replace("$$", ""))))
            i += 1; continue
        if ln.startswith("$$"):
            buf = [ln[2:]]
            i += 1
            while i < len(lines) and "$$" not in lines[i]:
                buf.append(lines[i]); i += 1
            if i < len(lines):
                buf.append(lines[i].replace("$$", "")); i += 1
            blocks.append(("formula", latex_to_text(" ".join(buf))))
            continue
        if ln.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in row if c):
                    tbl.append([inline(c) for c in row])
                i += 1
            blocks.append(("table", tbl))
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            blocks.append(("h%d" % (len(m.group(1)) - 1), inline(m.group(2))))
            i += 1; continue
        if ln.lstrip().startswith("> "):
            blocks.append(("quote", inline(ln.lstrip()[2:])))
            i += 1; continue
        if re.match(r"^\s*[-*]\s+", ln) or re.match(r"^\s*\d+\.\s+", ln):
            txt = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", ln)
            blocks.append(("list", inline(txt)))
            i += 1; continue
        # 普通段落：合并连续非空行
        buf = [ln.strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i].rstrip()
            if (not nxt.strip() or nxt.strip() == "---" or nxt.startswith("#") or
                nxt.startswith("|") or nxt.startswith("$$") or nxt.lstrip().startswith("> ") or
                re.match(r"^\s*[-*]\s+", nxt) or re.match(r"^\s*\d+\.\s+", nxt)):
                break
            buf.append(nxt.strip()); i += 1
        blocks.append(("p", inline(" ".join(buf))))
    return blocks

blocks = parse(body)
print("[2/3] 解析正文块 %d 个（标题 %d / 表格 %d / 公式 %d）" % (
    len(blocks), sum(1 for b in blocks if b[0].startswith("h")),
    sum(1 for b in blocks if b[0] == "table"),
    sum(1 for b in blocks if b[0] == "formula")))

# ---------- 4. 生成 docx ----------
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
for a in ("top_margin", "bottom_margin"): setattr(sec, a, Cm(2.5))
for a in ("left_margin", "right_margin"): setattr(sec, a, Cm(2.6))

st = doc.styles["Normal"]
st.font.name = "Times New Roman"
st.font.size = Pt(12)
st._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
st.paragraph_format.line_spacing = 1.5
st.paragraph_format.space_after = Pt(0)

def set_font(run, east="宋体", size=12, bold=False, color=None):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east)
    if color: run.font.color.rgb = RGBColor(*color)

def add_p(text, kind="p"):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    if kind == "title":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.space_before, pf.space_after = Pt(6), Pt(14)
        set_font(p.add_run(text), "黑体", 18, True)
    elif kind == "h0":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.space_before, pf.space_after = Pt(2), Pt(16)
        set_font(p.add_run(text), "楷体", 13)
    elif kind == "h1":
        pf.space_before, pf.space_after = Pt(16), Pt(8)
        set_font(p.add_run(text), "黑体", 15, True)
    elif kind == "h2":
        pf.space_before, pf.space_after = Pt(11), Pt(5)
        set_font(p.add_run(text), "黑体", 13, True)
    elif kind == "h3":
        pf.space_before, pf.space_after = Pt(8), Pt(4)
        set_font(p.add_run(text), "黑体", 12, True)
    elif kind == "quote":
        pf.left_indent = Cm(0.8); pf.space_after = Pt(6)
        set_font(p.add_run(text), "楷体", 10.5, color=(90, 90, 90))
    elif kind == "formula":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.space_before, pf.space_after = Pt(6), Pt(6)
        set_font(p.add_run("  " + text + "  "), "Cambria Math", 11)
    elif kind == "list":
        pf.left_indent = Cm(0.8); pf.first_line_indent = Cm(-0.35)
        pf.space_after = Pt(2)
        set_font(p.add_run("· " + text), "宋体", 12)
    else:
        pf.first_line_indent = Cm(0.85)
        pf.space_after = Pt(3)
        set_font(p.add_run(text), "宋体", 12)
    return p

first_h1 = True
for kind, val in blocks:
    if kind == "h0": add_p(val, "title")
    elif kind == "h1": add_p(val, "h0" if first_h1 else "h1"); first_h1 = False
    elif kind in ("h2", "h3"): add_p(val, kind)
    elif kind == "table":
        if not val: continue
        ncol = max(len(r) for r in val)
        t = doc.add_table(rows=len(val), cols=ncol)
        t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for ri, row in enumerate(val):
            for ci in range(ncol):
                cell = t.cell(ri, ci)
                cell.text = ""
                para = cell.paragraphs[0]
                para.paragraph_format.space_after = Pt(0)
                para.paragraph_format.line_spacing = 1.15
                set_font(para.add_run(row[ci] if ci < len(row) else ""),
                         "宋体", 9, bold=(ri == 0))
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
    else:
        add_p(val, kind)

os.makedirs(os.path.join(PKG, "01_期末论文"), exist_ok=True)
docx_path = os.path.join(PKG, "01_期末论文", "期末论文_通信退化条件下V2X碰撞预警有效性评测.docx")
doc.save(docx_path)

# ---------- 5. 生成打印用 HTML ----------
def esc(s): return htmllib.escape(s)
out = []
first_h1_html = True
for kind, val in blocks:
    if kind == "h0": out.append('<h1 class="title">%s</h1>' % esc(val))
    elif kind == "h1":
        if first_h1_html:
            out.append('<h2 class="sub">%s</h2>' % esc(val)); first_h1_html = False
        else:
            out.append('<h3>%s</h3>' % esc(val))
    elif kind == "h2": out.append('<h3>%s</h3>' % esc(val))
    elif kind == "h3": out.append('<h4>%s</h4>' % esc(val))
    elif kind == "p": out.append('<p>%s</p>' % esc(val))
    elif kind == "quote": out.append('<blockquote>%s</blockquote>' % esc(val))
    elif kind == "formula": out.append('<div class="formula">%s</div>' % esc(val))
    elif kind == "list": out.append('<p class="li">· %s</p>' % esc(val))
    elif kind == "table":
        if not val: continue
        out.append("<table>")
        for ri, row in enumerate(val):
            out.append("<tr>" + "".join("<%s>%s</%s>" % ("th" if ri == 0 else "td", esc(c), "th" if ri == 0 else "td") for c in row) + "</tr>")
        out.append("</table>")

HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>期末论文</title><style>
@page { size: A4; margin: 22mm 20mm; }
body { font-family: "SimSun","Songti SC","Microsoft YaHei",serif; font-size: 11.5pt; line-height: 1.75; color:#111; }
h1.title { font-family:"SimHei","Microsoft YaHei",sans-serif; font-size:19pt; text-align:center; margin:0 0 6pt; }
h2.sub { font-family:"KaiTi","Microsoft YaHei",sans-serif; font-size:12.5pt; text-align:center; font-weight:normal; color:#444; margin:0 0 22pt; }
h3 { font-family:"SimHei","Microsoft YaHei",sans-serif; font-size:14pt; margin:18pt 0 8pt; page-break-after:avoid; }
h4 { font-family:"SimHei","Microsoft YaHei",sans-serif; font-size:12pt; margin:12pt 0 5pt; page-break-after:avoid; }
p { text-indent: 2em; margin:0 0 5pt; text-align:justify; }
p.li { text-indent:0; padding-left:1.6em; }
blockquote { font-size:10pt; color:#666; border-left:3px solid #ccc; padding-left:12px; margin:8pt 0; }
.formula { text-align:center; font-family:"Cambria Math",Georgia,serif; font-size:11pt; margin:9pt 0; }
table { border-collapse:collapse; width:100%; font-size:9pt; margin:9pt 0 12pt; page-break-inside:avoid; }
th,td { border:1px solid #999; padding:4px 6px; text-align:left; }
th { background:#eef2f7; font-weight:bold; }
</style></head><body>
""" + "\n".join(out) + "\n</body></html>"
html_path = os.path.join(PKG, "01_期末论文", "_print.html")
open(html_path, "w", encoding="utf-8").write(HTML)
print("[3/3] 已生成 docx 与打印用 html")

# ---------- 6. 组装只含交付物的目录 ----------
def cp(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

C = lambda *a: os.path.join(ROOT, *a)
cp(C("汇报", "期末汇报_雏形v0.2.pptx"), os.path.join(PKG, "02_汇报PPT", "期末汇报.pptx"))
cp(C("产品原型", "v2x_预警死线_v0.2.html"), os.path.join(PKG, "03_演示系统", "v2x_预警死线.html"))
for f in ["实验明细_runs.csv", "实验汇总_summary.csv", "预警可行域_heatmap.csv",
          "E7_解析模型校验.csv", "关键数字.md", "E7_结论.md", "可视化数据校验.md", "README.md"]:
    cp(C("数据", f), os.path.join(PKG, "04_数据与复现", f))
for f in ["run_experiments.js", "gen_heatmap.js", "derive_bound.js",
          "build_prototype.js", "v0.2.template.html"]:
    cp(C("代码", f), os.path.join(PKG, "04_数据与复现", "源码", f))
cp(C("汇报", "build_ppt.py"), os.path.join(PKG, "04_数据与复现", "源码", "build_ppt.py"))
cp(C("汇报", "展示脚本与问答预案_v0.1.md"), os.path.join(PKG, "05_展示辅助", "展示脚本与问答预案.md"))

MANIFEST = """# 期末汇报提交清单

打包日期：2026-11-05　｜　课程：智能网联驾驶技术及应用　｜　题目：通信退化条件下 V2X 碰撞预警有效性评测与「预警死线」可视化

## 一句话

**01 是论文、02 是汇报 PPT、03 是现场演示、04 是支撑前三者全部数字的可复现证据。** 本包只放交付物；选题调研、方案迭代、README、旧版本、半成品等过程文件一律不进包，留在主库 `03_项目与工具/综合项目/智能驾驶研究`。

## 目录

| 路径 | 内容 | 是否必须提交 |
|---|---|---|
| `01_期末论文/*.docx` | 论文正文（可编辑，Word） | 二选一或都交 |
| `01_期末论文/*.pdf` | 论文正文（定版阅读用） | 二选一或都交 |
| `02_汇报PPT/期末汇报.pptx` | 16 页汇报，含 2 张原生折线图与产品截图 | 是 |
| `03_演示系统/v2x_预警死线.html` | **双击即开的离线单文件**，四视图 + 一键导览 | 建议随包交，现场演示用 |
| `04_数据与复现/` | 原始 CSV、关键数字、全部仿真源码 | 证明工作量，老师要时给 |
| `05_展示辅助/展示脚本与问答预案.md` | 12 分钟口播分配、逐页锚点、答辩问答 | 自用，不必提交 |

演示系统不需要安装任何东西，不联网、不依赖 GPU。汇报前请**在汇报用的电脑上双击试一次**。

## 数据口径（防止现场对不上）

- 论文表格的数字来自 `代码/run_experiments.js`（E1–E5）、`gen_heatmap.js`（E6）、`derive_bound.js`（E7），共 6+ 组实验、逐种子 CSV 全在包里。
- 原型**默认滑块组合**是单次演示，与论文批量实验的固定参数不同，数值不会逐位相同；这不是错误，口径已写在 `04_数据与复现/README.md`。
- E6 固定 `loss=10%` 的列与 E3 逐点相等、固定 `tau=100 ms` 的行与 E2 逐点相等，21/21 交叉点校验通过。
- **5.9 节修正了初稿口径**：硬边界是「单程时延 τ ≤ BSM 有效期 V」，早先写的「有效期 + 100 ms」是扫描步长造成的离散表现，答辩若被问到此点请按 5.9 节回答。

## 提交前必须做的三件事

1. **核对参考文献**。3GPP TS 22.185 的条文号、数值已回 ETSI 官方 PDF 核实；其余来自检索摘要的条目（CooperScene、SCORPION、LR-V2X、arXiv 编号等）在提交版里去掉了内部 `[待核]` 标记，但**尚未逐条回原文核验**，请对照主库 `文献/引用核实表_v0.1.md` 逐条确认，核不上就删，不要带着编造的卷期号交上去。
2. **按老师模板补格式**：作者/学号/班级、封面、字数、行距、参考文献格式、是否要查重报告。本包用的是通用学术论文排版，不是课程指定模板。
3. **确认提交物清单与截止时间**，尤其是「代码、数据、演示是否都要交」「个人还是小组署名」。当前按「单人先行完成、之后找队友」准备，署名栏留空。

## 一条命令复现全部数字

在本包 `04_数据与复现/源码/` 的上一级目录结构下（需主库同款目录布局），或直接在主库根目录执行：

```
node 代码/run_experiments.js      # E1–E5
node 代码/gen_heatmap.js          # E6
node 代码/derive_bound.js         # E7 解析判据
python 汇报/build_ppt.py          # 重新生成 PPT
```

`03_演示系统` 的源码模板是 `04_数据与复现/源码/v0.2.template.html` + `build_prototype.js`；**改原型请改模板再构建，不要直接改产物**。

## 已知局限（写进论文第 7 章，答辩主动说比被问出来好）

纯运动学一维仿真、三个课程级场景、BSM 有效期 500 ms 为设计参数而非标准规定值、丢包假设独立同分布、无实车/无真实链路 trace、ICW 为等效一维。结论只能表述为「受控退化下的趋势」，不能外推实车。
"""
open(os.path.join(PKG, "00_提交清单与说明.md"), "w", encoding="utf-8").write(MANIFEST)
print("已组装提交目录：", PKG)
