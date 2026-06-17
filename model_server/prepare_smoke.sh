#!/usr/bin/env bash
# Configure env, start ONE model server on GPU0:8081, run ONE real call.
set -o pipefail
REPO=/opt/calltone
cd "$REPO"
TOK="loadtest_$(openssl rand -hex 16)"
mkdir -p "$REPO/.hfcache"
cat > "$REPO/model_server/.env" <<EOF
MODEL_SERVER_TOKEN=$TOK
ALLOWED_IPS=127.0.0.1
HF_HOME=$REPO/.hfcache
HF_TOKEN=$(cat $REPO/.hf_token)
CALLTONE_PREWARM=0
MODEL_SERVER_DEBUG=0
EOF
chmod 600 "$REPO/model_server/.env"
echo "$TOK" > "$REPO/.srv_token"
echo "[prep] token written"

start_server(){ # $1=gpu  $2=port
  local gpu=$1
  local port=$2
  local log="$REPO/srv_${port}.log"
  set -a; source "$REPO/model_server/.env"; set +a
  CUDA_VISIBLE_DEVICES=$gpu PYTHONPATH="$REPO" nohup "$REPO/.venv/bin/uvicorn" \
    model_server.main:app --host 127.0.0.1 --port "$port" --workers 1 \
    > "$log" 2>&1 &
  echo "[prep] started server gpu=$gpu port=$port pid=$! log=$log"
}

start_server 0 8081
echo "[prep] waiting for /v1/health on 8081 (up to 240s)..."
for i in $(seq 1 120); do
  if curl -sf http://127.0.0.1:8081/v1/health >/dev/null 2>&1; then echo "[prep] HEALTHY after ${i}x2s"; break; fi
  sleep 2
done
curl -s http://127.0.0.1:8081/v1/health; echo
echo "[prep] running ONE smoke call (first call downloads faster-whisper CT2 ~3GB; be patient)..."
"$REPO/.venv/bin/python" "$REPO/gpu_loadtest.py" \
  --servers http://127.0.0.1:8081 --token "$TOK" \
  --audio "$REPO/sample.wav" --company metroboost \
  --calls 1 --concurrency 1 --label smoke --out "$REPO/smoke_result.json"
echo "[prep] SMOKE COMPLETE"
touch "$REPO/.smoke_done"
