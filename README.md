# Inference Engineering

端侧与边缘推理的工程研究仓：拆解单芯片上的推理链路，测量时间与内存的实际分布，检验云端推理技术在设备侧的成立条件。

Engineering research for inference on a single SoC: where the time goes, what the memory costs, and which cloud-era techniques survive device constraints. The first workload is the in-camera composition and pose inference in [`street-snap`](https://github.com/light-witness-lab/street-snap).

Evidence levels used everywhere: `verified` (measured on named hardware) · `loaded-only` (runs on emulator/desktop) · `not-verified`. Emulator numbers are never extrapolated to a real SoC.

## Field notes — what was built and what came out

| Note | Result | Status |
| --- | --- | --- |
| [Case: running a 600 M VLM on a phone CPU](docs/case-d1-omni-on-device.md) | A bidirectional decision head replaces autoregression: one forward pass, three logits, no KV cache, no output parsing. Three sessions (vision FP16/XNNPACK, embeddings + decision Q4). At 540×1170 a ranking takes ≈16–22 s; 1080×2340 frequently hits the 30 s budget and correctly times out. Adaptive budget `clamp(elapsed·1.5 + 2 s, 30–60 s)`. Background session warm-up applied 2026-10-20; INT8 vision tower queued pending calibration. | loaded-only (software-rendered emulator) |
| [CPU inference playbook](docs/on-device-cpu-inference-playbook.md) | Portable checklist ordered by leverage: reshape the workload before tuning kernels (generative→decision, single-pass candidate sheets, cheap always-on first stage), bounded self-limiting latency, drop-don't-queue scheduling, quantization/operator coverage, threading, warm-up, measure on the target device. | engineering checklist |
| [Composition pipeline v1 (frozen baseline)](docs/on-device-composition-pipeline-v1.md) | End-to-end shipping baseline: four frame-drop/coalescing layers, a pure-Kotlin rule layer at ≈2.4 evaluations/s drawing the guide immediately, one contact-sheet forward on the 600 M model, margin + permutation adoption gates. v2 optimization backlog itemized with evidence requirements; nothing in v2 has shipped. | loaded-only |
| [Pose coaching: filtering and retargeting](docs/on-device-pose-overlay-techniques.md) | One-Euro filtering on irregular live-stream cadence with visibility gating and 0.35 s hold-through, three-layer presence/pose debounce, bone-length retargeting of the target figure onto the observed body. | experimental (synthetic-geometry probes) |

## Goal and current gap

- **Goal:** content-adaptive understanding over a continuously analyzing viewfinder.
- **Today:** gated decisions at 1–3 per second; the model only picks between rule-layer candidates A/B/C or abstains. Continuous analysis is blocked by per-ranking latency (≈16–22 s on the emulator at 540×1170).
- **Next gate:** segmented p50/p95 latency and thermal-steady-state measurement on the Honor Vs3, then the INT8 vision tower with a gate-accuracy check. The executable benchmark protocol lives in the sibling repo [`edge-model-solutions/benchmarks/inference-perf`](https://github.com/light-witness-lab/edge-model-solutions/tree/main/benchmarks/inference-perf).

## Principles

- **Measure, don't assume.** A kernel setting ships only after on-device measurement.
- **Reshape before optimizing.** Decision outputs, shared-prefix single passes, and cheap first stages beat thread/quantization tuning; see the playbook's section 0.
- **Bound the latency.** Drop stale frames, never queue them; every slow path must degrade to a usable preview.
- **Separate facts from hypotheses.** Failed experiments and inapplicable cloud techniques are documented as such (case study §8 lists the cloud concepts that do not apply to a zero-token workload).
- **Keep it reproducible.** Record hardware, OS, runtime, revision, quantization, and the raw numbers.
