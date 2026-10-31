"""Gate a placebo DB with the authors' own scripts, unmodified: enrich_eventual_fill (imported, then main), regate_sandwiches and build_trader_swap_counts (run as scripts), then build_real_bots.build."""
# 그들 solana/detect 세 스크립트와 evm/realbots/build_real_bots 를 고치지 않고 부름 — 이 파일에는 그들 SQL 이 없음.
#   1) enrich_eventual_fill.py: DB 경로 · 창 · 작업 폴더 · 일꾼 수/메모리를 받는 CLI 가 없어(모듈 상수) import 뒤 그 상수만 정하고
#      main('--recompute-all') 을 부름. 일꾼은 fork 로 띄워 정한 상수가 일꾼에도 그대로 가게 함. phase0 · phase3 의 DuckDB 한도(60GB/6 · 40GB/10)는 그들 코드 값 그대로.
#   2) regate_sandwiches.py --db --slot-lo --slot-hi --threads --memory-limit (스크립트 실행).
#   3) build_trader_swap_counts.py --db --sandwich-table sandwiches --start-slot --end-slot --threads --memory-limit [--min-free-gb] (스크립트 실행).
#   4) build_real_bots.build(con) (import).
# 그들 regate · trader counts 는 임시 폴더를 그들 저장소 뿌리(duckdb_tmp_regate · duckdb_tmp_causes)에 만듦 — 그들 코드 그대로.
# 쓰기: python plc_gate.py --placebo-db WORK/placebo_P1.duckdb --nph AUTHORS_REPO
import argparse, multiprocessing, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plc_common import add_common_args, add_authors_modules, connect

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
ap.add_argument('--placebo-db', required=True)
ap.add_argument('--ef-work', default=None, help="enrich work folder (default: <placebo-db>.ef_work; an existing one is renamed to .prev)")
ap.add_argument('--enrich-procs', type=int, default=1, help='enrich extraction and bucket workers (their production: 2 and 10)')
ap.add_argument('--tail', type=int, default=None, help="exit tail in slots past HI for enrich (default: theirs, 2,600,000)")
ap.add_argument('--enrich-min-free-gb', type=float, default=None, help="enrich disk guard on the work folder (default: theirs, 150)")
ap.add_argument('--counts-min-free-gb', type=float, default=None, help="trader-counts disk guard on their repository volume (default: theirs, 300)")
args = ap.parse_args()
add_authors_modules(args.nph)
import run_detection_solana
import build_real_bots
DET = os.path.dirname(os.path.abspath(run_detection_solana.__file__))
PDB = os.path.abspath(args.placebo_db)
t0 = time.time()
def say(*a):
    print(f'[{time.time()-t0:7.1f}s]', *a, flush=True)

c = connect(PDB, args, read_only=True)
lo, hi = (int(x) for x in c.execute("SELECT lo, hi FROM meta").fetchone())
c.close()                                   # 그들 일꾼이 DB 를 열 수 있게 우리 쪽 연결은 닫아 둠
say('window', lo, hi, 'db', PDB)

# 1) eventual fill — 그들 모듈 상수만 정하고 main
import enrich_eventual_fill as ef
work = Path(args.ef_work or PDB + '.ef_work')
if work.exists():
    k = 1
    while Path(f'{work}.prev{k}').exists():
        k += 1
    work.rename(f'{work}.prev{k}')
ef.MAIN, ef.WORK = Path(PDB), work
ef.WINDOW_LO, ef.WINDOW_HI = lo, hi
if args.tail is not None:
    ef.TAIL = args.tail
ef.EXTRACT_HI = ef.WINDOW_HI + ef.TAIL
ef.EXTRACT_PROCS = ef.BUCKET_PROCS = args.enrich_procs
ef.EXTRACT_MEM = ef.BUCKET_MEM = args.memory
ef.EXTRACT_THREADS = ef.BUCKET_THREADS = args.threads
if args.enrich_min_free_gb is not None:
    ef.MIN_FREE_GB = args.enrich_min_free_gb
multiprocessing.set_start_method('fork', force=True)
say('enrich_eventual_fill main --recompute-all', {'WORK': str(work), 'TAIL': ef.TAIL, 'procs': args.enrich_procs, 'mem': args.memory, 'threads': args.threads})
argv0 = sys.argv
sys.argv = [os.path.join(DET, 'enrich_eventual_fill.py'), '--recompute-all']
ef.main()
sys.argv = argv0

# 2) regate · 3) trader swap counts — 그들 스크립트 그대로 실행
def script(name, extra):
    cmd = [sys.executable, os.path.join(DET, name), '--db', PDB] + [str(x) for x in extra]
    say('run', ' '.join(os.path.basename(x) if i == 1 else x for i, x in enumerate(cmd)))
    subprocess.run(cmd, check=True)
script('regate_sandwiches.py', ['--slot-lo', lo, '--slot-hi', hi, '--threads', args.threads, '--memory-limit', args.memory])
script('build_trader_swap_counts.py', ['--sandwich-table', 'sandwiches', '--start-slot', lo, '--end-slot', hi, '--threads', args.threads,
                                       '--memory-limit', args.memory] + (['--min-free-gb', args.counts_min_free_gb] if args.counts_min_free_gb is not None else []))

# 4) real bots — 그들 함수 그대로
con = connect(PDB, args)
build_real_bots.build(con)
con.execute("CHECKPOINT")
say('real bots', con.execute("SELECT count(*) FROM real_bots").fetchone()[0], '· sandwiches', con.execute("SELECT count(*) FROM sandwiches").fetchone()[0])
con.close()
say('done')
