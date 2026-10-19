# On-Device CPU Inference Playbook

A portable checklist distilled from the [d1-omni field note](./case-d1-omni-on-device.md). It
applies to interactive models that run locally on a phone CPU with a hard latency budget. Items are
ordered by leverage and are phrased as decisions, not prescriptions — measure each on the target
device before committing.

Evidence convention used here: a change is **verified** only with on-device measurement,
**loaded-only** when seen on an emulator/desktop, and **not-verified** until measured on hardware.

---

## 0. Reshape the problem before tuning kernels

The largest win is usually not a kernel. Ask what the caller actually consumes.

- Can a *generative* output become a *classification / decision* output? A softmax over a few
  fixed markers removes the decode loop, the KV cache, output-length variance, and output parsing.
- Can candidates be evaluated together in one pass (e.g. a contact sheet) instead of N passes?
- Can a cheap first stage do the always-on work and invoke the large model rarely?

In the reference case this conversion — one forward, three logits, explicit abstention — mattered
more than any thread or quantization setting.

## 1. Make latency bounded and self-limiting

Interactive viewfinders cannot wait on an open-ended inference.

- Set a **hard per-request deadline** with cooperative termination (`RunOptions.setTerminate` or
  equivalent); never abandon a native call without joining it at teardown.
- **Drop, don't queue.** At most one in-flight model call; a request arriving while busy returns
  "no result" and keeps only the newest frame. Backlogs feel like progressive slowdown.
- **Adapt cadence to the device.** Track elapsed time; give a slow device a longer deadline *and* a
  longer rest. Budget/cooldown controllers space out work; they never accumulate it.
- Keep the cheap UI layer updating independently so the screen never blocks on the model.
- Reuse prior answers when the scene is unchanged, but make reuse explicit (a change signature),
  not an accidental stale frame.

## 2. Quantization and operator coverage

- Prefer weight-only quantized matmuls for large towers (e.g. 4-bit block-quantized), but verify
  the **runtime version actually executes the intended kernel**. A graph that silently falls onto
  an unpacked path is both slow and wrong-precision.
- Pin the runtime version and, at load time, assert input dtypes/shapes and required inputs;
  fail closed on an incompatible graph.
- Provide a **fallback execution path** when an accelerated provider rejects an operator
  (XNNPACK/NNAPI may not cover custom quantized ops).
- Treat NNAPI/NPU delegation as exploratory: enumerate which ops actually delegate and which fall
  back to CPU; a single unsupported op can erase the benefit.

## 3. Threading and core placement (measure on a real SoC)

- Intra-op threads should reflect usable cores; `coerceIn(2, 4)` is a sane starting range on phones
  — more threads often cost more in synchronization and thermal ramp than they gain.
- Set inter-op threads to 1 for a serial multi-session pipeline; parallelism belongs *inside* a
  pass, not across dependent passes.
- Keep the model worker at normal/native priority so big.LITTLE scheduling does not demote native
  kernels; isolate camera/analysis work on its own executor.
- Sweep thread count and test big-core affinity **on hardware**; emulator i-cache and scheduling
  tell you nothing about a real cluster.

## 4. Startup and session lifecycle

- Session construction (graph load + optimization level + kernel selection) is a real cold-start
  cost. Build sessions once and reuse them; **warm them in the background** after install/enable,
  before the first user-visible request.
- Initialize the runtime environment once (it is typically process-global); sessions are owned,
  the shared environment is not.
- Release sessions and join native calls deterministically when the feature turns off or the model
  is uninstalled.

## 5. Input pipeline

- Cap and fix input resolution deliberately; every extra patch multiplies the vision tower cost.
- Do color conversion / resize / patch reorder on a background dispatcher; avoid per-pixel
  allocation in the hot path.
- If you want lower resolution, confirm the graph supports variable shapes; otherwise it requires
  a re-exported model, and you must re-prove gate accuracy — a "free" downscale usually is not.

## 6. Memory

With no KV cache (decision-style models), watch instead:

- session/workspace arena size and peak RSS on the target device;
- FP32 input and intermediate embedding buffers (a 1024×768 patch tensor and a
  prefix+text embedding buffer are allocated per call);
- buffer reuse across calls and prompt release of temporary `Tensor`/`Result` handles;
- model footprint versus the app's RAM budget under background-memory pressure.

## 7. Measure correctly

- Emit **per-stage timings** (vision / embeddings / decision), not just one opaque total, so a
  change is attributable to a stage.
- Report cold vs warm separately; report a latency distribution, not a single mean.
- Record runtime version, precision, threads, provider, device, SoC, OS, and thermal state.
- Never extrapolate QEMU/desktop numbers to a phone: topology, translation, cache, and the
  accelerator are all different. Label them loaded-only.
- Measure sustained throughput and temperature, not only the first shot; throttling is the
  real-world steady state.
- Quality and speed are separate axes. A faster model that no longer discriminates is a regression;
  keep a fixed, re-runnable accuracy/gate probe and a human-labelled evaluation for aesthetic
  claims.

## 8. A short ship checklist

- [ ] The model returns the minimal artifact the UI needs; abstention is explicit.
- [ ] Hard deadline + cooperative cancel + clean teardown.
- [ ] At most one in-flight call; busy frames are dropped/coalesced.
- [ ] Adaptive cadence; UI never blocks on inference.
- [ ] Pinned runtime; shape/dtype assertions; provider fallback proven.
- [ ] Sessions warmed and reused; runtime initialized once.
- [ ] Per-stage timings in logs; cold/warm and sustained measured on the target device.
- [ ] Accuracy/gate probe passes for any quantization or resolution change.
- [ ] Emulator results are labelled loaded-only; real-device and quality claims are not made until measured.
