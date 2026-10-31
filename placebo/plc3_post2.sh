#!/usr/bin/env bash
# Real-trader baseline (same denominator as the placebo) on the base DB; run after plc3_chain.sh.
# 필요한 환경변수: BASE_DB · NPH_REPO · WORK · LO · HI (plc3_chain.sh 와 같음) · 고를 수 있는 것: PY.
set -u
: "${BASE_DB:?set BASE_DB}" "${NPH_REPO:?set NPH_REPO}" "${WORK:?set WORK}" "${LO:?set LO}" "${HI:?set HI}"
PY=${PY:-python3}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$WORK/logs"
export NPH_REPO
echo "=== baseline $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
"$PY" -I -B "$HERE/plc_baseline.py" --base-db "$BASE_DB" --lo "$LO" --hi "$HI" --out "$WORK/baseline.json" > "$WORK/logs/plc_baseline.log" 2>&1
echo "=== baseline rc=$? $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
echo "=== POST DONE $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
