"use strict";
/*
 * 通信退化条件下 V2X 碰撞预警有效性评测 —— 批量实验脚本
 *
 * 仿真内核与 产品原型/v2x_预警死线_v0.1.html 同源（逐行对应 step / evaluate / criticalTime）。
 * 改一处必须两处同改，否则论文数字与现场演示会对不上。
 *
 * 运行： node 代码/run_experiments.js
 * 输出： 数据/ 下的 CSV 与 关键数字.md
 * 依赖： 无（Node >= 18）
 */
const fs = require("fs");
const path = require("path");

const OUT = path.resolve(__dirname, "..", "数据");
fs.mkdirSync(OUT, { recursive: true });

const DT = 0.05, MAXT = 10, LEN = 4.5, SAFE = 1.5, SEEDS = 30;
const SEED_BASE = 7919, SEED_OFFSET = 13;

const SCENES = {
  fcw: { key: "fcw", name: "FCW 前向碰撞预警", vH: 16.67, x0: 55, v0: 11.11, decT: 1.0, a: -6.0, ttcTh: 3.5, emergTh: 1.75 },
  ebw: { key: "ebw", name: "EBW 紧急制动预警", vH: 16.67, x0: 60, v0: 13.89, decT: 2.5, a: -9.0, ttcTh: 3.5, emergTh: 1.75 },
  icw: { key: "icw", name: "ICW 路口前车减速(等效一维)", vH: 18.06, x0: 55, v0: 11.11, decT: 2.0, a: -7.0, ttcTh: 3.5, emergTh: 1.75 },
};

const PRESETS = {
  ideal:  { loss: 0,  tau: 0,   freq: 10, noise: 0,   label: "理想链路" },
  gpp:    { loss: 10, tau: 100, freq: 10, noise: 0.2, label: "3GPP 100 ms 合规" },
  real:   { loss: 38, tau: 30,  freq: 10, noise: 0.3, label: "真实链路量级(待核)" },
  crowd:  { loss: 60, tau: 300, freq: 5,  noise: 0.5, label: "拥塞退化" },
  severe: { loss: 85, tau: 600, freq: 2,  noise: 1.0, label: "严重退化" },
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

const BASE = { loss: 0, tau: 0, freq: 10, noise: 0.2, tvalid: 0.5 };
const cfgOf = o => Object.assign({}, BASE, o);
const detailRows = [], summaryRows = [];

function runGroup(exp, sceneKey, tag, xName, xValue, cfg) {
  const sc = SCENES[sceneKey];
  let mSum = 0, mMin = Infinity, miss = 0, safe = 0, aoi = 0, blind = 0;
  for (let k = 1; k <= SEEDS; k++) {
    const seed = k * SEED_BASE + SEED_OFFSET;
    const s = runRaw(sc, cfg, seed), e = evaluate(s, sc);
    mSum += e.margin; mMin = Math.min(mMin, e.margin);
    if (e.missed) miss++;
    if (e.safe) safe++;
    aoi += e.aoiMean; blind += e.blindRate;
    detailRows.push([exp, sceneKey, tag, xName, xValue,
      Math.round(cfg.loss * 100), cfg.tau, cfg.freq, cfg.noise, Math.round(cfg.tvalid * 1000),
      seed, e.tc.toFixed(3), s.warnTime === null ? "" : s.warnTime.toFixed(3),
      e.margin.toFixed(4), e.missed ? 1 : 0, e.safe ? 1 : 0,
      e.aoiMean.toFixed(2), e.blindRate.toFixed(2), s.recv, s.sent].join(","));
  }
  const row = { exp, scene: sceneKey, tag, xName, xValue,
    margin: mSum / SEEDS, min: mMin === Infinity ? 0 : mMin,
    miss: miss / SEEDS * 100, safe: safe / SEEDS * 100,
    aoi: aoi / SEEDS, blind: blind / SEEDS };
  summaryRows.push(row);
  return row;
}

console.log("=== 实验开始 ===");
// E1 五预设 × 三场景
for (const sk of Object.keys(SCENES))
  for (const pk of Object.keys(PRESETS)) {
    const p = PRESETS[pk];
    runGroup("E1_preset", sk, pk, "preset", pk,
      cfgOf({ loss: p.loss / 100, tau: p.tau, freq: p.freq, noise: p.noise }));
  }
// E2 丢包扫描：固定 3GPP 合规时延 100 ms、10 Hz、有效期 500 ms
for (const sk of Object.keys(SCENES))
  for (let loss = 0; loss <= 90; loss += 10)
    runGroup("E2_loss_sweep", sk, "loss" + loss, "loss_pct", loss,
      cfgOf({ loss: loss / 100, tau: 100 }));
// E3 时延扫描：固定丢包 10%（3GPP 合规预设），找时延悬崖
for (const sk of Object.keys(SCENES))
  for (let tau = 0; tau <= 1000; tau += 100)
    runGroup("E3_tau_sweep", sk, "tau" + tau, "tau_ms", tau,
      cfgOf({ loss: 0.10, tau }));
// E4 消融：单因素 vs 组合
const ABL = {
  baseline: cfgOf({}),
  loss_only: cfgOf({ loss: 0.60 }),
  tau_only: cfgOf({ tau: 600 }),
  both: cfgOf({ loss: 0.60, tau: 600 }),
};
for (const sk of Object.keys(SCENES))
  for (const k of Object.keys(ABL))
    runGroup("E4_ablation", sk, k, "condition", k, ABL[k]);
// E5 有效期敏感性：验证「时延悬崖的位置由 BSM 有效期决定」是机制而非参数凑巧
const TVALIDS = [100, 300, 500, 700, 1000];
for (const tv of TVALIDS)
  for (let tau = 0; tau <= 1300; tau += 100)
    runGroup("E5_validity", "fcw", "tv" + tv + "_tau" + tau, "tau_ms", tau,
      cfgOf({ loss: 0.10, tau, tvalid: tv / 1000 }));
console.log(`=== 完成：${detailRows.length} 次独立运行 / ${summaryRows.length} 组汇总 ===`);

const D_HEAD = "exp,scene,tag,x_name,x_value,loss_pct,tau_ms,freq_hz,noise_m,valid_ms,seed,tc_s,warn_s,margin_s,missed,safe,aoi_mean_ms,blind_rate_pct,recv,sent\n";
const S_HEAD = "exp,scene,tag,x_name,x_value,n,margin_mean_s,margin_min_s,miss_rate_pct,safe_rate_pct,aoi_mean_ms,blind_rate_pct\n";
fs.writeFileSync(path.join(OUT, "实验明细_runs.csv"), "\ufeff" + D_HEAD + detailRows.join("\n") + "\n", "utf8");
fs.writeFileSync(path.join(OUT, "实验汇总_summary.csv"), "\ufeff" + S_HEAD + summaryRows.map(r =>
  [r.exp, r.scene, r.tag, r.xName, r.xValue, SEEDS, r.margin.toFixed(4), r.min.toFixed(4),
    r.miss.toFixed(2), r.safe.toFixed(2), r.aoi.toFixed(2), r.blind.toFixed(2)].join(",")).join("\n") + "\n", "utf8");

const pick = (exp, scene, tag) => summaryRows.find(r => r.exp === exp && r.scene === scene && String(r.tag) === String(tag));
const f = (r) => r ? `${r.margin.toFixed(2)}s / 漏警 ${r.miss.toFixed(0)}% / 来得及 ${r.safe.toFixed(0)}%` : "NA";
let md = "# 关键数字（由 run_experiments.js 自动生成，勿手改）\n\n";
md += `生成时间：${new Date().toISOString()}\n\n`;
md += `固定参数：DT=${DT}s, MAXT=${MAXT}s, 车长 LEN=${LEN}m, 安全余量 SAFE=${SAFE}s, `;
md += `TTC 阈值 ${SCENES.fcw.ttcTh}s / 紧急 ${SCENES.fcw.emergTh}s, BSM 有效期 ${BASE.tvalid * 1000}ms, `;
md += `每点 ${SEEDS} 个固定种子 (k*${SEED_BASE}+${SEED_OFFSET}, k=1..${SEEDS})。\n\n`;
md += `各场景理想链路关键时刻 tc：FCW ${criticalTime(SCENES.fcw).toFixed(2)}s, EBW ${criticalTime(SCENES.ebw).toFixed(2)}s, ICW ${criticalTime(SCENES.icw).toFixed(2)}s。\n\n`;
md += "## E1 预设对比（FCW）\n\n| 预设 | 丢包% | 时延ms | 频率Hz | 平均提前量 | 漏警率 | 来得及率 |\n|---|---|---|---|---|---|---|\n";
for (const pk of Object.keys(PRESETS)) {
  const p = PRESETS[pk], r = pick("E1_preset", "fcw", pk);
  md += `| ${p.label} | ${p.loss} | ${p.tau} | ${p.freq} | ${r.margin.toFixed(2)} s | ${r.miss.toFixed(0)}% | ${r.safe.toFixed(0)}% |\n`;
}
md += "\n## E1 三场景 × 三预设（平均提前量 s / 漏警率 %）\n\n| 场景 | 理想 | 3GPP 100ms | 严重退化 |\n|---|---|---|---|\n";
for (const sk of Object.keys(SCENES)) {
  md += `| ${SCENES[sk].name} | ${f(pick("E1_preset", sk, "ideal"))} | ${f(pick("E1_preset", sk, "gpp"))} | ${f(pick("E1_preset", sk, "severe"))} |\n`;
}
md += "\n## E2 丢包扫描（FCW，固定 100 ms / 10 Hz / 500 ms）\n\n| 丢包% | 平均提前量 s | 最小提前量 s | 漏警率 % | 来得及率 % | 平均 AoI ms | 失明率 % |\n|---|---|---|---|---|---|---|\n";
for (let loss = 0; loss <= 90; loss += 10) {
  const r = pick("E2_loss_sweep", "fcw", "loss" + loss);
  md += `| ${loss} | ${r.margin.toFixed(2)} | ${r.min.toFixed(2)} | ${r.miss.toFixed(0)} | ${r.safe.toFixed(0)} | ${r.aoi.toFixed(0)} | ${r.blind.toFixed(0)} |\n`;
}
md += "\n## E3 时延扫描（FCW，固定丢包 10%）\n\n| 单程时延 ms | 平均提前量 s | 漏警率 % | 来得及率 % | 平均 AoI ms | 失明率 % |\n|---|---|---|---|---|---|\n";
for (let tau = 0; tau <= 1000; tau += 100) {
  const r = pick("E3_tau_sweep", "fcw", "tau" + tau);
  md += `| ${tau} | ${r.margin.toFixed(2)} | ${r.miss.toFixed(0)} | ${r.safe.toFixed(0)} | ${r.aoi.toFixed(0)} | ${r.blind.toFixed(0)} |\n`;
}
md += "\n## E4 消融（FCW）\n\n| 条件 | 平均提前量 s | 漏警率 % | 来得及率 % |\n|---|---|---|---|\n";
for (const k of Object.keys(ABL)) {
  const r = pick("E4_ablation", "fcw", k);
  md += `| ${k} | ${r.margin.toFixed(2)} | ${r.miss.toFixed(0)} | ${r.safe.toFixed(0)} |\n`;
}
md += "\n## E5 有效期敏感性（FCW，固定丢包 10%，扫描单程时延）\n\n";
md += "记录漏警率首次达到 50% 的临界单程时延，用于检验断崖是否由 BSM 有效期决定。\n\n";
md += "| BSM 有效期 ms | 临界时延 ms | 临界处漏警率 % | 断崖前 100 ms 漏警率 % |\n|---|---|---|---|\n";
for (const tv of TVALIDS) {
  const rows = summaryRows.filter(r => r.exp === "E5_validity" && r.tag.startsWith("tv" + tv + "_"));
  const hit = rows.find(r => r.miss >= 50) || rows[rows.length - 1];
  const prev = rows.find(r => r.xValue === hit.xValue - 100);
  md += `| ${tv} | ${hit.xValue} | ${hit.miss.toFixed(0)} | ${prev ? prev.miss.toFixed(0) : "—"} |\n`;
}
md += "\n---\n\n所有数值来自 `实验明细_runs.csv`（逐种子）与 `实验汇总_summary.csv`（逐组均值）。";
md += "论文与汇报图表只引用本文件数字，改动实验参数后需重新运行脚本并同步全文。\n";
fs.writeFileSync(path.join(OUT, "关键数字.md"), md, "utf8");

console.log("\n--- E1 FCW 预设 ---");
for (const pk of Object.keys(PRESETS)) console.log(pk.padEnd(8), f(pick("E1_preset", "fcw", pk)));
console.log("\n--- E2 丢包扫描 FCW ---");
for (let loss = 0; loss <= 90; loss += 10) {
  const r = pick("E2_loss_sweep", "fcw", "loss" + loss);
  console.log(String(loss).padStart(3) + "%", r.margin.toFixed(2) + "s", "漏警", r.miss.toFixed(0) + "%", "来得及", r.safe.toFixed(0) + "%");
}
console.log("\n--- E3 时延扫描 FCW ---");
for (let tau = 0; tau <= 1000; tau += 100) {
  const r = pick("E3_tau_sweep", "fcw", "tau" + tau);
  console.log(String(tau).padStart(4) + "ms", r.margin.toFixed(2) + "s", "漏警", r.miss.toFixed(0) + "%", "失明", r.blind.toFixed(0) + "%");
}
console.log("\n--- E4 消融 FCW ---");
for (const k of Object.keys(ABL)) console.log(k.padEnd(10), f(pick("E4_ablation", "fcw", k)));
