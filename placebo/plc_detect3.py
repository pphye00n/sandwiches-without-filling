"""Run the authors' Solana sandwich detector (run_detection_solana.detect_chunk, imported unmodified) over a placebo DB with their production settings."""
# 운영 설정(그들 README 'production runs used 0.5'): amount_match_lo 0.5 · 조각 25,000 슬롯 · 나머지 그들 기본값
# (max_leaders_apart 2 · amount_match_hi 1.01 · victim_count 1 · transfer 0.95~1.05 · slot_margin 32 · victim_floor 0.01 · victim harm 켬 · min_front_wsol 0.01).
# 산출 = 위약 DB 안 sandwiches_raw · detection_runs_solana(그들 표).
# 쓰기: python plc_detect3.py --placebo-db WORK/placebo_P1.duckdb --nph AUTHORS_REPO [--chunks all|0,3,6,…]
import argparse, hashlib, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plc_common import add_common_args, add_authors_modules, open_placebo, chunk_grid, parse_chunks

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
ap.add_argument('--placebo-db', required=True)
ap.add_argument('--chunks', default='all', help="'all' or comma-separated chunk ids of the 25,000-slot grid from meta.lo")
args = ap.parse_args()
add_authors_modules(args.nph)
import run_detection_solana
from run_detection_solana import detect_chunk, init_output_table, init_runs_table   # 그들 코드 그대로(sha 는 로그에)
print('authors run_detection_solana.py sha256', hashlib.sha256(open(run_detection_solana.__file__, 'rb').read()).hexdigest(), flush=True)
t0 = time.time()
con, lo, hi = open_placebo(args.placebo_db, args)
init_runs_table(con)
con.execute("DELETE FROM detection_runs_solana")
init_output_table(con, 'sandwiches_raw')
keep = parse_chunks(args.chunks)
chunks = [c_ for i_, c_ in enumerate(chunk_grid(lo, hi)) if keep is None or i_ in keep]
print('chunks', len(chunks), 'slots', lo, hi, flush=True)
tv = te = 0
for i, (a, b) in enumerate(chunks, 1):
    t1 = time.time()
    nv, ne = detect_chunk(con, a, b, 'sandwiches_raw', max_leaders_apart=2, amount_match_lo=0.5, amount_match_hi=1.01, victim_count=1,
                          transfer_match_lo=0.95, transfer_match_hi=1.05, slot_margin=32, victim_floor=0.01, require_victim_harm=True,
                          min_front_wsol=0.01)
    con.execute("INSERT OR IGNORE INTO detection_runs_solana (slot_lo, slot_hi, n_vanilla, n_evasive) VALUES (?,?,?,?)", [a, b, nv, ne])
    con.execute("CHECKPOINT")
    tv += nv; te += ne
    print(f'[{i}/{len(chunks)}] {a}-{b}: +{nv} vanilla +{ne} evasive {time.time()-t1:.0f}s (total {tv}+{te})', flush=True)
print('done', tv, te, round(time.time() - t0), 's', flush=True)
