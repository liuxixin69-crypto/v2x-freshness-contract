# -*- coding: utf-8 -*-
"""Fig.5 — 真实 C-V2X trace 上的 C2 检验（E11）。
(a) 失明段长度 CCDF（双峰：微突发 / 覆盖中断）
(b) 各链路实测突发长度 L_B 与三个阈值（解析 5.5 / 经验 7 / 基线 15）
"""
import os, csv, collections
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "数据", "C2_trace")
FIG = os.path.join(BASE, "论文实验", "figures")
DPI = 300
plt.rcParams.update({"font.size": 8, "axes.titlesize": 8.5, "figure.dpi": DPI,
                     "savefig.bbox": "tight"})

runs = list(csv.DictReader(open(os.path.join(OUT, "runs.csv"), encoding="utf-8-sig")))
summ = list(csv.DictReader(open(os.path.join(OUT, "link_summary.csv"), encoding="utf-8-sig")))
for r in runs:
    r["n_miss"] = int(r["n_miss"])
for s in summ:
    for k in ("LB_burst", "n_micro", "dur_s", "avail"):
        s[k] = float(s[k])

by = collections.defaultdict(list)
for r in runs:
    by[r["label"]].append(r["n_miss"])

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.85),
                               gridspec_kw={"width_ratios": [1.15, 1]})

# ---------------- (a) CCDF ----------------
xs_all = np.sort([r["n_miss"] for r in runs])
for lab, v in by.items():
    v = np.sort(np.array(v))
    ccdf = 1.0 - np.arange(len(v)) / len(v)
    ax1.step(v, ccdf, where="post", color="0.62", lw=0.7, alpha=0.9, zorder=1)
ccdf_all = 1.0 - np.arange(len(xs_all)) / len(xs_all)
ax1.step(xs_all, ccdf_all, where="post", color="black", lw=1.7, zorder=3,
         label="pooled, 8 links")
ax1.axvspan(25, 1000, color="0.90", zorder=0)
ax1.axvline(15, color="tab:red", ls="--", lw=1.2, zorder=4)
ax1.axvline(25, color="0.45", ls=":", lw=0.9, zorder=2)
ax1.text(16.5, 1.6e-3, r"$W$ = 1.5 s" + "\n(15 pkt)", color="tab:red", fontsize=7,
         ha="left", va="bottom")
ax1.text(250, 0.30, "coverage\noutages", color="0.35", fontsize=7, ha="center")
ax1.set_xscale("log")
ax1.set_yscale("log")
ax1.set_xlim(0.9, 900)
ax1.set_ylim(8e-4, 1.6)
ax1.set_xlabel("blind-run length $L_{\\mathrm{blind}}$ (packets)")
ax1.set_ylabel(r"$\Pr[L_{\mathrm{blind}} \geq x]$")
ax1.set_title("(a) measured blind-run CCDF")
ax1.legend(loc="lower left", fontsize=6.5, frameon=False)
ax1.tick_params(labelsize=7)

# ---------------- (b) L_B vs thresholds ----------------
summ_sorted = sorted(summ, key=lambda s: s["LB_burst"])
ys = np.arange(len(summ_sorted))
for y, s in zip(ys, summ_sorted):
    ax2.plot([1, s["LB_burst"]], [y, y], color="0.80", lw=0.8, zorder=1)
    ax2.scatter(s["LB_burst"], y, s=18 + 0.25 * s["n_micro"], color="tab:blue",
                zorder=3, edgecolor="white", linewidth=0.5)
for x, lab, c, ls in [(5.5, "analytic 5.5", "tab:blue", "--"),
                      (7.0, "empirical 7", "tab:orange", "-."),
                      (15.0, "baseline 15", "tab:red", ":")]:
    ax2.axvline(x, color=c, ls=ls, lw=1.1, zorder=2)
    ax2.text(x, len(ys) + 1.30, lab, color=c, fontsize=6.2, ha="center", va="top",
             rotation=90)
ax2.set_yticks(ys)
ax2.set_yticklabels([s["label"].replace(" -> ", "→") for s in summ_sorted], fontsize=6.5)
ax2.set_xscale("log")
ax2.set_xlim(0.8, 24)
ax2.set_ylim(-0.6, len(ys) + 1.5)
ax2.set_xticks([1, 2, 5, 10, 20])
ax2.set_xticklabels(["1", "2", "5", "10", "20"])
ax2.set_xlabel("measured burst length $L_B$ (packets)")
ax2.set_title("(b) burst length vs. contract thresholds")
ax2.tick_params(labelsize=7)
ax2.grid(axis="x", color="0.92", lw=0.6)

fig.tight_layout(pad=0.4)
out = os.path.join(FIG, "fig5_trace_c2.png")
fig.savefig(out)
print("saved", out)
