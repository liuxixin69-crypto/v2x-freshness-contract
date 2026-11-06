#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
投稿前终校审计（E13）— 只读，不改文件。

检查项
------
1. 数字一致性：同一量在摘要 / §1 / §6.x / §7 / §8 是否写成同一个值
2. 图表编号：正文引用顺序是否单调；是否先引用后出现；是否漏引
3. 交叉引用：所有 "§N.N" 指向的小节是否真实存在
4. 术语：blind run / outage / BAD residence 等的混用
5. 排版伪影：残留 LaTeX、双空格、标点前后空格、英文破折号
6. 摘要词数（IEEE Access 上限 250）

用法：python 代码/E13_audit.py
"""
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD = os.path.join(BASE, "论文", "期刊版_初稿_EN_v0.2.md")

issues = []


def bad(kind, detail):
    issues.append((kind, detail))


def main():
    s = open(MD, encoding="utf-8").read()
    builder = os.path.join(BASE, "代码", "build_submission_docx.py")
    BUILDER_SRC = open(builder, encoding="utf-8").read() if os.path.exists(builder) else ""
    # 去掉代码块，避免误报
    body = re.sub(r"```.*?```", "", s, flags=re.S)

    # ---------- 1. 数字一致性 ----------------------------------------
    print("=" * 74)
    print("1. 关键数字出现的每一处（人工比对是否同一个量）")
    print("=" * 74)
    KEY = {
        "misclassification 40.6%": r"40\.6",
        "freshness misjudgement 10.9%": r"10\.9",
        "false reject 91.8%": r"91\.8",
        "mean-loss cap 75.4%": r"75\.4",
        "analytic L_B 5.5": r"5\.5\b",
        "measured L_B 2.10": r"2\.10|2\.1 (?:packets|packet)",
        "conditional tail 0.88%": r"0\.88",
        "tail upper bound 2.0%": r"2\.0%",
        "availability 95.9%": r"95\.9",
        "worst-link availability 98.4%": r"98\.4",
        "beacons 24,449": r"24,449",
        "runs 16,200": r"16,200",
        "coverage share 28.0%": r"28\.0%",
        "E7 MAE 4.44": r"4\.44",
    }
    for name, pat in KEY.items():
        hits = [m.start() for m in re.finditer(pat, body)]
        ctx = []
        for h in hits:
            frag = body[max(0, h - 55):h + 55].replace("\n", " ")
            ctx.append(frag.strip())
        print(f"\n[{name}]  x{len(hits)}")
        for c in ctx[:6]:
            print(f"    …{c}…")
        if len(hits) == 0:
            bad("数字缺失", name)

    # ---------- 2. 图表编号 -------------------------------------------
    print("\n" + "=" * 74)
    print("2. 图表引用顺序")
    print("=" * 74)
    for kind, pat in [("Fig.", r"Fig\.\s*(\d+)")]:
        refs = []
        for m in re.finditer(pat, body):
            tok = m.group(1)
            val = int(tok)
            refs.append((m.start(), val, tok))
        seq = [v for _, v, _ in refs]
        print(f"\n{kind} 引用序列：{seq}")
        # 首次出现顺序是否 1,2,3,...
        first = []
        for v in seq:
            if v not in first:
                first.append(v)
        print(f"  首次出现顺序：{first}")
        if first != sorted(first):
            bad("图表引用乱序", f"{kind} 首次出现 {first}")
        # 跳号
        expected = list(range(1, max(seq) + 1)) if seq else []
        missing = [v for v in expected if v not in seq]
        if missing:
            bad("图表未被引用", f"{kind} {missing} 从未在正文出现")

    # ---------- 2b. 表标题与逐表引用 ------------------------------------
    import glob
    from docx import Document
    dx = sorted(f for f in glob.glob(os.path.join(BASE, "论文实验", "投稿版_IEEE_Access_v*.docx"))
                if "cover_letter" not in f)
    if dx:
        d = Document(dx[-1])
        labels, titles = [], []
        ps = d.paragraphs
        for i, p in enumerate(ps):
            t = p.text.strip()
            if t.startswith("TABLE "):
                labels.append(t.split()[1])
                titles.append(ps[i + 1].text.strip() if i + 1 < len(ps) else "")
        print(f"\n  {os.path.basename(dx[-1])}")
        print(f"  表数 {len(d.tables)}，带标题的表 {len(labels)}：{labels}")
        if len(labels) != len(d.tables):
            bad("表缺标题", f"{len(d.tables) - len(labels)} 张表无 TABLE 编号/标题")
        for lab, ti in zip(labels, titles):
            # 引用可能写在 md 里，也可能写在生成脚本的字符串里（如 §6.A 的表）
            cited = len(re.findall(r"Table\s+%s\b" % lab, body + BUILDER_SRC))
            print(f"    TABLE {lab:<5} 正文引用 {cited} 次 | {ti[:52]}")
            if cited == 0:
                bad("表未被正文引用", f"TABLE {lab}")
            if not ti:
                bad("表标题为空", f"TABLE {lab}")

    # ---------- 3. 交叉引用 -------------------------------------------
    print("\n" + "=" * 74)
    print("3. §N.N 交叉引用")
    print("=" * 74)
    heads = re.findall(r"^##\s*(\d+)\.?", body, re.M)
    secs = sorted(set(re.findall(r"^###\s*(\d+\.\d+)", body, re.M)))
    print(f"存在的一级节：{heads}")
    print(f"存在的二级节：{secs}")
    cited = sorted(set(re.findall(r"§(\d+\.\d+)", body)))
    dangling = [c for c in cited if c not in secs]
    print(f"被引用的二级节：{cited}")
    if dangling:
        bad("悬空引用", f"§{', §'.join(dangling)} 不存在")
        print(f"  !! 悬空：{dangling}")
    else:
        print("  OK 无悬空")

    # ---------- 4. 术语混用 -------------------------------------------
    print("\n" + "=" * 74)
    print("4. 术语出现次数")
    print("=" * 74)
    TERMS = ["blind run", "blind-run", "outage", "outage run", "blindness ratio",
             "BAD residence", "BAD-state residence", "staleness", "freshness budget",
             "information outage", "consecutive outage"]
    for t in TERMS:
        n = len(re.findall(re.escape(t), body, re.I))
        print(f"  {t:<24} {n}")
    # 英美拼写混用
    SPELL = [("behaviour", "behavior"), ("modelling", "modeling"),
             ("labelled", "labeled"), ("artefact", "artifact"),
             ("optimise", "optimize"), ("colour", "color")]
    mixed = [p for p in SPELL if re.search(p[0], body) and re.search(p[1], body)]
    if mixed:
        for a, b in mixed:
            bad("拼写混用", f"{a} / {b} 同时出现")
        print(f"  !! 英美拼写混用：{mixed}")
    else:
        print("  OK 拼写风格一致")

    # ---------- 5. 排版伪影 -------------------------------------------
    print("\n" + "=" * 74)
    print("5. 排版伪影")
    print("=" * 74)
    clean = "\n".join(l for l in body.split("\n") if not l.lstrip().startswith(">"))
    checks = {
        "残留 $ 未配对段落": None,
        "双空格": r"[^\s]  +[^\s]",
        "标点前空格": r"\s+[,.;:](\s|$)",
        "中文标点混入": r"[\u3001\u3002\uff0c\uff1b]",
        "连续三点以上": r"\.\.\.",
        "直引号 \"": r'"',
        "百分号前空格": r"\d %",
    }
    for name, pat in checks.items():
        if pat is None:
            continue
        hits = re.findall(pat, clean)
        if hits:
            print(f"  {name}: {len(hits)}")
            if name in ("中文标点混入", "双空格", "直引号 \""):
                for m in list(re.finditer(pat, clean))[:4]:
                    frag = clean[max(0, m.start() - 60):m.start() + 60].replace("\n", " ")
                    print(f"      …{frag}…")
        else:
            print(f"  {name}: 0")

    # ---------- 6. 摘要 -----------------------------------------------
    print("\n" + "=" * 74)
    print("6. 摘要")
    print("=" * 74)
    m = re.search(r"##\s*Abstract\s*\n(.*?)\n##", body, re.S)
    ab = m.group(1).strip()
    bare = re.sub(r"\$[^$]*\$", "X", ab)
    n = len(bare.split())
    print(f"  词数 {n}（上限 250）  {'OK' if n <= 250 else '!! 超限'}")
    if n > 250:
        bad("摘要超长", f"{n} 词")
    # 摘要里出现的数字，必须在正文里也出现
    nums = set(re.findall(r"\d+\.\d+%|\d[\d,]{2,}", ab))
    for x in sorted(nums):
        if x.replace("%", "") not in body.replace(ab, "").replace("\\%", ""):
            bad("摘要数字正文无对应", x)
            print(f"  !! 摘要独有数字：{x}")

    # ---------- 汇总 ---------------------------------------------------
    print("\n" + "=" * 74)
    if issues:
        print(f"发现 {len(issues)} 类问题：")
        for k, d in issues:
            print(f"  [{k}] {d}")
        return 1
    print("未发现结构性问题。")
    return 0


def rom2int(r):
    vals = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
            "VII": 7, "VIII": 8, "IX": 9, "X": 10}
    return vals.get(r, 0)


if __name__ == "__main__":
    sys.exit(main())
