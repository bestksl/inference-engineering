# On-device pose coaching: temporal filtering and skeleton retargeting

*Engineering note · 2026-10-25 · Reference implementation: street-snap fork commit
`5cf1738` (org PR pending) · Evidence: **experimental** — synthetic-geometry JVM probes
only; nothing here has been measured on a photographed subject.*

Companion records: solution SOP
[`edge-model-solutions/solutions/pose-assistant`](https://github.com/light-witness-lab/edge-model-solutions),
evaluation record `evaluations/pose-assistant-geometric-probe-2026-10-25.json`, and the
[CPU inference playbook](./on-device-cpu-inference-playbook.md) (drop-don't-queue and
degradation-contract items both apply to the pose path).

---

## 1. The problem

A small pose landmarker running on a phone CPU (MediaPipe PoseLandmarker lite, 384 px
input, ~5.8 MB fp16 bundle) gives 33 normalized landmarks at an irregular cadence. Its raw
output is not directly usable as a UI or coaching signal:

1. **Per-frame jitter** — on a standing subject, joints move several normalized percent
   between results; a skeleton drawn straight from the output visibly vibrates and a
   threshold-based score bar flickers.
2. **Occlusion holes** — an arm crossing the body, a turned head, or one dropped result
   makes individual landmarks disappear for a frame or two.
3. **Generic proportions** — a target figure placed with a single torso similarity
   transform has the template's shoulder width and limb lengths, so it floats beside a
   person whose proportions differ.

All three were fixed without changing the model, with geometry the app can prove on the
JVM before any device test.

## 2. One-Euro filtering on an irregular live stream

The [One-Euro filter](https://dl.acm.org/doi/10.1145/2207676.2208639) (low cutoff at rest,
higher cutoff when motion is fast) is the right primitive, with several details that
matter in production:

- **Use the real inter-result delta time, never a frame counter.** A LIVE_STREAM graph
  delivers results whenever inference finishes; cadence varies with device load and frame
  throttling. Every filter step takes `dt = now − previousUpdate` for that joint.
- **Tune in the coordinate unit you actually use.** Coordinates are normalized 0..1, so a
  fast arm sweep is roughly 1–2 units/s while stance jitter is around 0.05 units/s.
  `min_cutoff = 1.0 Hz`, `beta = 0.8`, `derivative_cutoff = 1.0 Hz` worked on synthetic
  probes (alternating ±0.008 noise around a still point attenuates below 0.005; a 0.6-unit
  jump catches up within a few frames). These numbers are not portable claims — re-tune on
  device.
- **Gate updates on visibility.** Only visible landmarks update their filter. Feeding an
  inferred or zeroed position through the low-pass pulls the estimate toward garbage.
- **On brief occlusion, hold — don't extrapolate.** The last filtered position (with its
  last real visibility) is kept for a short TTL (350 ms). Extrapolation from velocity
  confidently walks off the body; a held stale point is visibly the same pose and degrades
  gracefully. Past the TTL the point goes invisible.
- **After a long gap, adopt instantly.** A point unseen for more than a reacquire window
  (1 s) may belong to a new configuration; snap to the new observation instead of
  interpolating across the gap (which would draw the joint flying across the frame).
- **Treat a backwards clock as a new session.** Graph restarts can reset the timestamp
  base; negative `dt` must reset filter state rather than produce NaNs or spikes.

The filter is one independent state machine per joint, with no cross-joint model: cheap,
trivially testable, and impossible to destabilize globally.

## 3. Match debounce time constants to what they protect

The pose path uses three distinct temporal layers; collapsing them into one global
"smoothing" constant is the usual mistake.

| Layer | Mechanism | Window | What it prevents |
| --- | --- | --- | --- |
| Joint | One-Euro + occlusion hold | 350 ms TTL, 1 s reacquire | jitter; one-frame limb disappearance |
| Presence | empty/near-empty result grace (fewer than 8 visible points) | 350 ms | whole-skeleton flicker and streak reset on one dropped detector result |
| Pose | score hysteresis 0.75 in / 0.60 out, 4-frame confirm, 3-frame drop | 3–4 results | the ready cue firing on one lucky frame |

Note that detector-level confidence gates (the landmarker's 0.5 thresholds) and product
gates are separate concerns: the detector decides whether a landmark exists, the product
layers decide how long evidence must persist before the UI changes. The coaching score
itself is consumed **after** filtering, so its inputs and the drawn skeleton are the same
signal.

## 4. Bone-length retargeting for a teaching overlay

A target pose is directional guidance ("your arm, going like this"), which suggests
retargeting rather than rigid alignment:

1. Similarity transform from the torso (centre, length, lean) gives a base projection in
   the template's fixed proportions.
2. Pin the shoulder pair and hip pair to the **observed** joints exactly. The target's
   torso line and body width are then the user's own.
3. For the head and each visible limb chain, place every segment along the **template
   segment's direction with the observed person's measured segment length**
   (shoulder→elbow, elbow→wrist; hip→knee, knee→ankle). The figure becomes "you, doing the
   pose", at the user's real size.
4. Hidden middle joint: the whole chain keeps the base projection. Hidden end joint with a
   visible middle: keep the chain connected with the template's already-scaled segment
   length. Never let a missing measurement detach a limb or anchor it to an origin.

The function needs only the four torso anchors; every other joint is optional, and it is
pure geometry — exact anchoring and bone-length preservation are assertable in unit tests,
which is what made the feature safe to ship before device testing. What those tests cannot
assert is whether the amber figure *reads* as correct to a person following it; that is a
T90/T91 question.

## 5. Head-pose proxies degrade with the observable anatomy

A 2-D "look back" / "chin up" proxy computed from ears requires two ears, but the pose
itself hides one. Whenever a measurement's ideal landmarks are occluded by the very pose
being coached, provide an anatomy-ratio fallback (one ear plus an adult
head-width/shoulder-width ratio, 0.40, explicitly experimental) and reserve the
"face hidden" message for the case where even the fallback inputs are gone. The
alternative — demanding landmarks the successful pose suppresses — makes the coach fail
precisely when the user does the action right.

## 6. What must not be inferred

- Passing synthetic geometry tests proves the mapping and the filter contract; it does not
  prove skeleton-to-body pixel accuracy on real silhouettes, scoring validity on real
  poses, or any latency/thermal property.
- One-Euro constants and the 0.40 head/shoulder ratio are calibrated on formulas and
  fixtures, not subjects. Re-tune from real sequences and record the values.
- 2-D angle proxies (chin-up, twist, weight shift) ignore depth; a side-profile chin-up is
  not observable head-on by construction. Do not upgrade the wording when the model
  happens to return a high score.

## 7. Applicability

The same toolkit transfers to any interactive on-device keypoint UI (hand/finger
coaching, fitness reps, AR alignment): visibility-gated One-Euro with real `dt`, layered
time constants by what each gate protects, and retargeted rather than rigidly overlaid
guides. Keep the geometry pure and exhaustively tested; keep the device-dependent
conclusions unclaimed until measured.
