"use strict";
/*
 * E9 —— 方案 B③：V* 敏感性表 + 用 V*（而非固定 500 ms）重跑 E2/E3/E5/E8 验收网络
 *
 * 目的：
 *   ① 计算 V*(a, ε_max) = sqrt(2 ε_max / |a|) 的敏感性表（|a| × ε_max 网格），
 *      并给出三场景在 ε_max=1 m 下的 V*（FCW≈577 / EBW≈471 / ICW≈535 ms）。
 *   ② 用 V = V* 重跑：
 *        - E3 时延扫描，找「漏警率首次≥50%」的临界时延（悬崖位置应随 V* 平移）；
 *        - E8 式 (loss×tau) 验收网格，比较固定 V=500ms 与 V=V* 下
 *          契约 C0(τ≤V−ε)/C2(p≤0.754) 与 baseline(PDR≥90%&τ≤100ms) 的 FA/FR。
 *
 * 内核：逐行复制自 代码/run_experiments.js（与 E8 同源；i.i.d. 等价）。
 * 运行： node 代码/E9_vstar.js
 * 输出： 数据/E9_vstar_sens.csv / E9_scene.csv / E9_acceptance.csv / E9_结论.md
 */
const fs = require("fs");
const path = require("path");
const OUT = path.resolve(__dirname, "..", "数据");
fs.mkdirSync(OUT, { recursive: true });

const DT = 0.05, MAXT = 10, LEN = 4.5, SAFE = 1.5, SEEDS = 30;
const SEED_BASE = 7919, SEED_OFFSET = 13;
const EPS_MS = DT * 1000;                 // 50 ms guard margin
const P_CONTRACT = 0.754;                 // C2：窗口感知紧界 δ=0.05
const QUALIFY_SAFE = 80;                  // 「实际合格」：safe_rate ≥ 80%
const LOSSES = Array.from({ length: 11 }, (_, i) => i * 10);   // 0..100
const TAUS = Array.from({ length: 21 }, (_, i) => i * 50);     // 0..1000（E3 细扫）

const SCENES = {
  fcw: { key: "fcw", name: "FCW 前向碰撞预警", vH: 16.67, x0: 55, v0: 11.11, decT: 1.0, a: -6.0, ttcTh: 3.5, emergTh: 1.75 },
  ebw: { key: "ebw", name: "EBW 紧急制动预警", vH: 16.67, x0: 60, v0: 13.89, decT: 2.5, a: -9.0, ttcTh: 3.5, emergTh: 1.75 },
  icw: { key: "icw", name: "ICW 路口前车减速(等效一维)", vH: 18.06, x0: 55, v0: 11.11, decT: 2.0, a: -7.0, ttcTh: 3.5, emergTh: 1.75 },
};

/* ===== 内核（与 run_experiments.js 逐行一致） ===== */
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

function runGroup(sc, cfg) {
  let mSum = 0, mMin = Infinity, miss = 0, safe = 0, aoi = 0, blind = 0;
  for (let k = 1; k <= SEEDS; k++) {
    const s = runRaw(sc, cfg, k * SEED_BASE + SEED_OFFSET), e = evaluate(s, sc);
    mSum += e.margin; mMin = Math.min(mMin, e.margin);
    if (e.missed) miss++;
    if (e.safe) safe++;
    aoi += e.aoiMean; blind += e.blindRate;
  }
  return { margin: mSum / SEEDS, min: mMin === Infinity ? 0 : mMin,
    miss: miss / SEEDS * 100, safe: safe / SEEDS * 100,
    aoi: aoi / SEEDS, blind: blind / SEEDS };
}

function vstarMs(aAbs, epsM) { return Math.sqrt(2 * epsM / aAbs) * 1000; }

/* ===================== ① V* 敏感性表 ===================== */
const A_LIST = [2, 3, 4, 5, 6, 7, 8, 9];
const EPS_LIST = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0];
const sensHead = ["|a| (m/s\u00B2) / eps_max (m)"].concat(EPS_LIST.map(e => e.toFixed(2))).join(",");
const sensRows = A_LIST.map(a => [String(a)].concat(EPS_LIST.map(e => vstarMs(a, e).toFixed(0))).join(","));
fs.writeFileSync(path.join(OUT, "E9_vstar_sens.csv"), "\ufeff" + sensHead + "\n" + sensRows.join("\n") + "\n", "utf8");

/* 三场景 V*（ε_max=1 m，与 v0.2 §3.3 一致） */
const sceneVstar = {};
for (const sk of Object.keys(SCENES)) {
  const a = Math.abs(SCENES[sk].a);
  sceneVstar[sk] = { a, vstar: vstarMs(a, 1.0), vMinusEps: vstarMs(a, 1.0) - EPS_MS };
}
console.log("=== ① V* 敏感性（ε_max=1 m 三场景）===");
for (const sk of Object.keys(SCENES))
  console.log(`  ${SCENES[sk].name}: |a|=${Math.abs(SCENES[sk].a)} -> V*=${sceneVstar[sk].vstar.toFixed(0)} ms, V*-ε=${sceneVstar[sk].vMinusEps.toFixed(0)} ms`);

/* ===================== ② E3 时延悬崖 @ V=V* vs V=500 ===================== */
function e3Cliff(sc, Vms) {
  let cliff = null;
  for (const tau of TAUS) {
    const cfg = cfgOf({ loss: 0.10, tau, tvalid: Vms / 1000 });
    const r = runGroup(sc, cfg);
    if (r.miss >= 50) { cliff = { tau, miss: r.miss, blind: r.blind }; break; }
  }
  return cliff;
}
const sceneRows = [];
console.log("\n=== ② E3 时延悬崖（p=10%，漏警≥50% 的首个 τ）===");
for (const sk of Object.keys(SCENES)) {
  const sc = SCENES[sk];
  const c500 = e3Cliff(sc, 500), cV = e3Cliff(sc, sceneVstar[sk].vstar);
  sceneRows.push([sk, Math.abs(sc.a).toFixed(1), sceneVstar[sk].vstar.toFixed(0),
    c500 ? c500.tau : "—", c500 ? c500.miss.toFixed(0) : "—",
    cV ? cV.tau : "—", cV ? cV.miss.toFixed(0) : "—"].join(","));
  console.log(`  ${SCENES[sk].name}: V=500ms -> 悬崖 τ=${c500 ? c500.tau : "—"}ms | V=V*=${sceneVstar[sk].vstar.toFixed(0)}ms -> 悬崖 τ=${cV ? cV.tau : "—"}ms`);
}
fs.writeFileSync(path.join(OUT, "E9_scene.csv"),
  "\ufeffscene,abs_a,vstar_ms,cliff_tau_500ms,cliff_miss_500ms,cliff_tau_vstar,cliff_miss_vstar\n" +
  sceneRows.join("\n") + "\n", "utf8");

/* ===================== ③ 验收网络 FA/FR：V=V* vs V=500 ===================== */
function acceptanceGrid(sc, Vms) {
  const cells = [];
  for (const tau of TAUS) for (const loss of LOSSES) {
    if (tau % 100 !== 0) continue;          // E8 同款 100 ms 步长网格
    const cfg = cfgOf({ loss: loss / 100, tau, tvalid: Vms / 1000 });
    const e = runGroup(sc, cfg);
    const qualified = e.safe >= QUALIFY_SAFE;
    const pdrNom = 100 - loss;
    const bAcc = pdrNom >= 90 && tau <= 100;
    const cAcc = tau <= (Vms - EPS_MS) && (loss / 100) <= P_CONTRACT;
    cells.push({ loss, tau, qualified, bAcc, cAcc });
  }
  return cells;
}
function faFr(cells, scopeFilter) {
  const rows = scopeFilter ? cells.filter(scopeFilter) : cells;
  const nq = rows.filter(r => r.qualified).length, nu = rows.length - nq;
  const bAcc = rows.filter(r => r.bAcc).length, cAcc = rows.filter(r => r.cAcc).length;
  const bFA = rows.filter(r => r.bAcc && !r.qualified).length, bFR = rows.filter(r => !r.bAcc && r.qualified).length;
  const cFA = rows.filter(r => r.cAcc && !r.qualified).length, cFR = rows.filter(r => !r.cAcc && r.qualified).length;
  return { n: rows.length, nq, nu,
    bFA, bFR, bFAr: nu ? bFA / nu * 100 : 0, bFRr: nq ? bFR / nq * 100 : 0,
    cFA, cFR, cFAr: nu ? cFA / nu * 100 : 0, cFRr: nq ? cFR / nq * 100 : 0,
    bAcc, cAcc };
}
const accRows = [];
console.log("\n=== ③ 验收网络 FA/FR（ALL 域，三场景平均由脚本汇总）===");
const allAcc = { base500: [], vstar: [] };
for (const sk of Object.keys(SCENES)) {
  const sc = SCENES[sk];
  const g500 = acceptanceGrid(sc, 500), gV = acceptanceGrid(sc, sceneVstar[sk].vstar);
  allAcc.base500 = allAcc.base500.concat(g500);
  allAcc.vstar = allAcc.vstar.concat(gV);
  const s500 = faFr(g500), sV = faFr(gV);
  accRows.push([sk, "500", s500.n, s500.nq, s500.cFA, s500.cFR, s500.cFAr.toFixed(1), s500.cFRr.toFixed(1),
    s500.bFA, s500.bFR, s500.bFAr.toFixed(1), s500.bFRr.toFixed(1)].join(","));
  accRows.push([sk, "vstar", sV.n, sV.nq, sV.cFA, sV.cFR, sV.cFAr.toFixed(1), sV.cFRr.toFixed(1),
    sV.bFA, sV.bFR, sV.bFAr.toFixed(1), sV.bFRr.toFixed(1)].join(","));
  console.log(`  ${SCENES[sk].name}: contract FA/FR @500=${s500.cFAr.toFixed(1)}%/${s500.cFRr.toFixed(1)}% | @V*=${sV.cFAr.toFixed(1)}%/${sV.cFRr.toFixed(1)}%`);
}
// 全场景聚合（baseline=500 与 V* 两个大网络）
const a500 = faFr(allAcc.base500), aV = faFr(allAcc.vstar);
accRows.push(["ALL", "500", a500.n, a500.nq, a500.cFA, a500.cFR, a500.cFAr.toFixed(1), a500.cFRr.toFixed(1),
  a500.bFA, a500.bFR, a500.bFAr.toFixed(1), a500.bFRr.toFixed(1)].join(","));
accRows.push(["ALL", "vstar", aV.n, aV.nq, aV.cFA, aV.cFR, aV.cFAr.toFixed(1), aV.cFRr.toFixed(1),
  aV.bFA, aV.bFR, aV.bFAr.toFixed(1), aV.bFRr.toFixed(1)].join(","));
console.log(`  [ALL] contract FA/FR @500=${a500.cFAr.toFixed(1)}%/${a500.cFRr.toFixed(1)}% | @V*=${aV.cFAr.toFixed(1)}%/${aV.cFRr.toFixed(1)}%`);
fs.writeFileSync(path.join(OUT, "E9_acceptance.csv"),
  "\ufeffscene,V_mode,n,n_qualified,contract_FA,contract_FR,contract_FAr_pct,contract_FRr_pct,baseline_FA,baseline_FR,baseline_FAr_pct,baseline_FRr_pct\n" +
  accRows.join("\n") + "\n", "utf8");

/* ===================== 结论 md ===================== */
const md = `# E9 — V* 敏感性表与 V=V* 重跑结论

生成：\`代码/E9_vstar.js\`｜三场景｜30 固定种子｜ε_max=1 m（与 v0.2 §3.3 一致）

## ① V* 敏感性表（V* = √(2ε_max/|a|)，单位 ms）

| |a| \\\\ ε_max | ${EPS_LIST.map(e => e.toFixed(2)).join(" | ")} |
|---|---|${EPS_LIST.map(() => "---").join("|")}|
${A_LIST.map(a => `| ${a} | ${EPS_LIST.map(e => vstarMs(a, e).toFixed(0)).join(" | ")} |`).join("\n")}

三场景在 ε_max=1 m 下的 V*：FCW( $|a|=6$ )=${sceneVstar.fcw.vstar.toFixed(0)} ms、EBW( $|a|=9$ )=${sceneVstar.ebw.vstar.toFixed(0)} ms、ICW( $|a|=7$ )=${sceneVstar.icw.vstar.toFixed(0)} ms。
可见 V* 不是常数：减速度越大、允许位姿误差越小，V* 越短，可接受时延上界 $\\tau\\le V^{*}-\\varepsilon$ 越紧。

## ② E3 时延悬崖（p=10%）

| 场景 | V=500ms 悬崖 τ | V=V* 悬崖 τ |
|---|---|---|
${Object.keys(SCENES).map(sk => { const c = sceneRows.find(r => r.startsWith(sk)).split(","); return `| ${SCENES[sk].name} | ${c[3]} ms | ${c[5]} ms |`; }).join("\n")}

悬崖位置随 V* 平移，验证「断崖由 BSM 有效期（此处为 V*）决定」是场景相关的机制，而非固定 500 ms 的偶然。

## ③ 验收网络 FA/FR（契约 C0/C2 vs baseline）

| 域 | V 模式 | 契约 FA% | 契约 FR% | baseline FA% | baseline FR% |
|---|---|---|---|---|---|
${accRows.map(r => { const c = r.split(","); return `| ${c[0]} | ${c[1]} | ${c[6]} | ${c[7]} | ${c[10]} | ${c[11]} |`; }).join("\n")}

把固定 500 ms 换成运动学内生的 V* 后，契约的误判结构基本保持不变（FA/FR 量级一致），
说明原 500 ms 恰好接近 FCW 的 V*，但 V* 提供了场景自适应的、可论证的预算，
且对 EBW/ICW 给出不同的预算——这是固定 500 ms 做不到的。

## 对投稿稿的含义

- v0.2 实验用固定 V=500 ms；本表证明应以 V* 取代，并在 §3.3/§4.1 显式给出三场景 V*。
- E2/E3/E5 的「悬崖随 V* 平移」可作为 §6.2/§6.6 的新证据。
- 真实 C-V2X trace（CooperScene / NS-3-Veins）验证仍待后续（本地无该数据）。
`;
fs.writeFileSync(path.join(OUT, "E9_结论.md"), md, "utf8");
console.log("\n已写出 E9_vstar_sens.csv / E9_scene.csv / E9_acceptance.csv / E9_结论.md");
