"""Generate one zero-information synthetic trader variant as rows in the authors' `swaps` schema (14 columns), using only their `swaps` and gated `sandwiches` tables."""
# 위약 3판 생성기 — 한 DB 에 한 변형 · 창 전체 조각 · 그들 `swaps` 14칸 + 그들 정제 `sandwiches`(간격·블록 안 자리 분포)만 읽음.
#   변형마다 따로(섞임 0) · 조각당 방아쇠 --per-chunk 개를 해시 순서로(같은 씨앗 = 같은 방아쇠) · k 법칙 = 정제 간격 분포 | 고정값 | U{1..20} | U{1..40}.
#   값(자기 충격 없음): 앞다리 = 그 자리 뒤 첫 실제 같은 방향 거래(≥ REF_MIN) 평균가 · 뒷다리 = 그 자리 뒤 첫 실제 매도(≥ REF_MIN) 평균가.
#   대체 사슬: 뒤 실제 거래(≥ REF_MIN) → 앞 실제 거래(≥ REF_MIN) → 뒤 아무 크기 → 앞 아무 크기 · 대체는 표지(ref_f · ref_b)로 남김(죽은 출시도 분모에).
#   참조 매수 피해자 막기: 앞다리 값이 뒤 실제 매수에서 왔으면 그 매수가 그들 피해 조건(v_in·f_out > v_out·f_in)을 float64 로도 못 넘게
#   앞다리 토큰 수를 math.nextafter 로 한 칸씩 내림.
#   결정성: 방아쇠·분포 배열은 정렬해서 읽음(같은 씨앗·같은 DuckDB/NumPy 판이면 같은 결과).
# 설정 JSON: {name, trig: P1|P2|P3, place: next|same|next_first, k: sampled|정수|U20|U40, size}
#   P1 = 남의 체결된 매수(WSOL ≥ 0.1) 방아쇠 · P2 = 곡선 풀 첫 스왑(생성 tx) 방아쇠 · P3 = 거래가 있던 (풀, 슬롯) 무작위 + 0~10 슬롯.
#   place next = 방아쇠 다음 슬롯 · 자리 = 정제 앞다리 블록 안 상대 자리 분포 · same = 방아쇠 tx 바로 뒤(같은 slot · tx_index · swap_index 900).
# 산출: OUT.parquet(합성 swaps 줄) · OUT_meta.parquet(왕복마다 자리·k·값·대체 표지) · OUT_gen.json(설정·씨앗·건수).
# 쓰기: python plc_gen3.py --base-db BASE.duckdb --out WORK/synth_P1.parquet --lo LO --hi HI --seed 31001 --config '{"name":"P1","trig":"P1","place":"next","k":"sampled","size":0.1}' --nph AUTHORS_REPO
import argparse, json, math, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pyarrow as pa, pyarrow.parquet as pq
from plc_common import CHUNK as CH, SYNTH_SWAP_INDEX as SWIX, CURVE, add_common_args, add_authors_modules, connect, synth_trader

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
ap.add_argument('--base-db', required=True, help="the authors' Solana DB after their stages 1-6 (swaps, sandwiches); opened read-only")
ap.add_argument('--out', required=True, help='output parquet of synthetic swaps rows (…_meta.parquet and …_gen.json are written next to it)')
ap.add_argument('--lo', type=int, required=True, help='first slot of the analysis window')
ap.add_argument('--hi', type=int, required=True, help='last slot of the analysis window')
ap.add_argument('--per-chunk', type=int, default=800, help='triggers sampled per 25,000-slot chunk (default 800)')
ap.add_argument('--seed', type=int, required=True, help='seed for trigger hashing and NumPy draws')
ap.add_argument('--config', required=True, help='variant JSON, e.g. {"name":"P1","trig":"P1","place":"next","k":"sampled","size":0.1}')
ap.add_argument('--ref-min', type=float, default=0.01, help='minimum WSOL size of a reference trade used for pricing (default 0.01)')
ap.add_argument('--chunks', default='all', help="'all' or comma-separated chunk ids; draws stay identical to the all-chunk run")
args = ap.parse_args()
WSOL = add_authors_modules(args.nph)
DB, OUTP, LO, HI = args.base_db, args.out, args.lo, args.hi
NPC, SEED, CFG, REF_MIN, CHUNKS = args.per_chunk, args.seed, json.loads(args.config), args.ref_min, args.chunks
NAME, TRIG, PLACE, KLAW, SIZE = CFG['name'], CFG['trig'], CFG.get('place', 'next'), str(CFG.get('k', 'sampled')), float(CFG.get('size', 0.1))
t0 = time.time()
def say(*a):
    print(f'[{time.time()-t0:7.1f}s]', *a, flush=True)
rng = np.random.default_rng(SEED)
con = connect(DB, args, read_only=True)
data_lo = con.execute("SELECT min(slot) FROM swaps").fetchone()[0]
con.execute(f"""CREATE TEMP TABLE slotsz AS SELECT slot::BIGINT AS slot, max(tx_index)::BIGINT + 1 AS n_idx, min(block_time) AS bt
    FROM swaps WHERE slot BETWEEN {LO - 2000} AND {HI + 2000} GROUP BY 1""")
con.execute(f"""CREATE TEMP TABLE wpool AS SELECT pool, any_value(program) AS program,
    any_value(CASE WHEN token_in = '{WSOL}' THEN token_out ELSE token_in END) AS tok,
    min(slot::BIGINT * 1000000000 + tx_index::BIGINT * 1000 + swap_index) AS first_ord
    FROM swaps WHERE NOT failed AND (token_in = '{WSOL}' OR token_out = '{WSOL}') GROUP BY 1""")
# 분포(그들 정제 sandwiches) — k 'sampled' · 앞/뒤 블록 안 상대 자리
kd = np.array([r[0] for r in con.execute(f"SELECT slots_apart FROM sandwiches WHERE front_slot BETWEEN {LO} AND {HI} ORDER BY 1").fetchall()], dtype=np.int64)
rel_f = np.array([r[0] for r in con.execute(f"""SELECT s.tx_index::DOUBLE / z.n_idx FROM (SELECT DISTINCT front_tx FROM sandwiches WHERE front_slot BETWEEN {LO} AND {HI}) x
    JOIN (SELECT DISTINCT tx_sig, slot::BIGINT AS slot, tx_index FROM swaps WHERE slot BETWEEN {LO} AND {HI + 64}) s ON s.tx_sig = x.front_tx JOIN slotsz z ON z.slot = s.slot ORDER BY 1""").fetchall()])
rel_b = np.array([r[0] for r in con.execute(f"""SELECT s.tx_index::DOUBLE / z.n_idx FROM (SELECT DISTINCT back_tx FROM sandwiches WHERE front_slot BETWEEN {LO} AND {HI}) x
    JOIN (SELECT DISTINCT tx_sig, slot::BIGINT AS slot, tx_index FROM swaps WHERE slot BETWEEN {LO} AND {HI + 64}) s ON s.tx_sig = x.back_tx JOIN slotsz z ON z.slot = s.slot ORDER BY 1""").fetchall()])
slot_n = dict(con.execute("SELECT slot, n_idx FROM slotsz").fetchall())
slot_bt = dict(con.execute("SELECT slot, bt FROM slotsz").fetchall())
FRONT_HI = HI - 60          # 마지막 조각: 뒷다리가 탐지기 재료 범위(hi + 128) 안에
chunk_ids = list(range((HI - LO) // CH + 1))
use = set(chunk_ids) if CHUNKS == 'all' else {int(x) for x in CHUNKS.split(',')}
say(NAME, TRIG, PLACE, KLAW, SIZE, 'REF_MIN', REF_MIN, 'chunks', len(use), 'k dist', np.percentile(kd, [10, 50, 90]).tolist())
win = f"slot BETWEEN {LO} AND {FRONT_HI}"
if TRIG == 'P1':
    trig = con.execute(f"""SELECT pool, slot::BIGINT, tx_index::BIGINT, swap_index::BIGINT, (slot - {LO}) // {CH} AS ch FROM (
        SELECT s.*, row_number() OVER (PARTITION BY (s.slot - {LO}) // {CH} ORDER BY hash(s.tx_sig || s.pool || '{SEED}')) AS rn
        FROM swaps s JOIN wpool w USING (pool) WHERE NOT s.failed AND s.token_in = '{WSOL}' AND s.amount_in >= 0.1 AND s.{win})
        WHERE rn <= {NPC} ORDER BY slot, tx_index, swap_index, pool""").fetchall()
elif TRIG == 'P2':
    trig = con.execute(f"""SELECT pool, slot, tx_index, swap_index, (slot - {LO}) // {CH} AS ch FROM (
        SELECT w.pool, (w.first_ord // 1000000000)::BIGINT AS slot, ((w.first_ord % 1000000000) // 1000)::BIGINT AS tx_index, (w.first_ord % 1000)::BIGINT AS swap_index,
               row_number() OVER (PARTITION BY ((w.first_ord // 1000000000) - {LO}) // {CH} ORDER BY hash(w.pool || '{SEED}')) AS rn
        FROM wpool w WHERE w.program = '{CURVE}' AND w.first_ord // 1000000000 >= {data_lo + 2000}
          AND w.first_ord // 1000000000 BETWEEN {LO} AND {FRONT_HI}) WHERE rn <= {NPC} ORDER BY slot, tx_index, swap_index, pool""").fetchall()
else:
    trig = con.execute(f"""SELECT pool, slot, 0, 0, (slot - {LO}) // {CH} AS ch FROM (
        SELECT pool, slot::BIGINT AS slot, row_number() OVER (PARTITION BY (slot - {LO}) // {CH} ORDER BY hash(pool || slot::VARCHAR || '{SEED}')) AS rn
        FROM (SELECT DISTINCT s.pool, s.slot FROM swaps s JOIN wpool w USING (pool) WHERE NOT s.failed AND s.{win}))
        WHERE rn <= {NPC} ORDER BY slot, pool""").fetchall()
say('triggers', len(trig))

def next_slot_with(slot, lim=40):
    for d in range(lim):
        if slot + d in slot_n:
            return slot + d
    return None

legs, busy = [], {}
st = dict(trig=len(trig), busy=0, noslot=0, kept=0, skipped_chunk=0)
n = 0
for pool, ts, ti, tw, ch in trig:
    if TRIG == 'P2' or PLACE == 'same':
        if PLACE == 'same':
            fs, fi = ts, ti                          # 방아쇠 tx 바로 뒤(같은 tx_index · swap_index 900)
        else:
            fs = ts + 1
            if fs not in slot_n:
                st['noslot'] += 1; continue
            fi = int(rng.choice(rel_f) * slot_n[fs])
    elif TRIG == 'P1':
        fs = ts + 1
        if fs not in slot_n:
            st['noslot'] += 1; continue
        fi = 0 if PLACE == 'next_first' else int(rng.choice(rel_f) * slot_n[fs])
    else:
        fs = next_slot_with(ts + int(rng.integers(0, 11)))
        if fs is None:
            st['noslot'] += 1; continue
        fi = int(rng.choice(rel_f) * slot_n[fs])
    if KLAW == 'sampled':
        k = int(rng.choice(kd))
    elif KLAW.startswith('U'):
        k = int(rng.integers(1, int(KLAW[1:]) + 1))
    else:
        k = int(KLAW)
    if k == 0:
        room = slot_n[fs] - fi - 1
        if room < 1:
            st['noslot'] += 1; continue
        bs, bi = fs, fi + 1 + int(rng.integers(0, room))
    else:
        bs = next_slot_with(fs + k)
        if bs is None:
            st['noslot'] += 1; continue
        bi = int(rng.choice(rel_b) * slot_n[bs])
    fo, bo = fs * 10**9 + fi * 1000 + SWIX, bs * 10**9 + bi * 1000 + SWIX
    if busy.get(pool, -1) >= fo:
        st['busy'] += 1; continue
    busy[pool] = bo
    if ch not in use:                       # 조각 일부만 돌릴 때: 무작위 뽑기 순서는 전 조각 판과 같게 두고 줄만 거름
        st['skipped_chunk'] += 1; n += 1; continue
    legs.append((n, 'F', pool, fs, fi, k, ch)); legs.append((n, 'B', pool, bs, bi, k, ch))
    n += 1; st['kept'] += 1
say('legs', st)
con.register('legs', pa.table({'n': [x[0] for x in legs], 'side': [x[1] for x in legs], 'pool': [x[2] for x in legs],
    'slot': pa.array([x[3] for x in legs], pa.int64()), 'tx_index': pa.array([x[4] for x in legs], pa.int64()), 'k': [x[5] for x in legs], 'ch': [x[6] for x in legs]}))
con.execute(f"CREATE TEMP TABLE lg AS SELECT *, slot * 1000000000 + tx_index * 1000 + {SWIX} AS ord FROM legs")
con.execute(f"""CREATE TEMP TABLE rs AS SELECT s.pool, s.tx_sig, s.slot::BIGINT * 1000000000 + s.tx_index::BIGINT * 1000 + s.swap_index AS ord,
    (s.token_in = '{WSOL}') AS is_buy, s.amount_in, s.amount_out,
    CASE WHEN s.token_in = '{WSOL}' THEN s.amount_in ELSE s.amount_out END AS sol,
    CASE WHEN s.token_in = '{WSOL}' THEN s.amount_in / s.amount_out ELSE s.amount_out / s.amount_in END AS px
    FROM swaps s WHERE NOT s.failed AND s.pool IN (SELECT DISTINCT pool FROM legs) AND s.amount_in > 0 AND s.amount_out > 0
      AND (s.token_in = '{WSOL}' OR s.token_out = '{WSOL}') AND s.slot BETWEEN {LO - 20000} AND {HI + 5000}""")
# 값 기준 거래 찾기: 먼저 주 경로 셋(뒤 매수 ≥REF · 뒤 매도 ≥REF · 앞 거래 ≥REF) · 대체 셋(아무 크기)은 주 경로가 빈 줄에만(같은 결과 · 빠르게)
con.execute(f"""CREATE TEMP TABLE pr1 AS
    SELECT l.*, nb.px AS nb_px, nb.amount_in AS nb_in, nb.amount_out AS nb_out, nb.tx_sig AS nb_tx, ns.px AS ns_px, pm.px AS pm_px
    FROM lg l
    ASOF LEFT JOIN (SELECT pool, ord, px, amount_in, amount_out, tx_sig FROM rs WHERE is_buy AND sol >= {REF_MIN}) nb ON nb.pool = l.pool AND nb.ord > l.ord
    ASOF LEFT JOIN (SELECT pool, ord, px FROM rs WHERE NOT is_buy AND sol >= {REF_MIN}) ns ON ns.pool = l.pool AND ns.ord > l.ord
    ASOF LEFT JOIN (SELECT pool, ord, px FROM rs WHERE sol >= {REF_MIN}) pm ON pm.pool = l.pool AND pm.ord < l.ord""")
con.execute("""CREATE TEMP TABLE miss AS SELECT n, side, pool, ord FROM pr1
    WHERE (side = 'F' AND nb_px IS NULL AND pm_px IS NULL) OR (side = 'B' AND ns_px IS NULL AND pm_px IS NULL)""")
con.execute("""CREATE TEMP TABLE pr2 AS
    SELECT m.n, m.side, na.px AS na_px, na.amount_in AS na_in, na.amount_out AS na_out, na.tx_sig AS na_tx, nsa.px AS nsa_px, pa_.px AS pa_px
    FROM miss m
    ASOF LEFT JOIN (SELECT pool, ord, px, amount_in, amount_out, tx_sig FROM rs WHERE is_buy) na ON na.pool = m.pool AND na.ord > m.ord
    ASOF LEFT JOIN (SELECT pool, ord, px FROM rs WHERE NOT is_buy) nsa ON nsa.pool = m.pool AND nsa.ord > m.ord
    ASOF LEFT JOIN (SELECT pool, ord, px FROM rs) pa_ ON pa_.pool = m.pool AND pa_.ord < m.ord""")
con.execute("CREATE TEMP TABLE pr AS SELECT p1.*, p2.na_px, p2.na_in, p2.na_out, p2.na_tx, p2.nsa_px, p2.pa_px FROM pr1 p1 LEFT JOIN pr2 p2 USING (n, side)")
say('priced legs', con.execute("SELECT count(*) FROM pr").fetchone(), 'needing fallback joins', con.execute("SELECT count(*) FROM miss").fetchone())
rows = con.execute("""SELECT f.n, f.pool, w.program, w.tok, f.slot, f.tx_index, b.slot, b.tx_index, f.k, f.ch,
        f.nb_px, f.nb_in, f.nb_out, f.nb_tx, f.pm_px, f.na_px, f.na_in, f.na_out, f.na_tx, f.pa_px,
        b.ns_px, b.pm_px, b.nsa_px, b.pa_px
    FROM pr f JOIN pr b ON b.n = f.n AND b.side = 'B' JOIN wpool w ON w.pool = f.pool WHERE f.side = 'F' ORDER BY f.n""").fetchall()
out = {c_: [] for c_ in ('slot', 'block_time', 'tx_sig', 'tx_index', 'swap_index', 'program', 'trader', 'signer', 'pool', 'token_in', 'token_out', 'amount_in', 'amount_out', 'failed')}
meta = []; drop = 0; nudged = 0
tr = synth_trader(NAME)
for (n, pool, prog, tok, fs, fi, bs, bi, k, ch, nb_px, nb_in, nb_out, nb_tx, fpm, na_px, na_in, na_out, na_tx, fpa, ns_px, bpm, nsa_px, bpa) in rows:
    # 앞다리 값: 뒤 매수(≥REF_MIN) → 앞 거래(≥REF_MIN) → 뒤 매수(아무 크기) → 앞 거래(아무 크기)
    if nb_px:
        pxf, ref_f, rin, rout, rtx = nb_px, 'next', nb_in, nb_out, nb_tx
    elif fpm:
        pxf, ref_f, rin, rout, rtx = fpm, 'prev', None, None, None
    elif na_px:
        pxf, ref_f, rin, rout, rtx = na_px, 'next_any', na_in, na_out, na_tx
    elif fpa:
        pxf, ref_f, rin, rout, rtx = fpa, 'prev_any', None, None, None
    else:
        drop += 1; continue
    if ns_px:
        pxb, ref_b = ns_px, 'next'
    elif bpm:
        pxb, ref_b = bpm, 'prev'
    elif nsa_px:
        pxb, ref_b = nsa_px, 'next_any'
    elif bpa:
        pxb, ref_b = bpa, 'prev_any'
    else:
        drop += 1; continue
    if not (pxf > 0 and pxb > 0):
        drop += 1; continue
    tokq = SIZE / pxf
    if rin is not None:                                  # R4: 참조 매수가 float64 로도 '엄격히 더 나쁜 값' 을 못 넘게
        while rin * tokq > rout * SIZE:
            tokq = math.nextafter(tokq, 0.0); nudged += 1
    sol_out = tokq * pxb
    for side, sl, ti, tin, tout, ain, aout in (('F', fs, fi, WSOL, tok, SIZE, tokq), ('B', bs, bi, tok, WSOL, tokq, sol_out)):
        out['slot'].append(sl); out['block_time'].append(slot_bt.get(sl)); out['tx_sig'].append(f'SYN{NAME}:{n}:{side}'); out['tx_index'].append(ti)
        out['swap_index'].append(SWIX); out['program'].append(prog); out['trader'].append(tr); out['signer'].append(tr); out['pool'].append(pool)
        out['token_in'].append(tin); out['token_out'].append(tout); out['amount_in'].append(float(ain)); out['amount_out'].append(float(aout)); out['failed'].append(False)
    meta.append((NAME, n, pool, prog, fs, fi, bs, bi, k, ch, pxf, sol_out / tokq, ref_f, ref_b, rtx, SIZE))
pq.write_table(pa.table({'slot': pa.array(out['slot'], pa.uint32()), 'block_time': pa.array(out['block_time'], pa.int64()), 'tx_sig': out['tx_sig'],
    'tx_index': pa.array(out['tx_index'], pa.uint32()), 'swap_index': pa.array(out['swap_index'], pa.uint32()), 'program': out['program'], 'trader': out['trader'],
    'signer': out['signer'], 'pool': out['pool'], 'token_in': out['token_in'], 'token_out': out['token_out'], 'amount_in': pa.array(out['amount_in'], pa.float64()),
    'amount_out': pa.array(out['amount_out'], pa.float64()), 'failed': out['failed']}), OUTP)
cols = ['variant', 'n', 'pool', 'program', 'front_slot', 'front_idx', 'back_slot', 'back_idx', 'k', 'ch', 'px_front', 'px_back', 'ref_f', 'ref_b', 'ref_tx', 'size']
pq.write_table(pa.table({c_: [m[i] for m in meta] for i, c_ in enumerate(cols)}), OUTP.replace('.parquet', '_meta.parquet'))
fb = {r: sum(1 for m in meta if m[12] == r) for r in ('next', 'prev', 'next_any', 'prev_any')}
bb = {r: sum(1 for m in meta if m[13] == r) for r in ('next', 'prev', 'next_any', 'prev_any')}
json.dump({'cfg': CFG, 'ref_min': REF_MIN, 'chunks': CHUNKS, 'seed': SEED, 'npc': NPC, 'stats': st, 'dropped_no_price': drop, 'nudged_steps': nudged,
           'front_ref': fb, 'back_ref': bb, 'rows': len(out['slot'])}, open(OUTP.replace('.parquet', '_gen.json'), 'w'), indent=1)
say('wrote', len(meta), 'RT · dropped', drop, '· R4 nudges', nudged, '· front_ref', fb, '· back_ref', bb)
