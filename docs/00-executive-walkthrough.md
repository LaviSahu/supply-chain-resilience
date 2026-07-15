# Executive Walkthrough

*A 10-minute, non-technical read. No code. Every number below came from
running `make demo` against the synthetic "Meridian Goods" network on
2026-07-14 — nothing here is invented or rounded for effect.*

For the one-page printable version of this same story, see
[`exec-brief.html`](exec-brief.html) (open in a browser, then Print → Save
as PDF).

## 1. The business question

Every supply chain quietly assumes that nothing important breaks at the
same time as anything else. That assumption is usually wrong, and it is
wrong in ways that are computable *in advance* — a single-source
supplier, a port with no bypass route, a demand spike that outruns
distribution capacity. The decision this tool is built to inform is not
"can something go wrong" (yes, always) but: **which failure would hurt us
most, how long would it take to recover, and is the fix worth what it
costs?** Resilience Radar answers that with arithmetic over a modeled
network and a 12-week what-if simulation — not a survey, not a
consultant's gut check.

## 2. The crown-jewel answer: which node hurts most, and for how long

Of the three disruption scenarios modeled, a **closure of the Port of
Singapore** — which takes the Singapore Regional Distribution Center
(DC-SG) offline for 2 weeks — is the worst outcome, even though it's the
*shortest* outage of the three. Here is why it beats a 4-week supplier
failure and a demand spike in actual damage done:

| | Port of Singapore Closure | Single-Source Supplier Failure | US East Demand Spike |
|---|---|---|---|
| Outage window | 2 weeks | 4 weeks | 3 weeks |
| Worst service level | **79.0%** | 85.9% | 97.9% |
| Time to Survive (TTS) | **0 weeks** | 1 week | 0 weeks |
| Time to Recover (TTR) | 2 weeks | 3 weeks | 3 weeks |
| Total lost revenue | **$578,800** | $529,143 | $98,400 |

**Time to Survive of 0 weeks** means there is no buffer at all — the very
first week of the closure already drops service below the 98% threshold.
That is the real finding: it isn't the longest disruption that hurts most,
it's the one with no slack behind it. A full DC closure hits every SKU
routed through Singapore at once; an air-freight bypass lane exists for
two products (SmartHome Hub, Wireless Charger), but three others (Tote
Bag, Travel Mug, Multi-Tool) have no bypass and take the full hit for both
weeks.

**The fix, and what it's worth:** the top-ranked response is
**Prioritized Allocation** — smarter demand/supply matching during the
shortage, at near-zero capital cost. It costs **$8,000** to implement and
avoids **$496,448** of the loss, for a **net benefit of $488,448**. A more
expensive option — dual-sourcing the disrupted input at **$180,000** —
avoids the full **$578,800** loss for a net benefit of **$398,800**: full
protection, but a smaller net return than the cheap fix. Both are
positive-return; three other levers in the playbook (pre-negotiated
alternate lanes, extra safety stock, pre-built buffer stock) come back
**negative** for this specific scenario — spending on them here would be
waste.

## 3. Where these numbers come from (the methodology)

TTR (Time to Recover) and TTS (Time to Survive) are established
supply-chain resilience metrics, not something invented for this demo.
They come from:

> Simchi-Levi, D., Schmidt, W., & Wei, Y. (2015). "Identifying Risks and
> Mitigating Disruptions in the Automotive Supply Chain." *Interfaces*,
> 45(5), 375–390. DOI: 10.1287/inte.2015.0804

In this tool: **TTS** is the number of consecutive weeks the network holds
service at or above 98% before a disruption first breaches that line;
**TTR** is the number of weeks from that first breach back to ≥98%
service. Every other number in this document — service levels, lost
revenue, mitigation costs and net benefits — is a direct, deterministic
output of a 12-week weekly simulation loop (capacity bottlenecks,
inventory drawdown, alternate-sourcing switch lag), not a model fitted to
match a story.

The wider KPI picture from the same run: **Revenue at Risk is $20,994,914**
across 35 open risks (3 CRITICAL, 6 HIGH, 2 MEDIUM, 24 LOW); the **Risk
Severity Index is 5.69** (mean score across the open register, on a 1–25
scale); and the network carries **1 identified single-source dependency** —
Rhineland Precision GmbH is the sole supplier of one input (SKU-E) into the
Wroclaw Assembly Plant, with zero sourcing redundancy. That same supplier
is independently the trigger of the "Single-Source Supplier Failure"
scenario above, which is the second-worst outcome in this analysis.

## 4. What's synthetic, and what this doesn't prove

Be clear-eyed about what this demo is and isn't:

- **The network and events are synthetic.** "Meridian Goods" is a
  fictional three-tier consumer-goods company; the ~35 disruption
  headlines are illustrative, not a live news feed. The three scenarios
  are hand-authored presets, not a stress-tested library of every failure
  mode.
- **The mechanics are real, not decorative.** The propagation math —
  capacity caps, inventory drain, lost sales, alternate-lane switch lag —
  is genuine deterministic simulation code, unit-tested (67 tests), and
  it recomputes fully if you edit the input JSON files. Nothing in the
  KPI tiles or the dashboard is hardcoded.
- **This is a methodology demonstration, not a fitted forecast.** It
  proves *the calculation is real and reproducible* — that TTR/TTS,
  mitigation ranking, and revenue-at-risk can be computed mechanically
  from a network model rather than argued from intuition. Applying this
  to a real supply chain would require replacing the synthetic network
  and event feed with the company's actual node/lane/SKU data and a real
  disruption-monitoring feed — the engine underneath does not change.
- **Costs and mitigation levers are illustrative placeholders**, not a
  procurement-grade costing exercise. Treat the ranking logic (net
  benefit = avoided loss − cost) as the reusable part; treat the specific
  dollar figures for mitigation cost as directional.

## 5. The executive takeaway

If you take one action from this analysis: **fund Prioritized Allocation
now.** It is the cheapest lever in the playbook ($8k) and it is the
top-ranked, positive-net-benefit response in *all three* modeled
scenarios — not just the worst one. Everything else in the mitigation
playbook (dual-sourcing, safety stock, alternate lanes, buffer stock) is
scenario-dependent and some options actively lose money if applied to the
wrong disruption. The broader decision this tool is built to support is
not "should we worry about Singapore" — it's **"do we have a repeatable,
numbers-first way to rank resilience spend before the disruption happens,
instead of after"** — and this demonstrates that the answer can be yes.
