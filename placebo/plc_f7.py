"""Curve-selection check (F7): split each price-rule placebo's bonding-curve round trips by whether the curve's public-constant CPMM replay matches its real buys, and compare labelled shares."""
# 곡선 거름(정확 CPMM 판이 쓰는 거름): 이력이 자료 안에 다 있고(첫 스왑 ≥ 자료 시작 + 2,000 슬롯) · pump.fun 공개 상수(생성 때 가상 30 SOL · 1,073,000,000 토큰)
# + 그 곡선 첫 스왑부터의 풀 쪽 금액 누적으로 준비금을 다시 지었을 때 그 곡선 실제 매수의 99%↑ 가 0.1% 안에 맞고 · 매수 ≥ 3.
# 그 거름 안 / 이력 다 있으나 거름 밖 / 이력 잘림 으로 나눠 위약 곡선 왕복의 찍힘 몫을 맞댐(거름이 붐비는 곡선을 고르는지 보는 것).
# 그들 swaps 칸 + 위약 DB 의 그들 sandwiches 만.
# 쓰기: python plc_f7.py --base-db BASE.duckdb --work WORK --out WORK/f7.json --nph AUTHORS_REPO [--variants P1,P3,P2s,P2n]
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plc_common import CURVE, add_common_args, add_authors_modules, connect, wilson, synth_trader

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
ap.add_argument('--base-db', required=True, help="the authors' Solana DB; opened read-only")
ap.add_argument('--work', required=True, help='folder with placebo_<V>.duckdb and synth_<V>_meta.parquet')
ap.add_argument('--variants', default='P1,P3,P2s,P2n')
ap.add_argument('--out', required=True, help='output JSON')
args = ap.parse_args()
WSOL = add_authors_modules(args.nph)
X0, Y0 = 30.0, 1_073_000_000.0          # pump.fun 곡선 공개 초기 가상 준비금(SOL · 토큰)
con = connect(args.base_db, args, read_only=True)
data_lo = con.execute("SELECT min(slot) FROM swaps").fetchone()[0]
con.execute(f"""CREATE TEMP TABLE call AS SELECT pool, min(slot) AS first_slot, count(*) AS n_sw FROM swaps
    WHERE NOT failed AND program = '{CURVE}' AND (token_in = '{WSOL}' OR token_out = '{WSOL}') GROUP BY 1""")
con.execute(f"""CREATE TEMP TABLE cpool AS SELECT pool FROM call WHERE first_slot >= {data_lo + 2000}""")
con.execute(f"""CREATE TEMP TABLE cs AS SELECT s.pool, s.slot::BIGINT * 1000000000 + s.tx_index::BIGINT * 1000 + s.swap_index AS ord, (s.token_in = '{WSOL}') AS is_buy,
    s.amount_in, s.amount_out,
    {X0} + SUM(CASE WHEN s.token_in = '{WSOL}' THEN s.amount_in ELSE -s.amount_out END) OVER w AS x_after,
    {Y0} - SUM(CASE WHEN s.token_in = '{WSOL}' THEN s.amount_out ELSE -s.amount_in END) OVER w AS y_after
    FROM swaps s JOIN cpool c USING (pool) WHERE NOT s.failed AND (s.token_in = '{WSOL}' OR s.token_out = '{WSOL}')
    WINDOW w AS (PARTITION BY s.pool ORDER BY s.slot, s.tx_index, s.swap_index ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)""")
con.execute(f"""CREATE TEMP TABLE chk AS WITH q AS (SELECT *, COALESCE(LAG(x_after) OVER w, {X0}) AS x_pre, COALESCE(LAG(y_after) OVER w, {Y0}) AS y_pre
        FROM cs WINDOW w AS (PARTITION BY pool ORDER BY ord))
    SELECT pool, count(*) AS nb, avg((abs(amount_out / (y_pre * amount_in / (x_pre + amount_in)) - 1) < 0.001)::INT) AS ok01
    FROM q WHERE is_buy AND amount_in > 0.001 GROUP BY 1""")
con.execute("DROP TABLE cs")
con.execute(f"""CREATE TEMP TABLE cls AS SELECT a.pool, a.n_sw,
    CASE WHEN a.first_slot < {data_lo + 2000} THEN 'c_history_cut' WHEN k.ok01 >= 0.99 AND k.nb >= 3 THEN 'a_cpmm_kept' ELSE 'b_full_history_not_kept' END AS grp
    FROM call a LEFT JOIN chk k USING (pool)""")
res = {'curves': con.execute("SELECT grp, count(*), round(avg(n_sw), 1), quantile_cont(n_sw, 0.5) FROM cls GROUP BY 1 ORDER BY 1").fetchall(), 'by_variant': {}}
print('curves', res['curves'], flush=True)
for V in args.variants.split(','):
    meta = os.path.join(args.work, f'synth_{V}_meta.parquet'); pdb = os.path.join(args.work, f'placebo_{V}.duckdb')
    if not (os.path.exists(meta) and os.path.exists(pdb)):
        print('skip', V, '(missing placebo DB or meta)', flush=True)
        continue
    TR = synth_trader(V)
    con.execute(f"ATTACH '{pdb}' AS pv (READ_ONLY)")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pr AS SELECT m.*, c.grp, g.front_tx IS NOT NULL AS hit FROM
        (SELECT *, 'SYN' || variant || ':' || n::VARCHAR || ':F' AS ftx FROM read_parquet('{meta}') WHERE program = '{CURVE}') m
        LEFT JOIN cls c ON c.pool = m.pool
        LEFT JOIN (SELECT front_tx FROM pv.sandwiches WHERE bot_front = '{TR}') g ON g.front_tx = m.ftx""")
    res['by_variant'][V] = {grp: {'n': n, 'hit_ci': wilson(h or 0, n)} for grp, n, h in
                            con.execute("SELECT COALESCE(grp, 'z_none'), count(*), sum(hit::INT) FROM pr GROUP BY 1 ORDER BY 1").fetchall()}
    con.execute("DETACH pv")
    print(V, res['by_variant'][V], flush=True)
json.dump(res, open(args.out, 'w'), indent=1, default=str)
print('done', flush=True)
