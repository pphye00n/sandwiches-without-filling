"""Real-trader baseline with the placebo's denominator: the share of real traders' short round trips (flat buy, then a 99-101% sell as their next trade in that pool) that the authors' gated detector labels, overall, inside the two-leader window, by holding time k, size, venue and real-bot status."""
# 짧은 왕복 = 거래자 T 가 풀 P 에서 매수 B(WSOL 지불) 뒤 바로 다음 T·P 거래가 매도 S 이고 S 가 B 의 토큰을 99~101% 되팖(한 번에 전부)
#   · B 바로 앞 T·P 거래는 없거나 매도(평평한 데서 시작 = 위약과 같음) · k = S 슬롯 − B 슬롯 · 창 안 = 리더 차(그들 leader_seq) ≤ 2.
# 찍힘 = 그들 정제 sandwiches 에 front_tx = B · bot_front = T · pool = P 인 줄이 있음. 그들 swaps · slot_leaders · sandwiches · real_bots 만.
# 쓰기: python plc_baseline.py --base-db BASE.duckdb --lo LO --hi HI --out WORK/baseline.json --nph AUTHORS_REPO
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plc_common import CHUNK, add_common_args, add_authors_modules, connect, wilson

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
ap.add_argument('--base-db', required=True, help="the authors' Solana DB after their stages 1-6; opened read-only")
ap.add_argument('--lo', type=int, required=True)
ap.add_argument('--hi', type=int, required=True)
ap.add_argument('--out', required=True, help='output JSON')
args = ap.parse_args()
WSOL = add_authors_modules(args.nph)
OUTJ, lo, hi = args.out, args.lo, args.hi
con = connect(args.base_db, args, read_only=True)
# 리더 차례 번호: 슬롯 순으로 리더가 바뀔 때마다 1 씩 오르는 번호(그들 detect_chunk 의 leader_seq 와 같은 정의 · 식은 우리 것)
con.execute(f"""CREATE TEMP TABLE lsm AS SELECT slot, sum(chg::INT) OVER (ORDER BY slot ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS leader_seq
    FROM (SELECT slot, leader IS DISTINCT FROM lag(leader) OVER (ORDER BY slot) AS chg FROM slot_leaders WHERE slot BETWEEN {lo - 256} AND {hi + 2000})""")
# 조각(25,000 슬롯)마다: 앞 2,000 · 뒤 300 슬롯 겹쳐 읽고 창 함수 → 왕복 시작 B 는 그 조각 안 것만(첫 판은 4,400만 줄 창 함수가 HDD 로 넘쳐 느림 → 조각으로)
CH = CHUNK
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
print('rtp', con.execute("SELECT count(*) FROM rtp").fetchone(), flush=True)
con.execute("""CREATE TEMP TABLE rt AS SELECT r.*, a.leader_seq AS ls_b, b.leader_seq AS ls_s FROM rtp r
    ASOF LEFT JOIN lsm a ON r.slot >= a.slot ASOF LEFT JOIN lsm b ON r.next_slot >= b.slot""")
con.execute("""CREATE TEMP TABLE rtf AS SELECT r.*, (r.ls_s - r.ls_b) AS la, g.front_tx IS NOT NULL AS hit, g.is_profitable AS prof,
    r.trader IN (SELECT bot FROM real_bots) AS is_realbot
    FROM rt r LEFT JOIN sandwiches g ON g.front_tx = r.tx_sig AND g.bot_front = r.trader AND g.pool = r.pool""")
res = {'window': [lo, hi]}
def part(where):
    n, h, p = con.execute(f"SELECT count(*), sum(hit::INT), sum(CASE WHEN hit THEN prof::INT END) FROM rtf WHERE {where}").fetchone()
    return {'n': n, 'hit_ci': wilson(h or 0, n), 'prof_among_hit_ci': wilson(p or 0, h or 0)}
res['short_rt_in_window'] = part('la <= 2')
res['in_window_by_size'] = {nm: part(f'la <= 2 AND {w}') for nm, w in (('lt0.05', 'amount_in < 0.05'), ('0.05-0.2', 'amount_in BETWEEN 0.05 AND 0.2'),
                                                                         ('0.2-1', 'amount_in > 0.2 AND amount_in < 1'), ('ge1', 'amount_in >= 1'))}
res['in_window_by_venue'] = {nm: part(f"la <= 2 AND program = '{nm}'") for nm in ('pump_amm', 'pump_amm_v2')}
res['in_window_realbot_vs_other'] = {'realbot': part('la <= 2 AND is_realbot'), 'other': part('la <= 2 AND NOT is_realbot')}
res['in_window_0.05-0.2_other'] = part('la <= 2 AND amount_in BETWEEN 0.05 AND 0.2 AND NOT is_realbot')
res['by_k_all'] = [[k, n, round(s, 4), round(w, 4)] for k, n, s, w in con.execute("""SELECT LEAST(k, 41), count(*), avg(hit::INT), avg((la <= 2)::INT) FROM rtf GROUP BY 1 ORDER BY 1""").fetchall()]
res['by_k_size_0.05-0.2'] = [[k, n, round(s, 4)] for k, n, s in con.execute("""SELECT LEAST(k, 41), count(*), avg(hit::INT) FROM rtf WHERE amount_in BETWEEN 0.05 AND 0.2 GROUP BY 1 ORDER BY 1""").fetchall()]
res['by_k_in_window'] = [[k, n, round(s, 4)] for k, n, s in con.execute("""SELECT LEAST(k, 41), count(*), avg(hit::INT) FROM rtf WHERE la <= 2 GROUP BY 1 ORDER BY 1""").fetchall()]
res['k_le_20_all_windows'] = part('k BETWEEN 1 AND 20')
res['k_le_40_all_windows'] = part('k BETWEEN 1 AND 40')
res['k_le_20_0.05-0.2'] = part('k BETWEEN 1 AND 20 AND amount_in BETWEEN 0.05 AND 0.2')
res['k_le_40_0.05-0.2'] = part('k BETWEEN 1 AND 40 AND amount_in BETWEEN 0.05 AND 0.2')
# 위약 k 분포(정제 간격)로 다시 무게: 실제 창 안 왕복의 k별 찍힘을 정제 k 분포로 평균
kdist = dict(con.execute(f"SELECT slots_apart, count(*) FROM sandwiches GROUP BY 1").fetchall())
kr = {k: s for k, n, s, w in res['by_k_all'] if n >= 50}
tot = sum(v for kk, v in kdist.items() if kk in kr)
res['real_rate_reweighted_to_placebo_k'] = round(sum(kr[kk] * v for kk, v in kdist.items() if kk in kr) / tot, 4) if tot else None
res['gated_explained'] = con.execute("""SELECT count(*), (SELECT count(*) FROM sandwiches) FROM rtf WHERE hit""").fetchone()
json.dump(res, open(OUTJ, 'w'), indent=1, default=str)
for k, v in res.items():
    if not k.startswith('by_k'):
        print(k, v, flush=True)
