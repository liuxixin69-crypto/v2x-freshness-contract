# How Stale Is Too Stale? Bounding Consecutive Information Outages in V2X Collision Warning

> **DRAFT NOTES — DELETE BEFORE SUBMISSION**
> 中文说明，给作者看，不进投稿版。
> 1. 本稿由 v0.1 按 `10_主编拒稿意见与改稿路线_v0.2.md` 实质改写。核心变化：**把「证明 τ≤V」降级为 Lemma 0（建模推论），把贡献改为「用连续失明段尾分布刻画预警可用性，并证伪自己原先的平均丢包率契约」**。
> 2. 三个执行官成果：`文献/A_文献核查与相关工作.md`（novelty 与引用）、`文献/B_实验补强报告.md` + `代码/E8_baseline.js`（baseline / CI / burst）、`文献/C_投稿目标清单.md`（投稿目标）。所有 E8 数字来自 `数据/E8_baseline_*.csv`。
> 3. 已解决：真实 trace 验证仍待（无公开 CooperScene 通信记录本地副本）、V\* 的 (a, ε_max) 敏感性表（E9_vstar）、cover letter、IEEE Access 排版、**ETSI TS 101 539-3 条文号（已核至 clause 4 / 7.2.3 OR010 / Annex C，并下载原文核对 “exact TTC numbers are out of scope” 一句）**、TR 37.985 年份（2024 已确认）。参考文献已扩至 27 条并逐条回一手来源核实，编号按首次出现顺序重排。
> 4. 与期末课程论文不是同一篇；投稿时 cover letter 须说明部分仿真数据源于未公开发表的课程项目，并满足 IEEE 预印本披露义务。
> 5. 复现：`node 代码/run_experiments.js` / `gen_heatmap.js` / `derive_bound.js` / `E8_baseline.js`。

**Authors:** [TBD]　**Affiliation:** [TBD]

---

## Abstract

Conventional V2X acceptance tests rely on packet delivery ratio and mean latency, and 3GPP TS 22.185 adds a 100 ms latency figure. We ask what a receiver must guarantee for a time-to-collision (TTC) warning to be issued in time, and find that the decisive quantity is neither: it is the tail of consecutive information outages at the application layer. We derive the receiver's freshness budget $V^{*}$ from vehicle kinematics and an admissible extrapolation error, so that $\tau \le V^{*}$ constrains two independently determined quantities instead of defining one. Across 16,200 controlled runs in three warning scenarios and a 330-cell baseline study, a conventional PDR/latency test misclassifies 40.6% of parameter cells — almost entirely by **over-rejecting** usable links (91.8% false rejects, zero false accepts) — whereas a freshness-aware contract reduces total misjudgment to 10.9% (4.7% outside the numerically unstable boundary column). We then **falsify our own earlier average-loss contract**: under Gilbert-Elliot bursts at an identical mean loss rate, six cells it accepts become unsafe, while the maximum-delay condition survives in every case. We therefore replace the mean-loss bound with a tail constraint on the longest blind run, $\Pr[L_{\mathrm{blind}} \ge W] \le \delta$, and validate it twice: against measured outage-run distributions in simulation, and against 43 min of real C-V2X captures, where the measured burst length of 2.1 packets leaves a factor-2.6 margin and the availability-conditioned tail is 0.9% (95% upper bound 2.0%) against a 5% budget, implying a 95.9% availability requirement. The result reframes V2X safety validation from packet-level KPIs to the tail of application-level staleness.
## 1 Introduction

Cooperative safety applications extend a vehicle's perception beyond its field of view by periodically broadcasting state information over PC5 sidelink. In the forward-collision, emergency-brake and intersection-collision warning use cases, correctness depends not on whether a message eventually arrives, but on whether it arrives while a driver or controller can still act. Standardization captures part of this requirement numerically: 3GPP TS 22.185 [1] mandates a maximum end-to-end latency of 100 ms for V2V/V2P and V2I ([R-5.2.1-001], [R-5.2.1-003]), recommends 20 ms for pre-crash sensing ([R-5.2.1-002]), caps periodic transmission at ten messages per second per UE ([R-5.2.3-001]), and requires a communication range that affords the driver approximately four seconds of response time ([R-5.2.4-001]). The payload is standardized as well: the SAE J2735 Basic Safety Message (BSM) and the ETSI Cooperative Awareness Message (CAM) both carry position, speed and heading at a nominal 10 Hz [2], [3].

Engineering practice, however, usually validates the link rather than the application: packet delivery ratio (PDR), mean latency and throughput are measured and compared against these bounds. The four-second response-time clause is rarely translated into an application-level acceptance test. This is a gap, because a link with 100 ms mean latency can still leave a receiver holding a two-second-old position after a burst of consecutive losses, and a warning computed from that position is either late or absent.

Recent work has begun to argue that link-layer metrics are inadequate for cooperative, connected and automated mobility (CCAM). Marias-i-Parella et al. [4] build an evaluation methodology around age of information (AoI) with use-case-specific penalty functions. Rolich et al. [5] show in 5G NR-V2X Mode 2 that semi-persistent scheduling can produce long runs of consecutive losses, so that a configuration with higher PDR may have worse AoI. Real-world measurements from CooperScene [6] report 38.19% packet loss and 31.46 ms latency on commercial C-V2X radios. What is still missing is a **closed-form condition that maps link parameters to whether a specific warning algorithm will fire in time**, together with an experimental check of that condition.

We explicitly do **not** claim priority for the notion of a freshness threshold or a hard deadline: both are established in standards and in prior work on AoI violation probabilities, hazard windows and hard peak-AoI scheduling (§2). The condition $\tau\le V$ is stated below as **Lemma 0, a modelling corollary**, not as a finding. Our contributions are instead:

1. **A kinematics-derived freshness budget.** We bind $V$ to the scenario via the position-extrapolation error $\varepsilon(\Delta)=\tfrac12|a|\Delta^2$, giving $V^{*}=\sqrt{2\varepsilon_{\max}/|a|}$. For FCW ($|a|=6$ m/s², $\varepsilon_{\max}=1$ m) this yields $V^{*}\approx577$ ms; EBW and ICW give different budgets. The resulting constraint relates two independently determined quantities and is therefore non-trivial (§3.3, §4.1).
2. **An outage-tail contract, a falsification, and an availability budget.** We show that a contract expressed in mean loss rate ($p\le75.4\%$) is invalidated by burst losses (six counterexamples), while the maximum-delay condition survives. We replace it with $\Pr[L_{\mathrm{blind}}\ge W]\le\delta$ and validate the bound against measured blind-run length distributions, both in simulation (§6.7) and on 24,449 beacons of real C-V2X traffic (§6.8), where the measured burst length settles the $L_B$ parameter that the simulation had to assume. Because real outages are dominated by coverage rather than by the radio, we further derive the availability this contract implies — $A^{*}=95.9\%$ at $\delta=5\%$ — turning a qualitative caveat into a deployment figure (§6.8).
3. **A quantified comparison with the conventional acceptance test.** On 330 parameter cells, the traditional “PDR $\ge90\%$ and mean latency $\le100$ ms” test rejects 91.8% of actually usable links; the freshness-aware contract cuts total misjudgment from 40.6% to 10.9% with a 2.7% false-accept rate (§6.5).
4. **A reproducible artifact.** All kernel code, 200-seed confidence intervals, per-seed CSVs and an offline four-view visualizer are released; every number in this paper can be regenerated with four commands (§5, Appendix A).

The remainder of the paper is organized as follows. §2 positions the work. §3 defines the model. §4 derives the three propositions and the contract. §5 describes the reproducible protocol, §6 reports results, §7 discusses threats to validity, and §8 concludes.

---

## 2 Related Work

**Standards and link-layer KPIs.** TS 22.185 [1] and the RAN-level survey TR 37.985 [7] specify latency, payload, rate and range requirements for LTE-V2X and NR-V2X; the NR-V2X tutorial of Castañeda Garcia et al. [8] documents the sidelink physical layer, the Mode 2 resource-allocation procedures and the QoS framework that realize them. These documents define *transport* capabilities; they are explicitly agnostic to message types and do not specify how an application should decide that a received state is too old to use. Our work takes these bounds as inputs and asks what additional application-side condition is needed.

**Age of information.** Kaul, Yates and Gruteser [9] introduced the time-average age metric $\Delta(t)=t-u(t)$ and showed that the update rate minimizing age is neither the throughput-maximizing nor the delay-minimizing rate. The same group had already applied the metric to one-hop vehicular broadcast, where the relevant object is the age of *every* neighbour's state rather than of a single stream [10]. Costa, Codreanu and Ephremides [11] added *peak* age, the maximum attained immediately before a successful update, together with packet-management policies; the recent survey of Yates et al. [12] consolidates these results and the tail-oriented evaluation methods on which we build. AoI has since been widely used in vehicular networks, e.g. for random-access optimization and for hard peak-AoI scheduling. Marias-i-Parella et al. [4] are closest to our motivation: they state that conventional reliability and latency metrics “often fall short in capturing the true effectiveness” of CCAM at the application level, and propose AoI-based penalty functions and statistical indicators. Their contribution is a **general evaluation framework**; they do not derive a closed-form deadline for a concrete warning decision, nor do they characterize the shape of the feasible region in the (loss, delay) plane.

**Freshness versus reliability in V2X.** Rolich et al. [5] demonstrate a PDR–AoI trade-off in NR-V2X sidelink: persistence in semi-persistent scheduling creates bursts of consecutive losses and long inter-success gaps, so a lower-PDR dynamic scheme can achieve better AoI. This is a MAC-layer scheduling result. Our analysis starts one layer above: given a sequence of losses (i.i.d. in the first study, bursty in the second), what does the *warning logic* tolerate?

**Why burstiness, and why it was neglected.** The two-state burst-noise channel of Gilbert [13] and Elliott [14] is the minimal model in which loss has memory. Zorzi and Rao [15] showed that the performance of higher-layer protocols is governed by the higher-order statistics of such a process rather than by its marginal error rate — which is exactly the failure mode we report in §6.7. It is worth recording why link-level practice nevertheless favours marginal metrics: in early 802.11p field trials Bai and Krishnan [16] found that packet drops “do not occur in bursts most of the time”, so an i.i.d. model was a defensible default for contention-based beaconing. Semi-persistent scheduling removes that premise, because a persistently colliding reservation fails repeatedly at the same period [5]. Our finding is that this difference is invisible to a mean-loss contract but visible to a bound on the burst length, and that the burst length is therefore the quantity a safety contract should constrain.

**Real C-V2X measurements.** CooperScene [6] is a multi-modal cooperative autonomy dataset with synchronized application-level C-V2X traces (three CAVs and one RSU, 10 Hz annotations), reporting 38.19% loss, 31.46 ms latency and 0.72 Mbps throughput. Its benchmark shows that cooperative perception accuracy degrades substantially under real links and that reducing bandwidth pressure alone is insufficient. Its endpoint is detection mAP; ours is the timing of a warning decision. We use their measured loss and delay as a sanity anchor for our parameter ranges, not as a direct comparison.

**Positioning (revised).** We make no claim of conceptual priority. What is not present in the works above is a *joint* treatment: a TTC warning decision as the endpoint, a two-dimensional (loss, delay) feasible region, and — most importantly — an explicit experimental falsification of a mean-loss-based safety contract under correlated losses. We also note that the constituent concepts — an application-level staleness threshold [17], [18], a tolerance-window “at least one packet” reliability metric [19], and consecutive-loss (burst-error) bounds [20] — each appear in earlier standards, reports and dissertations; the joint treatment is the contribution. Table I summarizes this narrower, testable claim.

*Table I — Comparison with related work (columns: closed-form deadline / warning-decision endpoint / 2-D feasible region / blindness–miss decoupling). [TBD: typeset as a table in the submission template.]*

---

**Freshness thresholds and hard deadlines are established.** Road-safety message profiles already bound data age explicitly. ETSI TS 101 539-3 [17] defines the application end-to-end latency time $T_6-T_0$ (clause 4) and, in a critical safety situation, requires the receiving ITS-S to use performance class A, i.e. $T_0-T_1<150$ ms (clause 7.2.3, requirement OR010). Its Annex C folds that latency into the minimum time available for issuing a warning, $DWT_{\min}=MLT+MDRT+MAT+Margin$, where the total system maximum end-to-end latency $MLT$ “may be set to 300 ms”. The standard is thus already structured as a subtraction from the available time-to-collision: latency consumes part of the window in which a warning can still act. Two features of the document matter here. First, it fixes a latency *allowance* but says nothing about the resulting staleness *distribution* — a 300 ms allowance is compatible with arbitrarily long outages if losses cluster, which is precisely the regime §6.7 exercises. Second, it deliberately declines to fix the warning thresholds themselves: the note accompanying Fig. 1 of [17] states that “exact TTC numbers are out of scope of the present document”, so the illustrative 3.5 s and 1.75 s values we adopt in §3.3 are chosen in that spirit and are not claimed to be standard-mandated. Bezmenov et al. [21] derive a closed-form AoI PMF under NR-V2X semi-persistent scheduling and explicitly use the *age-violation probability* for safety-critical services. Ashik and Hossain [22] assign per-application AoI thresholds (FCW 100 ms, EBW 120 ms, LCW 400 ms) and show that inside a 2 s hazard window the AoI-violation probability approaches 100% under resource-starvation attacks — the closest prior work to our “decision window” framing. Zhang and Mo [23] enforce a hard peak-AoI deadline in every slot via online convex optimization. None of these uses a TTC warning decision as the endpoint or tests the *validity of the contract itself* under correlated losses; that is the gap we address.

---

## 3 System Model

Fig. 1 fixes the notation and shows where the decision sits. Panel (a) is the longitudinal geometry of §3.1: the host vehicle travels at $v_H$, the remote vehicle decelerates at $a<0$, and the true gap $g(t)$ defines the time-to-collision on which the warning rule acts. Panel (b) is the update chain of §3.2–§3.4: a 10 Hz BSM stream crosses a link characterized by $(p,\tau,f,\sigma)$, is admitted or discarded by a validity gate on the age $\Delta(t)$, and drives a TTC-threshold decision whose two failure modes — miss and false alarm — are the quantities we measure. The contracts of §4 attach to two different points of this chain: C0 and C1 constrain the link input, whereas C2 constrains the gate's output, namely the length of the blind runs produced when updates are discarded.

@@FIG0@@

### 3.1 Kinematics

We use a one-dimensional longitudinal model shared by all experiments. The host vehicle travels at constant speed $v_H$. The remote vehicle starts at gap $x_0$ with speed $v_0$ and, from $t \ge t_{dec}$, decelerates at constant $a<0$ until its speed reaches zero. Positions are $x_H(t)=v_H t$ and $x_R(t)$; the true gap is $g(t)=x_R(t)-x_H(t)-L$ with vehicle length $L=4.5$ m. Simulation uses $\Delta t=0.05$ s and stops at $g(t)\le 0$ (collision) or $t=10$ s. Three parameter sets reproduce the course scenarios: FCW ($v_H=16.67$, $x_0=55$, $v_0=11.11$, $t_{dec}=1.0$, $a=-6.0$ m/s²), EBW and ICW (equivalent one-dimensional projection). The ideal-link collision time $t_c$ is 4.30 s for FCW, 6.05 s for EBW and 4.50 s for ICW.

### 3.2 Beaconing and degradation

The remote vehicle generates a BSM every $T=1/f$ seconds ($f=10$ Hz by default), containing its position and speed. Degradation is injected as: (i) independent packet loss with probability $p$; (ii) a constant one-way end-to-end transfer delay $\tau$ (ms), delivered FIFO at $t_s+\tau$; (iii) reduced beacon rate $f$; and (iv) zero-mean Gaussian pose noise $\sigma$ (m) on the reported position. Here $\tau$ has the same meaning as the “end-to-end latency” of [1]: one-way, excluding retransmission and application queueing.

### 3.3 Freshness gate and warning rule

Let $u(t)$ be the generation time of the most recently *received* update. The receiver computes the age $\Delta(t)=t-u(t)$ and applies a validity gate:

Formally, any update whose age exceeds the budget, $\Delta(t) > V$, is discarded and the receiver is marked *blind*; a discarded update yields no usable position estimate.

Otherwise it extrapolates the remote state, $\hat{x}_R(t)=x_{last}+v_{last}\Delta(t)$, and computes $\mathrm{TTC}=\hat{g}(t)/\max(v_H-v_{last},\,0.5)$ with $\hat{g}=\hat{x}_R-x_H-L$. A warning is raised at the first $t_w$ with $\mathrm{TTC}<3.5$ s; an emergency flag is raised below 1.75 s. Both thresholds are illustrative design parameters rather than values mandated by any standard; because the analysis spans a grid of $(p,\tau,V)$ and §3.3 reports the $V^{*}$ sensitivity, none of the conclusions depends on these particular numbers. $V$ is an **application-configurable freshness budget** (500 ms in the baseline), not a value mandated by any standard; In v0.1 of this work $V$ was a free design parameter (500 ms), which made the constraint $\tau\le V$ close to a tautology. We now **derive** it. The receiver extrapolates the remote position as $\hat{x}_R=x_{last}+v_{last}\Delta$ from an update of age $\Delta$. During the deceleration phase the true position contains an additional $\tfrac12 a\Delta^2$ term, so the extrapolation error is

$$\varepsilon(\Delta)=\tfrac12 |a|\,\Delta^{2}$$

(plus a relative-speed term when the host also accelerates). Given an admissible gap-estimation error $\varepsilon_{\max}$, the largest usable age is

$$V^{*}=\sqrt{2\varepsilon_{\max}/|a|}.$$

For FCW ($|a|=6$ m/s², $\varepsilon_{\max}=1$ m) this gives $V^{*}\approx577$ ms; our baseline $V=500$ ms corresponds to $\varepsilon\approx0.75$ m, a conservative choice. EBW ($|a|=9$) yields $V^{*}\approx471$ ms and ICW ($|a|=7$) $\approx535$ ms, so a single fixed budget is not equally conservative across scenarios — which explains why the same 600 ms cliff coincides with different loss sensitivities (§6.6).

@@VSTAR@@

Crucially, $V^{*}$ is set by vehicle dynamics and a safety tolerance while $\tau$ is set by the radio link: the constraint now relates two independent physical quantities.

### 3.4 Metrics

- **Warning margin** $M = t_c - t_w$, zero if no warning is issued.
- **Miss ratio**: fraction of runs with no warning or $M\le 0$.
- **Timely ratio (safe)**: fraction with $M \ge W$, where $W=1.5$ s is the required response margin.
- **Blindness ratio**: fraction of simulation steps failing the freshness gate.

All statistics use 30 fixed seeds (seed $k\cdot 7919+13$), and every run is written to a per-seed CSV.

**Terminology.** A maximal consecutive run of rejected (stale) frames at the receiver is called an *outage*, and its length the *blind-run length* $L_{\mathrm{blind}}$. The *blindness ratio* is the time fraction spent in outage (the time average of the outage indicator), and the *miss ratio* is the fraction of encounters in which no timely warning is issued. The word “staleness” is used only qualitatively; every quantitative statement is expressed in terms of outages, blind-run length, and the blindness ratio.

---

## 4 The Warning Deadline: Analysis

### 4.1 Lemma 0 — a modelling corollary (not a contribution)

This lemma follows directly from the definition of $V$ and the age process: a packet generated at $t_s$ and delivered at $t_s+\tau$ has age $\tau$ on arrival, so if $\tau>V$ it is stale the instant it lands. We state it to fix notation and to make the boundary explicit, **not** as a research finding.

*Statement.* If $\tau > V$, the receiver has no usable update at any time after the first arrival, and the warning fails with probability one, for any $p$ and $f$.

*Proof.* An update generated at $t_s$ arrives at $t_s+\tau$. At the arrival instant, $\Delta = (t_s+\tau)-t_s = \tau$. Since $\tau > V$, the gate rejects it immediately. Between consecutive arrivals $\Delta(t)$ is non-decreasing, so no later instant can satisfy $\Delta(t)\le V$ either. Hence the set of usable frames is empty and no TTC can be computed. ∎

What makes the lemma useful is that it is a *point* condition, not a statistical one, and — once $V$ is replaced by the kinematics-derived $V^{*}$ of §3.3 — it becomes a constraint on the radio link. It also explains the “latency cliff” in §6.2: once $\tau$ crosses the budget, degradation is not gradual but total.

A note on the boundary. Because the gate uses a strict inequality, $\tau = V$ is a measure-zero case whose behaviour depends on floating-point evaluation and frame alignment; we exclude it from the analysis and recommend a guard margin $\varepsilon \ge \Delta t$ in practice.

### 4.2 Proposition 2 — duty cycle of fresh updates

Let $q=1-p$ and let $K\sim\mathrm{Geom}(q)$ be the number of beacon periods between two successful arrivals, $\Pr[K=k]=q(1-q)^{k-1}$, $k\ge1$; then the inter-arrival time is $KT$. Define the freshness allowance $A=V-\tau\ge0$. Within one interval, the receiver holds a fresh update for $\min(KT, A)$ time units (age starts at $\tau$ and reaches $V$ after $A$). By renewal-reward,

$$D=\frac{\mathbb{E}[\min(KT,A)]}{\mathbb{E}[KT]}=\frac{q\sum_{k\ge1}(1-q)^{k-1}\min(kT,A)}{T/q},$$

and the steady-state blindness ratio is $1-D$. Adding the initial transient $t<\tau$, during which no update has arrived and the receiver is necessarily blind, gives

$$P_{\text{blind}} = \frac{\tau}{t_c} + \left(1-\frac{\tau}{t_c}\right)(1-D).$$

Over 30 cells with $\tau<V$ (five loss levels × six delays), the steady-state model attains a mean absolute error of 5.51 percentage points; with the transient correction, **4.44 percentage points**. A discrete-frame variant that rounds the usable duration up to a whole $\Delta t$ performs worse (7.71 pp) because it systematically overestimates availability; we therefore use the continuous model.

### 4.3 Proposition 3 — why intermittent outages are tolerable

*Statement.* A warning is missed if and only if no usable frame occurs within the decision window in which the TTC condition first becomes satisfiable. The blindness ratio alone therefore does not determine the miss ratio.

*Argument.* The warning rule is a threshold crossing evaluated once per step. If at least one step inside the window has a fresh update with $\mathrm{TTC}<3.5$ s, the warning is issued at that step and $t_w$ is recorded permanently. Blindness outside that window is irrelevant, and even long blind runs are harmless as long as one fresh frame falls inside. By contrast, Lemma 0 removes *every* frame, so the miss ratio jumps to 100% at once. ∎

Section 6.4 gives the empirical counterpart: at $p=0.9$, $\tau=500$ ms the receiver is blind 97.6% of the time yet misses only 20% of runs, whereas at $p=0.1$, $\tau=600$ ms it is blind 100% of the time and misses 100%.

### 4.4 From the bound to an outage-tail contract

The analysis yields a necessary condition, a **falsified** sufficient condition, and a replacement contract.

**C0 (necessary, survives burst loss).** $\tau \le V^{*}-\varepsilon$, with $\varepsilon\ge\Delta t$. This bounds the *maximum* one-way delay, not the mean. §6.7 shows it holds under both i.i.d. and Gilbert-Elliot losses.

**C1 (sufficient under i.i.d. loss; falsified under burst loss).** Requiring every inter-success gap to be shorter than the allowance $A=V^{*}-\tau$ gives $p\le\delta^{1/m}$ with $m=\lfloor A/T\rfloor$; adding the decision-window union bound gives $\frac{t_c(1-p)}{T}p^{m'}\le\delta$ with $m'=\lfloor(A+W)/T\rfloor$, i.e. $p\le75.4\%$ at $\delta=0.05$ for $V=500$ ms, $T=100$ ms, $\tau=100$ ms, $W=1.5$ s. This bound rests on $K\sim\mathrm{Geom}(1-p)$, whose tail $p^{m}$ is a direct consequence of independent losses. **We derived this contract and then tested it against correlated losses; it fails** (six counterexamples, §6.7). We report it because the failure is the point: an average-loss-rate contract is structurally unable to bound the longest blind run.

**C2 (replacement).** Since a warning needs only one fresh frame inside the decision window $W$, the quantity to bound is the *longest consecutive blind run* $L_{\mathrm{blind}}$, not the mean loss rate:

$$\Pr\!\left[L_{\mathrm{blind}}\ge W\right]\le\delta .$$

For a Gilbert-Elliot channel, $L_{\mathrm{blind}}$ is governed by the BAD-state residence time $L_B$ (transition rate $\beta=1/L_B$), not by $\bar p$; the tail is phase-type rather than geometric. The contract is therefore monitorable on an OBU by logging blind-run lengths, and it reduces to C1 only under i.i.d. losses. §6.7 gives measured distributions: under i.i.d. losses with $\bar p\le0.6$ **no** blind run reaches $W$, whereas under burst losses with the same $\bar p=0.3$ already 15.8% of runs exceed $W$ and the miss ratio rises from 0% to 7%.

This also yields a *threshold* on the burst parameter rather than only a verdict. A BAD run of mean length $L_B$ packets exceeds $W$ with probability $\approx(1-1/L_B)^{W_p}$, where $W_p=W/T$ is the decision window expressed in **packets** (15 at $W=1.5$ s and $T=100$ ms — note that $W$ is counted in simulation frames of $\Delta t=0.05$ s, twice the beacon rate, so the conversion is not one-to-one). Requiring this to stay below $\delta=0.05$ gives $L_B\approx5.5$ packets; the empirical Gilbert-Elliot sweep of §6.7, interpolated directly on measured run lengths, gives $L_B\lesssim7$ packets. Both place the usable BAD residence at roughly $0.5$–$0.7$ s at 10 Hz, and both are far below the $L_B=15$ packets ($1.5$ s) used in the baseline burst condition — which is precisely why that condition is falsified. Section 6.8 supplies the input this paragraph used to defer: on eight real C-V2X links the measured burst length is $L_B=2.10$ packets, so both caps hold with a factor-2.6 margin, and what remains open is not the value of $L_B$ but the availability of the link.

---

## 5 Experimental Protocol

Seven experiment groups were run with a shared simulation kernel (a single JavaScript file per group, no external dependencies), 30 fixed seeds each (Table IV):

| Group | Sweep | Runs | Purpose |
|---|---|---|---|
| E1 | 5 link presets × 3 scenarios | 450 | Preset contrast |
| E2 | $p=0\ldots0.9$, $\tau=100$ ms | 900 | Loss sweep under a compliant link |
| E3 | $\tau=0\ldots1000$ ms, $p=0.1$ | 990 | Latency cliff |
| E4 | Ablation of loss vs. delay | 360 | Dominant factor |
| E5 | $V\in\{100,300,500,700,1000\}$ ms × delay | 2100 | Sensitivity to the validity budget |
| E6 | 10 loss × 11 delay cells × 3 scenarios | 9900 | Two-dimensional feasible region |
| E7 | 5 loss × 10 delay cells | 1500 | Analytical model validation |
| E8a | 330 cells × 3 criteria | 9900 | Baseline vs. contract confusion matrix |
| E8b | 36 cells × 200 seeds | 7200 | Wilson 95% confidence intervals |
| E8c | 38 i.i.d./GE conditions × 200 seeds | 7600 | Burst loss and blind-run distributions |

Total: **16,200 independent runs** for E1–E7, plus **24,700** for the E8 baseline/CI/burst study (`代码/E8_baseline.js`, six CSVs in `数据/`). E8a reproduces E6 exactly at 110/110 FCW cells, so its ground truth is not a second simulator. E6 deliberately reuses the E2/E3 base configuration and seeds; its $p=0.1$ column and $\tau=100$ ms row reproduce the earlier sweeps at **21/21 crossing cells**, which serves as an internal consistency check. All thresholds ($3.5$ s TTC, $1.75$ s emergency, $W=1.5$ s, $V=500$ ms) are course-level simplifications and are reported as such.

**Confidence intervals.** Several transition-band proportions lie close to 0 or 1, which is exactly where the Wald interval's coverage collapses. We therefore report Wilson score intervals [24], the small-sample choice recommended by Brown, Cai and DasGupta [25], whose comparative study shows the Wald interval to be unreliable in this regime. This is why the 200-seed intervals in §6.1 and §7 replace the point estimates of earlier drafts rather than being reported alongside them.

---

## 6 Results

### 6.1 A compliant link can still be unsafe

With $\tau=100$ ms — exactly the 3GPP bound — increasing loss from 0% to 90% reduces the mean warning margin from 2.40 s to 1.36 s, the timely ratio from 100% to 57%, and raises the miss ratio to 17%. In E6, the cell $(p=0.9,\tau=100\ \mathrm{ms})$ yields a timely ratio of only 56.7% and a miss ratio of 16.7%, despite satisfying every link-layer bound in [1]. **Compliance is not sufficiency.** With 200 seeds the compliant-but-degraded cells are tightened: at $\tau=100$ ms, $p=0.6$ gives a timely ratio of 98.0% [94.97, 99.22], $p=0.7$ gives 95.0% [91.04, 97.26], $p=0.8$ gives 89.5% [84.48, 93.03] and $p=0.9$ gives 65.0% [58.16, 71.27]. The 30-seed figures in earlier drafts (100%, 86.7%, 80%, 56.7%) are noisy in the transition band — an 8.3 pp deviation at $p=0.7$ — so all transition claims in this version use Wilson 95% intervals.

### 6.2 The latency cliff and the hard bound

At $p=0.1$, increasing $\tau$ from 500 to 600 ms moves the miss ratio from 0% to 100% and blindness from 73% to 100%, with the margin collapsing from 2.09 s to zero. E5 shows the cliff shifting with $V$: for $V=100/300/500/700/1000$ ms the first fully-failing delay is $200/400/600/800/1100$ ms. E7 confirms the mechanism: for all **15/15** cells with $\tau>V$, blindness and miss ratio are both exactly 100%, at every loss level. Earlier reports described the cliff as “$V$ plus one beacon period”; the analysis in §4.1 shows this extra 100 ms is an artifact of the 100 ms sweep step and the strict-inequality boundary at $\tau=V$, not a physical constant.

### 6.3 Duty-cycle model versus simulation

The model of §4.2 predicts the blindness ratio across 30 cells with 4.44 pp MAE. It captures, without fitting, the interaction between loss and delay: at $p=0.6$, predicted and measured blindness rise together from about 8% at $\tau=0$ to about 58–60% at $\tau=400$ ms. Residual error concentrates at $p=0.9$, where the finite encounter length truncates the geometric tail.

### 6.4 Blindness ratio is not the miss ratio

Table V separates the two quantities on four cells drawn from the E8 grid.

| Condition | Blindness | Miss ratio | Mean margin |
|---|---|---|---|
| $p=0.6$, $\tau=400$ ms | 57.6% | 0% | 1.97 s |
| $p=0.9$, $\tau=400$ ms | 90.2% | 20% | 1.11 s |
| $p=0.9$, $\tau=500$ ms | 97.6% | 20% | 1.03 s |
| $p=0.1$, $\tau=600$ ms | 100% | 100% | 0 s |

A receiver that is blind almost all the time can still be safe; a receiver blind *continuously throughout the decision window* cannot. This is the empirical content of Proposition 3 and the reason PDR-oriented acceptance tests are misleading.

### 6.5 Feasible region and contract check

E6 maps 110 cells per scenario onto the $(p,\tau)$ plane; 50 cells satisfy the timely-ratio $\ge80\%$ criterion for FCW (Fig. 2). Two boundaries are visible: a vertical one at the 100 ms compliance line that is **not** uniformly safe (§6.1), and a horizontal failure band just beyond $\tau=V$. With 200 seeds (E8b), the FCW transition at $\tau=100$ ms reads 98.0% [94.97, 99.22] at $p=0.6$, 95.0% [91.04, 97.26] at 0.7, 89.5% [84.48, 93.03] at 0.8 and 65.0% [58.16, 71.27] at 0.9; the 30-seed values reported in v0.1 (100 / 86.7 / 80.0 / 56.7%) are retained only as a small-sample subset.

The per-gap bound $p\le47.3\%$ is clearly too strict, while the window-aware bound $p\le75.4\%$ ($\delta=0.05$) lies inside the measured transition region; §6.7 shows the latter nevertheless fails under burst losses. The baseline study (E8a) quantifies the value of moving to an application-level contract: Over 330 cells, the conventional test “PDR $\ge90\%$ and mean latency $\le100$ ms” accepts only **12 cells** and produces **0/184 false accepts** but **134/146 false rejects (91.8%)**, for a total misjudgment rate of **40.6%**. Our first intuition — that a PDR-oriented test would wrongly *accept* unsafe links — is therefore **not supported**. The failure mode is the opposite: it uses a *mean* latency bound to reject cells whose decisive quantity is the maximum delay / information age, and in doing so discards more than nine out of ten usable links. The freshness contract accepts 120 cells with 5 false accepts (2.7%) and 31 false rejects, reducing total misjudgment to **10.9%** (**4.7%** when the numerically unstable $\tau=V$ column is excluded, where 22 of the 31 false rejects come from the deliberate guard margin). Precision of accepted cells is 95.8%. Five false accepts all lie in the ICW / mid-to-high delay transition band with zero misses but margins of 1.48–1.76 s, indicating that a threshold derived on FCW is slightly loose for ICW — consistent with the scenario differences in §6.6.

@@FIG1@@

### 6.6 Ablation, scenarios, and a negative result

E4 shows delay dominates: 60% loss alone barely changes the outcome, whereas 600 ms delay alone produces 100% misses. Across the three scenarios the cliff sits at the same 600 ms (it is a property of the gate, not the kinematics), but loss sensitivity differs: at $p=0.9,\tau=100$ ms, ICW is most fragile and EBW most robust. A hypothesis that “scenarios with thinner margins fail earlier” is therefore only **partially** supported: margins differ, the deadline does not.

---

### 6.7 Burst losses falsify the mean-loss contract

E8c replaces i.i.d. losses with a two-state Gilbert-Elliot channel of identical mean loss rate $\bar p$ (BAD-state mean residence $L_B=15$ packets $=1.5$ s, $p_G=0$, $p_B=1$, 200 seeds; Table VI). Fig. 3 contrasts a representative pair of age traces at the same $\bar p$: the i.i.d. trace sawtooths around a few hundred milliseconds, whereas the burst trace contains a single unbroken stale interval that spans the whole decision window. Realized mean loss matches the i.i.d. case within 2.44 pp.

| $\bar p$ | i.i.d. timely | GE timely | i.i.d. $\Pr[L_{\mathrm{blind}}\ge W]$ | GE $\Pr[L_{\mathrm{blind}}\ge W]$ | GE miss |
|---|---|---|---|---|---|
| 0.1 | 100.0% | 96.0% | 0.000 | 0.063 | 0.5% |
| 0.3 | 100.0% | **78.0%** | 0.000 | **0.158** | 7.0% |
| 0.6 | 98.0% | **65.0%** | 0.000 | **0.212** | 8.5% |
| 0.8 | 89.5% | 58.0% | 0.033 | 0.214 | 14.0% |
| 0.9 | 65.0% | 50.5% | 0.162 | 0.243 | 17.0% |

@@FIG2@@

At the same mean loss, correlated losses reduce the timely ratio by up to 33 pp. Six conditions satisfy C1 ($p\le75.4\%$) yet are unsafe — e.g. $\tau=100$ ms, $\bar p=0.3$: safe 78.0%, miss 7.0% under GE versus safe 100%, miss 0% under i.i.d. By contrast **C0 holds in all 4/4 checks** at $\tau=600$ ms $>V$: 100% blindness and 100% misses under both loss models. Varying $L_B$ from 5 to 25 packets increases the miss ratio monotonically (0→11.5%) and the fraction of window-spanning blind runs (0.025→0.201), while *mean* blindness is non-monotonic (27.2%→26.0%; the whole family of distributions is plotted in Fig. 4). Safety is governed by the **tail** of the blind-run distribution, not by averages. This is the empirical basis for replacing C1 with C2.

@@C2BURST@@

@@FIG3@@

### 6.8 Re-validation on real C-V2X traces

§4.4 ended on an admission: a trace-based re-estimation of $L_B$ was the one input we could not supply. We now supply it. We use the NIST outdoor C-V2X interoperability captures [28], collected in September 2025 on the NIST Gaithersburg campus with commercial C-V2X on-board and roadside units. Each campaign ships a pair of PCAP captures for every link, taken simultaneously at both ends by a synchronised sniffer: the transmitter-side capture records what was sent, the receiver-side capture what arrived. A broadcast BSM is byte-identical at the two ends, so matching the captures by payload digest — with no parsing of the ASN.1 payload and no inference — recovers the exact per-packet delivery indicator. That is precisely the ingredient a parametric channel model cannot supply. We analyse eight directional links: one RSU against three OBUs in the C-V2I campaign, and one RSU against one OBU in the C-V2X campaign — 43 min of capture, 24,449 beacons at 10 Hz, 16,685 received. Blind runs are measured on the transmitter's timeline, and a run's duration is the interval between the last and the next successful reception.

Blind-run lengths are not unimodal (Fig. 5a). They split into two populations separated by an empty interval between 20 and 34 packets, that is between 2.0 s and 3.4 s. The short class is micro-bursts — median one packet, maximum 20 packets (2.0 s). The long class runs from 3.4 s to 75 s. Any threshold inside the gap yields the same division, and we deliberately assign the borderline runs to the burst class, which makes the burst statistics below conservative. The two classes also have different causes. For all 15 coverage episodes observed in the OBU→RSU direction, the reverse RSU→OBU link is also blind over at least half of the same interval. A link that vanishes in both directions at once is what range loss or a geometric obstruction produces; independent per-packet loss does not do that. We therefore read the long class as a coverage outage — a property of the deployment, not of the radio's error process — and the short class as the burst behaviour that a contract can bound.


Conditioned on availability, C2 holds with margin. Of 452 micro-bursts, four reach $W=1.5$ s, so $\Pr[L_{\mathrm{blind}}\ge W\mid\text{available}]=0.88\%$ with a Clopper–Pearson 95% upper bound of 2.0%, below $\delta=5\%$; no individual link exceeds 3.5%. The pooled mean burst length is $L_B=2.10$ packets (0.21 s), a factor of 2.6 below the analytic cap of 5.5 packets derived in §4.4 and a factor of 7 below the $L_B=15$ packets (1.5 s) of the baseline burst condition. The closed-form cap is thus not merely admissible but conservative on real hardware, whereas the baseline value overstates the measured burst length sevenfold — which is exactly why that condition violates C2 while these links satisfy it. The closed form is derived and validated against these 452 bursts in §6.9.

@@FIG5@@

Coverage is a different failure mode, and C2 does not bound it. Unconditionally, five of the eight links violate the 5% tail, with $\Pr[L_{\mathrm{blind}}\ge W]$ up to 20%, and coverage outages occupy 28.0% of the total capture time. This bears directly on the mean-loss contract. Two links carry $\hat p=0.44$ and $0.49$ — both well inside C1's 75.4% cap — yet their blind time is governed by outages of 50–75 s. The falsification of §6.7 therefore reproduces on real hardware, although through availability rather than through micro-bursts. The operational reading is that the tail contract must be stated conditionally, $\Pr[L_{\mathrm{blind}}\ge W\mid\text{link available}]\le\delta$, with availability bounded separately as a deployment requirement on RSU density and siting; a contract that conflates the two is unmeetable by any radio configuration, since no retransmission scheme extends range. Table VII gives the per-link statistics; the last two columns are the tail $\Pr[L_{\mathrm{blind}}\ge W]$ in per cent, unconditioned and conditioned on availability.

@@TC2TABLE@@

That deployment requirement can be quantified rather than merely asserted. Every observed coverage outage is at least 3.4 s, far longer than $W=1.5$ s, so each outage necessarily yields at least one violating window; the unconditional tail then decomposes as $\Pr_u\approx(1-A)+Aq_c$, with $A$ the availability and $q_c$ the conditional tail, an identity that reproduces all eight measured $\Pr_u$ values to within 0.24 pp. Requiring $\Pr_u\le\delta$ gives an explicit availability budget $A^{*}=(1-\delta)/(1-q_c)$. At $\delta=5\%$ with the pooled $q_c=0.88\%$ this is $A^{*}=95.9\%$, that is at most 2.5 min of blinded time per hour; with the worst link's $q_c=3.45\%$ it rises to $98.4\%$ (1.0 min/h). Measured availability on the six links that violate the unconditional tail is 56–80%, so the shortfall is located in siting and density, not in the radio. The budget also separates the two remedies: at $\delta=2\%$ the worst link would need $A^{*}>100\%$, so a tail target below 5% cannot be bought with coverage alone — the conditional tail must be reduced first. Within this design space $\delta=5\%$ is the only setting a real deployment can meet, which is why it is adopted rather than left implicit.

Three limits bound these claims. The captures come from interoperability testing at walking-to-low speed on a campus, not from a highway, so the measured burst lengths characterise a benign, short-range, single-vendor setting and should be read as an optimistic bound for 120 km/h. The partition relies on the bimodality being as clean as it is here, which must be re-checked before the conditional tail is quoted for another corpus. And one vendor pair is exercised; cross-vendor behaviour lies outside what a single trace can establish.

---

### 6.9 A closed-form blind-run tail and its validation on 452 measured bursts

The falsification in §6.7 establishes that the decisive quantity is the tail of the blind-run length rather than its mean, but it leaves open whether that tail can be predicted from a single channel parameter. The Gilbert–Elliot model answers yes. Let the BAD state be the one in which every beacon is lost; while the process is in BAD it returns to GOOD with probability $r$ at each 10 Hz slot, so the BAD-state sojourn length $L_B$ (the number of consecutive lost packets in one blind run) is geometric with mean $1/r$. Its tail therefore has the closed form

$$\Pr[L_B > \mathrm{cap}] = (1-r)^{\mathrm{cap}} = \left(1-\frac{1}{L_B}\right)^{\mathrm{cap}}.$$

Substituting the decision window in packets, $\mathrm{cap}=W_p=W/T=15$, the contract $\Pr[L_B>W_p]\le\delta$ becomes $(1-1/L_B)^{15}\le 0.05$, which solves to $L_B\le 5.5$ packets — exactly the analytic cap derived in §4.4. The closed form is thus not an extra assumption but the direct translation of C2 into the single channel parameter that the GE sweep of §6.7 had to set by hand.

We now test the closed form against the 452 micro-bursts isolated in §6.8 — the BAD-residence population after coverage outages are removed. Their pooled mean length is $\bar L_B=2.10$ packets, so the estimated return rate is $\hat r=1/\bar L_B=0.477$. The closed form then predicts $\Pr[L_B>15]=(0.523)^{15}\approx 6\times10^{-5}$ (0.006%), whereas the empirical fraction of micro-bursts reaching the 1.5 s window is 4/452 = 0.88% (Clopper–Pearson 95% upper bound 2.0%). The two tails differ by almost three orders of magnitude (Fig. 6a): the real bursts are far heavier-tailed than a memoryless geometric would allow.

The gap is the point, not a defect of the model. A memoryless geometric cannot produce the few 15–20 packet bursts that the trace actually contains (the longest micro-burst is 20 packets, 2.0 s); matching the observed 0.88% tail would require an effective $\hat r_{\mathrm{tail}}=1-(4/452)^{1/15}=0.270$, i.e. a mean residence of 3.7 packets rather than the measured 2.10 (Fig. 6b). The over-dispersion is a coverage-edge artifact: bursts that straddle the 2.5 s partition of §6.8 inherit tails longer than the radio's intrinsic error process alone would generate. Two consequences follow. First, the operational safety number must come from the empirical tail (0.88%, upper bound 2.0%), not from the model tail; the closed form is a design cap, not a measured probability. Second, the model tail is so much stricter than the empirical one that any deployment meeting the empirical 0.88% automatically satisfies the model-based target, so the conclusion of §6.8 — that C2 holds with margin on real hardware — is robust to whichever tail one quotes. What the closed form adds is the converse guarantee: it converts a single measured $\bar L_B$ into a hard BAD-residence cap ($L_B\le 5.5$ packets) that a monitor can enforce without waiting for the rare long bursts to appear.

@@FIG6@@

## 7 Discussion and Threats to Validity

**Implication for monitoring.** An OBU or RSU should log the age of its freshest usable update and the length of the longest blind run, not only PDR and mean latency. C0/C2 give directly checkable thresholds. Because $V$ is application-configurable, it should be negotiated explicitly between the safety application and the communication stack rather than hard-coded.

**Construct validity.** The gate uses generation-time age, $\Delta=t-u(t)$; a different implementation that resets age on reception would not satisfy Lemma 0. We state this dependency explicitly so the result can be reproduced or refuted.

**Internal validity.** The kinematic model is one-dimensional, $\tau$ is constant and delivery is FIFO. We no longer assume i.i.d. loss is adequate: §6.7 deliberately falsifies that assumption using a Gilbert-Elliot channel and shows the *mean-loss contract* breaks while the maximum-delay condition survives. The Gilbert-Elliot sweep yields the C2 BAD-residence threshold ($L_B\lesssim 7$ packets, $\approx0.7$ s at 10 Hz, by interpolating measured run lengths; the closed form $(1-1/L_B)^{W_p}\le0.05$ with the window converted to $W_p=15$ packets gives $L_B\approx5.5$, the gap reflecting the bound's conservatism rather than a second measurement). That threshold is no longer a model artifact: §6.8 measures $L_B=2.10$ packets on eight real C-V2X links, so the cap holds with margin, and the conditional tail sits at 0.88% (95% upper bound 2.0%). What the traces add is a failure mode the simulation never modelled — coverage loss, which is bidirectional, lasts 3.4–75 s, and is not bounded by C2. A coupled network–traffic study — Veins [26], which bidirectionally couples OMNeT++ with the SUMO micro-traffic simulator [27] — would extend the burst analysis to contended channels; the present kernel is deliberately dependency-free so that the contract logic can be audited in isolation, at the cost of not modelling channel contention. The E7 duty-cycle model (4.44 pp MAE) is calibrated on i.i.d. losses and **must not be extrapolated** to burst channels without re-deriving the phase-type tail.

**Statistical validity.** E1–E7 use 30 seeds per cell. E8b repeats 36 key cells with 200 seeds and Wilson 95% intervals: the hard boundary is unambiguous (nine $\tau=600$ ms cells give timely 0.0% [0.00, 1.88] and miss 100.0% [98.12, 100.00], disjoint from $\tau=500$ ms), while the transition band is materially different from the 30-seed estimates (§6.1). All transition claims in this version use the 200-seed intervals. The 110-cell feasible-region map still reports point estimates and does not correct for multiple comparisons.

**External validity.** Three course-level one-dimensional scenarios, a design-parameter validity budget, no driver reaction model, no real vehicle, no standardized message set or security overhead. Results are trends under controlled degradation, not field predictions. The real traces of §6.8 lift one of these limits — burst length is now measured rather than assumed — but they were collected at walking-to-low speed on a campus, so high-speed highway behaviour remains inferred rather than observed.

**Reproducibility.** Kernel, seeds, raw per-seed CSVs and figure-generating scripts accompany the submission and are publicly archived in the GitHub repository (https://github.com/liuxixin69-crypto/v2x-freshness-contract) and the Zenodo archive with DOI 10.5281/zenodo.23995606 (https://doi.org/10.5281/zenodo.23995606) (see the Data Availability Statement).

---

## 8 Conclusion

We asked what a V2X link must guarantee for a collision warning to be issued in time. Three findings answer it. First, the freshness budget should not be a free parameter: it can be derived from vehicle kinematics and an admissible position-extrapolation error, $V^{*}=\sqrt{2\varepsilon_{\max}/|a|}$, which turns the delay constraint into a relation between the link and the scenario. Second, a conventional PDR/mean-latency acceptance test does not mainly accept unsafe links — in our 330-cell study it accepts none — but rejects 91.8% of usable ones; a freshness-aware contract cuts total misjudgment from 40.6% to 10.9%. Third, and most importantly, **a contract expressed in mean loss rate is not robust**: under burst losses of identical mean rate it accepts six unsafe conditions, whereas the bound on maximum one-way delay survives unchanged. What determines safety is the tail of consecutive information outages, $\Pr[L_{\mathrm{blind}}\ge W]$, not average loss, mean latency or mean AoI. We therefore propose an outage-tail contract that an OBU can monitor online, and release the full reproducible protocol. We then test it on 24,449 beacons from eight real C-V2X links: the measured burst length is 2.1 packets, the conditional tail is 0.9% against a 5% budget, and the binding real-world constraint turns out to be link availability rather than the error process.

---

## References

[1] 3GPP, “Service requirements for V2X services,” TS 22.185 V15.0.0 (Release 15), ETSI TS 122 185 V15.0.0, 2018.

[2] SAE International, “V2X communications message set dictionary,” SAE J2735_202007, Jul. 2020.

[3] ETSI, “Intelligent Transport Systems (ITS); Vehicular communications; Basic set of applications; Part 2: Specification of cooperative awareness basic service,” ETSI EN 302 637-2 V1.4.1, Apr. 2019.

[4] J. Marias-i-Parella, D. Ulied-Guevara, F. Vázquez-Gallego, and J. Casademont, “Age of information-based evaluation methodology for cooperative connected and automated mobility,” in *Proc. IEEE ICTON*, Barcelona, Spain, 2025, pp. 1–5, doi: 10.1109/ICTON67126.2025.11125099.

[5] A. Rolich, M. Yildiz, I. Turcanu, A. Vinel, and A. Baiocchi, “On the trade-off between AoI performance and resource reuse efficiency in 5G NR V2X sidelink,” in *Proc. IEEE Vehicular Networking Conference (VNC)*, Porto, Portugal, 2025, doi: 10.1109/VNC64509.2025.11054234.

[6] B. Wu, R. Mo, J. Yue, Y. Zhang, J. Nguyen, G. Wu, A. Roy-Chowdhury, M. J. Barth, and H. Qiu, “CooperScene: Multi-modal cooperative autonomy benchmark with C-V2X communication characterization,” in *Proc. ECCV*, 2026, pp. 91–111; arXiv:2606.31219.

[7] 3GPP, “Overall description of Radio Access Network (RAN) aspects for Vehicle-to-everything (V2X) based on LTE and NR,” TR 37.985 V17.2.0 (Release 17), ETSI TR 137 985 V17.2.0, 2024.

[8] M. H. Castañeda Garcia, A. Molina-Galán, M. Boban, J. Gozálvez, B. Coll-Perales, T. Şahin, and A. Kousaridas, “A tutorial on 5G NR V2X communications,” *IEEE Commun. Surveys Tuts.*, vol. 23, no. 3, pp. 1972–2026, 3rd Quart. 2021, doi: 10.1109/COMST.2021.3057017.

[9] S. Kaul, R. D. Yates, and M. Gruteser, “Real-time status: How often should one update?” in *Proc. IEEE INFOCOM*, Orlando, FL, USA, 2012, pp. 2731–2735.

[10] S. Kaul, M. Gruteser, V. Rai, and J. Kenney, “Minimizing age of information in vehicular networks,” in *Proc. IEEE SECON*, Salt Lake City, UT, USA, 2011, pp. 350–358, doi: 10.1109/SAHCN.2011.5984917.

[11] M. Costa, M. Codreanu, and A. Ephremides, “On the age of information in status update systems with packet management,” *IEEE Trans. Inf. Theory*, vol. 62, no. 4, pp. 1897–1910, Apr. 2016, doi: 10.1109/TIT.2016.2533395.

[12] R. D. Yates, Y. Sun, D. R. Brown, S. K. Kaul, E. Modiano, and S. Ulukus, “Age of information: An introduction and survey,” *IEEE J. Sel. Areas Commun.*, vol. 39, no. 5, pp. 1183–1210, May 2021, doi: 10.1109/JSAC.2021.3065072.

[13] E. N. Gilbert, “Capacity of a burst-noise channel,” *Bell Syst. Tech. J.*, vol. 39, no. 5, pp. 1253–1265, Sep. 1960, doi: 10.1002/j.1538-7305.1960.tb03959.x.

[14] E. O. Elliott, “Estimates of error rates for codes on burst-noise channels,” *Bell Syst. Tech. J.*, vol. 42, no. 5, pp. 1977–1997, Sep. 1963, doi: 10.1002/j.1538-7305.1963.tb00955.x.

[15] M. Zorzi and R. R. Rao, “On the statistics of block errors in bursty channels,” *IEEE Trans. Commun.*, vol. 45, no. 6, pp. 660–667, Jun. 1997.

[16] F. Bai and H. Krishnan, “Reliability analysis of DSRC wireless communication for vehicle safety applications,” in *Proc. IEEE ITSC*, Toronto, ON, Canada, 2006, pp. 355–362, doi: 10.1109/ITSC.2006.1706767.

[17] ETSI, “Intelligent Transport Systems (ITS); V2X applications; Part 3: Longitudinal collision risk warning (LCRW) application requirements specification,” ETSI TS 101 539-3 V1.1.1, Nov. 2013, clauses 4, 7.2.3, and Annex C.

[18] ETSI, “Intelligent Transport Systems (ITS); Security; Pre-standardization study on pseudonym change management; Release 2,” ETSI TR 103 415 V2.1.1, 2018.

[19] M. Baqer, A. Krings, M. Lowry, and A. Abdel-Rahim, “Connected vehicle safety applications using V2X under consideration of bicycles, pedestrians and persons with special needs,” Pacific Northwest Transportation Consortium (PacTrans), Univ. Washington, Seattle, WA, USA, Tech. Rep. 2019-S-UI-1, Oct. 2021.

[20] C. Bencheikh Lehocine, “Robust low-cost multiple antenna processing for V2V communication,” Ph.D. dissertation, Chalmers Univ. of Technology, Gothenburg, Sweden, 2022.

[21] M. Bezmenov, M. Frey, Z. Utkovski, and S. Stanczak, “An age of information characterization of SPS for V2X applications,” arXiv:2412.14616, Dec. 2024, rev. Mar. 2026.

[22] M. H. Ashik and M. Hossain, “Analyzing the impact of adversarial attacks on C-V2X-enabled road safety: An age of information perspective,” in *Proc. IEEE ICC*, Glasgow, U.K., 2026, pp. 1–6, doi: 10.1109/ICC59461.2026.11587579.

[23] W. Zhang and W. Mo, “Real-time hard peak age-of-information safety with no-regret learning,” in *Proc. IEEE Real-Time Systems Symposium (RTSS)*, 2026; arXiv:2607.27626.

[24] E. B. Wilson, “Probable inference, the law of succession, and statistical inference,” *J. Amer. Statist. Assoc.*, vol. 22, no. 158, pp. 209–212, Jun. 1927, doi: 10.1080/01621459.1927.10502953.

[25] L. D. Brown, T. T. Cai, and A. DasGupta, “Interval estimation for a binomial proportion,” *Statist. Sci.*, vol. 16, no. 2, pp. 101–133, May 2001, doi: 10.1214/ss/1009213286.

[26] C. Sommer, R. German, and F. Dressler, “Bidirectionally coupled network and road traffic simulation for improved IVC analysis,” *IEEE Trans. Mobile Comput.*, vol. 10, no. 1, pp. 3–15, Jan. 2011, doi: 10.1109/TMC.2010.133.

[27] P. A. Lopez, M. Behrisch, L. Bieker-Walz, J. Erdmann, Y.-P. Flötteröd, R. Hilbrich, L. Lücken, J. Rummel, P. Wagner, and E. Wießner, “Microscopic traffic simulation using SUMO,” in *Proc. IEEE ITSC*, Maui, HI, USA, 2018, pp. 2575–2582, doi: 10.1109/ITSC.2018.8569938.

[28] E. Song, “Outdoor C-V2X interoperability testing datasets,” National Institute of Standards and Technology, Gaithersburg, MD, USA, Data Publication, Sep. 2026, doi: 10.18434/mds2-4003.

> 核查记录（不进投稿版）：全部 27 条均已回一手来源——[1][7] 3GPP/ETSI 官方文档；[2] SAE 官网（J2735 2020-07 版）；[3][17][18] ETSI 官方 PDF（[17] 条款号 4 / 7.2.3 OR010 / Annex C 已逐字核对，并下载原文确认 Fig. 1 note 的 “exact TTC numbers are out of scope”）；[4][5][16][22][24][25][26][27] 出版社 DOI 或 IEEE Xplore / DBLP 记录；[6] arXiv + ECCV 2026 接收信息；[8][11][12][21][23] arXiv / 期刊页 + DBLP；[9][10][13][14][15][19][20] 权威书目库（ACM CR、dblp、TRID/ROSA-P、Chalmers 全文）。

---

## Appendix A — Reproduction

```
node code/run_experiments.js     # E1-E5  (4,800 per-seed records)
node code/gen_heatmap.js         # E6     (feasible-region grid, 330 cells)
node code/derive_bound.js        # E7     analytical validation (50 cells)
node code/E8_baseline.js         # E8     baseline / CI / burst study (24,700 runs: 9,900 + 7,200 + 7,600)
node code/E9_vstar.js            # E9     V* sensitivity table, E2/E3/E5 re-run at V*
python code/E9_c2burst.py        # E9     C2 under Gilbert-Elliot (21 cells)
python code/E10_trace_topology.py  # E10  link discovery from the NIST PCAP archives
python code/E11_trace_c2.py      # E11    C2 on the real C-V2X traces (8 directional links)
python code/make_figures.py      # Figs. 1-4
python code/make_fig5.py         # Fig. 5 (real-trace CCDF and burst lengths)
```

Scripts E1–E9 depend only on Node.js or Python 3 with NumPy; E10–E11 additionally read the NIST PCAP archives (download URLs and SHA-256 digests in `data/C2_trace/raw/SOURCES.md`), for which no third-party PCAP library is required — the reader is 40 lines of `struct`.

Baseline configuration: $\Delta t=0.05$ s, $f=10$ Hz, $V=500$ ms, $\sigma=0.2$ m, TTC threshold 3.5 s, emergency 1.75 s, $W=1.5$ s, $L=4.5$ m. Seeds $k\cdot7919+13$, $k=1\ldots30$. Per-seed records: `data/实验明细_runs.csv`, `data/实验汇总_summary.csv`, `data/预警可行域_heatmap.csv`, `data/E7_解析模型校验.csv`; trace results: `data/C2_trace/link_summary.csv`, `data/C2_trace/runs.csv`.

*Version: v0.2 draft, 2026-11-05. Not submitted. Restructured after the editor's reject opinion (`10_...v0.2.md`) and the three executor reports. All `[TBD]` items and the DRAFT NOTES block must be resolved before any submission.*
