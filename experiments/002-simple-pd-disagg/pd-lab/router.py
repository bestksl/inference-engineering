#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案 002 阶段 1：单机 P/D 编排 router（约 200 行，零第三方依赖）。

四步见 experiments/002-simple-pd-disagg/README.md 第 3 节：
  ① P 端 /completion n_predict=0 只做 prefill
  ② P 端 /slots/0?action=save 把本请求 KV 存成文件
  ③ D 端 /slots/0?action=restore 从同一文件恢复
  ④ D 端 /completion 同前缀流式生成（期望零 prefill 命中）

router 无状态、单飞（两 server 都 -np 1）；状态只在 slot 文件与请求 id 上。
"""

import argparse
import http.client
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_P = "http://127.0.0.1:8081"
DEFAULT_D = "http://127.0.0.1:8082"
DEFAULT_LISTEN = ("127.0.0.1", 8090)
HTTP_TIMEOUT = 3600  # 32k prefill 在 14B 上可能是分钟级


def _conn(base, timeout):
    import urllib.parse
    u = urllib.parse.urlparse(base)
    return http.client.HTTPConnection(u.hostname, u.port, timeout=timeout)


def post_json(base, path, body, timeout=HTTP_TIMEOUT):
    """同步 POST JSON，返回 (status, dict_or_raw)。"""
    conn = _conn(base, timeout)
    try:
        conn.request("POST", path, json.dumps(body).encode(),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        raw = r.read()
    finally:
        conn.close()
    try:
        return r.status, json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return r.status, {"_raw": raw.decode("utf-8", "replace")}


def stream_completion(base, body, timeout=HTTP_TIMEOUT):
    """流式 POST /completion，逐个 yield SSE data 里的 JSON 事件。"""
    conn = _conn(base, timeout)
    try:
        conn.request("POST", "/completion", json.dumps(body).encode(),
                     {"Content-Type": "application/json", "Accept": "text/event-stream"})
        r = conn.getresponse()
        if r.status != 200:
            yield {"_error_status": r.status, "_raw": r.read().decode("utf-8", "replace")}
            return
        for line in r:
            line = line.strip()
            if line.startswith(b"data:"):
                payload = line[5:].strip()
                if payload and payload != b"[DONE]":
                    yield json.loads(payload)
    finally:
        conn.close()


def collect_completion(base, body, timeout=HTTP_TIMEOUT):
    """流式收完一个 completion，返回 (text, last_event, ttft_ms)。"""
    parts = []
    last = {}
    ttft_ms = None
    t0 = time.monotonic()
    for ev in stream_completion(base, body, timeout):
        if ev.get("_error_status"):
            raise RuntimeError("completion HTTP %s: %s" % (ev["_error_status"], ev.get("_raw", "")))
        if ev.get("content"):
            if ttft_ms is None:
                ttft_ms = (time.monotonic() - t0) * 1000.0
            parts.append(ev["content"])
        last = ev
    return "".join(parts), last, ttft_ms


def run_pd(prompt, n_predict=32, temperature=0.0,
           p_url=DEFAULT_P, d_url=DEFAULT_D, kv_dir="./kv", keep_kv=False):
    """四步编排。返回一份全量计时 report（dict）。任何一步失败都带 error 字段。"""
    rid = uuid.uuid4().hex[:12]
    filename = rid + ".bin"
    report = {"id": rid, "stage": "start", "n_predict": n_predict,
              "temperature": temperature, "checks": {}}
    t_all = time.monotonic()

    def fail(stage, status, msg):
        report.update(stage=stage, error={"http": status, "message": msg})
        _unlink(kv_dir, filename, report)
        report["wall_ms"] = (time.monotonic() - t_all) * 1000.0
        return report

    # ① prefill-only：完成后必须立刻 save（见方案文档注意点 1：idle slot 可能换出）
    status, pre = post_json(
        p_url, "/completion",
        {"prompt": prompt, "n_predict": 0, "temperature": 0.0, "cache_prompt": True})
    if status != 200:
        return fail("prefill", status, str(pre)[:500])
    p_timings = pre.get("timings", {})

    # ② save
    status, saved = post_json(
        p_url, "/slots/0?action=save", {"filename": filename})
    if status != 200 or not saved.get("result", True):
        return fail("save", status, str(saved)[:500])

    # ③ restore（D 端，同一共享目录下的同一文件名）
    status, restored = post_json(
        d_url, "/slots/0?action=restore", {"filename": filename})
    if status != 200 or not restored.get("result", True):
        return fail("restore", status, str(restored)[:500])

    # ④ 同前缀流式生成：期望 prompt 全命中、零 prefill
    body = {"prompt": prompt, "n_predict": n_predict, "temperature": temperature,
            "stream": True, "cache_prompt": True}
    try:
        text, last, ttft_ms = collect_completion(d_url, body)
    except Exception as e:  # noqa: BLE001 - 任意传输异常都落进报告
        return fail("decode", None, str(e))
    d_timings = last.get("timings", {})

    n_written = saved.get("n_written")
    n_saved = saved.get("n_saved")
    n_read = restored.get("n_read")
    p_prompt_ms = p_timings.get("prompt_ms")
    d_prompt_ms = d_timings.get("prompt_ms")
    p_prompt_n = p_timings.get("prompt_n")
    d_prompt_n = d_timings.get("prompt_n")
    zero_ms_limit = max(50.0, 0.05 * (p_prompt_ms or 0.0))

    report.update(
        stage="done",
        prefill={"prompt_n": p_prompt_n, "prompt_ms": p_prompt_ms,
                 "per_token_ms": p_timings.get("prompt_per_token_ms")},
        save={"n_saved": n_saved, "n_written": n_written,
              "save_ms": saved.get("save_ms"), "raw": {k: v for k, v in saved.items()
                                                        if k not in ("result", "timings")}},
        restore={"n_restored": restored.get("n_restored"), "n_read": n_read,
                 "restore_ms": restored.get("restore_ms"),
                 "raw": {k: v for k, v in restored.items()
                         if k not in ("result", "timings")}},
        decode={"ttft_ms": ttft_ms, "prompt_n": d_prompt_n, "prompt_ms": d_prompt_ms,
                "predicted_n": d_timings.get("predicted_n"),
                "predicted_ms": d_timings.get("predicted_ms"),
                "decode_tps": d_timings.get("predicted_per_second"),
                "stop_type": last.get("stop_type")},
        kv={"filename": filename,
            "bytes_per_token": (n_written / n_saved) if n_written and n_saved else None},
        text=text,
    )
    report["checks"] = {
        "tokens_match": p_prompt_n is not None and p_prompt_n == d_prompt_n,
        "zero_prefill": d_prompt_n == p_prompt_n and d_prompt_ms is not None
                        and d_prompt_ms <= zero_ms_limit,
        "kv_bytes_match": n_written is not None and n_written == n_read,
        "d_prompt_ms": d_prompt_ms, "zero_ms_limit": zero_ms_limit,
    }
    _unlink(kv_dir, filename, report)
    report["wall_ms"] = (time.monotonic() - t_all) * 1000.0
    return report


def _unlink(kv_dir, filename, report):
    if not kv_dir:
        return
    path = os.path.join(kv_dir, filename)
    try:
        os.remove(path)
        report.setdefault("kv", {})["file_deleted"] = True
    except FileNotFoundError:
        report.setdefault("kv", {})["file_deleted"] = None  # 共享目录不在本机/已删
    except OSError:
        report.setdefault("kv", {})["file_deleted"] = False


class Handler(BaseHTTPRequestHandler):
    busy = threading.Lock()  # 单飞：忙时直接 503，绝不排队（仓规：drop, don't queue）
    p_url = DEFAULT_P
    d_url = DEFAULT_D
    kv_dir = "./kv"

    def log_message(self, fmt, *args):
        sys.stderr.write("[router] %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/generate":
            self._send(404, {"error": "not found"})
            return
        if not Handler.busy.acquire(blocking=False):
            self._send(503, {"error": "router busy (single-flight)"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            report = run_pd(req["prompt"], int(req.get("n_predict", 32)),
                            float(req.get("temperature", 0.0)),
                            self.p_url, self.d_url, self.kv_dir,
                            bool(req.get("keep_kv", False)))
            self._send(200 if report.get("stage") == "done" else 502, report)
        except (KeyError, ValueError) as e:
            self._send(400, {"error": "bad request: %s" % e})
        finally:
            Handler.busy.release()


# ---- 无 llama.cpp 依赖的自测：假 P / 假 D，验证四步顺序、SSE 解析与判定逻辑 ----

def _selftest():
    import threading
    from http.server import HTTPServer
    order_p, order_d = [], []

    def make_p():
        class P(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                path = self.path
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if path == "/completion":
                    order_p.append("completion")
                    obj = {"timings": {"prompt_n": 8000, "prompt_ms": 4200.0}}
                elif path.startswith("/slots/0"):
                    order_p.append("save")
                    obj = {"result": True, "n_saved": 8000,
                           "n_written": 64_000_000, "save_ms": 312.0}
                else:
                    obj = {}
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        return HTTPServer(("127.0.0.1", 0), P)

    def make_d():
        class D(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                path = self.path
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if path.startswith("/slots/0"):
                    order_d.append("restore")
                    obj = {"result": True, "n_restored": 8000,
                           "n_read": 64_000_000, "restore_ms": 287.0}
                    data = json.dumps(obj).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                elif path == "/completion":
                    order_d.append("completion")
                    events = [
                        {"content": "Hello"}, {"content": " world"},
                        {"content": "", "stop": True, "stop_type": "limit",
                         "timings": {"prompt_n": 8000, "prompt_ms": 1.3,
                                     "predicted_n": 2, "predicted_ms": 55.0,
                                     "predicted_per_second": 36.4}},
                    ]
                    body = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n"
                                    for e in events)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
        return HTTPServer(("127.0.0.1", 0), D)

    sp, sd = make_p(), make_d()
    threading.Thread(target=sp.serve_forever, daemon=True).start()
    threading.Thread(target=sd.serve_forever, daemon=True).start()
    kv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kv")
    os.makedirs(kv, exist_ok=True)
    rep = run_pd("x " * 4000, n_predict=2,
                 p_url="http://127.0.0.1:%d" % sp.server_address[1],
                 d_url="http://127.0.0.1:%d" % sd.server_address[1],
                 kv_dir=kv)
    sp.shutdown()
    sd.shutdown()
    ok = (rep.get("stage") == "done" and rep["text"] == "Hello world"
          and order_p == ["completion", "save"] and order_d == ["restore", "completion"]
          and rep["checks"]["tokens_match"] and rep["checks"]["zero_prefill"]
          and rep["checks"]["kv_bytes_match"] and rep["kv"]["bytes_per_token"] == 8000.0
          and isinstance(rep["decode"]["ttft_ms"], float))
    print(json.dumps({"selftest": "PASS" if ok else "FAIL", "order_p": order_p,
                      "order_d": order_d, "checks": rep.get("checks"),
                      "bytes_per_token": rep.get("kv", {}).get("bytes_per_token"),
                      "ttft_ms": rep.get("decode", {}).get("ttft_ms")}, indent=2))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="单机 P/D 编排 router（方案 002 阶段 1）")
    ap.add_argument("--p-url", default=DEFAULT_P)
    ap.add_argument("--d-url", default=DEFAULT_D)
    ap.add_argument("--kv-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "kv"))
    ap.add_argument("--listen", default="%s:%d" % DEFAULT_LISTEN)
    ap.add_argument("--selftest", action="store_true", help="用假后端验证编排逻辑，不需要 llama.cpp")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    host, port = args.listen.rsplit(":", 1)
    Handler.p_url, Handler.d_url, Handler.kv_dir = args.p_url, args.d_url, args.kv_dir
    httpd = ThreadingHTTPServer((host, int(port)), Handler)
    print("pd-router on http://%s:%d  P=%s D=%s kv=%s"
          % (host, int(port), args.p_url, args.d_url, args.kv_dir), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
