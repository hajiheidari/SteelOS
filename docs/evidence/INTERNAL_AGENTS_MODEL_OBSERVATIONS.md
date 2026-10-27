# Pre-release synthetic model observations — 2026-10-27

These are development observations, not a production quality benchmark. All inputs were
fixed synthetic briefs and an ownership/storage note. No real customer data or business
records were sent to the model. Existing free cached qwen3:1.7b was used, with thinking off.

- Initial common-output evaluation:2/4 passed structural/evidence validation; marketing/sales
  returned generic503. Raw failed replies were not captured, so the exact causes are unknown.
- After source-aware schema restrictions:4/4 passed those structural checks. Manual inspection
  still found inadequate education structure and an English sales answer interpreting ورق as
  paper. A structural pass was not counted as usable business quality.
- Role-specific three-part outputs and Persian-script checks:4/4 passed the structural gate,
  but manual inspection found repetitive/hollow research/marketing text and weak teaching answers.
- A more detailed Persian prompt hit the90-second deadline on research (90.09s). That evaluation
  was interrupted; it is not a completed four-case benchmark.
- A shorter bounded run passed3/4; research had a valid exact S1 quote but no per-section alias.
  The contract now explicitly permits document-level exact quotes with optional per-section
  references. Unknown aliases and invented quotes remain rejected; no semantic grounding guarantee
  is claimed by this change.
- The later1.7B run passed4/4 structural checks, with measured case durations75.15/67.99/73.73/53.5s.
  Manual inspection still rejected quality: repetitive research, a confused explanation of storage
  in education, and awkward/partial marketing/sales text.1.7B is not accepted as sufficient for
  these broad Persian drafting tasks merely because JSON/evidence checks pass.

Raw intermediate JSON/logs were stored in /tmp. A subsequent managed-environment interruption
cleared temporary files; those raw artifacts are unavailable. This note retains only observations
actually seen in tool output, not reconstructed replies or a fabricated reproducibility artifact.
The environment reported offline/running with failure=null; the cause is unknown.

An optional stronger-model evaluation was initiated. Official registry metadata for
qwen3:4b-instruct-2507-q4_K_M reported a2,497,280,480-byte model layer,
sha256:85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9.
The license layer sha256:d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12
identified Apache License2.0. The interrupted download/evaluation is not evidence of successful
4B inference. No weights enter source control or mandatory CI/setup. Final quality/readiness must
be recorded separately after an actual successful run and human review.

## Recovered actual4B evaluation and manual review

Execution recovered and the same already verified optional free cache was used. The missing
CPU runtime dependencies were copied from the existing trusted pinned Ollama image, not an
unrelated binary download. Actual inference completed; the earlier missing-runner/transport
blocker is resolved. Inputs below are entirely synthetic. Raw receipts are retained:

| Policy | Structural/evidence result | Interpretation |
| --- | --- | --- |
| [v1](INTERNAL_AGENTS_4B_V1_SYNTHETIC.json) |2/4: research120.13s/education120.10s timeout; marketing107.85s/sales97.66s passed | No broad content acceptance; long and awkward replies |
| [v2](INTERNAL_AGENTS_4B_V2_SYNTHETIC.json) |4/4,103.16/85.98/92.82/66.66s | All four contained clipped text or semantic problems; NOT accepted quality |
| [v3](INTERNAL_AGENTS_4B_V3_SYNTHETIC.json) |1/4; only marketing passed | Research/education lacked required quotes and correctly failed; sales503 coincided with runner termination |
| [v4 operator-stopped](INTERNAL_AGENTS_4B_V4_OPERATOR_STOPPED.json) |Two selected source cases ended503 after deliberate runtime shutdown | NOT a model-quality score or a four-role evaluation |
| [v5 mmap](INTERNAL_AGENTS_4B_V5_MMAP_SYNTHETIC.json) |4/4,63.25/57.89/62.55/39.06s | Complete short Persian replies and exact source quotes; semantic acceptance still failed |

The v1 receipt predates started_at/completed fields; it contains all four actually observed
cases. Subsequent receipts explicitly separate structural passed from quality_acceptance,
and requested_kinds identifies targeted runs. completed means the selected loop ended,
including failures; it never means semantic approval. The operator-stopped v4 attempt must
not be used to infer failed inference quality. No raw failed reply was available for v3 sales.

### v5 content review (one fixed synthetic case per role)

- Research: rejected. It proposes comparing IDs/ownership with95% agreement rather than
  testing independence from storage. This is not an acceptable stock-ownership invariant.
- Education: rejected. Repeated tautology «مالکیت از مالکیت مالکیتی است» fails to teach
  the distinction or answer a concrete scenario, despite a correct document quote.
- Marketing: an initial human-editable sample, not full acceptance. Short Persian post
  avoids price/stock promises, but the publication checks omit explicit source/brand/channel
  permission checks required by the task. No actual publishing took place.
- Sales: rejected. «تأیید سطح وقایع وقایع» is meaningless; discovery omits a useful grade
  question and follow-up lacks actionable business detail. No quote/stock commitment occurred.

Thus neither1.7B nor this4B setup is accepted for reliable broad Persian teaching/research/
sales drafting. JSON, exact quotes and terminal punctuation are necessary gates, not factual
or semantic verification. The default-disabled experimental provider and human review remain.
The separate documented learning curriculum is authored product content with deterministic
self-checks; it is not a successful generative-tutor benchmark.

### Resource observations and cleanup

The native experiment had an8GiB cgroup and two-CPU quota; its2.497GB weights were stored
on /tmp tmpfs, which also consumes RAM. Ollama0.40.10 logged disabling mmap by default for
CPU. During v3 sales memory.events increased oom/oom_kill from0 to1 and the runner logged
signal:killed at11:48:38UTC. This is evidence for this experiment, not a retrospective
explanation of the earlier unknown environment interruption.

The owned runtime was stopped; v4 was intentionally not completed as a quality benchmark.
v5 explicitly used use_mmap=true; the runtime logged load_mode=mmap. Observed whole-cgroup
memory samples were about5.9–6.2GB and oom_kill stayed1 throughout the completed four cases.
These are sampled measurements, not a peak-memory/load benchmark or a hardware guarantee.
CPU affinity was limited for this owned evaluation; the runtime reported three inference
threads under the two-CPU quota. No paid resource, external API, deployment or customer data.
Only the owned temporary model processes were stopped after evaluation; the verified cache
remains optional /tmp data and may disappear on environment replacement. No unrelated model
volume/image was removed. Future acceptance requires a suitable locally available Persian
model/runtime and a reviewed broader task set; do not repeat endless prompt changes against
this inadequate four-case baseline or claim that adding quotes validates its content.
