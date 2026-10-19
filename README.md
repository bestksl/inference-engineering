# Inference Engineering

**Practical engineering for on-device LLM inference.**

Explore efficient local LLM inference on Android and PC, with a focus on KV cache management, memory efficiency, and reproducible performance evaluation.

KV cache optimization is the foundation. Prefill-Decode (PD) disaggregation is an exploratory direction.

## Scope

### 1. KV Cache Engineering

Optimize the memory footprint and runtime behavior of KV cache in resource-constrained environments.

Planned topics:
- KV cache memory usage and profiling
- Cache quantization and compression
- Prefix caching and reuse
- Cache eviction and memory-aware scheduling
- Long-context inference under constrained memory budgets

### 2. On-device Inference

Study practical deployment and optimization across local inference runtimes.

Target environments:
- Android and mobile devices
- Desktop and local GPU environments
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [ONNX Runtime](https://github.com/microsoft/onnxruntime)

The actual runtime and hardware support will be documented for each experiment.

### 3. Prefill-Decode Disaggregation

Explore whether separating prompt processing (Prefill) from token generation (Decode) can improve inference efficiency in local and edge environments.

Planned topics:
- Prefill and Decode performance characteristics
- Heterogeneous CPU/GPU/NPU execution
- KV cache transfer and reuse across execution stages
- Communication overhead and end-to-end latency
- Trade-offs between disaggregated and unified execution

PD disaggregation is an exploratory topic, not an assumed optimization. Its benefits depend on hardware topology, memory architecture, transfer overhead, and workload characteristics.

### 4. Benchmarking

Every optimization should be evaluated against a baseline.

Metrics may include:
- Time to First Token (TTFT)
- Time Per Output Token (TPOT)
- Tokens per second
- Peak memory usage
- Cache hit rate, where applicable
- Output quality and numerical differences

Experiments should record hardware, model, runtime version, configuration, workload, and measurement methodology.

## Project Status

| Area | Status |
|---|---|
| Repository scope and research roadmap | Defined |
| KV cache profiling and optimization | Planned |
| Local inference benchmarks | Planned |
| PD disaggregation experiments | Planned |

Status will be updated as implementations and measurements become available. Planned work should not be interpreted as completed functionality.

## Repository Structure

```text
inference-engineering/
├── benchmarks/     # Reproducible benchmark workloads
├── experiments/    # Optimization experiments
├── docs/           # Design notes and findings
└── README.md
```

Directories will be added as the corresponding work is implemented.

## Principles

- **Measure first:** identify bottlenecks before optimizing.
- **Reproducibility:** document configurations and benchmark methodology.
- **Hardware-aware:** distinguish device-specific results from general conclusions.
- **Evidence over claims:** report regressions and negative results as well as improvements.
- **Incremental engineering:** prioritize practical, measurable improvements.

## License

License to be determined.

---

Part of [Light Witness Lab](https://github.com/light-witness-lab).
