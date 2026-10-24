# ⌘ Inference Engineering

**On-device AI · Edge Inference · Runtime Optimization**

Researching and engineering efficient LLM inference across mobile devices, desktop systems, and edge computing platforms.

从端侧运行时到边缘推理引擎，研究模型部署、内存管理、异构计算与性能优化，探索不同硬件约束下的大模型推理边界。

---

## 01 / Scope

Inference engineering across three deployment environments:

| Environment | Focus |
|---|---|
| Mobile | Smartphones, tablets, and resource-constrained devices |
| Desktop | Local LLM applications and CPU/GPU-accelerated inference |
| Edge | Jetson-class devices, edge GPUs, and heterogeneous compute systems |

The goal is not simply to run a model, but to understand **why it runs, how efficiently it runs, and where its bottlenecks lie.**

## 02 / Frameworks & Runtimes

### Mobile & On-device

Frameworks designed for local inference, cross-platform execution, and device-level optimization.

- [llama.cpp](https://github.com/ggml-org/llama.cpp) — Portable LLM inference, quantization, and hardware backends.
- [MLC LLM](https://github.com/mlc-ai/mlc-llm) — Compiler-based deployment across supported device backends.
- [ExecuTorch](https://github.com/pytorch/executorch) — PyTorch ecosystem for edge and mobile deployment.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime) — Cross-platform inference with hardware execution providers.
- [LiteRT](https://github.com/google-ai-edge/LiteRT) — On-device inference within Google's AI Edge ecosystem.

### Edge GPU & Local Serving

Inference engines and serving systems relevant to GPU-equipped edge devices and local workstations.

- [SGLang](https://github.com/sgl-project/sglang) — Serving architecture, scheduling, caching, and edge-GPU deployment.
- [vLLM](https://github.com/vllm-project/vllm) — Memory management, batching, scheduling, and serving architecture.
- [TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) — NVIDIA GPU inference optimization and deployment.
- [MLX](https://github.com/ml-explore/mlx) — Machine learning on Apple silicon.

Framework selection depends on hardware, model architecture, runtime dependencies, memory capacity, and deployment requirements. These projects are not assumed to be interchangeable.

## 03 / Core Engineering Topics

### Model Deployment

- Model formats, conversion, and compatibility.
- Weight-only and activation quantization.
- Model loading, initialization, and startup latency.
- CPU, GPU, NPU, and accelerator backend selection.
- Operator coverage, fallback behavior, and numerical consistency.

### Memory & KV Cache

- KV cache allocation and memory footprint.
- Long-context inference under constrained memory.
- Cache reuse and prefix caching.
- KV cache quantization and memory reduction.
- Cache eviction, lifecycle management, and memory fragmentation.

### Execution Optimization

- Prefill and decode performance.
- Attention kernels and operator fusion.
- CPU/GPU/NPU execution paths.
- Speculative decoding and token generation efficiency.
- Threading, batching, scheduling, and synchronization overhead.
- Power consumption, thermal throttling, and sustained performance.

### Edge Inference Architecture

- Local inference services and API interfaces.
- Heterogeneous execution across available compute devices.
- Model partitioning and execution placement.
- Prefill-Decode disaggregation where the hardware topology justifies it.
- Edge-cloud collaboration and local-first inference.
- Resource isolation and concurrent model execution.

## 04 / Performance Evaluation

Performance claims should be backed by reproducible measurements.

| Metric | What it measures |
|---|---|
| TTFT | Time to first token |
| TPOT | Average time per output token |
| Throughput | Tokens generated per unit time |
| Peak memory | Maximum runtime memory consumption |
| Model loading time | Time required to make the model ready |
| Energy consumption | Energy cost of inference, where measurable |
| Sustained performance | Performance under prolonged workloads |

Benchmarking principles:

- Compare equivalent models, prompts, output lengths, and precision settings.
- Record hardware, OS, driver, runtime, and configuration versions.
- Separate cold-start performance from steady-state performance.
- Report latency distributions rather than averages alone when possible.
- Include memory usage and power constraints alongside speed.
- Keep scripts, configurations, raw measurements, and analysis reproducible.

## 05 / Research & Experiments

Experiments are organized around explicit hypotheses and measurable outcomes.

- **Runtime comparison** — Evaluate framework behavior on identical workloads.
- **Quantization trade-offs** — Measure memory savings, latency, and quality impact.
- **KV cache efficiency** — Investigate memory growth and long-context behavior.
- **Heterogeneous execution** — Study backend selection and cross-device overhead.
- **Edge serving** — Evaluate concurrency, scheduling, and resource contention.
- **PD disaggregation** — Explore whether separating prefill and decode improves a specific edge workload after accounting for transfer costs.

PD disaggregation is an exploratory topic, not a default optimization. Its usefulness depends on available devices, interconnect bandwidth, workload characteristics, and KV transfer overhead.

### Field Notes & Guides

Concrete engineering write-ups grounded in shipped source, with explicit evidence levels.

- [Case Study: Running a 600 M Vision-Language Model on a Phone CPU](docs/case-d1-omni-on-device.md) — decision-head instead of token generation, ONNX Runtime 1.22 CPU/FP16/Q4 sessions, adaptive 30–60 s budgeting, and a measure-first optimization roadmap. *Timings loaded-only (software-rendered emulator); real device not-verified.*
- [On-Device CPU Inference Playbook](docs/on-device-cpu-inference-playbook.md) — portable checklist: bounded latency, drop-don't-queue scheduling, quantization/operator coverage, threading, session warm-up, and how to measure without extrapolating from emulators.
- [On-Device Composition Pipeline — v1 Architecture](docs/on-device-composition-pipeline-v1.md) — frozen v1 baseline of the camera-to-guide pipeline (four-layer frame dropping, rule layer, contact sheet, three ONNX sessions, adoption gates, adaptive cadence), known bottlenecks, and a measured-evidence v2 optimization backlog. *Loaded-only; real device not-verified.*
- [On-Device Pose Coaching: Temporal Filtering and Skeleton Retargeting](docs/on-device-pose-overlay-techniques.md) — visibility-gated One-Euro filtering on irregular live-stream cadence, three-layer presence/pose debounce, and bone-length retargeting of the target figure onto the observed body. *Experimental; synthetic-geometry probes only, real subjects not-verified.*

## 06 / Repository Structure

```text
inference-engineering/
├── README.md
├── docs/
│   ├── case-d1-omni-on-device.md
│   ├── on-device-composition-pipeline-v1.md
│   ├── on-device-cpu-inference-playbook.md
│   └── on-device-pose-overlay-techniques.md
├── benchmarks/
│   ├── configs/
│   ├── scripts/
│   └── results/
├── experiments/
│   ├── quantization/
│   ├── kv-cache/
│   ├── heterogeneous-execution/
│   └── edge-serving/
└── tools/
```

This structure is a proposed layout; directories should be added as corresponding work becomes available.

## 07 / Engineering Principles

- **Measure, don't assume.** Performance conclusions require evidence.
- **Reproduce before comparing.** Keep workloads and configurations explicit.
- **Optimize for constraints.** Memory, power, thermals, and latency all matter.
- **Separate facts from hypotheses.** Document limitations and failed experiments.
- **Prefer portable knowledge.** Distinguish framework-specific behavior from general inference principles.

## 08 / Status

This repository is a research and engineering workspace for on-device and edge inference.

Framework coverage, benchmarks, and experimental results should be documented as they are validated. Planned work is not presented as completed implementation.

---

**Understand the runtime. Measure the bottleneck. Optimize the inference.**

以实测为依据，以工程为边界。
