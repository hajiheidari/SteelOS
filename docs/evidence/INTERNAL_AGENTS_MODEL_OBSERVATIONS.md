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
