# 推理链路实验 · Inference Path Experiments

本仓所有「把一条推理链路真正布起来」的实验都放在这里。每个方案一个编号目录，
文档回答同样的四个问题：**用什么技术方案、推理怎么流动、怎么落地布起来、证据到哪一级**。
这里写的是**实现路径设计**（architecture & wiring），不是逐步照敲的部署 runbook；
实测命令与数据在各方案跑通后以 `results-*.md` 补入。

证据标签沿用仓规：`verified`（指名硬件上实测）· `loaded-only`（仅资料/他人机器/桌面模拟）·
`not-verified`（设计假说，待证伪）。

## 方案索引

| 编号 | 方案 | 形态 | 状态 |
| --- | --- | --- | --- |
| [001](001-on-device-vlm/README.md) | 端侧单芯片 VLM：手机 CPU 上的 600M 决策模型 | Android 端侧，无云端，双支路（MediaPipe 姿态 + ONNX Runtime 稀疏排序） | 基线已冻结（loaded-only，真机待测） |
| [002](002-simple-pd-disagg/README.md) | 单机简易 P/D 分离：llama.cpp/Metal 双实例 + KV 文件交接 | Mac Studio M1 Max，双 llama-server + 小 router | 实现路径设计完成，未开跑（not-verified） |

## 每个方案文档的统一骨架

1. **一句话方案**：技术选型与它在回答什么问题。
2. **架构图**：组件、进程、数据流（mermaid）。
3. **推理链路**：一个请求/一帧输入从进到出经过哪些阶段，数据以什么形态传递。
4. **落地形态**：进程怎么起、端口/目录怎么划、组件之间用什么协议交接。
5. **边界与证据**：不成立的条件、当前证据等级、下一步实测项。

## 编号约定

- 编号只增不复用；一个方案可以多轮迭代，结果写进同目录的 `results-*.md`。
- 方案 002 的前置可行性调研（SGLang/vLLM/Mooncake/llama.cpp issue 取证）在私有学习仓
  `bestksl/Learn001` 的 `docs/`；方案 002 目录下的 [review.md](002-simple-pd-disagg/review.md)
  是比例经济学与 12 项方案评审的本地副本。
