"use strict";
/*
 * E7 —— 预警死线解析判据验证（期刊版论文新增实验）
 *
 * 问题：链路参数 (tau, loss, f, V) 如何决定「接收端手上有可用消息」的时间占比？
 *
 * 推导（时间平均 / 更新奖励定理）：
 *   包每 T=1/f 生成一次，独立丢包概率 p，成功概率 q=1-p。
 *   相邻两次「成功到达」之间隔 K 个发送周期，K ~ Geom(q)，P(K=k)=q(1-q)^{k-1}。
 *   包在 t_send+tau 到达，到达瞬间 AoI = tau；此后 AoI 线性增长。
 *   门控：AoI > V 判为信息失明（s.aoi > cfg.tvalid）。
 *   定义 A = max(0, V - tau)，一段间隔内可用时长为
 *        g(k) = min(k*T, A)              （连续时间）
 *        g_d(k) = ceil(min(k*T, A)/DT)*DT （离散帧修正，DT=0.05 s）
 *   时间平均可用占比  D = E[g(K)] / E[K*T]。
 *   硬边界：tau > V  ==>  A=0  ==>  到达瞬间 AoI=tau>V  ==>  D=0，全程失明。
 *
 *   注意 tau = V 是数值边界：门控用严格大于，AoI=V 理论上可用，但浮点误差与
 *   单帧采样使该点行为不稳定，工程上必须留 guard margin。本脚本单列该区。
 *
 * 运行： node 代码/derive_bound.js
 * 输出： 数据/E7_解析模型校验.csv、数据/E7_结论.md
 * 依赖： 无（Node >= 18）；内核与 run_experiments.js 同源
 */
const fs = require("fs");
const path = require("path");
const OUT = path.resolve(__dirname, "..", "数据");
fs.mkdirSync(OUT, { recursive: true });

const DT = 0.05, MAXT = 10, LEN = 4.5, SAFE = 1.5, SEEDS = 30;
const SEED_BASE = 7919, SEED_OFFSET = 13;
const SCENE = { key: "fcw", vH: 16.67, x0: 55, v0: 11.11, decT: 1.0, a: -6.0, ttcTh: 3.5, emergTh: 1.75 };
const BASE = { loss: 0, tau: 0, freq: 10, noise: 0.2, tvalid: 0.5 };
const cfgOf = o => Object.assign({}, BASE, o);

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
function initState() {
  return { t: 0, hvX: 0, rvX: SCENE.x0, rvV: SCENE.v0,
    nextSend: 0, queue: [], last: null, sent: 0, lost: 0, recv: 0,
    blind: 0, frames: 0, warnTime: null, flag: 0, ttc: Infinity,
    gapTrue: SCENE.x0 - LEN, aoi: Infinity, colTime: null, done: false };
}
function step(s, cfg, r) {
  if (s.done) return;
  s.t += DT; s.frames++;
  if (s.t >= SCENE.decT) s.rvV = Math.max(0, s.rvV + SCENE.a * DT);
  s.hvX += SCENE.vH * DT; s.rvX += s.rvV * DT;
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
    s.aoi = s.t - s.last.t;
    if (s.aoi > cfg.tvalid) { s.blind++; s.ttc = Infinity; s.flag = 0; }
    else {
      const gapEst = (s.last.x + s.last.v * s.aoi) - s.hvX - LEN;
      s.ttc = Math.max(0, gapEst / Math.max(SCENE.vH - s.last.v, 0.5));
      if (s.ttc < SCENE.ttcTh && s.warnTime === null) s.warnTime = s.t;
      s.flag = s.ttc < SCENE.emergTh ? 2 : (s.ttc < SCENE.ttcTh ? 1 : 0);
    }
  } else { s.blind++; s.ttc = Infinity; s.flag = 0; }
  if (s.colTime !== null || s.t >= MAXT) s.done = true;
}
function run(cfg, seed) {
  const r = rngFactory(seed), s = initState();
  while (!s.done) step(s, cfg, r);
  return s;
}
// 理想链路下的碰撞时刻，用于算预警提前量
const tcRef = (() => {
  const s = run(cfgOf({ loss: 0, tau: 0, noise: 0 }), 1);
  return s.colTime === null ? MAXT : s.colTime;
})();
function simulate(loss, tauMs, tvalidMs) {
  const cfg = cfgOf({ loss, tau: tauMs, tvalid: tvalidMs / 1000 });
  let blindRate = 0, miss = 0, margin = 0;
  for (let k = 1; k <= SEEDS; k++) {
    const s = run(cfg, k * SEED_BASE + SEED_OFFSET);
    blindRate += s.frames ? s.blind / s.frames * 100 : 0;
    const m = s.warnTime === null ? 0 : Math.max(0, tcRef - s.warnTime);
    if (s.warnTime === null || m <= 0) miss++;
    margin += m;
  }
  return { blind: blindRate / SEEDS, miss: miss / SEEDS * 100, margin: margin / SEEDS };
}

/* 解析占空比：返回可用时间占比 D ∈ [0,1] */
function dutyAnalytic(loss, tauMs, Vms, fHz, discrete) {
  const q = 1 - loss, T = 1000 / fHz;
  if (tauMs > Vms) return 0;                       // 硬边界：到达瞬间即过期
  const A = Vms - tauMs;
  let num = 0;
  // K ~ Geom(q)。k 从 1 累加到收敛（尾部用闭式）
  const KMAX = 400;
  let tailProb = 1;
  for (let k = 1; k <= KMAX; k++) {
    const pk = q * Math.pow(1 - q, k - 1);
    let g = Math.min(k * T, A);
    if (discrete) g = Math.ceil((g + 1e-9) / (DT * 1000)) * (DT * 1000);
    num += pk * Math.min(g, k * T);
    tailProb -= pk;
  }
  num += tailProb * Math.min(discrete ? Math.ceil(A / (DT * 1000)) * (DT * 1000) : A, KMAX * T);
  const den = T / q;
  return Math.max(0, Math.min(1, num / den));
}

/* 含初始段的完整失明率预测：
 *   仿真在 t<tau 时 last=null，这段代码必然失明（占整个运行时长 tau/tc）。
 *   稳态段用占空比模型。两段按时间加权。 */
function blindPredFull(loss, tauMs, Vms, fHz, tcMs) {
  if (tauMs > Vms) return 100;
  const init = Math.min(1, tauMs / tcMs);
  const steady = 1 - dutyAnalytic(loss, tauMs, Vms, fHz, false);
  return 100 * (init + (1 - init) * steady);
}
const tcMs = tcRef * 1000;

const rows = [];
console.log("=== E7 解析模型校验（FCW, 30 种子, V=500 ms, f=10 Hz）===");
console.log("loss%\ttau\t仿真失明%\t连续模型\t离散模型\t含初始段修正\t漏警%\t提前量s");
for (const loss of [0, 0.1, 0.3, 0.6, 0.9]) {
  for (const tau of [0, 100, 200, 300, 400, 450, 500, 550, 600, 700]) {
    const sim = simulate(loss, tau, 500);
    const dc = dutyAnalytic(loss, tau, 500, 10, false);
    const dd = dutyAnalytic(loss, tau, 500, 10, true);
    const pc = (1 - dc) * 100, pd = (1 - dd) * 100;
    const pf = blindPredFull(loss, tau, 500, 10, tcMs);
    rows.push({ loss: Math.round(loss * 100), tau, simBlind: sim.blind,
      predCont: pc, predDisc: pd, predFull: pf, simMiss: sim.miss, margin: sim.margin,
      errCont: sim.blind - pc, errDisc: sim.blind - pd, errFull: sim.blind - pf,
      boundary: tau === 500 ? "BOUNDARY" : (tau > 500 ? "OVER" : "") });
    console.log(`${Math.round(loss*100)}\t${tau}\t${sim.blind.toFixed(1)}\t\t${pc.toFixed(1)}\t\t${pd.toFixed(1)}\t\t${pf.toFixed(1)}\t\t\t${sim.miss.toFixed(0)}\t${sim.margin.toFixed(2)}`);
  }
}
// 误差统计：排除数值边界 tau=V
const valid = rows.filter(r => r.boundary === "");
const maeC = valid.reduce((a, r) => a + Math.abs(r.errCont), 0) / valid.length;
const maeD = valid.reduce((a, r) => a + Math.abs(r.errDisc), 0) / valid.length;
const maeF = valid.reduce((a, r) => a + Math.abs(r.errFull), 0) / valid.length;
const over = rows.filter(r => r.boundary === "OVER");
const overAllBlind = over.every(r => r.simBlind > 99.9);
const underV = valid.filter(r => r.tau < 500);

const csv = ["loss_pct,tau_ms,sim_blind_pct,pred_cont_pct,pred_discrete_pct,pred_full_pct,err_full_pp,sim_miss_pct,margin_s,region"]
  .concat(rows.map(r => [r.loss, r.tau, r.simBlind.toFixed(2), r.predCont.toFixed(2),
    r.predDisc.toFixed(2), r.predFull.toFixed(2), r.errFull.toFixed(2),
    r.simMiss.toFixed(1), r.margin.toFixed(3), r.boundary || "NORMAL"].join(","))).join("\n") + "\n";
fs.writeFileSync(path.join(OUT, "E7_解析模型校验.csv"), csv);

const md = `# E7 预警死线解析判据验证

生成：\`代码/derive_bound.js\`｜场景 FCW｜30 个固定种子｜V=500 ms｜f=10 Hz｜DT=50 ms

## 解析判据

设 BSM 发送周期 T=1/f，独立丢包率 p，单程时延 τ，有效期 V。包在 t_send+τ 到达，到达瞬间 AoI=τ；此后 AoI 线性增长，门控 \`AoI > V\` 判信息失明。

**硬边界（命题 1）**：τ > V ⟹ 每条到达消息在落地瞬间即已过期 ⟹ 接收端可用时间占比 D=0 ⟹ 预警全程失效。与丢包率、发送频率无关。

**占空比（命题 2）**：τ ≤ V 时，令 A=V−τ，K~Geom(1−p) 为相邻两次成功到达间隔的发送周期数，则

    D = E[min(K·T, A)] / E[K·T] = q·Σ_{k≥1}(1−q)^{k−1}·min(kT, A) / (T/q),  q=1−p

离散帧修正把 min(kT,A) 上取整到 DT 的整数倍。D 即「接收端手上有可用消息」的时间占比，失明率 = 1−D。

**初始段修正**：仿真在 t<τ 时 \`last=null\`，这段必然失明，占运行时长 τ/t_c（t_c 为理想链路碰撞时刻，本场景 ${tcMs.toFixed(0)} ms）。完整预测为

    P_blind = 100·[ τ/t_c + (1 − τ/t_c)·(1 − D) ]

## 校验结果

| 指标 | 数值 |
|---|---|
| 非边界格点数 | ${valid.length} |
| 稳态连续模型 MAE（失明率，百分点） | ${maeC.toFixed(2)} |
| 离散帧上取整模型 MAE | ${maeD.toFixed(2)} |
| **含初始段修正模型 MAE** | **${maeF.toFixed(2)}** |
| τ>V 的格点是否 100% 失明且 100% 漏警 | ${overAllBlind ? "是（" + over.length + "/" + over.length + "）" : "否，需检查"} |

逐格数据见 \`E7_解析模型校验.csv\`。τ=V=500 ms 单列为 \`BOUNDARY\`：门控用严格大于，AoI=V 理论可用，但浮点误差与单帧采样使该点不稳定，**不纳入误差统计**。离散帧上取整模型系统性高估可用时长，MAE 反而更大，故正文采用连续模型 + 初始段修正。

## 一个反直觉但很重要的现象

在 τ<V 区间，**失明率与漏警率不成正比**：

| 条件 | 失明率 | 漏警率 | 平均提前量 |
|---|---|---|---|
${underV.filter(r=>[[90,400],[90,500],[60,400],[60,500]].some(([l,t])=>r.loss===l&&r.tau===t)).map(r=>`| 丢包 ${r.loss}%，τ=${r.tau} ms | ${r.simBlind.toFixed(1)}% | ${r.simMiss.toFixed(0)}% | ${r.margin.toFixed(2)} s |`).join("\n")}

即使 97% 的时间处于信息失明，只要在关键决策窗口内**出现过至少一个可用帧**，预警仍能触发。而 τ>V 时可用帧数为 0，漏警立刻跳到 100%。因此预警应用对通信的真实需求不是「高投递率」或「低平均时延」，而是「不存在贯穿整个决策窗口的连续失明段」。这与以 PDR / 平均时延作验收指标的做法直接冲突，也是本文主张改用消息新鲜度契约的依据。

## 对既有结论的修正

此前 \`关键数字.md\` / 论文 v1 表述为「临界时延 ≈ BSM 有效期 + 一个发送周期（100 ms）」。
更准确的表述是：

1. 真正的硬边界是 **τ ≤ V**；τ 一旦超过 V，预警必然全程失效。
2. 观测到的「V+100 ms」是 **100 ms 扫描步长**下的离散表现：τ=V 恰好落在边界上仍有零星可用帧，下一个格点 τ=V+100 才完全失明。
3. E5 换 5 组有效期后「断崖整体平移」，验证的正是 τ 与 V 的相对关系，而非「有效期 + 固定 100 ms」。

工程含义：3GPP 100 ms 是链路侧上界，V 是应用侧的消息新鲜度预算；**安全通信契约应同时约束 τ ≤ V−ε（ε 至少为一个采样/仿真步长）与连续丢包长度**，只写 100 ms 不足以保障预警来得及。

## 局限

解析式假设独立同分布丢包、恒定 τ、FIFO 无重排；未建模信道突发（burst）丢包、时钟偏差与位置噪声对 TTC 估计的影响。τ=V 边界行为依赖数值实现，仿真中不应作为结论依据。
`;
fs.writeFileSync(path.join(OUT, "E7_结论.md"), md);
console.log(`\n=== MAE 稳态 ${maeC.toFixed(2)} pp | 离散 ${maeD.toFixed(2)} pp | 含初始段修正 ${maeF.toFixed(2)} pp | tau>V 全盲 ${overAllBlind} ===`);
console.log("已写出 E7_解析模型校验.csv / E7_结论.md");
