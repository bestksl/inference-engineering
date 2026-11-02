#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案 002 阶段 1 的客户端与测量工具（零第三方依赖，Python 3.9+）。

子命令：
  mkprompt  生成确定性长 prompt（token 数只是估计，实际以 server timings.prompt_n 为准）
  baseline E0：直接打单体 server（:8080），流式记 TTFT/timings
  pd       E1：打 router（:8090）跑四步，打印 router 的全量计时 JSON
  check    一致性验收：temp=0 时 baseline 与 P/D 输出必须逐字一致

原始 JSON 一律落到 stdout，人读摘要走 stderr，便于 `... | tee results/raw-*.json`。
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import router  # noqa: E402

WORDS = ("the quick brown fox jumps over the lazy dog while the river keeps moving "
         "and every measured word stays exactly where the deterministic text put it ")


def mkprompt(target_tokens, out):
    # 英文经验 ~4 字符/token；只用于控制量级，真实 token 数看 prompt_n
    target_chars = target_tokens * 4
    parts = ["[pd-lab deterministic prompt; target ~%d tokens]\n" % target_tokens]
    while sum(len(p) for p in parts) < target_chars:
        parts.append(WORDS)
    text = "".join(parts)
    with open(out, "w") as f:
        f.write(text)
    sys.stderr.write("wrote %s: %d chars (~%d tokens est.; actual = prompt_n)\n"
                     % (out, len(text), target_tokens))


def baseline_once(base_url, prompt, n_predict, temp):
    body = {"prompt": prompt, "n_predict": n_predict, "temperature": temp,
            "stream": True, "cache_prompt": True}
    t0 = time.monotonic()
    text, last, ttft_ms = router.collect_completion(base_url, body)
    wall = (time.monotonic() - t0) * 1000.0
    t = last.get("timings", {})
    return {"mode": "baseline", "url": base_url, "text": text, "ttft_ms": ttft_ms,
            "wall_ms": wall,
            "timings": {"prompt_n": t.get("prompt_n"), "prompt_ms": t.get("prompt_ms"),
                        "predicted_n": t.get("predicted_n"),
                        "predicted_ms": t.get("predicted_ms"),
                        "decode_tps": t.get("predicted_per_second")},
            "stop_type": last.get("stop_type")}


def pd_once(router_url, prompt, n_predict, temp):
    status, rep = router.post_json(router_url.rstrip("/"), "/generate",
                                  {"prompt": prompt, "n_predict": n_predict,
                                   "temperature": temp})
    rep["_http"] = status
    return rep


def main():
    ap = argparse.ArgumentParser(description="E0/E1 测量客户端")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("mkprompt"); sp.add_argument("--tokens", type=int, default=8000)
    sp.add_argument("--out", required=True)

    for name in ("baseline", "pd", "check"):
        s = sub.add_parser(name)
        s.add_argument("--prompt-file", required=True)
        s.add_argument("--n-predict", type=int, default=32)
        s.add_argument("--temp", type=float, default=0.0)
        s.add_argument("--baseline-url", default="http://127.0.0.1:8080")
        s.add_argument("--router-url", default="http://127.0.0.1:8090")

    args = ap.parse_args()
    if args.cmd == "mkprompt":
        mkprompt(args.tokens, args.out)
        return

    prompt = open(args.prompt_file, encoding="utf-8").read()

    if args.cmd == "baseline":
        out = baseline_once(args.baseline_url, prompt, args.n_predict, args.temp)
    elif args.cmd == "pd":
        out = pd_once(args.router_url, prompt, args.n_predict, args.temp)
    else:  # check：E1 验收三件事——不重算 + 逐字一致
        base = baseline_once(args.baseline_url, prompt, args.n_predict, args.temp)
        pd = pd_once(args.router_url, prompt, args.n_predict, args.temp)
        same = base["text"] == pd.get("text", "")
        checks = pd.get("checks", {})
        out = {"mode": "check", "consistent": same,
               "tokens_match": checks.get("tokens_match"),
               "zero_prefill": checks.get("zero_prefill"),
               "kv_bytes_match": checks.get("kv_bytes_match"),
               "baseline": {k: base[k] for k in ("ttft_ms", "timings", "stop_type")},
               "pd": {"ttft_ms": (pd.get("decode") or {}).get("ttft_ms"),
                      "save_ms": (pd.get("save") or {}).get("save_ms"),
                      "restore_ms": (pd.get("restore") or {}).get("restore_ms"),
                      "bytes_per_token": (pd.get("kv") or {}).get("bytes_per_token"),
                      "timings": pd.get("decode"),
                      "stage": pd.get("stage"), "error": pd.get("error")},
               "text_baseline": base["text"], "text_pd": pd.get("text", "")}
        sys.stderr.write("CONSISTENCY %s | tokens_match=%s zero_prefill=%s kv_bytes_match=%s\n"
                         % ("PASS" if same else "FAIL", checks.get("tokens_match"),
                            checks.get("zero_prefill"), checks.get("kv_bytes_match")))
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(0 if same and checks.get("tokens_match") and checks.get("zero_prefill") else 1)

    sys.stderr.write(json.dumps({k: v for k, v in out.items() if k != "text"},
                                ensure_ascii=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if out.get("stage") and out["stage"] != "done":
        sys.exit(2)


if __name__ == "__main__":
    main()
