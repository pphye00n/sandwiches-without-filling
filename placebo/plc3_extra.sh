#!/usr/bin/env bash
# Extra measurements (non-bot k curves, in-window shares, real-bot placement), the curve-selection check, then the markdown tables.
# 필요한 환경변수: BASE_DB · NPH_REPO · WORK · LO · HI · 고를 수 있는 것: PY · VARIANTS.
set -u
: "${BASE_DB:?set BASE_DB}" "${NPH_REPO:?set NPH_REPO}" "${WORK:?set WORK}" "${LO:?set LO}" "${HI:?set HI}"
PY=${PY:-python3}; VARIANTS=${VARIANTS:-P1,P3,P2s,P2n,H20,H40,K2,K5,K8,S1}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$WORK/logs"
export NPH_REPO
echo "=== extra $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
"$PY" -I -B "$HERE/plc_extra.py" --base-db "$BASE_DB" --work "$WORK" --variants "$VARIANTS" --lo "$LO" --hi "$HI" --out "$WORK/extra.json" > "$WORK/logs/plc_extra.log" 2>&1
echo "=== extra rc=$? $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
echo "=== f7 $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
"$PY" -I -B "$HERE/plc_f7.py" --base-db "$BASE_DB" --work "$WORK" --out "$WORK/f7.json" > "$WORK/logs/plc_f7.log" 2>&1
echo "=== f7 rc=$? $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
"$PY" -I -B "$HERE/plc3_tables.py" "$WORK" > "$WORK/tables.md" 2> "$WORK/logs/plc3_tables.log"
echo "=== tables rc=$? $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
