# Case Study: Running a 600 M Vision-Language Model on a Phone CPU

*Field note · 2026-10-20 · Status: **loaded-only** — all timings come from a software-rendered
Android emulator; no physical-device number has been measured yet.*

This is the repository's first concrete engineering case. It documents how a sibling project
([`street-snap`](https://github.com/light-witness-lab/street-snap), an Android street-photography
camera) runs a ~600 M vision-language model entirely on-device to rank composition candidates,
what is slow, why, and which optimizations are queued versus already applied.

Everything below is grounded in shipped source, not aspiration. Numbers carry explicit evidence
tags; nothing measured under QEMU is extrapolated to a real SoC.

---

## 1. The workload

The camera continuously samples the viewfinder. A cheap **rule layer** (96 px statistics, pure
Kotlin) produces three candidate crops `A / B / C` at roughly one evaluation per second and draws
them immediately. A large on-device model runs **infrequently** and does only one thing: choose
which of the three candidates is best, or abstain.

The decisive engineering choice is that the model **does not generate tokens**. Instead of an
autoregressive VLM that emits a rectangle and an explanation token by token, the graph ends in a
bidirectional decision head whose output is a softmax over three fixed option markers. One forward
pass yields the answer.

This single choice removes an entire failure class from the on-device problem:

| Autoregressive VLM | This decision-head design |
|---|---|
| Prefill + a decode loop, one matmul per token | One vision pass + one embedding pass + one decision pass |
| Growing KV cache, per-token state | No KV cache at all |
| Output length → unbounded latency | Fixed latency: three logits |
| Free-form text must be parsed/sandboxed | Three bounded logits; bad text cannot inject behavior |
| TTFT + TPOT both matter | Only one end-to-end latency matters |

The model still abstains, and abstention is first-class. Two independent gates must pass before
the model overrides the rule layer:

- **support** ≥ 0.10 — probability mass of the three valid labels against the full vocabulary;
- **margin** ≥ 0.10 — gap between the top two label probabilities;
- plus a cross-call **order-consistency** check at the call site.

These gates are *observable diagnostics*, not calibrated probabilities of photographic quality.

## 2. Model graph and quantization

Model: `onnx-community/d1-omni-600M-ONNX` (pinned revision), running through three separate
`OrtSession`s in one process-wide `OrtEnvironment`:

| Session | Content | Weight precision | Execution |
|---|---|---|---|
| `vision` | SigLIP2 image tower (NaFlex patch layout) | **FP16** | XNNPACK |
| `embeddings` | token → hidden embeddings, block-gather | **Q4** (`GatherBlockQuantized`) | CPU |
| `decision` | bidirectional head, `MatMulNBits` | **Q4** | CPU |

Input contract:

- One fixed **512 × 512** contact sheet containing the A/B/C candidates.
- SigLIP2 NaFlex: a 32 × 32 grid of 16 px patches → **1024 patch rows × 768 floats** (RGB,
  scaled to `[-1, 1]`), fed as FP32.
- The vision tower projects these to **256 prefix embeddings** (a 2 × 2 unshuffle projector).
- The text sequence (a fixed choice prompt) is token-embedded, concatenated after the image
  prefix, and the decision graph gathers the three marker logits. Output shape `[1, 3]`.

> **Quantization caveat (shipped workaround).** The official 8-bit decision graph is unusable on
> ONNX Runtime 1.22: its nodes lack `accuracy_level=4`, so the runtime takes an unpacked path that
> only supports 4-bit weights. The pinned build therefore uses the Q4 graph. This is exactly the
> kind of operator-coverage/version interaction called out in the framework notes — the same
> model is not interchangeable across runtime versions.

## 3. Runtime configuration

- **Runtime:** ONNX Runtime **1.22.0**, vendored as a local AAR
  (`onnxruntime-android-1.22.0-arm64.aar`), `arm64-v8a` only. No download of a new runtime is
  permitted at install time.
- **Thread budget:** `intraOpThreads = availableProcessors().coerceIn(2, 4)`; every session sets
  `interOpNumThreads = 1` and `OptLevel.ALL_OPT`. The three passes are therefore *intra-session*
  parallel but *serial with respect to each other*.
- **Vision** enables XNNPACK (`intra_op_num_threads` = the 2–4 budget) but sets the standard ORT
  intra-op count to 1; the convolution-heavy tower is intended to ride XNNPACK's own pool.
- **Embeddings / decision** run on the stock CPU executor with 2–4 intra-op threads; they do **not**
  enable XNNPACK because the quantized block ops may not be covered by a vendor XNNPACK path.
- **Graceful fallback:** if a session fails to construct with XNNPACK, it retries CPU-only, so a
  supported graph still loads even where the accelerated path rejects an operator.
- **Thread priority:** the single model worker keeps `THREAD_PRIORITY_DEFAULT` deliberately, so
  native kernels are not demoted on big.LITTLE scheduling. Camera analysis runs on a separate
  executor and is never blocked behind model work.
- **Concurrency:** at most one inference. A second call while one is in flight returns `null`
  immediately (an atomic `running` flag) — work is **dropped, never queued**.
- **Cancellation:** a deadline abort calls `RunOptions.setTerminate(true)`; `close()` terminates
  and then joins the native call so the process never tears down a session mid-kernel.

## 4. Request lifecycle and adaptive scheduling

A `CompositionCadence` controller turns observed latency into the next deadline and rest interval,
so a slow device is not asked to keep a fast device's cadence:

- initial per-request budget **30 s**, hard ceiling **60 s**;
- on completion: `nextBudget = clamp(elapsed·1.5 + 2 s, 30 s … 60 s)`;
- cooldown before sampling another fresh frame: `clamp(elapsed/2, 3 s … 15 s)`;
- on a true timeout: budget doubles toward 60 s and cooldown goes to 15 s;
- the viewfinder rule layer keeps running throughout, so the screen never waits on the model;
- unchanged frames reuse the prior answer instead of re-inferring.

Budgets and cooldowns **never queue frames**; they only space out fresh work. The combination of
"busy → drop" plus adaptive cooldown means latency is self-limiting: a slow model simply produces
fewer, fully-completed rankings rather than a growing backlog.

## 5. Measured numbers (loaded-only)

All figures are from an **Android 35 ARM64 emulator (QEMU, software-rendered)** driving the
shipped APK. They characterize *functional* behavior and relative cost only.

| Viewfinder surface | Observed d1 end-to-end | Outcome |
|---|---|---|
| 1080 × 2340 | frequently approaches / exceeds the 30 s budget | often falls back via timeout |
| 540 × 1170 | ≈ 16 – 22 s | completes within budget |

Per-pass timings (`rank_vision_ms`, `rank_decision_ms`, `rank_total_ms`) are emitted to logcat and
are the intended basis for before/after optimization comparisons.

**Evidence boundary — do not over-read these.**

- QEMU translates CPU instructions and has no representative cache hierarchy, big/LITTLE core
  topology, thermal envelope, NPU, or GPU compute path. These numbers can be *slower or faster*
  than any real phone.
- The target handset (a foldable phone) has **not** run this model. Real-device latency, sustained
  performance under thermal throttling, and power draw are all **not-verified**.
- No aesthetic-quality claim is being measured. Whether the chosen crop is actually better is a
  separate question whose only accepted evidence is an independent human-labelled photo set.

## 6. Where the time goes (hypotheses, ranked)

To be confirmed by per-pass sampling on a real device; listed in anticipated order of impact:

1. **The FP16 vision tower over 1024 patches.** Convolution over a 512 sheet on CPU is the most
   likely dominant cost; the fixed 32 × 32 grid means patch count cannot be trimmed without
   changing/exporting the graph.
2. **Q4 block-quantized matmuls in embeddings + decision.** Already aggressively quantized; gains
   here are more likely from thread placement and core affinity than from fewer bits.
3. **Cold session construction.** Three sessions are created with `ALL_OPT`, paying graph
   optimization and kernel selection up front before the first ranking.
4. **Frame preparation.** Pixel extraction and the NaFlex patch reorder on `Dispatchers.Default`;
   small versus the kernels but non-zero, and it scales with the 512² copy.

## 7. Optimization roadmap

Ordered "measure first, then change." Items tagged with status.

| # | Lever | Expectation / cost | Status |
|---|---|---|---|
| 1 | **Warm up sessions in the background** once the model is installed and the feature is enabled, so first user-visible ranking doesn't pay session-build cost | Removes a one-time multi-second cold-start hit; no model change | **applied 2026-10-20.** Bundled-asset import, install lookup and all three `ALL_OPT` session constructions now run on `Dispatchers.IO` in a session-scoped job launched *before* `ImageAnalysis` is bound, so graph optimization overlaps CameraX binding; the runtime is published via a ready-deferred and self-closes if the session was torn down meanwhile |
| 2 | **Verify busy-frame dropping/coalescing end to end** (analysis frames while inferring keep only the newest) | Guarantees no backlog / "gets slower the longer it runs"; the ranker already returns null while busy, this closes the frame-side gap | **applied 2026-10-20 (audit, no code change needed).** Four layers confirmed: `STRATEGY_KEEP_ONLY_LATEST`, a `CONFLATED` single-consumer frame gate, an in-flight gate with rest in the serial frame clock, and single-flight scheduling (model job + busy flag + a shared inference mutex); old frames are replaced and recycled, never queued |
| 3 | **Per-pass timing on real hardware** (vision vs embeddings vs decision), thread count 2/4, and big-core affinity | Converts §6 from hypothesis to fact; gates every later change | blocked: needs a device |
| 4 | **Lower input resolution (512 → 384/320)** | NaFlex patches and the 256-prefix projector are fixed; requires a re-exported variable-resolution graph **and** a regression probe proving the support/margin gates still discriminate | proposed, risky |
| 5 | **INT8 vision tower** | FP16→INT8 conv may be the biggest steady-state win, but needs quantization calibration and a precision/gate-accuracy check | proposed |
| 6 | **NNAPI / NPU execution provider** | The custom block-quantized ops (`MatMulNBits`, `GatherBlockQuantized`) are unlikely to be delegated; treat as exploratory and measure op-by-op fallback | exploratory |
| 7 | **Reuse unchanged-scene answers / continuous equal-value acceptance** | Already partly present (sample interval + unchanged-frame reuse); tighten without adding latency | partial |
| 8 | **Sustained-performance & power measurement** | Thermal throttle curve and energy per ranking, not just first-shot latency | blocked: needs a device |

The rule is the repository's own principle: **measure, don't assume.** Items 4–6 must not ship on
emulator intuition; each needs either a re-exported graph validated by the composition regression
probe or real-device measurement.

## 8. Topics from the README that do *not* apply here

It is worth recording the negative results too.

- **KV cache (allocation, quantization, reuse, eviction):** not applicable. The decision-head
  redesign removes the decode loop, so there is no per-token cache to manage. The relevant memory
  questions are session/workspace size and the FP32 patch and embedding buffers, not KV growth.
- **Speculative decoding / TPOT:** not applicable; there are no generated tokens.
- **Prefill–decode disaggregation:** not applicable. There is a single fixed forward per request on
  a single local device; there is no separable prefill/decode phase and no interconnect transfer
  whose cost could justify disaggregation.
- **Continuous batching / serving concurrency:** not applicable; this is one interactive local
  consumer with at most one in-flight ranking, deliberately.

The general principle that *does* transfer: **reshape the model to the decision you actually
need.** Eliminating generation was worth more here than any kernel-level tuning of a generator.

## 9. Evidence and limitations

- Architecture, quantization, threading, scheduling, and gate values above are read from shipping
  source (ONNX Runtime session construction, NaFlex patch layout, adaptive cadence, ranking
  gates).
- Latency ranges are **loaded-only**, from a software-rendered emulator, and are not performance
  claims for hardware.
- No real-device, thermal, power, or aesthetic-quality measurement is included; all are
  **not-verified** and are prerequisites before any user-facing performance statement.
