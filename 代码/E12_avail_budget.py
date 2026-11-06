#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
E12 — Availability budget implied by the C2 tail contract.

Idea
----
The E11 trace showed that the unconditional tail Pr[L_blind >= W] is dominated
by coverage outages, while the tail conditioned on link availability is small.
C2 was therefore restated as a conditional contract.  That leaves a question the
paper previously answered only qualitatively ("availability is a deployment
requirement"): *how much* availability is required?

Because every observed coverage outage (>= 3.4 s) is far longer than the window
W = 1.5 s, each outage necessarily produces at least one violating window.  The
unconditional tail therefore decomposes as

    Pr_u = (1 - A) * 1 + A * q_c          (A = availability, q_c = conditional tail)

and requiring Pr_u <= delta gives the availability budget

    A* = (1 - delta) / (1 - q_c).

This script checks the decomposition against the measured per-link numbers and
tabulates A* over delta and q_c.

Outputs
-------
数据/C2_trace/E12_avail_budget.csv
数据/C2_trace/E12_avail_budget.md
"""
import csv
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE = os.path.join(BASE, "数据", "C2_trace")

DELTAS = [0.10, 0.05, 0.02, 0.01]


def load_links():
    with open(os.path.join(TRACE, "link_summary.csv"), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def a_star(delta, q_c):
    """Availability required for Pr_u <= delta."""
    return (1.0 - delta) / (1.0 - q_c)


def main():
    links = load_links()

    # ---- 1. validate the decomposition on measured data -------------------
    print("=" * 78)
    print("A. Decomposition check:  Pr_u  ?=  (1-A) + A*q_c")
    print("=" * 78)
    print(f"{'link':<16}{'A':>7}{'q_c %':>7}{'Pr_u meas %':>13}"
          f"{'Pr_u model %':>14}{'err pp':>8}")
    errs = []
    for r in links:
        A = float(r["avail"])
        qc = float(r["frac_cond"])
        pu = float(r["frac_uncond"])
        model = (1.0 - A) + A * qc
        err = (model - pu) * 100
        errs.append(abs(err))
        print(f"{r['label']:<16}{A:>7.3f}{qc * 100:>7.2f}{pu * 100:>13.2f}"
              f"{model * 100:>14.2f}{err:>8.2f}")
    print(f"\nmax |error| = {max(errs):.2f} pp  (identity holds by construction when "
          f"outage runs are longer than W)")

    # ---- 2. conditional tail, two definitions -----------------------------
    # (a) run-based:  fraction of blind RUNS that reach W  (E11 headline, 0.88%)
    # (b) time-based: fraction of AVAILABLE TIME spent in runs >= W (0.30%)
    # The decomposition in part A matches (b) exactly, but we carry (a) into the
    # budget because it is the larger of the two and therefore conservative.
    n_micro = sum(int(r["n_micro"]) for r in links)
    k_micro = sum(int(r["k_micro_geW"]) for r in links)
    q_run = k_micro / n_micro
    q_run_worst = max(float(r["pr_cond"]) for r in links)
    worst_lbl = max(links, key=lambda r: float(r["pr_cond"]))["label"]

    tot_sent = sum(int(r["n_sent"]) for r in links)
    q_time = sum(float(r["frac_cond"]) * int(r["n_sent"]) for r in links) / tot_sent

    print(f"\nconditional tail, run-based  q = {k_micro}/{n_micro} = {q_run * 100:.2f}%"
          f"  (worst link {q_run_worst * 100:.2f}%, {worst_lbl})")
    print(f"conditional tail, time-based q = {q_time * 100:.2f}%"
          f"   <-- the one the identity in part A satisfies")
    print(f"budget uses the run-based value (larger, hence conservative)")

    pooled = q_run
    worst = q_run_worst

    # ---- 3. availability budget -------------------------------------------
    rows = []
    print("\n" + "=" * 78)
    print("B. Availability budget  A* = (1-delta)/(1-q_c)")
    print("=" * 78)
    print(f"{'delta':>7}{'A* (pooled)':>14}{'outage/h':>11}"
          f"{'A* (worst)':>13}{'outage/h':>11}")
    for d in DELTAS:
        a_p = a_star(d, pooled)
        a_w = a_star(d, worst)
        rows.append([f"{d * 100:.0f}", f"{a_p * 100:.2f}", f"{(1 - a_p) * 60:.2f}",
                     f"{a_w * 100:.2f}", f"{(1 - a_w) * 60:.2f}"])
        print(f"{d * 100:>6.0f}%{a_p * 100:>13.2f}%{(1 - a_p) * 60:>10.2f}m"
              f"{a_w * 100:>12.2f}%{(1 - a_w) * 60:>10.2f}m")

    # ---- 4. per-link verdict at delta = 5% --------------------------------
    d0 = 0.05
    print("\n" + "=" * 78)
    print(f"C. Per-link: measured A vs required A* at delta = {d0:.0%}")
    print("=" * 78)
    print(f"{'link':<16}{'A meas':>9}{'A* req':>9}{'gap pp':>8}{'verdict':>10}")
    for r in links:
        A = float(r["avail"])
        qc = float(r["frac_cond"])
        need = a_star(d0, qc)
        gap = (A - need) * 100
        print(f"{r['label']:<16}{A * 100:>8.1f}%{need * 100:>8.1f}%"
              f"{gap:>8.1f}{'PASS' if gap >= 0 else 'FAIL':>10}")

    # ---- 5. write ---------------------------------------------------------
    csv_path = os.path.join(TRACE, "E12_avail_budget.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["delta_pct", "A_star_pooled_pct", "allowed_outage_min_per_h",
                    "A_star_worst_pct", "allowed_outage_min_per_h_worst"])
        w.writerows(rows)

    md = []
    md.append("# E12 — 由 C2 尾部契约反推的可用度预算\n")
    md.append("## 方法与前提\n")
    md.append("C2 为条件契约 $\\Pr[L_{\\mathrm{blind}}\\ge W\\mid \\text{link available}]\\le\\delta$。"
              "要让**无条件**违约率也守住 $\\delta$，需要链路可用度 $A$ 满足\n")
    md.append("$$\\Pr\\nolimits_u=(1-A)+A\\,q_c\\ \\le\\ \\delta"
              "\\quad\\Longrightarrow\\quad A^{*}=\\frac{1-\\delta}{1-q_c}$$\n")
    md.append("前提是每次覆盖中断本身的时长都超过 $W$，从而必产生违约窗口。"
              "E11 实测中断段最短 3.4 s，$W=1.5$ s，前提成立。\n")
    md.append("## 分解式的实测校验\n")
    md.append("| 链路 | A | $q_c$ (%) | $\\Pr_u$ 实测 (%) | $\\Pr_u$ 模型 (%) | 误差 (pp) |")
    md.append("|---|---|---|---|---|---|")
    for r in links:
        A = float(r["avail"]); qc = float(r["frac_cond"]); pu = float(r["frac_uncond"])
        md.append(f"| {r['label']} | {A:.3f} | {qc*100:.2f} | {pu*100:.2f} | "
                  f"{((1-A)+A*qc)*100:.2f} | {(((1-A)+A*qc)-pu)*100:+.2f} |")
    md.append(f"\n最大误差 {max(errs):.2f} pp。\n")
    md.append("## 可用度预算\n")
    md.append(f"$q_c$ 有两个口径：**按盲段条数** {q_run*100:.2f}%"
              f"（{k_micro}/{n_micro} 条突发达 $W$，为 E11 的口径），"
              f"**按可用时间内的时间占比** {q_time*100:.2f}%（分解式严格成立的那个）。"
              f"预算取前者（数值更大，保守）；最差链路按条数为 {worst*100:.2f}%（{worst_lbl}）。\n")
    md.append("| $\\delta$ | $A^{*}$ (pooled) | 允许中断 | $A^{*}$ (worst) | 允许中断 |")
    md.append("|---|---|---|---|---|")
    for row in rows:
        md.append(f"| {row[0]}% | {row[1]}% | {row[2]} min/h | {row[3]}% | {row[4]} min/h |")
    md.append("\n## 逐链路判定（$\\delta=5\\%$）\n")
    md.append("| 链路 | $A$ 实测 | $A^{*}$ 需求 | 余量 (pp) | 判定 |")
    md.append("|---|---|---|---|---|")
    for r in links:
        A = float(r["avail"]); need = a_star(d0, float(r["pr_cond"]))
        gap = (A - need) * 100
        md.append(f"| {r['label']} | {A*100:.1f}% | {need*100:.1f}% | {gap:+.1f} | "
                  f"{'✅ 通过' if gap >= 0 else '❌ 未达'} |")
    md.append("\n## 结论\n")
    md.append(f"1. 在 $\\delta=5\\%$、$q_c={q_run*100:.2f}\\%$ 下，链路可用度须达 **{rows[1][1]}%**"
              f"（每小时允许中断 {rows[1][2]} 分钟）；最差链路须达 {rows[1][3]}%。\n")
    md.append("2. 该数据集 8 条链路实测可用度 55.9%–100%，即互操作测试的部署密度"
              "**不足以**支撑无条件 5% 尾部——这解释了为何 5 条链路无条件违约，"
              "也说明 C2 必须写成条件契约。\n")
    md.append("3. 预算随 $\\delta$ 收紧极快：$\\delta=2\\%$ 时须 "
              f"{rows[2][1]}%，$\\delta=1\\%$ 时须 {rows[3][1]}%。"
              "因此 $\\delta\\le2\\%$ 在真实部署中只能靠近连续覆盖实现，"
              "实用取值应落在 5% 一档。\n")
    md_path = os.path.join(TRACE, "E12_avail_budget.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"\n写出 {os.path.relpath(csv_path, BASE)}")
    print(f"写出 {os.path.relpath(md_path, BASE)}")


if __name__ == "__main__":
    main()
