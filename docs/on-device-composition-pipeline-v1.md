# On-Device Composition Pipeline — v1 Architecture (Frozen Baseline)

*Field architecture · 2026-10-20 · Source baseline: street-snap `f809fc2` · Status: **loaded-only** —
all timings come from a software-rendered Android emulator; no real-device number has been measured.
This document freezes the shipping v1 pipeline as an optimization baseline. v2 work is proposed in
§7 with evidence requirements; nothing there has shipped.*

Companion documents: the workload/model detail and measured numbers live in the
[d1-omni case study](./case-d1-omni-on-device.md); the portable checklist distilled from this
system lives in the [CPU inference playbook](./on-device-cpu-inference-playbook.md).

---

## 1. What the pipeline does

An Android camera (`street-snap`) continuously analyses the viewfinder and draws a suggested crop
rectangle over the live preview:

- a **rule layer** (pure Kotlin over 96 px statistics) produces three candidate crops A/B/C at
  ≈ 2.4 evaluations/s on the AVD and draws a blue "frame analysis" guide immediately;
- a **600 M on-device VLM** runs at most once every few seconds and only picks A, B, C, or abstains.
  Adoption promotes the blue rectangle to a yellow "AI" guide;
- the model never generates coordinates, never touches the photo (crops are preview overlays only),
  and every path can abstain — abstention keeps the rule layer's guide rather than guessing.

The whole point of v1 is bounded, never-blocking assistance: the viewfinder stays live regardless
of model speed, and a slow device simply gets fewer completed rankings.

## 2. The ten stages, end to end

| # | Stage | Where (street-snap source) | Key facts |
|---|---|---|---|
| 1 | Frame acquisition | `camera/…/CompositionFrameSource.kt` | CameraX `ImageAnalysis` on the 640×480 YUV stream, `STRATEGY_KEEP_ONLY_LATEST`; rule cadence `minimumIntervalMs = 250`, scene re-sample `sceneIntervalMs = 250` (both validated 100…60000) |
| 2 | Frame drop/coalesce (4 layers) | `CompositionFrameSource` + `CompositionAssistant.kt` | (a) keep-only-latest, (b) `CONFLATED` single-consumer gate, (c) in-flight gate + rest in the serial frame clock, (d) single-flight model job (busy flag + inference mutex). Old frames are replaced and recycled, never queued |
| 3 | Cheap statistics | `composition/SceneReadings.kt`, `FastCompositionAdvisor.kt` | 96 px downsample, BT.601 luma, mirrored wings / column surveys / Otsu / autocorrelation; p50 2–3 ms on the AVD; no NN, no model dependency |
| 4 | Rule candidates | `FastCompositionAdvisor.kt` | 17 composition vocabularies, zero prior base scores; exactly three candidates A/B/C with normalized crops, Chinese advice copy and a precomputed move sentence (`CompositionActions.plan`, dead zones 6 % pan/tilt, 7 % dolly) |
| 5 | Scene dedup & gating | `CompositionAssistant.kt` | scene signature + unchanged frame reuse; the model is not re-run for static scenes; per-result generation drops frames from torn-down sessions |
| 6 | Model input build | `composition/CandidateContactSheet.kt`, `edge/D1NaFlex.kt`, `edge/D1Prompt.kt` | A/B/C rendered into one fixed 512×512 sheet; SigLIP2 NaFlex 32×32 grid → 1024 patch rows × 768 floats in [−1,1]; fixed marker choice prompt, 896 text positions (`comp-choice-v0`, frozen after an A/B wording experiment rejected the richer variant) |
| 7 | Model forward (three sessions) | `edge/D1OmniRuntime.kt` | one process ORT 1.22 (vendored arm64 AAR): FP16 vision tower (XNNPACK, 2–4 threads) → Q4 embeddings (`GatherBlockQuantized`) → Q4 decision head (`MatMulNBits`); single forward, three logits; one inference at a time, deadline calls `setTerminate`, close joins |
| 8 | Adoption gates | `edge/CropRanking.kt`, `composition/CandidateSelectionGate.kt` | support ≥ 0.10 (three valid labels vs full vocabulary) **and** margin ≥ 0.10 (top-1 minus top-2), plus cross-call order consistency (two calls with A/B/C permuted must select the same panel identity). Fail any gate → abstain, blue guide stays |
| 9 | Adaptive scheduling | `CompositionCadence.kt` | initial budget 30 s, ceiling 60 s; after completion `budget = clamp(elapsed·1.5 + 2 s, 30…60)`, cooldown `clamp(elapsed/2, 3…15 s)`; timeout doubles toward 60 s and sets 15 s cooldown. Budgets never queue frames |
| 10 | UI & closed loop | `CameraScreen.kt`, `composition/AlignmentFeedback.kt` | blue/yellow crop + Chinese action card; 220 ms rectangle interpolation; cross-fade with 600 ms clear grace; geometric "aligned" state (centre ≤ 0.09, scale ≥ 0.88) confirmed over 5 frames → persistent green frame, one-shot haptic pulse opt-in; bottom-right animated move arrow shows which way to nudge |

Cross-cutting: **session warm-up** — installed-model lookup, asset import and all three `ALL_OPT`
session builds run on `Dispatchers.IO` in a session-scoped job launched *before* `ImageAnalysis`
binds (applied 2026-10-20); the runtime is published through a ready-deferred and self-closes if the
session was torn down meanwhile.

## 3. Data and latency flow (v1 numbers, loaded-only)

```
camera @30fps ──KEEP_ONLY_LATEST──▶ 250 ms frame clock ──▶ 96px stats (~2–3 ms p50)
      │                                                        │
      └─ Preview (Camera2 TotalCaptureResult → live AE OSD)     ▼
                                                    3 candidates + blue guide (≈2.4/s on AVD)
                                                             │ scene changed & cooldown elapsed
                                                             ▼
                                            512 A/B/C sheet (build cost not separately profiled)
                                                             ▼
              vision FP16 ──▶ embeddings Q4 ──▶ decision Q4 ──▶ gates ──▶ yellow guide | abstain
              30–60 s deadline, single flight, drop-while-busy
```

| Surface (AVD, QEMU software render) | Observed |
|---|---|
| Rule layer rate after cadence tuning | 2.36–2.40 evaluations/s (0.87 before); interval p50 ≈ 410 ms; a ~180 ms fixed frame-prep/dispatch floor dominates, not the rule math |
| d1 end-to-end at 540×1170 | ≈ 16–22 s, completes within budget |
| d1 end-to-end at 1080×2340 | frequently approaches / exceeds 30 s → contract-correct timeout, blue guide retained |
| Per-pass log tags | `rank_vision_ms`, `rank_decision_ms`, `rank_total_ms`; app UI keeps a rolling 10-call wall-clock history (median/min/max) |

These are functional/relative measurements only. QEMU has no representative cache hierarchy,
big/LITTLE topology, thermal envelope, GPU or NPU — numbers can be faster or slower on hardware.
The target handset (Honor Vs3) has not run the pipeline. **not-verified.**

## 4. v1 invariants (do not regress in v2)

1. **Drop, never queue** at every stage; slow inference reduces result frequency, never adds latency
   to a later frame.
2. **Abstention is first-class** — the model only overrides the rule layer through two numeric gates
   and an order-consistency check; gates are observable diagnostics, not calibrated probabilities.
3. **The photo is sacred** — overlays never alter `ImageCapture` output; the long-press trial zoom
   is a display transform proven to leave JPEGs at full 3:4.
4. **Only real values on screen** — ISO/shutter/aperture come from actual `CaptureResult`s;
   capabilities gate which controls exist; no fabricated AUTO numbers.
5. **Untrusted model text** is parsed for exactly one bounded rectangle and cannot inject action
   copy; move sentences are generated by local geometry.
6. **Measure first** — every v2 change below needs either a re-exported graph validated by the
   composition regression probe or real-device measurement; emulator intuition does not ship.

## 5. Known v1 bottlenecks (hypothesis order, to be confirmed on-device)

1. FP16 vision tower over 1024 patches — convolution over the 512 sheet, most likely dominant.
2. Q4 block-quantized matmuls (embeddings + decision) — gains more likely from thread/core
   placement than fewer bits.
3. Cold session construction — already amortized by background warm-up (one-time cost).
4. Frame preparation/delivery — the measured ~180 ms floor even at a 200 ms frame clock was
   attributed (AVD-only) to the 384-edge YUV copy/getPixels plus CameraX frame-delivery granularity
   under software rendering; the model-side sheet build/NaFlex reorder has not been profiled
   separately and is not included in that number.
5. Sustained behaviour — thermal throttling and power draw have never been observed.

## 6. What v1 deliberately does not do

No autoregressive decode, no KV cache, no speculative decoding, no prefill/decode disaggregation,
no continuous batching (one interactive consumer, at most one in-flight ranking). No NNAPI/NPU path
yet. No aesthetic-quality claim: both v0 prompt variants and the rule layer were shown to be
position-answerers on synthetic probes; the only accepted aesthetic evidence is an independent
human-labelled photo set.

## 7. v2 optimization directions

Each item states lever, expected payoff, and the evidence required to ship. Ordered "measure first".

| # | Lever | Expectation | Evidence required / status |
|---|---|---|---|
| V2-1 | **Real-device per-pass profiling** (vision vs embeddings vs decision; 2/4 threads; big-core affinity) | Turns §5 from hypothesis to fact; gates everything else | Honor Vs3 measurement of `rank_*_ms` plus the in-app rolling history; **blocked: needs a device** |
| V2-2 | **Vision input 512 → 384** | Desktop probe (loaded-only, ORT 1.22 CPU): vision 1227 → 608 ms median (0.496×); gate-selected −1/18; bias metrics pass at 384; 320 failed confidence inflation and is rejected | Graph export supports variable NaFlex resolution, but this is an App contract change (patch layout/manifest): re-export + regression probe + **real-device** timing before shipping; proposed |
| V2-3 | **INT8 vision tower** | Likely biggest steady-state win vs FP16 conv | Quantization calibration + precision/gate-accuracy check on the probe set; no emulator-only claim |
| V2-4 | **NNAPI / NPU EP probe** | Possible accelerator win for the vision tower | Op-by-op fallback audit — `MatMulNBits`/`GatherBlockQuantized` are unlikely to delegate; exploratory |
| V2-5 | **Thread placement & affinity** | Cheap upside for Q4 passes once V2-1 maps the cores | Device A/B with fixed affinity; keep the demotion-safe XNNPACK fallback |
| V2-6 | **Frame prep trimming** (copy/reorder at §5 item 4) | Lower the ~180 ms floor; rule rate ceiling rises | Profile `CompositionFrameSource` → sheet pixels on device; verify KEEP_ONLY_LATEST backpressure unchanged |
| V2-7 | **Sustained performance & power** | Thermal curve, J/ranking, throttled steady-state | Device soak test, not first-shot timing |
| V2-8 | **Cascade value measurement** | Quantify how often the model actually changes the rule choice over real scenes; may justify an even rarer trigger or a smaller gate-keeper model | Independent human-labelled photo set — the same prerequisite as any aesthetic claim |

Process: v2 changes ship as dated amendments to this document (v1.1, v1.2…) with before/after
measurements attached; the frozen baseline above is not rewritten.

## 8. Evidence & limitations

- Architecture, parameters and file locations are read from shipping source at street-snap
  `f809fc2` (2026-10-20).
- Latencies are **loaded-only**, from a software-rendered emulator, and are not performance claims
  for hardware.
- Real-device latency, thermal/power behaviour, the live AE values, and the night-scene HDF glow
  are **not-verified** and require the Honor Vs3.
- Aesthetic correctness is **not-verified** pending an independent human-labelled photo set.
