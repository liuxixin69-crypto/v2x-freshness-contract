# When 100 ms Is Not Enough: An Information-Freshness Bound for V2X Collision Warning under Lossy Links

> **DRAFT NOTES — DELETE THIS BLOCK BEFORE SUBMISSION**
> 这是给作者看的中文说明，不进投稿版。
> 1. 本稿与期末课程论文**不是同一篇**：研究问题、理论分析（第 4 章全部）、图表组织、文字均为新写；仅复用 E1–E6 的仿真数据，并新增 E7。投稿时须在 cover letter 说明「部分仿真数据源于一项未公开发表的课程项目」。
> 2. 参考文献只列了 `文献/引用核实表_v0.1.md` 中标记「已核实」的 6 条。**任何标记「需复核」的工作都不得加进 References**，尤其不要沿用 `03` 文件里那条与原文冲突的 mAP 数值。
> 3. 标 `[TBD]` 的是投稿前必须补的：baseline 误判率实验、burst 丢包 trace、100+ 种子与置信区间、作者与单位信息、目标会议模板。第 7 章已主动写明这些局限。
> 4. 所有数字可用 `node 代码/run_experiments.js`、`gen_heatmap.js`、`derive_bound.js` 一条命令复现，逐种子 CSV 在 `数据/`。
> 5. 目标与档位选择见 `09_可发表论文_选题与投稿方案_v0.1.md`。

**Authors:** [TBD]　**Affiliation:** [TBD]

---

## Abstract

3GPP TS 22.185 requires an end-to-end latency of at most 100 ms for V2V messaging, and this bound is widely treated as the link-layer acceptance criterion for cooperative safety applications. We show that compliance with this bound is not sufficient for a warning to be issued in time. Reproducing three course-standard collision-warning scenarios (FCW, EBW, ICW) with 10 Hz BSM broadcasts under controlled loss, delay, rate reduction and pose noise, we derive and validate a closed-form freshness condition at the application layer. Because a packet generated at $t_s$ and delivered at $t_s+\tau$ already has age $\tau$ on arrival, any $\tau > V$ — where $V$ is the receiver's configurable validity budget for a state update — makes every arriving message stale at the instant it lands, and the warning fails with probability one, independent of packet loss and transmission rate. For $\tau \le V$, we derive the fraction of time during which a fresh update is available, $D = \mathbb{E}[\min(KT,A)]/\mathbb{E}[KT]$ with $A=V-\tau$ and $K\sim\mathrm{Geom}(1-p)$; adding the initial no-update transient yields a prediction of the blindness ratio with a mean absolute error of 4.44 percentage points over 30 grid cells. Across 16,200 independent runs we observe that a link fully compliant with the 100 ms bound still delivers only 56.7% timely warnings at 90% loss, while a receiver that is blind 97.6% of the time may still warn successfully — intermittent staleness is tolerable, a staleness gap spanning the decision window is not. We therefore replace packet-level KPIs with an explicit freshness contract, $\tau \le V-\varepsilon$ plus a bound on consecutive loss length, and solve the latter analytically: for $V=500$ ms, $T=100$ ms, $\tau=100$ ms and a 1.5 s decision window, a window-aware union bound gives $p \le 75.4\%$ at $\delta=0.05$, consistent with the measured feasible region.

**Index Terms** — C-V2X, basic safety message, forward collision warning, age of information, information freshness, safety contract, latency cliff.

---

## 1 Introduction

Cooperative safety applications extend a vehicle's perception beyond its field of view by periodically broadcasting state information over PC5 sidelink. In the forward-collision, emergency-brake and intersection-collision warning use cases, correctness depends not on whether a message eventually arrives, but on whether it arrives while a driver or controller can still act. Standardization captures part of this requirement numerically: 3GPP TS 22.185 [1] mandates a maximum end-to-end latency of 100 ms for V2V/V2P and V2I ([R-5.2.1-001], [R-5.2.1-003]), recommends 20 ms for pre-crash sensing ([R-5.2.1-002]), caps periodic transmission at ten messages per second per UE ([R-5.2.3-001]), and requires a communication range that affords the driver approximately four seconds of response time ([R-5.2.4-001]).

Engineering practice, however, usually validates the link rather than the application: packet delivery ratio (PDR), mean latency and throughput are measured and compared against these bounds. The four-second response-time clause is rarely translated into an application-level acceptance test. This is a gap, because a link with 100 ms mean latency can still leave a receiver holding a two-second-old position after a burst of consecutive losses, and a warning computed from that position is either late or absent.

Recent work has begun to argue that link-layer metrics are inadequate for cooperative, connected and automated mobility (CCAM). Marias-i-Parella et al. [3] build an evaluation methodology around age of information (AoI) with use-case-specific penalty functions. Rolich et al. [4] show in 5G NR-V2X Mode 2 that semi-persistent scheduling can produce long runs of consecutive losses, so that a configuration with higher PDR may have worse AoI. Real-world measurements from CooperScene [5] report 38.19% packet loss and 31.46 ms latency on commercial C-V2X radios. What is still missing is a **closed-form condition that maps link parameters to whether a specific warning algorithm will fire in time**, together with an experimental check of that condition.

This paper makes four contributions:

1. **A hard freshness bound.** We prove that $\tau > V$ implies zero usable updates and certain warning failure, independent of loss rate and beacon frequency, and verify it on 15/15 out-of-bound grid cells (Proposition 1, §4.1).
2. **A duty-cycle model.** For $\tau \le V$ we derive the fraction of time the receiver holds a fresh update and predict the blindness ratio with 4.44 percentage points MAE (Proposition 2, §4.2).
3. **A decoupling result.** We show experimentally and argue analytically that blindness ratio and miss ratio are not proportional: a receiver blind 97.6% of the time still warns in 80% of runs, because a warning needs only *one* fresh frame inside the decision window (Proposition 3, §4.3).
4. **A freshness contract.** We convert the analysis into two bounds on the admissible loss rate — a conservative per-gap bound and a window-aware union bound — and compare both against a two-dimensional feasible region measured over 110 parameter cells (§4.4, §6.5).

The remainder of the paper is organized as follows. §2 positions the work. §3 defines the model. §4 derives the three propositions and the contract. §5 describes the reproducible protocol, §6 reports results, §7 discusses threats to validity, and §8 concludes.

---

## 2 Related Work

**Standards and link-layer KPIs.** TS 22.185 [1] and the RAN-level survey TR 37.985 [6] specify latency, payload, rate and range requirements for LTE-V2X and NR-V2X. These documents define *transport* capabilities; they are explicitly agnostic to message types and do not specify how an application should decide that a received state is too old to use. Our work takes these bounds as inputs and asks what additional application-side condition is needed.

**Age of information.** Kaul, Yates and Gruteser [2] introduced the time-average age metric $\Delta(t)=t-u(t)$ and showed that the update rate minimizing age is neither the throughput-maximizing nor the delay-minimizing rate. AoI has since been widely used in vehicular networks, e.g. for random-access optimization and for hard peak-AoI scheduling. Marias-i-Parella et al. [3] are closest to our motivation: they state that conventional reliability and latency metrics "often fall short in capturing the true effectiveness" of CCAM at the application level, and propose AoI-based penalty functions and statistical indicators. Their contribution is a **general evaluation framework**; they do not derive a closed-form deadline for a concrete warning decision, nor do they characterize the shape of the feasible region in the (loss, delay) plane.

**Freshness versus reliability in V2X.** Rolich et al. [4] demonstrate a PDR–AoI trade-off in NR-V2X sidelink: persistence in semi-persistent scheduling creates bursts of consecutive losses and long inter-success gaps, so a lower-PDR dynamic scheme can achieve better AoI. This is a MAC-layer scheduling result. Our analysis starts one layer above: given a sequence of losses (i.i.d. in this first study), what does the *warning logic* tolerate? Our finding that long staleness gaps matter more than the average loss rate is consistent with their burst-loss observation, and it identifies the burst length as the quantity a safety contract should bound.

**Real C-V2X measurements.** CooperScene [5] is a multi-modal cooperative autonomy dataset with synchronized application-level C-V2X traces (three CAVs and one RSU, 10 Hz annotations), reporting 38.19% loss, 31.46 ms latency and 0.72 Mbps throughput. Its benchmark shows that cooperative perception accuracy degrades substantially under real links and that reducing bandwidth pressure alone is insufficient. Its endpoint is detection mAP; ours is the timing of a warning decision. We use their measured loss and delay as a sanity anchor for our parameter ranges, not as a direct comparison.

**Positioning.** Table I summarizes the distinction. To our knowledge, no prior work combines a freshness gate with a TTC-based warning rule into a provable deadline, verifies it against a two-dimensional parameter sweep, and quantifies the gap between a conservative per-message contract and a window-aware one.

*Table I — Comparison with related work (columns: closed-form deadline / warning-decision endpoint / 2-D feasible region / blindness–miss decoupling). [TBD: typeset as a table in the submission template.]*

---

## 3 System Model

### 3.1 Kinematics

We use a one-dimensional longitudinal model shared by all experiments. The host vehicle travels at constant speed $v_H$. The remote vehicle starts at gap $x_0$ with speed $v_0$ and, from $t \ge t_{dec}$, decelerates at constant $a<0$ until its speed reaches zero. Positions are $x_H(t)=v_H t$ and $x_R(t)$; the true gap is $g(t)=x_R(t)-x_H(t)-L$ with vehicle length $L=4.5$ m. Simulation uses $\Delta t=0.05$ s and stops at $g(t)\le 0$ (collision) or $t=10$ s. Three parameter sets reproduce the course scenarios: FCW ($v_H=16.67$, $x_0=55$, $v_0=11.11$, $t_{dec}=1.0$, $a=-6.0$ m/s²), EBW and ICW (equivalent one-dimensional projection). The ideal-link collision time $t_c$ is 4.30 s for FCW, 6.05 s for EBW and 4.50 s for ICW.

### 3.2 Beaconing and degradation

The remote vehicle generates a BSM every $T=1/f$ seconds ($f=10$ Hz by default), containing its position and speed. Degradation is injected as: (i) independent packet loss with probability $p$; (ii) a constant one-way end-to-end transfer delay $\tau$ (ms), delivered FIFO at $t_s+\tau$; (iii) reduced beacon rate $f$; and (iv) zero-mean Gaussian pose noise $\sigma$ (m) on the reported position. Here $\tau$ has the same meaning as the "end-to-end latency" of [1]: one-way, excluding retransmission and application queueing.

### 3.3 Freshness gate and warning rule

Let $u(t)$ be the generation time of the most recently *received* update. The receiver computes the age $\Delta(t)=t-u(t)$ and applies a validity gate:

$$\text{if } \Delta(t) > V \text{ then the update is discarded and the receiver is } \textit{blind}.$$

Otherwise it extrapolates the remote state, $\hat{x}_R(t)=x_{last}+v_{last}\Delta(t)$, and computes $\mathrm{TTC}=\hat{g}(t)/\max(v_H-v_{last},\,0.5)$ with $\hat{g}=\hat{x}_R-x_H-L$. A warning is raised at the first $t_w$ with $\mathrm{TTC}<3.5$ s; an emergency flag is raised below 1.75 s. $V$ is an **application-configurable freshness budget** (500 ms in the baseline), not a value mandated by any standard; all results are stated in terms of the ratio $\tau/V$ and do not depend on its absolute value.

### 3.4 Metrics

- **Warning margin** $M = t_c - t_w$, zero if no warning is issued.
- **Miss ratio**: fraction of runs with no warning or $M\le 0$.
- **Timely ratio (safe)**: fraction with $M \ge W$, where $W=1.5$ s is the required response margin.
- **Blindness ratio**: fraction of simulation steps failing the freshness gate.

All statistics use 30 fixed seeds (seed $k\cdot 7919+13$), and every run is written to a per-seed CSV.

---

## 4 The Warning Deadline: Analysis

### 4.1 Proposition 1 — a hard bound independent of loss

*Statement.* If $\tau > V$, the receiver has no usable update at any time after the first arrival, and the warning fails with probability one, for any $p$ and $f$.

*Proof.* An update generated at $t_s$ arrives at $t_s+\tau$. At the arrival instant, $\Delta = (t_s+\tau)-t_s = \tau$. Since $\tau > V$, the gate rejects it immediately. Between consecutive arrivals $\Delta(t)$ is non-decreasing, so no later instant can satisfy $\Delta(t)\le V$ either. Hence the set of usable frames is empty and no TTC can be computed. ∎

The proposition is unusually strong: it is a *point* condition on the pair $(\tau, V)$, not a statistical one. It also explains the "latency cliff" reported in §6.2: once $\tau$ crosses $V$, degradation is not gradual but total.

A note on the boundary. Because the gate uses a strict inequality, $\tau = V$ is a measure-zero case whose behaviour depends on floating-point evaluation and frame alignment; we exclude it from the analysis and recommend a guard margin $\varepsilon \ge \Delta t$ in practice.

### 4.2 Proposition 2 — duty cycle of fresh updates

Let $q=1-p$ and let $K\sim\mathrm{Geom}(q)$ be the number of beacon periods between two successful arrivals, $\Pr[K=k]=q(1-q)^{k-1}$, $k\ge1$; then the inter-arrival time is $KT$. Define the freshness allowance $A=V-\tau\ge0$. Within one interval, the receiver holds a fresh update for $\min(KT, A)$ time units (age starts at $\tau$ and reaches $V$ after $A$). By renewal-reward,

$$D=\frac{\mathbb{E}[\min(KT,A)]}{\mathbb{E}[KT]}=\frac{q\sum_{k\ge1}(1-q)^{k-1}\min(kT,A)}{T/q},$$

and the steady-state blindness ratio is $1-D$. Adding the initial transient $t<\tau$, during which no update has arrived and the receiver is necessarily blind, gives

$$P_{\text{blind}} = \frac{\tau}{t_c} + \left(1-\frac{\tau}{t_c}\right)(1-D).$$

Over 30 cells with $\tau<V$ (five loss levels × six delays), the steady-state model attains a mean absolute error of 5.51 percentage points; with the transient correction, **4.44 percentage points**. A discrete-frame variant that rounds the usable duration up to a whole $\Delta t$ performs worse (7.71 pp) because it systematically overestimates availability; we therefore use the continuous model.

### 4.3 Proposition 3 — why intermittent staleness is tolerable

*Statement.* A warning is missed if and only if no usable frame occurs within the decision window in which the TTC condition first becomes satisfiable. The blindness ratio alone therefore does not determine the miss ratio.

*Argument.* The warning rule is a threshold crossing evaluated once per step. If at least one step inside the window has a fresh update with $\mathrm{TTC}<3.5$ s, the warning is issued at that step and $t_w$ is recorded permanently. Blindness outside that window is irrelevant, and even long blind runs are harmless as long as one fresh frame falls inside. By contrast, Proposition 1 removes *every* frame, so the miss ratio jumps to 100% at once. ∎

Section 6.4 gives the empirical counterpart: at $p=0.9$, $\tau=500$ ms the receiver is blind 97.6% of the time yet misses only 20% of runs, whereas at $p=0.1$, $\tau=600$ ms it is blind 100% of the time and misses 100%.

### 4.4 From the bound to a freshness contract

The analysis yields two levels of contract, both expressed in quantities an OBU can monitor.

**C0 (necessary).** $\tau \le V-\varepsilon$, with $\varepsilon\ge\Delta t$. This is a hard requirement on the *maximum* one-way delay, not the mean.

**C1 (conservative, sufficient).** Require every inter-success gap to be shorter than the freshness allowance: $KT\le A$, i.e. $K\le m=\lfloor A/T\rfloor$. Since $\Pr[K>m]=p^m$, enforcing $\Pr[\text{violation}]\le\delta$ gives

$$p \le \delta^{1/m}.$$

With $V=500$ ms, $T=100$ ms, $\tau=100$ ms ($A=400$ ms, $m=4$) and $\delta=0.05$, this yields $p\le 47.3\%$.

**C2 (window-aware).** C1 is over-restrictive because it forbids *any* long gap, while Proposition 3 only forbids a gap that spans the decision window $W$. The blind duration in an interval is $\max(0,KT-A)$; requiring $\Pr[KT-A>W]\le\delta$ with $m'=\lfloor(A+W)/T\rfloor$ gives $p^{m'}\le\delta$ per interval. With $N\approx t_c q/T$ intervals in one encounter, a union bound gives

$$\frac{t_c(1-p)}{T}\,p^{m'} \le \delta,$$

solved numerically. For $W=1.5$ s, $t_c=4.30$ s, $A=400$ ms ($m'=19$), the solution is **$p\le 75.4\%$** at $\delta=0.05$ and $78.9\%$ at $\delta=0.10$ — substantially less conservative than C1 and, as §6.5 shows, much closer to the measured feasible region.

The contract is deliberately stated in terms of maximum delay and consecutive loss length rather than PDR or mean latency: these are the quantities the propositions identify as decisive.

---

## 5 Experimental Protocol

Seven experiment groups were run with a shared simulation kernel (a single JavaScript file per group, no external dependencies), 30 fixed seeds each:

| Group | Sweep | Runs | Purpose |
|---|---|---|---|
| E1 | 5 link presets × 3 scenarios | 450 | Preset contrast |
| E2 | $p=0\ldots0.9$, $\tau=100$ ms | 900 | Loss sweep under a compliant link |
| E3 | $\tau=0\ldots1000$ ms, $p=0.1$ | 990 | Latency cliff |
| E4 | Ablation of loss vs. delay | 360 | Dominant factor |
| E5 | $V\in\{100,300,500,700,1000\}$ ms × delay | 1650 | Sensitivity to the validity budget |
| E6 | 10 loss × 11 delay cells × 3 scenarios | 9900 | Two-dimensional feasible region |
| E7 | 5 loss × 10 delay cells | 1500 | Analytical model validation |

Total: **16,200 independent runs**. E6 deliberately reuses the E2/E3 base configuration and seeds; its $p=0.1$ column and $\tau=100$ ms row reproduce the earlier sweeps at **21/21 crossing cells**, which serves as an internal consistency check. All thresholds ($3.5$ s TTC, $1.75$ s emergency, $W=1.5$ s, $V=500$ ms) are course-level simplifications and are reported as such.

---

## 6 Results

### 6.1 A compliant link can still be unsafe

With $\tau=100$ ms — exactly the 3GPP bound — increasing loss from 0% to 90% reduces the mean warning margin from 2.40 s to 1.36 s, the timely ratio from 100% to 57%, and raises the miss ratio to 17%. In E6, the cell $(p=0.9,\tau=100\ \mathrm{ms})$ yields a timely ratio of only 56.7% and a miss ratio of 16.7%, despite satisfying every link-layer bound in [1]. **Compliance is not sufficiency.**

### 6.2 The latency cliff and the hard bound

At $p=0.1$, increasing $\tau$ from 500 to 600 ms moves the miss ratio from 0% to 100% and blindness from 73% to 100%, with the margin collapsing from 2.09 s to zero. E5 shows the cliff shifting with $V$: for $V=100/300/500/700/1000$ ms the first fully-failing delay is $200/400/600/800/1100$ ms. E7 confirms the mechanism: for all **15/15** cells with $\tau>V$, blindness and miss ratio are both exactly 100%, at every loss level. Earlier reports described the cliff as "$V$ plus one beacon period"; the analysis in §4.1 shows this extra 100 ms is an artifact of the 100 ms sweep step and the strict-inequality boundary at $\tau=V$, not a physical constant.

### 6.3 Duty-cycle model versus simulation

The model of §4.2 predicts the blindness ratio across 30 cells with 4.44 pp MAE. It captures, without fitting, the interaction between loss and delay: at $p=0.6$, predicted and measured blindness rise together from about 8% at $\tau=0$ to about 58–60% at $\tau=400$ ms. Residual error concentrates at $p=0.9$, where the finite encounter length truncates the geometric tail.

### 6.4 Blindness ratio is not the miss ratio

| Condition | Blindness | Miss ratio | Mean margin |
|---|---|---|---|
| $p=0.6$, $\tau=400$ ms | 57.6% | 0% | 1.97 s |
| $p=0.9$, $\tau=400$ ms | 90.2% | 20% | 1.11 s |
| $p=0.9$, $\tau=500$ ms | 97.6% | 20% | 1.03 s |
| $p=0.1$, $\tau=600$ ms | 100% | 100% | 0 s |

A receiver that is blind almost all the time can still be safe; a receiver blind *continuously throughout the decision window* cannot. This is the empirical content of Proposition 3 and the reason PDR-oriented acceptance tests are misleading.

### 6.5 Feasible region and contract check

E6 maps 110 cells per scenario onto the $(p,\tau)$ plane; 50 cells satisfy the timely-ratio $\ge80\%$ criterion for FCW. Two boundaries are visible: a vertical one at the 100 ms compliance line that is **not** uniformly safe (§6.1), and a horizontal failure band just beyond $\tau=V$. Along $\tau=100$ ms, the timely ratio stays at 100% up to $p=0.6$, then falls to 86.7% at 0.7, 80.0% at 0.8 and 56.7% at 0.9.

Against this, C1's $p\le47.3\%$ is clearly too strict, while C2's $p\le75.4\%$ ($\delta=0.05$) lies inside the measured transition region and is slightly conservative — consistent with a bound derived from a union bound and a simplified window model. The gap between C1 and C2 is a quantitative measure of Proposition 3. `[TBD: baseline experiment — count how many "unsafe" cells a conventional PDR ≥ 90% + mean latency ≤ 100 ms test would wrongly accept.]`

### 6.6 Ablation, scenarios, and a negative result

E4 shows delay dominates: 60% loss alone barely changes the outcome, whereas 600 ms delay alone produces 100% misses. Across the three scenarios the cliff sits at the same 600 ms (it is a property of the gate, not the kinematics), but loss sensitivity differs: at $p=0.9,\tau=100$ ms, ICW is most fragile and EBW most robust. A hypothesis that "scenarios with thinner margins fail earlier" is therefore only **partially** supported: margins differ, the deadline does not.

---

## 7 Discussion and Threats to Validity

**Implication for monitoring.** An OBU or RSU should log the age of its freshest usable update and the length of the longest blind run, not only PDR and mean latency. C0/C2 give directly checkable thresholds. Because $V$ is application-configurable, it should be negotiated explicitly between the safety application and the communication stack rather than hard-coded.

**Construct validity.** The gate uses generation-time age, $\Delta=t-u(t)$; a different implementation that resets age on reception would not satisfy Proposition 1. We state this dependency explicitly so the result can be reproduced or refuted.

**Internal validity.** Loss is i.i.d., $\tau$ is constant, delivery is FIFO without reordering, and all runs share the same one-dimensional kinematics. Real C-V2X exhibits burst losses and time-varying delay [4], [5]; the i.i.d. assumption is the single most important simplification, and C2's union bound must be re-derived under a burst model. `[TBD: repeat E6/E7 with a burst-loss trace from a public dataset or an NS-3/Veins link simulation.]`

**Statistical validity.** Thirty seeds per cell are sufficient for the large effects reported (0%→100% cliffs) but not for tight confidence intervals on the transition; `[TBD: 100+ seeds and bootstrap 95% CIs]`.

**External validity.** Three course-level one-dimensional scenarios, a design-parameter validity budget, no driver reaction model, no real vehicle, no standardized message set or security overhead. Results are trends under controlled degradation, not field predictions.

**Reproducibility.** Kernel, seeds, raw per-seed CSVs and figure-generating scripts are released with the paper `[TBD: GitHub + Zenodo DOI]`.

---

## 8 Conclusion

We asked what a V2X link must guarantee for a collision warning to be issued in time. The answer is not "100 ms": a link meeting that bound loses 43% of its timely warnings at 90% packet loss. The decisive quantity is information freshness at the receiver. We proved a hard bound $\tau\le V$, derived the fresh-update duty cycle (4.44 pp MAE), showed that intermittent staleness is tolerable while a window-spanning blind run is not, and converted these results into a two-part contract that bounds both maximum delay and consecutive loss length. The analysis reframes safety validation from packet-level KPIs to application-level freshness, and it is directly testable on an OBU.

---

## References

[1] 3GPP, "Service requirements for V2X services," TS 22.185 V15.0.0 (Release 15), ETSI TS 122 185 V15.0.0, 2018.

[2] S. Kaul, R. D. Yates, and M. Gruteser, "Real-time status: How often should one update?" in *Proc. IEEE INFOCOM*, Orlando, FL, USA, 2012, pp. 2731–2735.

[3] J. Marias-i-Parella, D. Ulied-Guevara, F. Vázquez-Gallego, and J. Casademont, "Age of information-based evaluation methodology for cooperative connected and automated mobility," in *Proc. IEEE ICTON*, 2025, doi: 10.1109/ICTON67126.2025.11125099.

[4] A. Rolich, M. Yildiz, I. Turcanu, A. Vinel, and A. Baiocchi, "On the trade-off between AoI performance and resource reuse efficiency in 5G NR V2X sidelink," in *Proc. IEEE Vehicular Networking Conference (VNC)*, 2025.

[5] B. Wu, R. Mo, J. Yue, Y. Zhang, J. Nguyen, G. Wu, A. Roy-Chowdhury, M. J. Barth, and H. Qiu, "CooperScene: Multi-modal cooperative autonomy benchmark with C-V2X communication characterization," in *Proc. ECCV*, 2026, arXiv:2606.31219.

[6] 3GPP, "Overall description of Radio Access Network (RAN) aspects for Vehicle-to-everything (V2X) based on LTE and NR," TR 37.985 V17.2.0 (Release 17), ETSI TR 137 985 V17.2.0, 2022.

> 以上 6 条均已回官方 PDF / 出版社 / 机构仓储核实，见 `文献/引用核实表_v0.1.md`。**投稿版请删除本行标注。**

---

## Appendix A — Reproduction

```
node code/run_experiments.js     # E1-E5
node code/gen_heatmap.js         # E6
node code/derive_bound.js        # E7 + analytical validation
```

Baseline configuration: $\Delta t=0.05$ s, $f=10$ Hz, $V=500$ ms, $\sigma=0.2$ m, TTC threshold 3.5 s, emergency 1.75 s, $W=1.5$ s, $L=4.5$ m. Seeds $k\cdot7919+13$, $k=1\ldots30$. Per-seed records: `data/实验明细_runs.csv`, `data/实验汇总_summary.csv`, `data/预警可行域_heatmap.csv`, `data/E7_解析模型校验.csv`.

*Version: v0.1 draft, 2026-11-05. Not submitted. All `[TBD]` items and the DRAFT NOTES block must be resolved before any submission.*
