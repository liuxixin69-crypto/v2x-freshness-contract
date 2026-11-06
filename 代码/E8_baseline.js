"use strict";
/*
 * E8 —— 实验补强：传统 baseline 判据 / 200 种子 Wilson 置信区间 / Gilbert-Elliot burst 丢包
 *
 * 交付：
 *   代码/E8_baseline.js                 本文件（独立运行、无外部依赖、Node >= 18）
 *   数据/E8_baseline_grid.csv          ① E6 同款网格逐格判据结果
 *   数据/E8_baseline_summary.csv       ① 混淆矩阵汇总（含全部误判率定义）
 *   数据/E8_baseline_wilson.csv        ② 200 种子 safe / 漏警率 95% Wilson CI
 *   数据/E8_baseline_burst.csv         ③ i.i.d. vs GE burst 逐条件汇总
 *   数据/E8_baseline_burst_runs.csv    ③ 连续失明段长度分布（逐长度计数）
 *   数据/E8_baseline_burst_hist.csv    ③ 连续失明段长度分布（分桶汇总，含百分比）
 *
 * 运行： node 代码/E8_baseline.js
 * 实测： Node v22.22.2（C:/Users/喜哈哈/.workbuddy/binaries/node/versions/22.22.2-6/node.exe）
 *
 * 内核：rngFactory / gauss / initState / step / runRaw / criticalTime / evaluate
 *       逐行复制自 代码/run_experiments.js（与 gen_heatmap.js / derive_bound.js 同源）。
 *       唯一改动：step 中丢包判定写成 `cfg.deliver ? cfg.deliver() : r() >= cfg.loss`。
 *       未注入 cfg.deliver 时与原文逐字等价（同样是每次发送恰好消耗一次 r()），
 *       因此 i.i.d. 结果与 E2/E3/E6 位一致；脚本末尾用 数据/预警可行域_heatmap.csv 交叉校验。
 *       注入 cfg.deliver 时把 i.i.d. 丢包替换为两状态 Gilbert-Elliot 丢包，
 *       运动学、AoI 门控、TTC 判定、位姿噪声全部保持不变（同一 step）。
 *
 * 口径：DT=0.05 s, MAXT=10 s, LEN=4.5 m, SAFE=1.5 s, V=500 ms, f=10 Hz,
 *       noise=0.2 m, 种子 k*7919+13 (k=1..N), 场景 FCW / EBW / ICW。
 */
const fs = require("fs");
const path = require("path");
const OUT = path.resolve(__dirname, "..", "数据");
fs.mkdirSync(OUT, { recursive: true });

/* ===================== 固定参数与口径 ===================== */
const DT = 0.05, MAXT = 10, LEN = 4.5, SAFE = 1.5;
const SEED_BASE = 7919, SEED_OFFSET = 13;
const N30 = 30, N200 = 200;
const V_MS = 500, F_HZ = 10;
const EPS_MS = DT * 1000;                       // 50 ms = 一个仿真/采样步长
const V_MINUS_EPS = V_MS - EPS_MS;               // 450 ms，契约 C0 的时延上界
const P_CONTRACT = 0.754;                        // 契约 C2：窗口感知紧界 (delta=0.05)
const QUALIFY_SAFE = 80;                         // 「实际合格」判据：safe_rate >= 80%
const PDR_BASELINE_MIN = 90;                     // baseline：PDR >= 90%
const DELAY_BASELINE_MAX = 100;                  // baseline：平均时延 <= 100 ms
const W_S = SAFE, W_FRAMES = Math.round(W_S / DT); // 决策窗口 1.5 s = 30 帧
const Z95 = 1.959963984540054;
const GE_SEED_XOR = 0x9e3779b9;                  // GE 独立 RNG 流（与位姿噪声流去相关）

const BASE = { loss: 0, tau: 0, freq: 10, noise: 0.2, tvalid: 0.5 };
const cfgOf = o => Object.assign({}, BASE, o);
const LOSSES = Array.from({ length: 10 }, (_, i) => i * 10);   // 0..90，步长 10（E6 同款）
const TAUS = Array.from({ length: 11 }, (_, i) => i * 100);    // 0..1000，步长 100（E6 同款）

const SCENES = {
  fcw: { key: "fcw", name: "FCW 前向碰撞预警", vH: 16.67, x0: 55, v0: 11.11, decT: 1.0, a: -6.0, ttcTh: 3.5, emergTh: 1.75 },
  ebw: { key: "ebw", name: "EBW 紧急制动预警", vH: 16.67, x0: 60, v0: 13.89, decT: 2.5, a: -9.0, ttcTh: 3.5, emergTh: 1.75 },
  icw: { key: "icw", name: "ICW 路口前车减速(等效一维)", vH: 18.06, x0: 55, v0: 11.11, decT: 2.0, a: -7.0, ttcTh: 3.5, emergTh: 1.75 },
};

/* ===== 内核：逐行复制自 run_experiments.js（唯一改动见文件头说明） ===== */
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
    if (cfg.deliver ? cfg.deliver() : r() >= cfg.loss) {
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

/* ===================== 工具 ===================== */
const seedOf = k => k * SEED_BASE + SEED_OFFSET;

/* 单次运行：可注入丢包模型；同时逐帧记录「连续失明段」长度（帧数）。
 * 失明段通过 s.blind 的增量判定：每帧 s.blind 至多 +1，故增量>0 即本帧失明。 */
function runOne(sc, cfg, seed, modelFactory) {
  const r = rngFactory(seed), s = initState(sc);
  // 关键：丢包模型必须与 step 共用同一个 r（i.i.d. 时每次发送消耗一次 r()，
  // 与 run_experiments.js 原始内核逐位一致；否则 gauss 噪声流会错位）。
  const lm = modelFactory(r);
  const c = Object.assign({}, cfg, { deliver: lm.deliver });
  let prevBlind = 0, cur = 0; const runs = [];
  while (!s.done) {
    step(s, sc, c, r);
    if (s.blind > prevBlind) cur++;
    else if (cur > 0) { runs.push(cur); cur = 0; }
    prevBlind = s.blind;
  }
  if (cur > 0) runs.push(cur);
  return { s, runs, stats: lm.stats() };
}

/* i.i.d. 丢包模型：注入的 deliver 恰好每次发送消耗一次 r()，与原始内核位一致。 */
function modelIID(loss, r) {
  const c = { sent: 0, lost: 0 };
  return {
    deliver: () => { c.sent++; const ok = r() >= loss; if (!ok) c.lost++; return ok; },
    stats: () => ({ sent: c.sent, lost: c.lost, realizedLoss: c.sent ? c.lost / c.sent : 0,
      alpha: NaN, beta: NaN, piBad: NaN, L_B: NaN, L_G: NaN, pG: NaN, pB: NaN })
  };
}

/* 两状态 Gilbert-Elliot（经典 Gilbert：GOOD 全送达 pG=0，BAD 全丢 pB=1）。
 * 参数：pbar 目标平均丢包率、L_B BAD 态平均驻留包数。
 *   beta  = 1 / L_B                      (BAD -> GOOD)
 *   alpha = pbar / (L_B * (1 - pbar))   (GOOD -> BAD)
 *   pi_B  = alpha / (alpha + beta) = pbar
 *   L_G   = 1 / alpha
 * 状态按平稳分布 pi_B 初始化，保证短运行内 E[丢包占比] = pbar。
 * 独立 RNG 流 geRng，与位姿噪声流 r 去相关。 */
function modelGE(pbar, L_B, geSeed, r) {
  const beta = 1 / L_B;
  const alpha = pbar <= 0 ? 0 : pbar / (L_B * (1 - pbar));
  if (alpha > 1) throw new Error(`GE 参数非法：alpha=${alpha.toFixed(3)}>1，请增大 L_B 或降低 pbar`);
  const piB = alpha + beta > 0 ? alpha / (alpha + beta) : 0;
  const gr = rngFactory(geSeed);
  let state = gr() < piB ? 1 : 0;            // 1 = BAD, 0 = GOOD
  const c = { sent: 0, lost: 0 };
  return {
    deliver: () => {
      c.sent++;
      if (state === 1) { if (gr() < beta) state = 0; }
      else { if (gr() < alpha) state = 1; }
      const drop = state === 1;              // pB = 1, pG = 0
      if (drop) c.lost++;
      return !drop;                          // true = 送达
    },
    stats: () => ({ sent: c.sent, lost: c.lost, realizedLoss: c.sent ? c.lost / c.sent : 0,
      alpha, beta, piBad: piB, L_B, L_G: alpha > 0 ? 1 / alpha : Infinity, pG: 0, pB: 1 })
  };
}

/* 汇总 n 个种子。geConf = null 表示 i.i.d.（cfg.loss 生效）；否则为 {pbar, L_B}。
 * subN > 0 时额外统计前 subN 个种子的 safe/miss 计数，用于与 30 种子结果对照。 */
function aggregate(sc, cfg, nSeeds, geConf, subN) {
  subN = subN || 0;
  let safe = 0, miss = 0, margin = 0, blind = 0, aoi = 0;
  let subSafe = 0, subMiss = 0;
  let gSent = 0, gLost = 0;
  const runs = [];
  let geStats = null;
  for (let k = 1; k <= nSeeds; k++) {
    const seed = seedOf(k);
    const factory = geConf
      ? (r => modelGE(geConf.pbar, geConf.L_B, (seed ^ GE_SEED_XOR) >>> 0, r))
      : (r => modelIID(cfg.loss, r));
    const out = runOne(sc, cfg, seed, factory);
    const e = evaluate(out.s, sc);
    if (e.safe) safe++;
    if (e.missed) miss++;
    if (k <= subN) { subSafe += e.safe ? 1 : 0; subMiss += e.missed ? 1 : 0; }
    margin += e.margin; blind += e.blindRate; aoi += e.aoiMean;
    const st = out.stats; gSent += st.sent; gLost += st.lost; geStats = st;
    for (const L of out.runs) runs.push(L);
  }
  return {
    n: nSeeds, safe, miss,
    safeRate: safe / nSeeds * 100, missRate: miss / nSeeds * 100,
    margin: margin / nSeeds, blind: blind / nSeeds, aoi: aoi / nSeeds,
    realizedLoss: gSent ? gLost / gSent : 0, gSent, gLost,
    subN, subSafe, subMiss, subSafeRate: subN ? subSafe / subN * 100 : 0,
    subMissRate: subN ? subMiss / subN * 100 : 0,
    geStats, runs
  };
}

function wilson(k, n, z) {
  z = z === undefined ? Z95 : z;
  if (!n) return [0, 0];
  const p = k / n, z2 = z * z, den = 1 + z2 / n;
  const center = (p + z2 / (2 * n)) / den;
  const half = (z / den) * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n));
  return [Math.max(0, (center - half) * 100), Math.min(100, (center + half) * 100)];
}

function runStats(runs) {
  if (!runs.length) return { count: 0, mean: 0, p50: 0, p95: 0, max: 0, fracGeW: 0, maxS: 0 };
  const sorted = runs.slice().sort((a, b) => a - b);
  const q = f => sorted[Math.min(sorted.length - 1, Math.floor(f * (sorted.length - 1)))];
  return {
    count: runs.length,
    mean: runs.reduce((a, b) => a + b, 0) / runs.length,
    p50: q(0.5), p95: q(0.95), max: sorted[sorted.length - 1],
    fracGeW: runs.filter(L => L >= W_FRAMES).length / runs.length,
    maxS: sorted[sorted.length - 1] * DT
  };
}

const pct = v => v.toFixed(1);
const f2 = v => v.toFixed(2);
const f3 = v => v.toFixed(3);

function writeCsv(name, head, rows) {
  fs.writeFileSync(path.join(OUT, name), "\ufeff" + head + "\n" + rows.join("\n") + "\n", "utf8");
}

/* ===================== ① Baseline 判据 vs 契约判据（E6 同款网格） ===================== */
/* 判据形式化：
 *   baseline_accept   = (PDR_nominal >= 90%) && (mean_delay <= 100 ms)
 *                        PDR_nominal = 100 - loss_pct；恒定单程时延下 mean_delay = tau_ms
 *   baseline_accept_realized = 同上，但用仿真实测链路 PDR = 100*(1-realizedLoss)
 *   contract_accept   = (tau_ms <= V - eps) && (p <= 0.754)
 *   actual_qualified  = (safe_rate_pct >= 80)      ← 地面真值
 *   FA(误判为合格/假阳性) = accept && !actual_qualified
 *   FR(误判为不合格/假阴性) = !accept && actual_qualified
 */
const gridRows = [];
const GRID_HEAD = "scene,loss_pct,tau_ms,n,safe_rate_pct,miss_rate_pct,margin_mean_s,blind_rate_pct,mean_aoi_ms," +
  "pdr_nominal_pct,pdr_realized_pct,mean_delay_ms,actual_qualified," +
  "baseline_accept,baseline_accept_realized,baseline_FA,baseline_FR,baseline_realized_FA,baseline_realized_FR," +
  "contract_accept,contract_FA,contract_FR";
const gridData = {};   // 供汇总与 E6 校验

console.log("=== E8 ① 开始：E6 同款 10 丢包 × 11 时延网格 × 3 场景 × 30 种子 ===");
for (const sk of Object.keys(SCENES)) {
  const sc = SCENES[sk];
  for (const tau of TAUS) {
    for (const loss of LOSSES) {
      const cfg = cfgOf({ loss: loss / 100, tau });
      const a = aggregate(sc, cfg, N30, null, 0);
      const qualified = a.safeRate >= QUALIFY_SAFE;
      const pdrNom = 100 - loss;
      const pdrReal = 100 * (1 - a.realizedLoss);
      const bAcc = pdrNom >= PDR_BASELINE_MIN && tau <= DELAY_BASELINE_MAX;
      const bAccReal = pdrReal >= PDR_BASELINE_MIN && tau <= DELAY_BASELINE_MAX;
      const cAcc = tau <= V_MINUS_EPS && (loss / 100) <= P_CONTRACT;
      const row = {
        scene: sk, loss, tau, n: N30, safeRate: a.safeRate, missRate: a.missRate,
        margin: a.margin, blind: a.blind, aoi: a.aoi, pdrNom, pdrReal, meanDelay: tau,
        qualified, bAcc, bAccReal, cAcc
      };
      gridData[`${sk}|${loss}|${tau}`] = row;
      gridRows.push([
        sk, loss, tau, N30, pct(a.safeRate), pct(a.missRate), f3(a.margin), pct(a.blind), pct(a.aoi),
        pct(pdrNom), pct(pdrReal), tau, qualified ? 1 : 0,
        bAcc ? 1 : 0, bAccReal ? 1 : 0,
        (bAcc && !qualified) ? 1 : 0, (!bAcc && qualified) ? 1 : 0,
        (bAccReal && !qualified) ? 1 : 0, (!bAccReal && qualified) ? 1 : 0,
        cAcc ? 1 : 0, (cAcc && !qualified) ? 1 : 0, (!cAcc && qualified) ? 1 : 0
      ].join(","));
    }
  }
}
writeCsv("E8_baseline_grid.csv", GRID_HEAD, gridRows);

/* 汇总：三种判据 × 每个场景 / 全场景 */
const summaryRows = [];
const SUM_HEAD = "criterion,scope,n_cells,n_qualified,n_unsafe,n_accepted,FA,FR," +
  "false_accept_rate_pct,false_reject_rate_pct,total_misjudgment_rate_pct,precision_pct";
const CRITERIA = [
  { key: "baseline", acc: r => r.bAcc, fa: r => r.bAcc && !r.qualified, fr: r => !r.bAcc && r.qualified },
  { key: "baseline_realizedPDR", acc: r => r.bAccReal, fa: r => r.bAccReal && !r.qualified, fr: r => !r.bAccReal && r.qualified },
  { key: "contract", acc: r => r.cAcc, fa: r => r.cAcc && !r.qualified, fr: r => !r.cAcc && r.qualified },
];
const allKeys = Object.keys(gridData);
const scopes = [
  ["ALL", allKeys],
  // E7 已声明 tau=V=500 ms 为数值边界、仿真中不作结论依据；给出排除该列后的稳健口径
  ["EXCL_TAU500", allKeys.filter(k => gridData[k].tau !== 500)],
  ...Object.keys(SCENES).map(sk => [sk, allKeys.filter(k => k.startsWith(sk + "|"))])
];
for (const cr of CRITERIA) {
  for (const [scope, keys] of scopes) {
    const rows = keys.map(k => gridData[k]);
    const nq = rows.filter(r => r.qualified).length, nu = rows.length - nq;
    const acc = rows.filter(cr.acc).length;
    const fa = rows.filter(cr.fa).length, fr = rows.filter(cr.fr).length;
    summaryRows.push([
      cr.key, scope, rows.length, nq, nu, acc, fa, fr,
      pct(nu ? fa / nu * 100 : 0), pct(nq ? fr / nq * 100 : 0),
      pct((fa + fr) / rows.length * 100), pct(acc ? (acc - fa) / acc * 100 : 0)
    ].join(","));
    if (scope === "ALL") {
      console.log(`  [${cr.key}] 格点 ${rows.length} | 实际合格 ${nq} / 不安全 ${nu} | 判合格 ${acc} | ` +
        `FA ${fa} FR ${fr} | 误判为合格率 ${pct(nu ? fa / nu * 100 : 0)}% | ` +
        `总误判率 ${pct((fa + fr) / rows.length * 100)}%`);
    }
  }
}
writeCsv("E8_baseline_summary.csv", SUM_HEAD, summaryRows);

/* ===================== ② 200 种子 Wilson 95% 置信区间 ===================== */
/* 关键格点：tau=100 时 p=0/0.6/0.8/0.9（另补 0.1、0.7 便于对照契约 75.4%）；
 *           tau=500/600 时 p=0.1（E3 断崖口径）并补 0.6/0.9 看边界对丢包的敏感性。 */
const WILSON_CELLS = [];
for (const p of [0, 0.1, 0.6, 0.7, 0.8, 0.9]) WILSON_CELLS.push({ tau: 100, p });
for (const tau of [500, 600]) for (const p of [0.1, 0.6, 0.9]) WILSON_CELLS.push({ tau, p });
const wilsonRows = [];
const WIL_HEAD = "scene,tau_ms,loss_pct,n,safe_k,safe_rate_pct,safe_ci95_lo_pct,safe_ci95_hi_pct," +
  "miss_k,miss_rate_pct,miss_ci95_lo_pct,miss_ci95_hi_pct," +
  "safe30_k,safe30_rate_pct,miss30_k,miss30_rate_pct,margin_mean_s";
console.log("=== E8 ② 开始：关键格点扩到 200 种子 + Wilson 95% CI ===");
for (const sk of Object.keys(SCENES)) {
  const sc = SCENES[sk];
  for (const c of WILSON_CELLS) {
    const cfg = cfgOf({ loss: c.p, tau: c.tau });
    const a = aggregate(sc, cfg, N200, null, N30);
    const sCI = wilson(a.safe, N200), mCI = wilson(a.miss, N200);
    wilsonRows.push([sk, c.tau, Math.round(c.p * 100), N200,
      a.safe, pct(a.safeRate), f2(sCI[0]), f2(sCI[1]),
      a.miss, pct(a.missRate), f2(mCI[0]), f2(mCI[1]),
      a.subSafe, pct(a.subSafeRate), a.subMiss, pct(a.subMissRate), f3(a.margin)].join(","));
    if (sk === "fcw") {
      console.log(`  FCW tau=${String(c.tau).padStart(3)} p=${c.p.toFixed(1)} n=200 | ` +
        `safe ${pct(a.safeRate)}% [${f2(sCI[0])}, ${f2(sCI[1])}] | ` +
        `miss ${pct(a.missRate)}% [${f2(mCI[0])}, ${f2(mCI[1])}] | 30种子 safe ${pct(a.subSafeRate)}%`);
    }
  }
}
writeCsv("E8_baseline_wilson.csv", WIL_HEAD, wilsonRows);

/* ===================== ③ Gilbert-Elliot burst 丢包 ===================== */
/* 参数（写入 CSV，逐条可查）：
 *   pG=0, pB=1；alpha=pbar/(L_B*(1-pbar)), beta=1/L_B, pi_B=pbar, L_G=1/alpha
 *   主实验 L_B=15 包（10 Hz 下 1.5 s），平稳初始化，200 种子。
 *   三组：MAIN(tau=100, 5 档 pbar, iid vs GE, 3 场景)、
 *         C0(tau=600> V, pbar=0.1/0.6, iid vs GE, FCW)、
 *         SENS(tau=100, pbar=0.3, L_B=5/10/15/25, GE, FCW)。
 */
const BURST_HEAD = "group,scene,model,loss_target_pct,loss_realized_pct,tau_ms," +
  "mean_bad_run_pkts,mean_good_run_pkts,alpha,beta,pi_bad,p_good,p_bad,n_seeds," +
  "safe_rate_pct,miss_rate_pct,margin_mean_s,blind_rate_pct," +
  "blind_runs_n,blind_run_mean_frames,blind_run_p50_frames,blind_run_p95_frames," +
  "blind_run_max_frames,blind_run_max_s,frac_runs_ge_W," +
  "pdr_nominal_pct,pdr_realized_pct,mean_delay_ms," +
  "actual_qualified,baseline_accept,baseline_FA,contract_accept,contract_FA";
const burstRows = [], runHistRows = [];
const RUN_HIST_HEAD = "group,scene,model,loss_target_pct,tau_ms,mean_bad_run_pkts,blind_run_frames,run_count";

function burstCondition(group, sk, model, pbar, tau, L_B, nSeeds) {
  const sc = SCENES[sk], cfg = cfgOf({ loss: pbar, tau });
  const geConf = model === "ge" ? { pbar, L_B } : null;
  const a = aggregate(sc, cfg, nSeeds, geConf, 0);
  const st = a.geStats, rs = runStats(a.runs);
  const pdrNom = 100 * (1 - pbar), pdrReal = 100 * (1 - a.realizedLoss);
  const qualified = a.safeRate >= QUALIFY_SAFE;
  const bAcc = pdrNom >= PDR_BASELINE_MIN && tau <= DELAY_BASELINE_MAX;
  const cAcc = tau <= V_MINUS_EPS && pbar <= P_CONTRACT;
  const L_B_out = model === "ge" ? L_B : "";
  burstRows.push([
    group, sk, model, pct(pbar * 100), f3(a.realizedLoss * 100), tau,
    L_B_out, model === "ge" ? f2(st.L_G) : "",
    model === "ge" ? f3(st.alpha) : "", model === "ge" ? f3(st.beta) : "",
    model === "ge" ? f3(st.piBad) : "", model === "ge" ? st.pG : "", model === "ge" ? st.pB : "",
    nSeeds, pct(a.safeRate), pct(a.missRate), f3(a.margin), pct(a.blind),
    rs.count, f2(rs.mean), rs.p50, rs.p95, rs.max, f2(rs.maxS), f3(rs.fracGeW),
    pct(pdrNom), pct(pdrReal), tau,
    qualified ? 1 : 0, bAcc ? 1 : 0, (bAcc && !qualified) ? 1 : 0,
    cAcc ? 1 : 0, (cAcc && !qualified) ? 1 : 0
  ].join(","));
  // 连续失明段长度分布（逐长度计数）
  const hist = new Map();
  for (const L of a.runs) hist.set(L, (hist.get(L) || 0) + 1);
  for (const L of [...hist.keys()].sort((x, y) => x - y)) {
    runHistRows.push([group, sk, model, pct(pbar * 100), tau, L_B_out, L, hist.get(L)].join(","));
  }
  return { a, rs, qualified, bAcc, cAcc, pdrReal };
}

console.log("=== E8 ③ 开始：Gilbert-Elliot burst 丢包（L_B=15 包, pG=0/pB=1, 200 种子）===");
const MAIN_PBARS = [0.1, 0.3, 0.6, 0.8, 0.9], L_MAIN = 15;
const mainRes = [];
for (const sk of Object.keys(SCENES)) {
  for (const pbar of MAIN_PBARS) {
    const iid = burstCondition("MAIN", sk, "iid", pbar, 100, L_MAIN, N200);
    const ge = burstCondition("MAIN", sk, "ge", pbar, 100, L_MAIN, N200);
    mainRes.push({ sk, pbar, iid, ge });
    if (sk === "fcw") {
      console.log(`  FCW pbar=${pbar.toFixed(1)} tau=100 | iid safe ${pct(iid.a.safeRate)}% miss ${pct(iid.a.missRate)}% ` +
        `失明 ${pct(iid.a.blind)}% 最长盲段 ${f2(iid.rs.maxS)}s | ` +
        `GE safe ${pct(ge.a.safeRate)}% miss ${pct(ge.a.missRate)}% 失明 ${pct(ge.a.blind)}% ` +
        `最长盲段 ${f2(ge.rs.maxS)}s >=W占比 ${f3(ge.rs.fracGeW)} | ` +
        `实测丢包 ${f3(ge.a.realizedLoss * 100)}%`);
    }
  }
}
// C0 校验：tau > V 时，burst 丢包下是否仍然 100% 漏警
for (const pbar of [0.1, 0.6]) {
  burstCondition("C0", "fcw", "iid", pbar, 600, L_MAIN, N200);
  const g = burstCondition("C0", "fcw", "ge", pbar, 600, L_MAIN, N200);
  console.log(`  [C0] tau=600ms>V, pbar=${pbar.toFixed(1)} GE | safe ${pct(g.a.safeRate)}% ` +
    `miss ${pct(g.a.missRate)}% 失明 ${pct(g.a.blind)}%`);
}
// 突发长度敏感性
for (const L_B of [5, 10, 15, 25]) {
  const g = burstCondition("SENS", "fcw", "ge", 0.3, 100, L_B, N200);
  console.log(`  [SENS] L_B=${String(L_B).padStart(2)} 包, pbar=0.3 | safe ${pct(g.a.safeRate)}% ` +
    `miss ${pct(g.a.missRate)}% 最长盲段 ${f2(g.rs.maxS)}s >=W占比 ${f3(g.rs.fracGeW)}`);
}
writeCsv("E8_baseline_burst.csv", BURST_HEAD, burstRows);
writeCsv("E8_baseline_burst_runs.csv", RUN_HIST_HEAD, runHistRows);

/* 连续失明段长度分桶汇总：把逐长度计数按帧数区间求和，便于报告直接引用 */
const HIST_BUCKETS = [[1, 5], [6, 15], [16, 29], [30, 59], [60, Infinity]];
const HIST_HEAD = "group,scene,model,loss_target_pct,tau_ms,mean_bad_run_pkts,bucket_lo_frames,bucket_hi_frames,run_count,run_pct,total_runs";
const histGroups = new Map();
for (const line of runHistRows) {
  const c = line.split(",");
  const key = [c[0], c[1], c[2], c[3], c[4], c[5]].join("|");
  const L = +c[6], n = +c[7];
  if (!histGroups.has(key)) histGroups.set(key, { meta: c.slice(0, 6), counts: HIST_BUCKETS.map(() => 0), total: 0 });
  const g = histGroups.get(key);
  g.total += n;
  for (let i = 0; i < HIST_BUCKETS.length; i++) {
    if (L >= HIST_BUCKETS[i][0] && L <= HIST_BUCKETS[i][1]) { g.counts[i] += n; break; }
  }
}
const histRows = [];
for (const g of histGroups.values()) {
  for (let i = 0; i < HIST_BUCKETS.length; i++) {
    const b = HIST_BUCKETS[i];
    histRows.push([...g.meta, b[0], b[1] === Infinity ? "inf" : b[1],
      g.counts[i], f2(g.total ? g.counts[i] / g.total * 100 : 0), g.total].join(","));
  }
}
writeCsv("E8_baseline_burst_hist.csv", HIST_HEAD, histRows);

/* ===================== 与 E6 的位一致交叉校验 ===================== */
function stripBom(t) { return t.replace(/^\ufeff/, ""); }
let checkLine = "E6 一致性校验：跳过（未找到 数据/预警可行域_heatmap.csv）";
const e6Path = path.join(OUT, "预警可行域_heatmap.csv");
if (fs.existsSync(e6Path)) {
  const lines = stripBom(fs.readFileSync(e6Path, "utf8")).trim().split(/\r?\n/);
  const head = lines[0].split(","), ix = n => head.indexOf(n);
  const e6 = new Map();
  for (const l of lines.slice(1)) {
    const c = l.split(",");
    if (c[ix("scene")] !== "fcw") continue;
    e6.set(`${c[ix("loss_pct")]}|${c[ix("tau_ms")]}`, {
      safe: +c[ix("safe_rate_pct")], miss: +c[ix("miss_rate_pct")], margin: +c[ix("margin_mean_s")]
    });
  }
  let ok = 0, total = 0, worst = 0;
  for (const tau of TAUS) for (const loss of LOSSES) {
    const r = gridData[`fcw|${loss}|${tau}`], e = e6.get(`${loss}|${tau}`);
    if (!e) continue;
    total++;
    worst = Math.max(worst, Math.abs(r.safeRate - e.safe), Math.abs(r.missRate - e.miss));
    if (Math.abs(r.safeRate - e.safe) < 0.051 && Math.abs(r.missRate - e.miss) < 0.051) ok++;
  }
  checkLine = `E6 一致性校验：FCW ${ok}/${total} 格点 safe/miss 完全一致（最大偏差 ${worst.toFixed(3)} pp）`;
  console.log(`=== ${checkLine} ===`);
} else {
  console.log(`=== ${checkLine} ===`);
}

console.log("\n--- 关键结论数字（全部来自上述 CSV）---");
const bFA = allKeys.filter(k => gridData[k].bAcc && !gridData[k].qualified).length;
const bFR = allKeys.filter(k => !gridData[k].bAcc && gridData[k].qualified).length;
const cFA = allKeys.filter(k => gridData[k].cAcc && !gridData[k].qualified).length;
const cFR = allKeys.filter(k => !gridData[k].cAcc && gridData[k].qualified).length;
const nUnsafe = allKeys.filter(k => !gridData[k].qualified).length;
const nQual = allKeys.length - nUnsafe;
console.log(`baseline: 误判为合格(FA) ${bFA}/${nUnsafe} = ${pct(nUnsafe ? bFA / nUnsafe * 100 : 0)}%；` +
  `误判为不合格(FR) ${bFR}/${nQual}；总误判率 ${pct((bFA + bFR) / allKeys.length * 100)}%`);
console.log(`contract: 误判为合格(FA) ${cFA}/${nUnsafe} = ${pct(nUnsafe ? cFA / nUnsafe * 100 : 0)}%；` +
  `误判为不合格(FR) ${cFR}/${nQual}；总误判率 ${pct((cFA + cFR) / allKeys.length * 100)}%`);
console.log("已写出 6 个 CSV：E8_baseline_grid / summary / wilson / burst / burst_runs / burst_hist");
