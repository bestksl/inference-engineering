
<div align="center">

# INFERENCE ENGINEERING

### Practical LLM Inference · 推理系统工程实践

**Understand the internals. Measure the trade-offs. Optimize what matters.**

从原理分析到性能验证，从推理链路到工程优化。

[![Focus](https://img.shields.io/badge/Focus-LLM%20Inference-58A6FF?style=flat-square)](#scope)
[![Approach](https://img.shields.io/badge/Approach-Evidence--Driven-8957E5?style=flat-square)](#methodology)
[![Status](https://img.shields.io/badge/Stage-Experiments%20%26%20Engineering-238636?style=flat-square)](#scope)

</div>

---

## About

`inference-engineering` is an open-source collection of experiments, technical investigations, and engineering practices for LLM inference.

本项目关注大模型推理过程中的关键机制与工程权衡，通过源码分析、实验复现和性能基准，理解推理系统如何工作，以及优化在什么条件下真正有效。

The goal is not to build another inference engine from scratch, but to understand existing systems, validate optimization techniques, and turn useful findings into reproducible engineering practices.

## Scope

| Area | Topics |
| --- | --- |
| **KV Cache** | Memory management, prefix caching, cache reuse, memory efficiency |
| **Prefill & Decode** | PD disaggregation, scheduling, workload characteristics |
| **Serving** | Continuous batching, request scheduling, concurrency |
| **Performance** | TTFT, TPOT, throughput, latency, resource utilization |
| **Runtime & Engines** | SGLang, vLLM, configuration and implementation comparisons |
| **Communication** | KV transfer, data movement, distributed inference overhead |

## Methodology

We prefer measurable results over assumptions.

1. **Understand** — Read the implementation and identify the mechanism.
2. **Establish a baseline** — Record environment, configuration, workload, and metrics.
3. **Experiment** — Change one variable at a time whenever practical.
4. **Measure** — Compare latency, throughput, memory, and resource utilization.
5. **Document** — Publish results, limitations, reproduction steps, and failed attempts.

## Experiments

Experiments and findings will be added as they are implemented and validated.

- [ ] KV Cache behavior and memory analysis
- [ ] Prefill / Decode disaggregation experiments
- [ ] Serving configuration and scheduling comparisons
- [ ] Reproducible inference benchmarks
- [ ] Performance profiling and bottleneck analysis

## Repository Structure

```text
inference-engineering/
├── docs/           # Technical notes and architecture analysis
├── experiments/    # Reproducible experiments
├── benchmarks/     # Benchmark scripts and results
├── configs/        # Experiment configurations
├── scripts/        # Utilities and automation
└── README.md
```

The structure will evolve with actual experiments rather than speculative abstractions.

## Principles

- **Evidence over assumptions** — Measure before drawing conclusions.
- **Reproducibility over screenshots** — Preserve configurations and test conditions.
- **Trade-offs over hype** — Document limitations as well as improvements.
- **Engineering over buzzwords** — Prefer working experiments to unsupported claims.

---

<div align="center">

**READ THE CODE. RUN THE EXPERIMENT. VERIFY THE RESULT.**

理解机制 · 验证假设 · 沉淀实践

Part of [Light Witness Lab](https://github.com/light-witness-lab).

</div>
