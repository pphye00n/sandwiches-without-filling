"""Extra measurements on the authors' schema: non-bot baseline k curves, each placebo variant's in-window share, and where each synthetic trader sits in the real-bot density/profit-rate distribution."""
# (A) 기준선을 real bot 아닌 거래자로 나눠 k 곡선(전 창 · 0.05–0.2 WSOL · 곳별) — 위약 변형의 k 분포로 다시 무게 주는 건 plc3_tables.py 에서.
# (B) 위약 변형마다 창 안(리더 차 ≤ 2 · 그들 leader_seq) 왕복 몫과 그 안 찍힘 몫 — 기준선(창 안)과 같은 분모.
# (D) 실제 real bot 분포(밀도 · 수익률 · sw)와 각 합성 거래자의 자리 · 실패 tx 를 셌다면(가정: 밀도 × (1 − f)) 남는 real bot 수.
# 그들 swaps · slot_leaders · sandwiches · real_bots · bot_stats 만 읽음(원 DB 와 위약 DB 들 · 모두 읽기만).
# 쓰기: python plc_extra.py --base-db BASE.duckdb --work WORK --lo LO --hi HI --out WORK/extra.json --nph AUTHORS_REPO [--variants P1,P3,…]
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plc_common import CHUNK as CH, CURVE, PUMPSWAP, add_common_args, add_authors_modules, connect, wilson, synth_trader

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
ap.add_argument('--base-db', required=True, help="the authors' Solana DB after their stages 1-6; opened read-only")
ap.add_argument('--work', required=True, help='folder with placebo_<V>.duckdb and synth_<V>_meta.parquet')
ap.add_argument('--variants', default='P1,P3,P2s,P2n,H20,H40,K2,K5,K8,S1')
ap.add_argument('--lo', type=int, required=True)
ap.add_argument('--hi', type=int, required=True)
ap.add_argument('--out', required=True, help='output JSON')
args = ap.parse_args()
WSOL = add_authors_modules(args.nph)
lo, hi, WORK = args.lo, args.hi, args.work
con = connect(args.base_db, args, read_only=True)
res = {'window': [lo, hi]}
# 리더 차례 번호: 슬롯 순으로 리더가 바뀔 때마다 1 씩 오르는 번호(그들 detect_chunk 의 leader_seq 와 같은 정의 · 식은 우리 것)
con.execute(f"""CREATE TEMP TABLE lsm AS SELECT slot, sum(chg::INT) OVER (ORDER BY slot ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS leader_seq
    FROM (SELECT slot, leader IS DISTINCT FROM lag(leader) OVER (ORDER BY slot) AS chg FROM slot_leaders WHERE slot BETWEEN {lo - 256} AND {hi + 2000})""")
# (A) plc_baseline.py 와 같은 짧은 왕복 정의(그대로)
con.execute("CREATE TEMP TABLE rtp (trader VARCHAR, pool VARCHAR, tx_sig VARCHAR, slot BIGINT, ord BIGINT, amount_in DOUBLE, amount_out DOUBLE, program VARCHAR, next_slot BIGINT, next_tx VARCHAR, k BIGINT)")
a = lo
while a <= hi:
    b = min(a + CH - 1, hi)
    con.execute(f"""INSERT INTO rtp SELECT trader, pool, tx_sig, slot, ord, amount_in, amount_out, program, next_slot, next_tx, next_slot - slot FROM (
        SELECT *, LAG(is_buy) OVER w AS prev_buy, LEAD(is_buy) OVER w AS next_buy, LEAD(amount_in) OVER w AS next_in,
               LEAD(slot) OVER w AS next_slot, LEAD(tx_sig) OVER w AS next_tx
        FROM (SELECT s.trader, s.pool, s.tx_sig, s.slot::BIGINT AS slot, s.slot::BIGINT * 1000000000 + s.tx_index::BIGINT * 1000 + s.swap_index AS ord,
                     (s.token_in = '{WSOL}') AS is_buy, s.amount_in, s.amount_out, s.program
              FROM swaps s WHERE NOT s.failed AND (s.token_in = '{WSOL}' OR s.token_out = '{WSOL}') AND s.slot BETWEEN {a - 2000} AND {b + 300}) x
        WINDOW w AS (PARTITION BY trader, pool ORDER BY ord))
        WHERE is_buy AND slot BETWEEN {a} AND {b} AND (prev_buy IS NULL OR NOT prev_buy)
          AND next_buy = FALSE AND next_in BETWEEN 0.99 * amount_out AND 1.01 * amount_out""")
    a += CH
con.execute("""CREATE TEMP TABLE rt AS SELECT r.*, a.leader_seq AS ls_b, b.leader_seq AS ls_s FROM rtp r
    ASOF LEFT JOIN lsm a ON r.slot >= a.slot ASOF LEFT JOIN lsm b ON r.next_slot >= b.slot""")
con.execute("CREATE TEMP TABLE rb AS SELECT bot FROM real_bots")
con.execute("""CREATE TEMP TABLE rtf AS SELECT r.*, (r.ls_s - r.ls_b) AS la, g.front_tx IS NOT NULL AS hit, g.is_profitable AS prof, rb.bot IS NOT NULL AS is_realbot
    FROM rt r LEFT JOIN sandwiches g ON g.front_tx = r.tx_sig AND g.bot_front = r.trader AND g.pool = r.pool LEFT JOIN rb ON rb.bot = r.trader""")
print('rtf', con.execute("SELECT count(*), sum(hit::INT) FROM rtf").fetchone(), flush=True)
kq = lambda w: [[k, n, round(s, 4)] for k, n, s in con.execute(f"SELECT LEAST(k, 41), count(*), avg(hit::INT) FROM rtf WHERE {w} GROUP BY 1 ORDER BY 1").fetchall()]
res['base_by_k_all'] = kq('TRUE')
res['base_by_k_other'] = kq('NOT is_realbot')
res['base_by_k_other_0.05-0.2'] = kq('NOT is_realbot AND amount_in BETWEEN 0.05 AND 0.2')
res['base_by_k_other_venue'] = {v: kq(f"NOT is_realbot AND program = '{v}'") for v in (CURVE, PUMPSWAP)}
res['base_in_window_other_by_venue'] = {}
for v in (CURVE, PUMPSWAP):
    n, h = con.execute(f"SELECT count(*), sum(hit::INT) FROM rtf WHERE la <= 2 AND NOT is_realbot AND program = '{v}'").fetchone()
    res['base_in_window_other_by_venue'][v] = {'n': n, 'hit_ci': wilson(h or 0, n)}
res['base_in_window_frac'] = con.execute("SELECT avg((la <= 2)::INT), avg(CASE WHEN NOT is_realbot THEN (la <= 2)::INT END) FROM rtf").fetchone()
res['base_traders_with_gated_sandwich'] = con.execute("SELECT count(DISTINCT bot_front), count(*) FROM sandwiches").fetchone()
res['base_realbot_sandwiches'] = con.execute("SELECT count(*), sum(sw_count) FROM real_bots").fetchone()
# (B) 위약 변형마다 창 안 몫 · (D) 합성 거래자 자리
res['placebo_in_window'] = {}; res['synth_vs_realbots'] = {}
for V in args.variants.split(','):
    meta = os.path.join(WORK, f'synth_{V}_meta.parquet'); pdb = os.path.join(WORK, f'placebo_{V}.duckdb')
    if not (os.path.exists(meta) and os.path.exists(pdb)):
        print('skip', V, '(missing placebo DB or meta)', flush=True)
        continue
    TR = synth_trader(V)
    con.execute(f"ATTACH '{pdb}' AS pv (READ_ONLY)")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pm AS SELECT m.*, 'SYN' || m.variant || ':' || m.n::VARCHAR || ':F' AS ftx FROM read_parquet('{meta}') m""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pg AS SELECT front_tx FROM pv.sandwiches WHERE bot_front = '{TR}'""")
    con.execute("""CREATE OR REPLACE TEMP TABLE pr AS SELECT p.*, (b.leader_seq - a.leader_seq) AS la, g.front_tx IS NOT NULL AS hit FROM pm p
        ASOF LEFT JOIN lsm a ON p.front_slot >= a.slot ASOF LEFT JOIN lsm b ON p.back_slot >= b.slot LEFT JOIN pg g ON g.front_tx = p.ftx""")
    n, nin, hin, hall = con.execute("SELECT count(*), sum((la <= 2)::INT), sum(CASE WHEN la <= 2 THEN hit::INT END), sum(hit::INT) FROM pr").fetchone()
    res['placebo_in_window'][V] = {'n_rt': n, 'in_window_frac': round(nin / n, 4), 'n_in': nin, 'hit_in_window_ci': wilson(hin or 0, nin),
                                   'hit_all': hall, 'hits_out_of_window': (hall or 0) - (hin or 0),
                                   'by_la': con.execute("SELECT LEAST(la, 4), count(*), round(avg(hit::INT), 4) FROM pr GROUP BY 1 ORDER BY 1").fetchall()}
    sb = con.execute(f"SELECT sandwich_density, profit_rate, sw_count FROM pv.bot_stats WHERE bot = '{TR}'").fetchone()
    if sb:
        d, p, sw = sb
        res['synth_vs_realbots'][V] = {'density': round(d, 4), 'profit_rate': round(p, 4), 'sw_count': sw,
            'realbots_with_lower_density': con.execute(f"SELECT avg((sandwich_density < {d})::INT) FROM real_bots").fetchone()[0],
            'realbots_with_lower_profit_rate': con.execute(f"SELECT avg((profit_rate < {p})::INT) FROM real_bots").fetchone()[0],
            'realbots_lower_on_both': con.execute(f"SELECT sum((sandwich_density < {d} AND profit_rate < {p})::INT) FROM real_bots").fetchone()[0]}
    con.execute("DETACH pv")
    print(V, res['placebo_in_window'][V], res['synth_vs_realbots'].get(V), flush=True)
res['realbot_dist'] = {'n': con.execute("SELECT count(*) FROM real_bots").fetchone()[0],
    'density_q_05_10_25_50_75_90': con.execute("SELECT quantile_cont(sandwich_density, [0.05, 0.1, 0.25, 0.5, 0.75, 0.9]) FROM real_bots").fetchone()[0],
    'profit_rate_q_05_10_25_50_75_90': con.execute("SELECT quantile_cont(profit_rate, [0.05, 0.1, 0.25, 0.5, 0.75, 0.9]) FROM real_bots").fetchone()[0],
    'sw_count_q_05_10_25_50_75_90': con.execute("SELECT quantile_cont(sw_count, [0.05, 0.1, 0.25, 0.5, 0.75, 0.9]) FROM real_bots").fetchone()[0],
    'density_within_0.25_0.26_0.27_0.30': [con.execute(f"SELECT sum((sandwich_density >= 0.25 AND sandwich_density < {x})::INT) FROM real_bots").fetchone()[0] for x in (0.26, 0.27, 0.30)],
    'profit_rate_below_0.70': con.execute("SELECT sum((profit_rate < 0.70)::INT) FROM real_bots").fetchone()[0],
    'stay_if_density_times': {str(f): con.execute(f"SELECT sum((sandwich_density * (1 - {f}) >= 0.25)::INT) FROM real_bots").fetchone()[0] for f in (0.05, 0.10, 0.15)}}
print('realbot_dist', res['realbot_dist'], flush=True)
json.dump(res, open(args.out, 'w'), indent=1, default=str)
print('done', flush=True)
