# -*- coding: utf-8 -*-
"""方案 B⑥：导出 IEEE 分辨率配图（300 dpi）到 论文实验/figures/。
Fig1: 三场景可行域热力图 (safe-rate) + 80% 等高线
Fig2: AoI 阶梯 / 失明段时序 (i.i.d. vs GE)，解释 C2 的 L_blind
Fig3: SENS 组盲段长度分布随 L_B 增长，佐证 L_B 阈值
"""
import os, csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(BASE, "论文实验", "figures")
os.makedirs(FIG, exist_ok=True)
DPI = 300
plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "figure.dpi": DPI,
                     "savefig.bbox": "tight", "axes.titlesize": 9})

# ----------------------------------------------------------------------------
# Fig1: 可行域热力图（来自 E6 同款网格）
# ----------------------------------------------------------------------------
def load_heatmap():
    path = os.path.join(BASE, "数据", "预警可行域_heatmap.csv")
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    scenes = ["fcw", "ebw", "icw"]
    losses = sorted({int(r["loss_pct"]) for r in rows})
    taus = sorted({int(r["tau_ms"]) for r in rows})
    grids = {}
    for sc in scenes:
        g = np.full((len(losses), len(taus)), np.nan)
        for r in rows:
            if r["scene"] != sc:
                continue
            i = losses.index(int(r["loss_pct"]))
            j = taus.index(int(r["tau_ms"]))
            g[i, j] = float(r["safe_rate_pct"])
        grids[sc] = g
    return scenes, losses, taus, grids

scenes, losses, taus, grids = load_heatmap()
scene_names = {"fcw": "FCW", "ebw": "EBW", "icw": "ICW"}

fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.8), sharey=True)
for ax, sc in zip(axes, scenes):
    g = grids[sc]
    ext = [min(taus), max(taus), min(losses), max(losses)]
    im = ax.imshow(g, origin="lower", aspect="auto", extent=ext,
                   cmap="RdYlGn", vmin=0, vmax=100)
    ax.contour(taus, losses, g, levels=[80], colors="black", linewidths=1.2, linestyles="--")
    ax.set_title(scene_names[sc], pad=4)
    ax.set_xlabel("one-way delay τ (ms)")
    if ax is axes[0]:
        ax.set_ylabel("packet loss (%)")
    ax.set_xticks([0, 250, 500, 750, 1000])
    ax.set_yticks([0, 20, 40, 60, 80])
    ax.tick_params(labelsize=7.5)
cbar = fig.colorbar(im, ax=axes, shrink=0.92, pad=0.02)
cbar.set_label("safe rate (%)", fontsize=8)
cbar.ax.tick_params(labelsize=7.5)
fig.savefig(os.path.join(FIG, "fig1_feasible_region.png"))
plt.close(fig)

# ----------------------------------------------------------------------------
# Fig2: AoI ladder（i.i.d. vs GE），解释 L_blind
# ----------------------------------------------------------------------------
def aoi_trace(model, p=0.3, tau_ms=100, V_ms=500, T_ms=100, Tmax=6.0, seed=12345, L_B=15):
    dt = 0.05
    T = T_ms / 1000.0
    tau = tau_ms / 1000.0
    V = V_ms / 1000.0
    rng = np.random.default_rng(seed)
    arrivals = []  # (t_arr, t_s)
    if model == "iid":
        state = 0
    else:
        beta = 1.0 / L_B
        alpha = p / (L_B * (1 - p)) if p < 1 else 0
        piB = alpha / (alpha + beta) if (alpha + beta) > 0 else 0
        state = 1 if rng.random() < piB else 0
    k = 0
    t_s = 0.0
    while t_s <= Tmax + 0.5:
        if model == "iid":
            drop = rng.random() < p
        else:
            if state == 1:
                drop = True
                if rng.random() < beta:
                    state = 0
            else:
                drop = False
                if rng.random() < alpha:
                    state = 1
        if not drop:
            arrivals.append((t_s + tau, t_s))
        k += 1
        t_s = k * T
    arrivals.sort()
    n = int(round(Tmax / dt))
    ts = np.arange(n) * dt
    aoi = np.full(n, np.inf)
    ai = 0
    for i, t in enumerate(ts):
        while ai < len(arrivals) and arrivals[ai][0] <= t + 1e-9:
            ai += 1
        if ai > 0:
            aoi[i] = t - arrivals[ai - 1][1]
    blind = aoi > V
    return ts, aoi, blind, V

fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.2), sharex=True)
for ax, (model, title, seed) in zip(axes, [("iid", "i.i.d. loss (p=0.3)", 11),
                                             ("ge", "Gilbert-Elliot burst (p̄=0.3, L_B=15)", 22)]):
    ts, aoi, blind, V = aoi_trace(model, seed=seed)
    ax.plot(ts, np.minimum(aoi, 1.2), color="#1f77b4", lw=1.0, label="AoI")
    ax.axhline(V, color="red", ls="--", lw=1.0, label="freshness budget V=500 ms")
    for i in range(1, len(ts)):
        if blind[i]:
            ax.axvspan(ts[i] - 0.025, ts[i] + 0.025, color="red", alpha=0.18, lw=0)
    runs, cur = [], 0
    for b in blind:
        if b:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    if runs:
        mx = max(runs)
        ax.text(0.98, 0.92, f"longest blind run ≈ {mx*0.05:.1f} s", transform=ax.transAxes,
                ha="right", va="top", fontsize=8, color="darkred")
    ax.set_ylim(0, 1.25)
    ax.set_ylabel("age (s)")
    ax.set_title(title, pad=4)
    ax.legend(loc="upper left", fontsize=7, framealpha=0.8)
    ax.tick_params(labelsize=7.5)
axes[-1].set_xlabel("time (s)")
fig.savefig(os.path.join(FIG, "fig2_aoi_ladder.png"))
plt.close(fig)

# ----------------------------------------------------------------------------
# Fig3: 盲段长度分布随 L_B 增长（SENS 组，佐证 L_B 阈值）
# ----------------------------------------------------------------------------
def load_burstruns():
    path = os.path.join(BASE, "数据", "E8_baseline_burst_runs.csv")
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

rows = load_burstruns()
W = 30
lbs = [5, 10, 15, 25]
fig, ax = plt.subplots(figsize=(3.6, 3.0))
colors = {"5": "#1f77b4", "10": "#ff7f0e", "15": "#2ca02c", "25": "#d62728"}
for lb in lbs:
    xs, ys = [], []
    for r in rows:
        if r["group"] == "SENS" and r["scene"] == "fcw" and r["model"] == "ge" \
           and r["loss_target_pct"] == "30.0" and r["mean_bad_run_pkts"] == str(lb):
            xs.append(int(r["blind_run_frames"]))
            ys.append(int(r["run_count"]))
    if not xs:
        continue
    xs = np.array(xs); ys = np.array(ys, dtype=float)
    ys = ys / ys.sum()
    ax.plot(xs, ys, marker="o", ms=3, color=colors[str(lb)], label=f"L_B={lb}")
ax.axvline(W, color="black", ls="--", lw=1.0)
ax.text(W + 0.5, ax.get_ylim()[1] * 0.9, "W=30", fontsize=7)
ax.set_xlabel("blind-run length (frames)")
ax.set_ylabel("fraction of runs")
ax.set_title("Blind-run tail grows with BAD-state residence $L_B$\n(FCW, $\\bar{p}=0.3$, GE)", fontsize=9)
ax.legend(fontsize=7, title="BAD residence", title_fontsize=7)
ax.tick_params(labelsize=7.5)
fig.savefig(os.path.join(FIG, "fig3_blindrun_lb.png"))
plt.close(fig)

# ----------------------------------------------------------------------------
# Fig0: 系统模型示意 —— (a) 纵向几何与预警决策 (b) 更新链路 / 有效性闸门 / 契约
# ----------------------------------------------------------------------------
from matplotlib.patches import FancyBboxPatch

fig = plt.figure(figsize=(7.0, 3.95))
gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.02], hspace=0.26)

# ---- (a) 纵向几何 ----------------------------------------------------------
ax = fig.add_subplot(gs[0])
ax.set_xlim(-14, 74)
ax.set_ylim(-0.62, 1.80)
ax.axis("off")

ax.add_patch(plt.Rectangle((-14, 0.0), 88, 0.62, facecolor="#f2f2f2",
                           edgecolor="none", zorder=0))
for yy in (0.0, 0.62):
    ax.plot([-14, 74], [yy, yy], color="0.45", lw=0.9, zorder=1)
ax.plot([-14, 74], [0.31, 0.31], color="0.72", lw=0.8, ls=(0, (6, 5)), zorder=1)

for x0 in (-4.5, 55.0):
    ax.add_patch(FancyBboxPatch((x0, 0.06), 4.5, 0.50,
                                boxstyle="round,pad=0,rounding_size=0.10",
                                facecolor="#dbe3ee", edgecolor="black",
                                lw=0.9, zorder=3))

ax.text(-2.25, -0.14, "host vehicle", ha="center", va="top", fontsize=7.4)
ax.text(-2.25, -0.33, r"$v_H=16.67\ \mathrm{m\,s^{-1}}$", ha="center",
        va="top", fontsize=7.0)
ax.text(57.25, -0.14, "remote vehicle", ha="center", va="top", fontsize=7.4)
ax.text(57.25, -0.33,
        r"$v_0=11.11\ \mathrm{m\,s^{-1}}$,  $a=-6\ \mathrm{m\,s^{-2}}$",
        ha="center", va="top", fontsize=7.0)

# 间隙尺寸线
for xx in (0.0, 55.0):
    ax.plot([xx, xx], [0.62, 1.24], ls=":", color="0.55", lw=0.7, zorder=2)
ax.annotate("", xy=(55, 1.24), xytext=(0, 1.24),
            arrowprops=dict(arrowstyle="<|-|>", lw=0.9, color="black",
                            shrinkA=0, shrinkB=0, mutation_scale=7))
ax.text(27.5, 1.30, r"$g(t)=x_R(t)-x_H(t)-L$   ($L=4.5$ m)",
        ha="center", va="bottom", fontsize=7.2)

# 速度箭头
ax.annotate("", xy=(6.5, 0.94), xytext=(-4.5, 0.94),
            arrowprops=dict(arrowstyle="-|>", lw=1.1, color="0.15",
                            shrinkA=0, shrinkB=0, mutation_scale=9))
ax.text(1.0, 1.00, r"$v_H$", fontsize=7.6)
ax.annotate("", xy=(63.0, 0.94), xytext=(55.0, 0.94),
            arrowprops=dict(arrowstyle="-|>", lw=1.1, color="0.15",
                            shrinkA=0, shrinkB=0, mutation_scale=9))
ax.text(58.5, 1.00, r"$v_R(t)$", fontsize=7.6)

ax.text(74, 1.66, r"$\mathrm{TTC}(t)=g(t)\,/\,\left(v_H-v_R(t)\right)$",
        ha="right", va="center", fontsize=7.4)
ax.set_title("(a) Longitudinal geometry and the warning decision",
             fontsize=8.4, loc="left", pad=1)

# ---- (b) 更新链路 ----------------------------------------------------------
ax = fig.add_subplot(gs[1])
ax.set_xlim(0, 1)
ax.set_ylim(0, 0.99)
ax.axis("off")

boxes = [
    ("Remote vehicle", "BSM @ 10 Hz\nposition, speed"),
    ("C-V2X link", "loss $p$, delay $\\tau$\nrate $f$, noise $\\sigma$"),
    ("Validity gate", "$\\Delta(t)=t-u(t)$\nuse iff $\\Delta\\leq V$"),
    ("TTC rule", "warn: TTC $\\leq 3.5$ s\nemerg.: $\\leq 1.75$ s"),
    ("Outcome", "warn / miss /\nfalse alarm"),
]
bw, gap, yc, bh = 0.170, 0.035, 0.66, 0.50
step = bw + gap

for k, (head, body) in enumerate(boxes):
    x = k * step
    ax.add_patch(FancyBboxPatch((x, yc - bh / 2), bw, bh,
                                boxstyle="round,pad=0,rounding_size=0.012",
                                facecolor="white", edgecolor="black",
                                lw=0.9, zorder=3))
    ax.text(x + bw / 2, yc + 0.115, head, ha="center", va="center",
            fontsize=6.55, fontweight="bold", zorder=4)
    ax.text(x + bw / 2, yc - 0.075, body, ha="center", va="center",
            fontsize=6.0, zorder=4)
    if k < len(boxes) - 1:
        ax.annotate("", xy=((k + 1) * step, yc), xytext=(x + bw, yc),
                    arrowprops=dict(arrowstyle="-|>", lw=0.9, color="black",
                                    shrinkA=0, shrinkB=0, mutation_scale=7))

# 反馈：陈旧更新被丢弃 -> 无状态可用（说明文字只占左段，避免与竖线交叉）
xg = 2 * step + bw / 2
x1 = bw / 2
ax.plot([xg, xg], [yc - bh / 2, 0.165], ls="--", lw=0.8, color="0.35", zorder=2)
ax.plot([xg, x1], [0.165, 0.165], ls="--", lw=0.8, color="0.35", zorder=2)
ax.annotate("", xy=(x1, yc - bh / 2), xytext=(x1, 0.165),
            arrowprops=dict(arrowstyle="-|>", lw=0.8, color="0.35",
                            ls="--", shrinkA=0, shrinkB=0, mutation_scale=7))
ax.text((xg + x1) / 2 - 0.045, 0.205,
        "stale update discarded $\\Rightarrow$ receiver blind",
        ha="center", va="bottom", fontsize=6.1, style="italic", color="0.25")

ax.text(0.985, 0.042,
        "contracts:  C0  $\\tau\\leq V^{*}-\\epsilon$   ·   C1  mean $p$   ·   "
        "C2  $\\Pr[L_{\\mathrm{blind}}\\geq W]\\leq\\delta$",
        ha="right", va="center", fontsize=6.2, color="0.15",
        bbox=dict(boxstyle="round,pad=0.30", fc="#f4f4f4", ec="0.70", lw=0.6))

ax.set_title("(b) Update chain, validity gate, and warning decision",
             fontsize=8.4, loc="left", pad=1)

fig.savefig(os.path.join(FIG, "fig0_system_model.png"))
plt.close(fig)

print("已生成:")
for f in ["fig0_system_model.png", "fig1_feasible_region.png",
          "fig2_aoi_ladder.png", "fig3_blindrun_lb.png"]:
    p = os.path.join(FIG, f)
    print(f"  {f}  ({os.path.getsize(p)} bytes)")
