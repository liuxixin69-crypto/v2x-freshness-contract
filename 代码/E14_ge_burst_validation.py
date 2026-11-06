# -*- coding: utf-8 -*-
"""E14 — GE 模型下 burst 长度闭式解的推导，并用真实 trace 的 452 个微突发验证。

闭式解：在 Gilbert-Elliot 模型里，BAD 停留长度（一次失明段丢失的连续包数）L_B
服从几何分布，均值 = 1/r，尾概率有闭式
    P(L_B > cap) = (1 - r)^cap = (1 - 1/L_B)^cap.
本脚本：
  1) 从 数据/C2_trace/runs.csv 取出 §6.8 隔离出的 452 个微突发（n_miss < 25 包）；
  2) 计算经验 CCDF：P(L_B > cap)，cap = 1..24；
  3) 由实测均值 L_B=2.10 反推 r̂ = 1/2.10，得到闭式 CCDF；
  4) 用经验尾部在 cap=15（W=1.5s）反解“尾匹配” r_tail，量化真实突发的过离散；
  5) 生成 Fig.6（CCDF 对比 + 直方图），写出 E14_ge_validation.{csv,md}。
"""
import os, csv, math, collections
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(BASE, "数据", "C2_trace", "runs.csv")
FIG = os.path.join(BASE, "论文实验", "figures")
DPI = 300

# 契约参数（与 §4.4 / E11 一致）
T_BSM = 0.10
W_S = 1.5
W_PKT = round(W_S / T_BSM)            # 15 包
T_COV_PKT = 25                        # 微突发/覆盖中断分界（2.5 s）
DELTA = 0.05

plt.rcParams.update({"font.size": 8, "axes.titlesize": 8.5, "figure.dpi": DPI,
                     "savefig.bbox": "tight", "font.family": "serif"})

# ---------------- 读取微突发 ----------------
rows = list(csv.DictReader(open(RUNS, encoding="utf-8-sig")))
for r in rows:
    r["n_miss"] = int(r["n_miss"])
micro = [r["n_miss"] for r in rows if r["n_miss"] < T_COV_PKT]
N = len(micro)
assert N == 452, "微突发数应为 452，实得 %d" % N

xs = np.array(sorted(micro), dtype=float)
mean_LB = float(xs.mean())
r_hat = 1.0 / mean_LB                                  # 由均值反推回归率
print("N_micro =", N, " mean L_B = %.4f" % mean_LB, " r_hat = %.4f" % r_hat)

# ---------------- 经验 CCDF: P(L_B > cap) ----------------
caps = np.arange(1, 25)
emp_ccdf = np.array([(xs > c).mean() for c in caps])    # P(n_miss > cap)

# ---------------- 闭式 CCDF（r_hat） ----------------
cf_ccdf = np.array([(1.0 - r_hat) ** c for c in caps])

# ---------------- 经验尾部在 cap=15 反解“尾匹配” r_tail ----------------
k_win = int((xs >= W_PKT).sum())                        # 达到窗口的微突发数（包级口径）
emp_at_W = k_win / N                                    # 经验尾部 @15 包
# 解 (1 - r_tail)^W_PKT = emp_at_W  ->  r_tail = 1 - emp_at_W^(1/W_PKT)
r_tail = 1.0 - emp_at_W ** (1.0 / W_PKT)
mean_tail = 1.0 / r_tail
print("k>=W(15pkt)=%d  emp@W=%.5f  r_tail=%.4f  mean_tail=%.3f"
      % (k_win, emp_at_W, r_tail, mean_tail))

# 闭式 @15 包（r_hat）
cf_at_W = (1.0 - r_hat) ** W_PKT
print("closed-form @W=%.5f (%.4g%%)" % (cf_at_W, cf_at_W * 100))

ratio = emp_at_W / cf_at_W if cf_at_W > 0 else float("inf")
print("emp / closed-form = %.1f x" % ratio)

# 解析阈值：解 (1 - 1/L_B)^W_PKT <= DELTA  ->  L_B <= 1/(1-DELTA^(1/W_PKT))
LB_cap = 1.0 / (1.0 - DELTA ** (1.0 / W_PKT))
print("analytic L_B cap (delta=0.05) = %.3f packets" % LB_cap)

# ---------------- 写 CSV / MD ----------------
out_csv = os.path.join(BASE, "数据", "C2_trace", "E14_ge_validation.csv")
with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["cap_pkt", "emp_P_LB_gt_cap", "closedform_P_LB_gt_cap_rhat"])
    for c, e, cf in zip(caps, emp_ccdf, cf_ccdf):
        w.writerow([int(c), "%.6e" % e, "%.6e" % cf])

out_md = os.path.join(BASE, "数据", "C2_trace", "E14_ge_validation.md")
with open(out_md, "w", encoding="utf-8") as f:
    f.write("# E14 — GE 闭式解 vs 452 个实测微突发\n\n")
    f.write("微突发数 N = %d，实测均值 L_B = %.2f 包，r_hat = 1/L_B = %.4f\n\n" % (N, mean_LB, r_hat))
    f.write("闭式：P(L_B > cap) = (1 - r)^cap = (1 - 1/L_B)^cap\n\n")
    f.write("- 闭式 @ W=15 包：P = (%.4f)^15 = %.3e (%.4g%%)\n" % (1 - r_hat, cf_at_W, cf_at_W * 100))
    f.write("- 经验尾部 @ W（gap_s>=1.5s 口径）：4/452 = 0.88%%（CP95 上界 2.0%%）\n")
    f.write("- 经验尾部 @ W（包级口径 n_miss>=15）：%d/452 = %.2f%%\n" % (k_win, emp_at_W * 100))
    f.write("- 经验/闭式 = %.0f 倍（真实突发比无记忆几何重尾）\n" % ratio)
    f.write("- 若用经验尾部反解尾匹配 r_tail = %.4f -> 均长 %.2f 包（远高于实测 2.10）\n" % (r_tail, mean_tail))
    f.write("- 解析阈值 L_B <= %.2f 包（delta=0.05, W_p=15）\n" % LB_cap)

# ---------------- Fig.6 ----------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.95),
                               gridspec_kw={"width_ratios": [1.18, 1]})

# (a) CCDF 经验 vs 闭式 vs 尾匹配
ax1.step(caps, emp_ccdf, where="post", color="black", lw=1.8, zorder=4,
         label="measured (452 bursts)")
ax1.step(caps, cf_ccdf, where="post", color="tab:blue", lw=1.4, ls="-", zorder=3,
         label="closed form, $\\hat r=1/\\bar L_B$")
cf_tail = np.array([(1.0 - r_tail) ** c for c in caps])
ax1.step(caps, cf_tail, where="post", color="tab:red", lw=1.2, ls="--", zorder=2,
         label="tail-matched")
ax1.axvline(W_PKT, color="tab:orange", ls=":", lw=1.3, zorder=1)
ax1.text(W_PKT + 0.4, 2.0e-1, "$W$=15 pkt", color="tab:orange", fontsize=7, va="center")
ax1.set_yscale("log")
ax1.set_xlim(0.5, 24.5)
ax1.set_ylim(8e-4, 1.4)
ax1.set_xlabel("blind-run length cap (packets)")
ax1.set_ylabel(r"$\Pr[L_{\mathrm{blind}} > \mathrm{cap}]$")
ax1.set_title("(a) measured vs. closed-form blind-run tail")
ax1.legend(loc="upper left", fontsize=6.3, frameon=True, framealpha=1.0,
           edgecolor="white", handlelength=2.0, labelspacing=0.32)
ax1.tick_params(labelsize=7)
ax1.grid(axis="y", color="0.92", lw=0.5)

# (b) 微突发长度直方图（过离散：绝大多数 1 包，少数长突发）
bins = np.arange(0.5, 22.5, 1.0)
ax2.hist(xs, bins=bins, color="tab:blue", edgecolor="white", linewidth=0.4)
ax2.set_yscale("log")
ax2.axvline(W_PKT, color="tab:orange", ls=":", lw=1.3)
ax2.set_xlim(0.5, 21)
ax2.set_ylim(0.7, 400)
ax2.set_xlabel("micro-burst length (packets)")
ax2.set_ylabel("count (log)")
ax2.set_title("(b) length distribution of 452 micro-bursts")
ax2.tick_params(labelsize=7)
ax2.grid(axis="y", color="0.92", lw=0.5)

fig.tight_layout(pad=0.4)
out_png = os.path.join(FIG, "fig6_ge_burst_ccdf.png")
fig.savefig(out_png)
print("saved", out_png)
