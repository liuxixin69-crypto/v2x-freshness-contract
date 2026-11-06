# 复现包（Reproducibility Package）

本目录配套论文 *"How Stale Is Too Stale? Bounding Consecutive Information Outages in V2X Collision Warning"*（投稿 IEEE Access v2.0），
提供从干净克隆到生成投稿稿的一键复现能力。

## 1. 环境依赖

| 工具 | 版本 | 用途 |
|---|---|---|
| Node.js | ≥ 18 | 运行 E8 / E9 仿真（纯 JS，无外部 npm 依赖） |
| Python | ≥ 3.9 | 运行分析与生成脚本 |
| matplotlib | ≥ 3.x | 导出 IEEE 分辨率配图 |
| numpy | ≥ 1.x | 数值计算 |
| python-docx | ≥ 1.x | 生成 .docx 投稿稿 |
| Pillow | ≥ 9.x | 公式 PNG 嵌入 |

安装：
```bash
pip install -r 论文实验/复现包/requirements.txt
```

许可：代码与派生 CSV/PNG 为 MIT（见 `LICENSE`）；NIST 原始抓包不随包分发，遵循 NIST 自身条款。

## 2. 一键复现

```bash
bash 论文实验/复现包/reproduce.sh
# 或强制重跑全部（含最重的 E8）：
FORCE=1 bash 论文实验/复现包/reproduce.sh
```

脚本依次执行：
1. `代码/E8_baseline.js` —— 基线判据 / Wilson 置信区间 / Gilbert-Elliot 突发（24,700 次受控运行：9,900 + 7,200 + 7,600 → `数据/E8_baseline_*.csv`）。
2. `代码/E9_vstar.js` —— V* 敏感性表 + 用 V* 重跑 E2/E3/E5（`数据/E9_vstar_*.csv`）。
3. `代码/E9_c2burst.py` —— C2 在 GE 突发下的实证 + L_B 阈值（`数据/E9_c2burst.csv`）。
4. `代码/E10_trace_topology.py` + `代码/E11_trace_c2.py` —— 真实 C-V2X 抓包：链路发现 + C2 复核（`数据/C2_trace/*.csv`）。需要 `数据/C2_trace/raw/` 下的 NIST PCAP 压缩包；缺失时脚本自动跳过这一步。
5. `代码/E12_avail_budget.py` —— 由 C2 尾部契约反推可用度预算 A*（`数据/C2_trace/E12_avail_budget.csv`）。只依赖第 4 步的 `link_summary.csv`，无原始 PCAP 也能运行。
6. `代码/make_figures.py` + `代码/make_fig5.py` —— 五张 IEEE 配图（`论文实验/figures/fig0~5_*.png`）。
7. `代码/build_submission_docx.py` —— 生成投稿稿（`论文实验/投稿版_IEEE_Access_<MS_VERSION>.docx` + 投稿信 + 待办清单）。版本用环境变量控制，默认 `v2.0`。

> 说明：脚本以脚本所在位置推算项目根目录，**不依赖绝对路径**，可在任意克隆路径下运行。
> 所有随机性由固定种子（`k*7919+13, k=1..N`）控制，结果可复现。

## 3. 关键数字与产物对应

| 论文断言 | 数据产物 | 生成脚本 |
|---|---|---|
| 可行域 / 契约对比（§6.5） | `数据/E8_baseline_grid.csv`, `E8_baseline_summary.csv` | E8 |
| 突发使尾部变重、C2 需 L_B 约束（§6.7） | `数据/E8_baseline_burst*.csv`, `E9_c2burst.csv` | E8 + E9_c2burst |
| V* 场景相关、悬崖随 V* 平移（§3.3） | `数据/E9_vstar_sens.csv`, `E9_scene.csv`, `E9_acceptance.csv` | E9 |
| 真实 C-V2X 链路上 C2 的余量（§6.8） | `数据/C2_trace/link_summary.csv`, `runs.csv` | E10 + E11 |
| 可用度预算 A*=95.9% @ δ=5%（§6.8） | `数据/C2_trace/E12_avail_budget.csv` | E12 |
| 五张配图（Fig.1–5，含 system model） | `论文实验/figures/fig0_system_model.png` 等 5 个 | make_figures + make_fig5 |

## 4. 待用户完成的外部步骤（需凭据/网络，本包不代执行）

- **GitHub 仓库**：将上述 `代码/`、`数据/`、`论文实验/` 推送到公开仓库，并在投稿稿 Data Availability 段填入仓库 URL。
- **Zenodo 归档 + DOI**：在 Zenodo 创建新归档（可用本目录 `zenodo.json` 作为元数据），
  归档后获得 DOI，回填到 `代码/build_submission_docx.py` 的 Data Availability 段落与投稿信。
- **NIST PCAP 下载**：`数据/C2_trace/raw/` 下的三个压缩包体积约 23 MB，未随仓库分发时，
  需按 `数据/C2_trace/raw/SOURCES.md` 的地址与 SHA-256 自行下载，否则第 4 步自动跳过。

> 真实 trace 验证已接入（NIST mds2-4003，8 条有向链路，43 min，24,449 信标），
> 不再列为待办。CooperScene [6] 仅作为参数范围的外部锚点，未做直接对比。

## 5. 目录约定

```
智能驾驶研究/
├── 代码/            # E8 / E9 / E10 / E11 / E12 / make_figures / build_submission_docx 等
├── 数据/            # 所有 CSV 产物（仿真、敏感性、突发、真实 trace）
├── 论文/            # 源稿（期刊版_初稿_EN_v0.2.md 等）
└── 论文实验/        # 投稿产物
    ├── 投稿版_IEEE_Access_v1.7.docx
    ├── figures/     # IEEE 配图
    └── 复现包/      # 本目录（LICENSE / CITATION.cff / requirements.txt / zenodo.json）
```
