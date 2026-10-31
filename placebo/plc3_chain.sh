#!/usr/bin/env bash
# Placebo round 3: for each variant, one placebo DB (generate -> build -> detect -> gate -> report), then the REF_MIN sensitivity runs on 10 chunks.
# 필요한 환경변수: BASE_DB(그들 ingest + 그들 1~6단계를 마친 swaps_solana.duckdb) · NPH_REPO(그들 저장소 뿌리) · WORK(출력 폴더) · LO · HI(앞다리 슬롯 창).
# 고를 수 있는 것: PY(기본 python3) · NPC(조각당 방아쇠 · 기본 800) · PLC_THREADS · PLC_MEMORY · PLC_TEMP_DIR.
# 이미 report_<V>.json 이 있는 변형은 건너뜀(다시 돌리려면 그 파일을 옮길 것). 한 번에 하나씩 차례로 돎.
set -u
: "${BASE_DB:?set BASE_DB}" "${NPH_REPO:?set NPH_REPO}" "${WORK:?set WORK}" "${LO:?set LO}" "${HI:?set HI}"
PY=${PY:-python3}; NPC=${NPC:-800}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$WORK/logs"
export NPH_REPO
run() {   # run TAG SCRIPT ARGS...
  local tag=$1 script=$2; shift 2
  echo "=== $tag $script $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
  "$PY" -I -B "$HERE/$script" "$@" > "$WORK/logs/${script%.py}_$tag.log" 2>&1
  local rc=$?
  echo "=== $tag $script rc=$rc $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
  return $rc
}
variant() {   # variant NAME SEED CONFIG_JSON REF_MIN CHUNKS
  local name=$1 seed=$2 cfg=$3 ref=$4 chunks=$5
  [ -f "$WORK/report_$name.json" ] && return 0
  run "$name" plc_gen3.py --base-db "$BASE_DB" --out "$WORK/synth_$name.parquet" --lo "$LO" --hi "$HI" --per-chunk "$NPC" --seed "$seed" \
      --config "$cfg" --ref-min "$ref" --chunks "$chunks" || return 1
  run "$name" plc_build_db.py --base-db "$BASE_DB" --placebo-db "$WORK/placebo_$name.duckdb" --synth "$WORK/synth_$name.parquet" --lo "$LO" --hi "$HI" || return 1
  run "$name" plc_detect3.py --placebo-db "$WORK/placebo_$name.duckdb" --chunks "$chunks" || return 1
  run "$name" plc_gate.py --placebo-db "$WORK/placebo_$name.duckdb" || return 1
  run "$name" plc_report3.py --placebo-db "$WORK/placebo_$name.duckdb" --meta "$WORK/synth_${name}_meta.parquet" --out "$WORK/report_$name.json" --chunks "$chunks"
}
# 변형 10개(각자 창 전체) — 씨앗: P1 계열 31001 · P2 31002 · P3 31003
variant P1  31001 '{"name":"P1","trig":"P1","place":"next","k":"sampled","size":0.1}' 0.01 all
variant P3  31003 '{"name":"P3","trig":"P3","k":"sampled","size":0.1}' 0.01 all
variant P2s 31002 '{"name":"P2s","trig":"P2","place":"same","k":"sampled","size":0.1}' 0.01 all
variant P2n 31002 '{"name":"P2n","trig":"P2","place":"next","k":"sampled","size":0.1}' 0.01 all
variant H20 31001 '{"name":"H20","trig":"P1","place":"next","k":"U20","size":0.1}' 0.01 all
variant H40 31001 '{"name":"H40","trig":"P1","place":"next","k":"U40","size":0.1}' 0.01 all
variant K2  31001 '{"name":"K2","trig":"P1","place":"next","k":2,"size":0.1}' 0.01 all
variant K5  31001 '{"name":"K5","trig":"P1","place":"next","k":5,"size":0.1}' 0.01 all
variant K8  31001 '{"name":"K8","trig":"P1","place":"next","k":8,"size":0.1}' 0.01 all
variant S1  31001 '{"name":"S1","trig":"P1","place":"next","k":"sampled","size":1.0}' 0.01 all
variant Y5  31001 '{"name":"Y5","trig":"P1","place":"next","k":5,"size":0.1,"age_max":150}' 0.01 all
variant Y8  31001 '{"name":"Y8","trig":"P1","place":"next","k":8,"size":0.1,"age_max":150}' 0.01 all
variant Yb  31001 '{"name":"Yb","trig":"P1","place":"next","k":"realbot","size":0.1,"age_max":150}' 0.01 all
# REF_MIN 민감도: 10조각(0,3,…,27) · 같은 씨앗 → 같은 방아쇠·자리·k · 값 규칙만 다름
SUB=${SUB:-0,3,6,9,12,15,18,21,24,27}
variant P1r2  31001 '{"name":"P1r2","trig":"P1","place":"next","k":"sampled","size":0.1}' 0.02 "$SUB"
variant P1r5  31001 '{"name":"P1r5","trig":"P1","place":"next","k":"sampled","size":0.1}' 0.05 "$SUB"
variant P3r2  31003 '{"name":"P3r2","trig":"P3","k":"sampled","size":0.1}' 0.02 "$SUB"
variant P3r5  31003 '{"name":"P3r5","trig":"P3","k":"sampled","size":0.1}' 0.05 "$SUB"
variant H20r2 31001 '{"name":"H20r2","trig":"P1","place":"next","k":"U20","size":0.1}' 0.02 "$SUB"
variant H20r5 31001 '{"name":"H20r5","trig":"P1","place":"next","k":"U20","size":0.1}' 0.05 "$SUB"
echo "=== ALL DONE $(date -u +%H:%M:%S)" >> "$WORK/chain.log"
