# pd-lab · 方案 002 阶段 1 脚手架

把 [方案 002](../README.md) 第 6 节「阶段 1」布起来的最小工具集：
1:1、单请求、单 slot、同机同盘、14B Q4。**只做协议跑通与开销测量，不追求性能提升。**

| 文件 | 作用 |
| --- | --- |
| `serve.sh` | 起停三个 llama-server：P `:8081`、D `:8082`、baseline `:8080`，带 `/health` 等待 |
| `router.py` | `:8090`，约 200 行零依赖编排：prefill-only → save → restore → 流式 decode + 全量计时 |
| `bench.py` | `mkprompt` 造确定性 prompt；`baseline`/`pd`/`check` 三个测量子命令 |

运行期目录（git 忽略）：`models/` 放 GGUF、`kv/` 是两端共享的 slot 文件目录、
`logs/` 是 pid 与 server 日志、`prompts/` 放生成的 prompt。

## 0. 前置（只需一次）

```bash
# llama.cpp 正式版（含 slot save/restore 端点），Metal 构建
cmake -B build -DGGML_METAL=1 -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build build --config Release -j
export LLAMA_SERVER=/path/to/llama.cpp/build/bin/llama-server

# 模型：两端共用同一个 GGUF、同一套上下文参数（KV 布局必须一致）
# 下载 DeepSeek-R1-Distill-Qwen-14B 的 Q4_K_M GGUF 后：
export PD_MODEL="$PWD/models/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"
```

不依赖 llama.cpp 先验证脚手架本身：`python3 router.py --selftest`（假 P/假 D，应打印
`"selftest": "PASS"`）。

## 1. E1：P/D 四步跑通（阶段 1 主战场）

```bash
./serve.sh up                      # 起 P:8081 + D:8082，等两个都 healthy
python3 router.py                  # 另开终端，router 监听 :8090
python3 bench.py mkprompt --tokens 8000 --out prompts/8k.txt
python3 bench.py check --prompt-file prompts/8k.txt --n-predict 32
```

`check` 是阶段 1 验收命令，退出码 0 必须同时满足：

1. **不重算**：D 端 `timings.prompt_n` 与 P 端相等，且 `prompt_ms` 接近 0
   （阈值 `max(50 ms, 0.05 × P 端 prompt_ms)`，原始值在 JSON 里都有）；
2. **逐字一致**：temp=0 下，P/D 路径与单体 baseline 输出完全相同；
3. **KV 完整**：restore 的 `n_read` == save 的 `n_written`。

JSON 里同时给出阶段 1 要的数据：`bytes_per_token = n_written / n_saved`、
`save_ms`、`restore_ms`、D 端 `ttft_ms`、端到端 `wall_ms`、`decode_tps`。

## 2. E0：单体基线

```bash
./serve.sh baseline                # :8080
python3 bench.py baseline --prompt-file prompts/8k.txt --n-predict 32
```

基线扫点（评审 E0）：用 `mkprompt --tokens 512|2048|8192|32768` 各造一份，
逐长度跑 baseline 与 `pd`，对比 TTFT，以及 save+restore 在总时延中的占比
（E3 净收益拐点的输入）。

## 3. 结果落档（跑通后）

按仓规把以下内容写进 `../results-stage1.md`（不预写）：

- llama.cpp 版本 commit；模型文件名与 `shasum -a 256`；三端完整启动参数（`logs/*.log` 开头有回显）；
- `bench.py` 的原始 JSON（建议 `| tee results/raw-*.json`）；
- 证据等级：在 M1 Max 本机实测即 `verified`，模拟器/他人数字不许混入；
- 踩中的 `not-verified` 清单（方案文档第 5 节六条）哪条成立、哪条不成立，逐条记录。

## 已知边界

- 单飞：router 忙时直接 503，不排队（与 App 侧 drop-don't-queue 同一纪律）；
  1:2 配比与并发扫点是阶段 2，本版不做。
- 正确性阶段固定 temp=0；sampler/RNG 是否随 slot 迁移不做假设。
- 32k 上下文 + 双实例各存一份权重，64 GB 机器内存余量自行留意（`logs/*.log` 有加载量）。
- `kv/` 必须是两端**同一个绝对路径目录**；`serve.sh` 已保证。
