#!/bin/bash
# 方案 002 阶段 1：起停三个 llama-server（P :8081 / D :8082 / baseline :8080）。
# bash 3.2（macOS 自带）可跑；不依赖 brew 任何东西，只要有 curl 和 llama-server。
#
#   ./serve.sh p | d | baseline   起单个
#   ./serve.sh up                 起 P+D（阶段 1 主战场）
#   ./serve.sh down               全部停掉
#   ./serve.sh status             三个 /health
#   ./serve.sh logs p|d|baseline  tail -f 日志
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
KV_DIR="$DIR/kv"
LOG_DIR="$DIR/logs"
mkdir -p "$KV_DIR" "$LOG_DIR" "$DIR/models" "$DIR/prompts"

# 可覆盖项：export PD_MODEL=... LLAMA_SERVER=... PD_CTX=16384 ./serve.sh up
PD_MODEL="${PD_MODEL:-$DIR/models/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf}"
PD_CTX="${PD_CTX:-32768}"
PD_NGL="${PD_NGL:-99}"
PORT_P="${PORT_P:-8081}"
PORT_D="${PORT_D:-8082}"
PORT_B="${PORT_B:-8080}"

resolve_bin() {
  if [ -n "${LLAMA_SERVER:-}" ]; then BIN="$LLAMA_SERVER"; return; fi
  if command -v llama-server >/dev/null 2>&1; then BIN="$(command -v llama-server)"; return; fi
  if [ -x "$DIR/llama-server" ]; then BIN="$DIR/llama-server"; return; fi
  echo "ERROR: 找不到 llama-server。请 export LLAMA_SERVER=/path/to/build/bin/llama-server" >&2
  echo "       （Metal 构建：cmake -B build -DGGML_METAL=1 && cmake --build build --config Release -j）" >&2
  exit 1
}

wait_health() {
  port="$1"; name="$2"
  echo -n "waiting for $name (:$port) health"
  i=0
  until curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$port/health"; do
    i=$((i + 1))
    if [ "$i" -ge 900 ]; then  # 30 分钟上限（14B 首次加载以分钟计）
      echo " TIMEOUT；最后 20 行日志："
      tail -20 "$LOG_DIR/$name.log"
      exit 1
    fi
    echo -n "."; sleep 2
  done
  echo " ok"
}

alive() {
  name="$1"; pidf="$LOG_DIR/$name.pid"
  [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null
}

start_one() {
  name="$1"; port="$2"; extra="$3"
  if alive "$name"; then echo "$name already running (pid $(cat "$LOG_DIR/$name.pid"))"; return; fi
  if [ ! -f "$PD_MODEL" ]; then
    echo "ERROR: 模型不存在：$PD_MODEL" >&2
    echo "       下载 Q4_K_M GGUF 后 export PD_MODEL=绝对路径 再试。" >&2
    exit 1
  fi
  resolve_bin
  echo "starting $name on :$port -> $LOG_DIR/$name.log"
  nohup "$BIN" -m "$PD_MODEL" -ngl "$PD_NGL" -c "$PD_CTX" -np 1 \
    --host 127.0.0.1 --port "$port" $extra \
    >"$LOG_DIR/$name.log" 2>&1 &
  echo $! > "$LOG_DIR/$name.pid"
  wait_health "$port" "$name"
}

stop_one() {
  name="$1"
  if alive "$name"; then
    kill "$(cat "$LOG_DIR/$name.pid")" && echo "stopped $name"
    rm -f "$LOG_DIR/$name.pid"
  else
    echo "$name not running"; rm -f "$LOG_DIR/$name.pid"
  fi
}

case "${1:-}" in
  p)        start_one p "$PORT_P" "--slot-save-path $KV_DIR" ;;
  d)        start_one d "$PORT_D" "--slot-save-path $KV_DIR" ;;
  baseline) start_one baseline "$PORT_B" "" ;;
  up)
    start_one p "$PORT_P" "--slot-save-path $KV_DIR"
    start_one d "$PORT_D" "--slot-save-path $KV_DIR"
    echo "P+D ready。另开终端：python3 router.py，再 python3 bench.py check --prompt-file prompts/8k.txt"
    ;;
  down) stop_one p; stop_one d; stop_one baseline ;;
  status)
    for pair in "baseline:$PORT_B" "p:$PORT_P" "d:$PORT_D"; do
      n="${pair%%:*}"; p="${pair##*:}"
      if curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$p/health"; then
        echo "$n (:$p) healthy"
      else
        echo "$n (:$p) DOWN"
      fi
    done ;;
  logs) tail -f "$LOG_DIR/${2:-p}.log" ;;
  *)
    grep '^#' "$0" | sed 's/^# \{0,1\}//'
    exit 1 ;;
esac
