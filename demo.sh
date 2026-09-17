#!/bin/zsh
set -euo pipefail

demo_root="${0:A:h}"
demo_runtime="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if ! command -v node >/dev/null 2>&1; then
  export PATH="${demo_runtime}/node/bin:${PATH}"
fi
cd "${demo_root}"
command -v node >/dev/null || { print -u2 "Node.js is required to run the frontend."; exit 1; }
[[ -x .venv/bin/uvicorn ]] || { print -u2 "Install backend dependencies into .venv first; see README.md."; exit 1; }
[[ -f frontend/node_modules/vite/bin/vite.js ]] || { print -u2 "Install frontend dependencies first; see README.md."; exit 1; }

demo_api_port="${API_PORT:-8001}"
demo_ip="${DEMO_HOST:-$(ipconfig getifaddr en0 || ipconfig getifaddr en1 || true)}"
[[ -n "${demo_ip}" ]] || { print -u2 "Connect to Wi-Fi, or set DEMO_HOST to your Mac's local IP address."; exit 1; }
for demo_port in "${demo_api_port}" 5173; do
  if lsof -nP -iTCP:"${demo_port}" -sTCP:LISTEN >/dev/null 2>&1; then
    print -u2 "Port ${demo_port} is already in use. Stop the previous demo, or set API_PORT for a different API port."
    exit 1
  fi
done

if ! docker info >/dev/null 2>&1; then
  open -a Docker
  print "Waiting for Docker Desktop…"
  for demo_attempt in {1..45}; do
    docker info >/dev/null 2>&1 && break
    sleep 1
  done
fi
docker compose up -d --wait db

demo_api_pid=""
demo_web_pid=""
cleanup() {
  [[ -z "${demo_web_pid}" ]] || kill "${demo_web_pid}" 2>/dev/null || true
  [[ -z "${demo_api_pid}" ]] || kill "${demo_api_pid}" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM

.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port "${demo_api_port}" &
demo_api_pid=$!
demo_ready=0
for demo_attempt in {1..30}; do
  kill -0 "${demo_api_pid}" 2>/dev/null || { print -u2 "API startup failed; see the error above."; exit 1; }
  if curl --max-time 1 -fsS "http://127.0.0.1:${demo_api_port}/health" >/dev/null 2>&1; then
    demo_ready=1
    break
  fi
  sleep 1
done
[[ "${demo_ready}" == 1 ]] || { print -u2 "The API did not become ready."; exit 1; }

print "Open on your iPhone (same Wi-Fi): http://${demo_ip}:5173/"
print "API documentation: http://${demo_ip}:${demo_api_port}/docs"
print "Keep this terminal and Mac running. Press Ctrl+C to stop the demo."
cd frontend
VITE_API_URL="http://${demo_ip}:${demo_api_port}" node node_modules/vite/bin/vite.js --host 0.0.0.0 --port 5173 --strictPort &
demo_web_pid=$!
wait "${demo_web_pid}"
