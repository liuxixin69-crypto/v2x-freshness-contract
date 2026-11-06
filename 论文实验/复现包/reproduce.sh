#!/usr/bin/env bash
# ============================================================================
# 一键复现脚本 — 复现包 v2（覆盖论文 §3.3 / §6.5 / §6.7 / §6.8 与 Fig.1-5）
#
# 从干净克隆出发，依次运行：
#   E8 基线+突发 -> E9 V* 敏感性 + C2 突发实证 -> E10/E11 真实抓包 -> 配图 -> 投稿稿
#
# 依赖：Node.js >= 18、Python >= 3.9（含 numpy、matplotlib、python-docx、Pillow）
# 用法：  bash 论文实验/复现包/reproduce.sh
#         FORCE=1 bash 论文实验/复现包/reproduce.sh        # 强制重跑全部
#         MS_VERSION=v2.0 bash 论文实验/复现包/reproduce.sh
#
# 论文断言 → 产物：
#   §6.5 330 格混淆矩阵 -> 数据/E8_baseline_summary.csv, E8_baseline_grid.csv
#   §6.7 突发 vs 均值    -> 数据/E9_c2burst.csv, E8_baseline_burst_runs.csv
#   §3.3 V* 敏感性       -> 数据/E9_vstar_sens.csv, E9_scene.csv, E9_acceptance.csv
#   §6.8 真实抓包复核    -> 数据/C2_trace/link_summary.csv, runs.csv
#   §6.8 可用度预算      -> 数据/C2_trace/E12_avail_budget.csv
#   Fig.1-5              -> 论文实验/figures/*.png
# ============================================================================
set -euo pipefail

# 项目根目录：脚本位于 论文实验/复现包/，上两级即项目根
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
echo "项目根: $ROOT"

FORCE="${FORCE:-0}"
MS_VERSION="${MS_VERSION:-v2.0}"

# ① 基线 + 突发（最重，约 1-2 min）
if [ "$FORCE" = "1" ] || [ ! -f "数据/E8_baseline_summary.csv" ]; then
  echo "[1/7] E8 baseline + Gilbert-Elliot burst (node) ..."
  node 代码/E8_baseline.js
else
  echo "[1/7] E8 产物已存在，跳过（FORCE=1 可强制重跑）"
fi

# ② V* 敏感性表 + E2/E3/E5 用 V* 重跑（论文 §3.3）
echo "[2/7] E9 V* sensitivity (node) ..."
node 代码/E9_vstar.js

# ③ C2 在 GE 突发下的实证 + L_B 阈值（论文 §6.7）
echo "[3/7] E9 C2 burst empirical (python) ..."
python3 代码/E9_c2burst.py

# ④ 真实 C-V2X 抓包：链路发现 + C2 复核（论文 §6.8）
#    需要 数据/C2_trace/raw/ 下的 NIST PCAP 压缩包（不复现则不下载也能跑完前 3 步）
RAW="数据/C2_trace/raw"
if [ -d "$RAW" ] && [ -n "$(ls -A "$RAW" 2>/dev/null)" ]; then
  echo "[4/7] E10/E11 real C-V2X traces (NIST PCAP) ..."
  python3 代码/E10_trace_topology.py
  python3 代码/E11_trace_c2.py
else
  echo "[4/7] 跳过 E10/E11：$RAW/ 下没有 NIST PCAP 压缩包"
  echo "      下载地址与 SHA-256 见 数据/C2_trace/raw/SOURCES.md"
fi

# ⑤ 由 C2 尾部契约反推可用度预算 A*（论文 §6.8）
#    仅依赖 数据/C2_trace/link_summary.csv，无原始 PCAP 也可运行
if [ -f "数据/C2_trace/link_summary.csv" ]; then
  echo "[5/7] E12 availability budget ..."
  python3 代码/E12_avail_budget.py
else
  echo "[5/7] 跳过 E12：缺少 数据/C2_trace/link_summary.csv（先跑第 4 步）"
fi

# ⑥ IEEE 分辨率配图（Fig. 1-5）
echo "[6/7] IEEE figures (matplotlib) ..."
python3 代码/make_figures.py
python3 代码/make_fig5.py

# ⑦ 生成投稿稿（IEEE Access 双栏 docx + 投稿信 + 待办清单）
echo "[7/7] build submission docx (python-docx, $MS_VERSION) ..."
MS_VERSION="$MS_VERSION" python3 代码/build_submission_docx.py

echo "DONE -> 论文实验/投稿版_IEEE_Access_${MS_VERSION}.docx"
