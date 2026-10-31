"""Build one self-contained placebo DuckDB: physical copies of the base swaps (plus one variant's synthetic rows), slot_leaders and token_transfers from the window start on, and a `meta` row."""
# 한 DB 에 한 변형(섞임 0). 그들 스크립트(enrich · regate · trader counts)가 DB 파일을 --db 로 직접 열어 쓰므로 위약 DB 는 원 DB 없이도 서는 한 파일이어야 함
# → 원 DB 의 swaps · slot_leaders · token_transfers 를 창 시작 − MARGIN 슬롯부터 자료 끝까지 그대로 복사하고 합성 줄을 swaps 에 더함(원 DB 는 읽기만).
# 위약 DB 하나 = 그 구간 swaps 의 사본(우리 44시간 창에서 약 3GB).
# --synth 를 안 주면 합성 줄 0 개(같은 파이프라인으로 원판을 다시 내는 대조용).
# 쓰기: python plc_build_db.py --base-db BASE.duckdb --placebo-db WORK/placebo_P1.duckdb --synth WORK/synth_P1.parquet --lo LO --hi HI
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plc_common import SWAPS_COLS, add_common_args, connect

ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]), nph=False)
ap.add_argument('--base-db', required=True, help="the authors' Solana DB (swaps, slot_leaders, token_transfers); opened read-only")
ap.add_argument('--placebo-db', required=True, help='placebo DB to create (an existing file is renamed to .prev, never deleted)')
ap.add_argument('--synth', default=None, help='synthetic rows parquet from plc_gen3.py (omit for zero synthetic rows)')
ap.add_argument('--lo', type=int, required=True, help='first slot of the analysis window (front legs)')
ap.add_argument('--hi', type=int, required=True, help='last slot of the analysis window (front legs)')
ap.add_argument('--margin', type=int, default=2000, help='slots copied before LO (the detector needs 128; default 2000)')
args = ap.parse_args()
base_db = os.path.abspath(args.base_db)
if os.path.exists(args.placebo_db):
    os.rename(args.placebo_db, args.placebo_db + '.prev')
con = connect(args.placebo_db, args)
con.execute("SET preserve_insertion_order=true")     # 원 DB 저장 순서 그대로 복사(판마다 같은 배치)
con.execute(f"ATTACH '{base_db}' AS base (READ_ONLY)")
first = args.lo - args.margin
con.execute(f"CREATE TABLE swaps AS SELECT {SWAPS_COLS} FROM base.swaps WHERE slot >= {first}")
n_base = con.execute("SELECT count(*) FROM swaps").fetchone()[0]
if args.synth:
    con.execute(f"INSERT INTO swaps SELECT {SWAPS_COLS} FROM read_parquet('{args.synth}') ORDER BY slot, tx_index, swap_index")
n_syn = con.execute("SELECT count(*) FROM swaps").fetchone()[0] - n_base
con.execute(f"CREATE TABLE slot_leaders AS SELECT * FROM base.slot_leaders WHERE slot >= {first}")
has_tt = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_catalog = 'base' AND table_name = 'token_transfers'").fetchone()[0]
if has_tt:
    con.execute(f"CREATE TABLE token_transfers AS SELECT * FROM base.token_transfers WHERE slot >= {first}")
else:   # 그들 ingest 스키마 그대로의 빈 표(그들 evasive 갈래가 읽음)
    con.execute("""CREATE TABLE token_transfers (slot UINTEGER NOT NULL, block_time BIGINT, tx_sig VARCHAR NOT NULL, tx_index UINTEGER NOT NULL,
        transfer_index UINTEGER NOT NULL, mint VARCHAR, amount DOUBLE, sender_ata VARCHAR, recipient_ata VARCHAR, sender_owner VARCHAR,
        recipient_owner VARCHAR, signer VARCHAR)""")
con.execute("CREATE TABLE meta (lo BIGINT, hi BIGINT, base_db VARCHAR)")
con.execute("INSERT INTO meta VALUES (?, ?, ?)", [args.lo, args.hi, base_db])
con.execute("DETACH base")
con.execute("CHECKPOINT")
print('swaps rows copied from base', n_base, '· synthetic rows', n_syn, '· from slot', first, flush=True)
print('synthetic traders', con.execute("SELECT count(DISTINCT trader) FROM swaps WHERE trader LIKE 'SYNTH%'").fetchone()[0], flush=True)
print('slot_leaders rows', con.execute("SELECT count(*) FROM slot_leaders").fetchone()[0], '· token_transfers', 'copied' if has_tt else 'empty table', flush=True)
con.close()
