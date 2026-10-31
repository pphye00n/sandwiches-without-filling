"""Report one placebo variant from the authors' outputs (sandwiches_raw, sandwiches, bot_stats, real_bots) and the generator's meta: labelled shares with Wilson intervals, k curve, per-chunk spread, price fallbacks, the three real-bot thresholds, and hygiene against the base run."""
# 찍힌 몫(raw · 정제 · 윌슨 95% 구간) · 그들 수익 표시 · 피해자 · 꼴 · k 곡선 · 조각별 흩어짐 · 값 대체(ref_f · ref_b) 표와 대체 뺀 판 · 풀 나이 칸 ·
# 참조 매수 홀로 피해자 점검 · 매도 앞다리 찍힘 · 합성 real bot 세 문턱(+ 실패 tx 를 셌다면의 가정 밀도) · 위생(실제 정제·real bot 원판 대비).
# 원판(base) = 원 DB 안 그들 산출(sandwiches_raw · sandwiches · real_bots) — 위약 DB 의 meta.base_db 를 base 로 붙여 읽음.
# 쓰기: python plc_report3.py --placebo-db WORK/placebo_P1.duckdb --meta WORK/synth_P1_meta.parquet --out WORK/report_P1.json [--chunks all|…]
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plc_common import CHUNK as CH, CURVE, PUMPSWAP, FEE_RATE, add_common_args, open_placebo, wilson, synth_trader

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]), nph=False)
ap.add_argument('--placebo-db', required=True)
ap.add_argument('--meta', required=True, help='…_meta.parquet written by plc_gen3.py')
ap.add_argument('--out', required=True, help='output JSON')
ap.add_argument('--chunks', default='all', help="must match the chunks passed to plc_gen3.py/plc_detect3.py")
args = ap.parse_args()
META, OUTJ, CHUNKS = args.meta, args.out, args.chunks
con, lo, hi = open_placebo(args.placebo_db, args, read_only=True)
con.execute(f"CREATE TEMP TABLE m AS SELECT *, 'SYN' || variant || ':' || n::VARCHAR || ':F' AS ftx FROM read_parquet('{META}')")
V = con.execute("SELECT any_value(variant) FROM m").fetchone()[0]
TR = synth_trader(V)
con.execute("CREATE TEMP TABLE pfirst AS SELECT pool, min(slot)::BIGINT AS first_slot FROM base.swaps WHERE pool IN (SELECT DISTINCT pool FROM m) GROUP BY 1")
con.execute(f"""CREATE TEMP TABLE rt AS SELECT m.*, r.front_tx IS NOT NULL AS raw_hit, g.front_tx IS NOT NULL AS gated_hit,
    g.is_profitable AS g_prof, g.victim_count AS g_vict, g.sandwich_type AS g_type, g.leaders_apart AS g_la, g.victim_txs AS g_vtx,
    m.front_slot - pf.first_slot AS age, m.size * (m.px_back / m.px_front) AS back_out,
    CASE WHEN m.program = '{CURVE}' THEN {FEE_RATE[CURVE]} ELSE {FEE_RATE[PUMPSWAP]} END AS fee_rate
    FROM m LEFT JOIN sandwiches_raw r ON r.front_tx = m.ftx AND r.bot_front = '{TR}'
    LEFT JOIN sandwiches g ON g.front_tx = m.ftx AND g.bot_front = '{TR}' LEFT JOIN pfirst pf ON pf.pool = m.pool""")
q1 = lambda sql: con.execute(sql).fetchone()
n_rt, n_raw, n_g, n_prof = q1("SELECT count(*), sum(raw_hit::INT), sum(gated_hit::INT), sum(CASE WHEN gated_hit THEN g_prof::INT END) FROM rt")
res = {'variant': V, 'trader_prefix': TR[:9], 'window': [lo, hi], 'chunks': CHUNKS,
       'n_rt': n_rt, 'raw_hit': n_raw, 'gated_hit': n_g, 'raw_share_ci': wilson(n_raw, n_rt), 'gated_share_ci': wilson(n_g, n_rt),
       'prof_flag_among_gated_ci': wilson(n_prof or 0, n_g),
       'sell_front_detections': q1(f"SELECT count(*) FROM sandwiches WHERE bot_front = '{TR}' AND front_tx LIKE '%:B'")[0],
       'curve_share': q1(f"SELECT avg((program='{CURVE}')::INT) FROM rt")[0]}
res['by_venue'] = con.execute("SELECT program, count(*), avg(gated_hit::INT) FROM rt GROUP BY 1 ORDER BY 1").fetchall()
res['victims_gated'] = q1("SELECT quantile_cont(g_vict, [0.5,0.75,0.9]), avg(g_vict), avg((g_vict>=2)::INT) FROM rt WHERE gated_hit")
res['type_gated'] = con.execute("SELECT g_type, count(*) FROM rt WHERE gated_hit GROUP BY 1 ORDER BY 2 DESC").fetchall()
res['leaders_apart_gated'] = con.execute("SELECT g_la, count(*) FROM rt WHERE gated_hit GROUP BY 1 ORDER BY 1").fetchall()
res['by_k'] = [[k, n, round(s, 4)] for k, n, s in con.execute("SELECT k, count(*), avg(gated_hit::INT) FROM rt GROUP BY 1 ORDER BY 1").fetchall()]
per = con.execute("SELECT ch, count(*), avg(gated_hit::INT), sum(gated_hit::INT), sum(CASE WHEN gated_hit THEN g_prof::INT ELSE 0 END) FROM rt GROUP BY 1 ORDER BY 1").fetchall()
vals = [x[2] for x in per if x[1] >= 50]
res['per_chunk'] = {'n_chunks': len(vals), 'mean': round(sum(vals) / len(vals), 4) if vals else None,
                    'sd': round((sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / max(len(vals) - 1, 1)) ** 0.5, 4) if vals else None,
                    'min': round(min(vals), 4) if vals else None, 'max': round(max(vals), 4) if vals else None, 'rows': [[a, b, round(c, 4), h, pf] for a, b, c, h, pf in per]}
# R9: 값 대체
res['fallback_table'] = con.execute("""SELECT ref_f, ref_b, count(*), round(avg(gated_hit::INT), 4), round(avg(CASE WHEN gated_hit THEN g_prof::INT END), 4)
    FROM rt GROUP BY 1, 2 ORDER BY 3 DESC""").fetchall()
res['front_fallback_share'] = q1("SELECT round(avg((ref_f <> 'next')::INT), 4) FROM rt")[0]
res['back_fallback_share'] = q1("SELECT round(avg((ref_b <> 'next')::INT), 4) FROM rt")[0]
nn = q1("SELECT count(*), sum(gated_hit::INT), sum(CASE WHEN gated_hit THEN g_prof::INT END) FROM rt WHERE ref_f = 'next'")
res['no_front_fallback'] = {'n_rt': nn[0], 'gated_share_ci': wilson(nn[1] or 0, nn[0]), 'prof_flag_ci': wilson(nn[2] or 0, nn[1] or 0)}
nn2 = q1("SELECT count(*), sum(gated_hit::INT), sum(CASE WHEN gated_hit THEN g_prof::INT END) FROM rt WHERE ref_f = 'next' AND ref_b = 'next'")
res['no_fallback_both'] = {'n_rt': nn2[0], 'gated_share_ci': wilson(nn2[1] or 0, nn2[0]), 'prof_flag_ci': wilson(nn2[2] or 0, nn2[1] or 0)}
# R4 점검: 피해자가 하나뿐인 찍힘에서 그 피해자가 참조 매수인 몫(고친 뒤 0 이어야)
res['ref_only_victim'] = q1("""SELECT count(*) FILTER (WHERE gated_hit AND g_vict = 1), count(*) FILTER (WHERE gated_hit AND g_vict = 1 AND ref_tx IS NOT NULL AND g_vtx[1] = ref_tx),
    count(*) FILTER (WHERE gated_hit AND ref_tx IS NOT NULL AND list_contains(g_vtx, ref_tx)) FROM rt""")
res['by_age_curve'] = con.execute(f"""SELECT CASE WHEN age IS NULL THEN 'z_null' WHEN age<=2 THEN 'a<=2' WHEN age<=10 THEN 'b<=10' WHEN age<=150 THEN 'c<=150'
    WHEN age<=1500 THEN 'd<=1500' ELSE 'e>1500' END AS g, count(*), round(avg(gated_hit::INT), 4) FROM rt WHERE program='{CURVE}' GROUP BY 1 ORDER BY 1""").fetchall()
res['by_age_pumpswap'] = con.execute(f"""SELECT CASE WHEN age IS NULL THEN 'z_null' WHEN age<=2 THEN 'a<=2' WHEN age<=150 THEN 'b<=150'
    WHEN age<=16800 THEN 'c<=1h' ELSE 'd>1h' END AS g, count(*), round(avg(gated_hit::INT), 4) FROM rt WHERE program='{PUMPSWAP}' GROUP BY 1 ORDER BY 1""").fetchall()
res['ret_q'] = q1("""SELECT quantile_cont(back_out / size - 1, [0.1, 0.5, 0.9]), quantile_cont((back_out - size - fee_rate * (size + back_out)) / size, [0.1, 0.5, 0.9]),
    quantile_cont(CASE WHEN gated_hit THEN back_out / size - 1 END, [0.1, 0.5, 0.9]),
    quantile_cont(CASE WHEN gated_hit THEN (back_out - size - fee_rate * (size + back_out)) / size END, [0.1, 0.5, 0.9]),
    avg(CASE WHEN gated_hit THEN (back_out - size - fee_rate * (size + back_out) > 0)::INT END) FROM rt""")
b = con.execute(f"""SELECT sw_count, profitable, profit_rate, n_pools, total_swaps, sandwich_txs, sandwich_density FROM bot_stats WHERE bot = '{TR}'""").fetchone()
if b:
    sw, prof, rate, npools, tot, legs, dens = b
    res['synth_bot'] = {'sw_count': sw, 'profitable': prof, 'profit_rate_ci': wilson(prof, sw), 'n_pools': npools, 'total_swaps': tot, 'sandwich_txs': legs,
                        'density': round(dens, 4), 'sw_ok': sw >= 100, 'rate_ok': rate >= 0.6, 'dens_ok': dens >= 0.25,
                        'is_real_bot': bool(q1(f"SELECT count(*) FROM real_bots WHERE bot = '{TR}'")[0]),
                        'density_if_failed_counted': {f: round(dens * (1 - f), 4) for f in (0.05, 0.10, 0.15)}}
# 위생(처리한 조각 범위만)
if CHUNKS == 'all':
    rng_sql = f"front_slot BETWEEN {lo} AND {hi}"
else:
    rng_sql = '(' + ' OR '.join(f'front_slot BETWEEN {lo + int(c_) * CH} AND {min(lo + (int(c_) + 1) * CH - 1, hi)}' for c_ in CHUNKS.split(',')) + ')'
q2 = lambda t, w: con.execute(f"SELECT count(*), count(DISTINCT bot_front) FROM {t} WHERE {w}").fetchone()
res['hygiene'] = {'gated_real_placebo': q2('sandwiches', f"bot_front NOT LIKE 'SYNTH%' AND {rng_sql}"), 'gated_base': q2('base.sandwiches', rng_sql),
                  'raw_real_placebo': q2('sandwiches_raw', f"bot_front NOT LIKE 'SYNTH%' AND {rng_sql}"), 'raw_base': q2('base.sandwiches_raw', rng_sql),
                  'real_gated_with_synth_victim': q1(f"SELECT count(*) FROM sandwiches WHERE bot_front NOT LIKE 'SYNTH%' AND len(list_filter(victim_addresses, x -> x LIKE 'SYNTH%')) > 0")[0]}
if CHUNKS == 'all':
    res['hygiene']['realbots_placebo'] = q1("SELECT count(*), sum(sw_count) FROM real_bots WHERE bot NOT LIKE 'SYNTH%'")
    res['hygiene']['realbots_base'] = q1("SELECT count(*), sum(sw_count) FROM base.real_bots")
    res['hygiene']['realbots_changed'] = q1("""SELECT count(*) FILTER (WHERE b.bot IS NULL), count(*) FILTER (WHERE p.bot IS NULL) FROM
        (SELECT bot FROM real_bots WHERE bot NOT LIKE 'SYNTH%') p FULL OUTER JOIN (SELECT bot FROM base.real_bots) b USING (bot)""")
json.dump(res, open(OUTJ, 'w'), indent=1, default=str)
print(json.dumps({k: res[k] for k in ('variant', 'n_rt', 'gated_share_ci', 'prof_flag_among_gated_ci', 'front_fallback_share', 'back_fallback_share', 'ref_only_victim')}, default=str))
print(json.dumps(res.get('synth_bot'), default=str)); print(json.dumps(res['hygiene'], default=str)); print('per_chunk', {k: v for k, v in res['per_chunk'].items() if k != 'rows'})
