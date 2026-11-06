"use strict";
/*
 * E6 预警可行域热力图 —— 二维扫描（丢包率 × 单程时延）
 *
 * 仿真内核与 代码/run_experiments.js、产品原型 v0.2 同源。
 * 口径刻意与 E2/E3 完全对齐（BASE: noise=0.2, freq=10, tvalid=0.5, 30 个固定种子）：
 *   - 网格中 loss=10 的整列 应逐点等于 E3_tau_sweep
 *   - 网格中 tau=100 的整行 应逐点等于 E2_loss_sweep
 * 这两条构成可复现校验，结果写入 数据/可视化数据校验.md。
 *
 * 运行： node 代码/gen_heatmap.js
 * 输出： 数据/预警可行域_heatmap.csv / .json / 可视化数据校验.md
 */
const fs = require("fs");
const path = require("path");
const OUT = path.resolve(__dirname, "..", "数据");
fs.mkdirSync(OUT, { recursive: true });

const DT = 0.05, MAXT = 10, LEN = 4.5, SAFE = 1.5, SEEDS = 30;
const SEED_BASE = 7919, SEED_OFFSET = 13;
const BASE = { loss: 0, tau: 0, freq: 10, noise: 0.2, tvalid: 0.5 };
const LOSSES = Array.from({ length: 10 }, (_, i) => i * 10);      // 0..90
const TAUS   = Array.from({ length: 11 }, (_, i) => i * 100);     // 0..1000

const SCENES = {
  fcw: { key: "fcw", name: "FCW 前向碰撞预警", vH: 16.67, x0: 55, v0: 11.11, decT: 1.0, a: -6.0, ttcTh: 3.5, emergTh: 1.75 },
  ebw: { key: "ebw", name: "EBW 紧急制动预警", vH: 16.67, x0: 60, v0: 13.89, decT: 2.5, a: -9.0, ttcTh: 3.5, emergTh: 1.75 },
  icw: { key: "icw", name: "ICW 路口前车减速(等效一维)", vH: 18.06, x0: 55, v0: 11.11, decT: 2.0, a: -7.0, ttcTh: 3.5, emergTh: 1.75 },
};

function rngFactory(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function gauss(r) {
  let u = 0, v = 0;
  while (u === 0) u = r();
  while (v === 0) v = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
function initState(sc) {
  return { t: 0, hvX: 0, rvX: sc.x0, rvV: sc.v0,
    nextSend: 0, queue: [], last: null, sent: 0, lost: 0, recv: 0,
    blind: 0, frames: 0, warnTime: null, flag: 0, ttc: Infinity,
    gapTrue: sc.x0 - LEN, aoi: Infinity, colTime: null, done: false,
    aoiSum: 0, aoiN: 0 };
}
function step(s, sc, cfg, r) {
  if (s.done) return;
  s.t += DT; s.frames++;
  if (s.t >= sc.decT) s.rvV = Math.max(0, s.rvV + sc.a * DT);
  s.hvX += sc.vH * DT; s.rvX += s.rvV * DT;
  s.gapTrue = s.rvX - s.hvX - LEN;
  if (s.gapTrue <= 0 && s.colTime === null) s.colTime = s.t;
  if (s.t + 1e-9 >= s.nextSend) {
    s.sent++;
    if (r() >= cfg.loss) {
      const n = cfg.noise > 0 ? gauss(r) * cfg.noise : 0;
      s.queue.push({ t: s.t, x: s.rvX + n, v: s.rvV, arriveAt: s.t + cfg.tau / 1000 });
    } else s.lost++;
    s.nextSend += 1 / cfg.freq;
  }
  while (s.queue.length && s.queue[0].arriveAt <= s.t + 1e-9) { s.last = s.queue.shift(); s.recv++; }
  if (s.last) {
    s.aoi = s.t - s.last.t; s.aoiSum += s.aoi; s.aoiN++;
    if (s.aoi > cfg.tvalid) { s.blind++; s.ttc = Infinity; s.flag = 0; }
    else {
      const gapEst = (s.last.x + s.last.v * s.aoi) - s.hvX - LEN;
      s.ttc = Math.max(0, gapEst / Math.max(sc.vH - s.last.v, 0.5));
      if (s.ttc < sc.ttcTh && s.warnTime === null) s.warnTime = s.t;
      s.flag = s.ttc < sc.emergTh ? 2 : (s.ttc < sc.ttcTh ? 1 : 0);
    }
  } else { s.blind++; s.ttc = Infinity; s.flag = 0; }
  if (s.colTime !== null || s.t >= MAXT) s.done = true;
}
function runRaw(sc, cfg, seed) {
  const r = rngFactory(seed), s = initState(sc);
  while (!s.done) step(s, sc, cfg, r);
  return s;
}
function criticalTime(sc) {
  if (sc._crit) return sc._crit;
  const s = runRaw(sc, { loss: 0, tau: 0, freq: 10, noise: 0, tvalid: 0.5 }, 1);
  sc._crit = s.colTime === null ? MAXT : s.colTime;
  return sc._crit;
}
function evaluate(s, sc) {
  const tc = criticalTime(sc);
  const margin = s.warnTime === null ? 0 : Math.max(0, tc - s.warnTime);
  const missed = s.warnTime === null || margin <= 0;
  return { tc, margin, missed, safe: !missed && margin >= SAFE,
    aoiMean: s.aoiN ? s.aoiSum / s.aoiN * 1000 : 0,
    blindRate: s.frames ? s.blind / s.frames * 100 : 0 };
}

const csvRows = ["scene,loss_pct,tau_ms,n,margin_mean_s,miss_rate_pct,safe_rate_pct,aoi_mean_ms,blind_rate_pct"];
const grid = {};
let totalRuns = 0;

for (const sk of Object.keys(SCENES)) {
  const sc = SCENES[sk];
  // 行 = tau（11），列 = loss（10）；每格 [safe%, miss%, margin*100]
  const rows = [];
  for (const tau of TAUS) {
    const row = [];
    for (const loss of LOSSES) {
      const cfg = Object.assign({}, BASE, { loss: loss / 100, tau });
      let m = 0, miss = 0, safe = 0, aoi = 0, blind = 0;
      for (let k = 1; k <= SEEDS; k++) {
        const s = runRaw(sc, cfg, k * SEED_BASE + SEED_OFFSET);
        const e = evaluate(s, sc);
        m += e.margin; if (e.missed) miss++; if (e.safe) safe++;
        aoi += e.aoiMean; blind += e.blindRate;
      }
      const cell = {
        safe: +(safe / SEEDS * 100).toFixed(1),
        miss: +(miss / SEEDS * 100).toFixed(1),
        margin: +(m / SEEDS).toFixed(3),
        aoi: +(aoi / SEEDS).toFixed(1),
        blind: +(blind / SEEDS).toFixed(1)
      };
      row.push([cell.safe, cell.miss, Math.round(cell.margin * 100)]);
      csvRows.push([sk, loss, tau, SEEDS, cell.margin.toFixed(3), cell.miss.toFixed(1),
        cell.safe.toFixed(1), cell.aoi.toFixed(1), cell.blind.toFixed(1)].join(","));
      totalRuns += SEEDS;
    }
    rows.push(row);
  }
  grid[sk] = rows;
}
fs.writeFileSync(path.join(OUT, "预警可行域_heatmap.csv"), "\ufeff" + csvRows.join("\n") + "\n", "utf8");
const payload = {
  meta: {
    generated: new Date().toISOString(),
    source: "代码/gen_heatmap.js（与 run_experiments.js 同源内核）",
    losses: LOSSES, taus: TAUS, seeds: SEEDS,
    base: { freq: 10, noise: 0.2, bsm_valid_ms: 500, safe_margin_s: SAFE },
    cell_format: "[safe_rate_percent, miss_rate_percent, margin_s_x100]",
    note: "行=单程时延 ms，列=丢包率 %；离线内嵌进 v0.2 原型，改有效期后请用页面内重算功能"
  },
  grid
};
fs.writeFileSync(path.join(OUT, "预警可行域_heatmap.json"), JSON.stringify(payload), "utf8");

// ---- 一致性校验：拿既有 E2/E3 汇总逐点比对 ----
function readSummary(file) {
  return fs.readFileSync(file, "utf8").replace(/^\ufeff/, "").trim().split(/\r?\n/);
}
const lines = readSummary(path.join(OUT, "实验汇总_summary.csv"));
const head = lines[0].split(",");
const idx = n => head.indexOf(n);
const records = lines.slice(1).map(l => l.split(","));
const e2 = new Map(), e3 = new Map();
for (const r of records) {
  const exp = r[idx("exp")], scene = r[idx("scene")];
  if (scene !== "fcw") continue;
  if (exp === "E2_loss_sweep") e2.set(+r[idx("x_value")], r);
  if (exp === "E3_tau_sweep") e3.set(+r[idx("x_value")], r);
}
const checks = [];
for (const [i, tau] of TAUS.entries()) {
  const cell = grid.fcw[i][1]; // loss=10 列
  const r = e3.get(tau);
  if (!r) continue;
  checks.push({ kind: "E3_tau_sweep", x: tau,
    heatmap: [cell[2] / 100, cell[1], cell[0]],
    existing: [+r[idx("margin_mean_s")], +r[idx("miss_rate_pct")], +r[idx("safe_rate_pct")]],
    ok: Math.abs(cell[2] / 100 - +r[idx("margin_mean_s")]) < 0.0051 &&
        Math.abs(cell[1] - +r[idx("miss_rate_pct")]) < 0.05 &&
        Math.abs(cell[0] - +r[idx("safe_rate_pct")]) < 0.05 });
}
for (const [j, loss] of LOSSES.entries()) {
  const cell = grid.fcw[1][j]; // tau=100 行
  const r = e2.get(loss);
  if (!r) continue;
  checks.push({ kind: "E2_loss_sweep", x: loss,
    heatmap: [cell[2] / 100, cell[1], cell[0]],
    existing: [+r[idx("margin_mean_s")], +r[idx("miss_rate_pct")], +r[idx("safe_rate_pct")]],
    ok: Math.abs(cell[2] / 100 - +r[idx("margin_mean_s")]) < 0.0051 &&
        Math.abs(cell[1] - +r[idx("miss_rate_pct")]) < 0.05 &&
        Math.abs(cell[0] - +r[idx("safe_rate_pct")]) < 0.05 });
}
const passed = checks.filter(c => c.ok).length;
let md = "# 可视化数据一致性校验\n\n";
md += `生成时间：${new Date().toISOString()}\n\n`;
md += `本轮二维扫描 **${totalRuns} 次独立运行**（3 场景 × ${TAUS.length} 档时延 × ${LOSSES.length} 档丢包 × ${SEEDS} 种子），`;
md += `累计与既有实验合计约 ${(totalRuns + 4800).toLocaleString()} 次。\n\n`;
md += `校验方法：热力图与 E2/E3 使用同一内核、同一 BASE 与同一批种子，因此 `;
md += `固定 loss=10% 的时延列应逐点等于 E3_tau_sweep，固定 tau=100 ms 的丢包行应逐点等于 E2_loss_sweep。\n\n`;
md += `**结果：${passed} / ${checks.length} 个交叉点完全一致。**\n\n`;
md += "| 对照实验 | 扫描点 | 热力图(提前量/漏警/来得及) | 既有 CSV | 一致 |\n|---|---|---|---|---|\n";
for (const c of checks) {
  const f = a => a.map((v, i) => i === 0 ? v.toFixed(2) + "s" : v.toFixed(0) + "%").join(" / ");
  md += `| ${c.kind} | ${c.x} | ${f(c.heatmap)} | ${f(c.existing)} | ${c.ok ? "✓" : "✗"} |\n`;
}
md += "\n口径：BASE = 10 Hz、位姿噪声 0.2 m、BSM 有效期 500 ms、安全余量 1.5 s、种子 k*7919+13 (k=1..30)。\n";
md += "页面中「按当前参数重算」使用 20 种子现场计算，属演示功能；论文引用请以本文件与 CSV 的 30 种子结果为准。\n";
fs.writeFileSync(path.join(OUT, "可视化数据校验.md"), md, "utf8");

console.log(`=== E6 完成：${totalRuns} 次运行 / 3 场景 × ${TAUS.length}×${LOSSES.length} 网格 ===`);
console.log(`一致性校验：${passed}/${checks.length} 交叉点一致`);
if (passed !== checks.length) {
  console.log("不一致点：", JSON.stringify(checks.filter(c => !c.ok).slice(0, 5)));
  process.exitCode = 1;
}
// 打印几条用于汇报的硬数字
const q = (loss, tau) => grid.fcw[TAUS.indexOf(tau)][LOSSES.indexOf(loss)];
console.log("FCW 合规区内 (loss=90%,tau=100ms):", q(90, 100));
console.log("FCW 悬崖两侧 (loss=10%,tau=500/600ms):", q(10, 500), q(10, 600));
console.log("FCW 理想 (loss=0,tau=0):", q(0, 0));
