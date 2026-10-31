"""Shared helpers for the placebo-injection scripts: authors' module paths, DuckDB settings, Wilson intervals, synthetic names."""
# 공개판 공통 도구. 경로·키·주소는 없음 — DB 경로 · 그들 저장소 경로 · 출력 폴더는 모두 CLI 인자 또는 환경변수.
import math
import os
import sys

# 그들 swaps 표 14칸(그들 solana/ingest/fetch_swaps_solana.py 순서)
SWAPS_COLS = ('slot, block_time, tx_sig, tx_index, swap_index, program, trader, signer, pool, '
              'token_in, token_out, amount_in, amount_out, failed')
CHUNK = 25_000              # 그들 운영 조각 격자(--chunk-slots 25000)
SYNTH_SWAP_INDEX = 900      # 합성 줄은 실제 (slot, tx_index) 를 나눠 쓰고 swap_index 900
CURVE = 'pump_amm'          # 그들 program 표기: pump.fun 본딩 곡선
PUMPSWAP = 'pump_amm_v2'    # 그들 program 표기: PumpSwap
SYNTH_PREFIX = 'SYNTH'      # 합성 거래자 이름 머리(실제 주소 아님 · base58 이 아님)
FEE_RATE = {CURVE: 0.0125, PUMPSWAP: 0.003}   # 수수료 뒤 손익 어림용 표준 수수료(한 쪽)


def add_common_args(ap, nph=True):
    """Add --threads/--memory/--temp-dir (and --nph) with environment-variable defaults."""
    ap.add_argument('--threads', type=int, default=int(os.environ.get('PLC_THREADS', '2')), help='DuckDB threads (env PLC_THREADS, default 2)')
    ap.add_argument('--memory', default=os.environ.get('PLC_MEMORY', '6GB'), help="DuckDB memory_limit (env PLC_MEMORY, default '6GB')")
    ap.add_argument('--temp-dir', default=os.environ.get('PLC_TEMP_DIR'), help='DuckDB spill directory (env PLC_TEMP_DIR, optional)')
    if nph:
        ap.add_argument('--nph', default=os.environ.get('NPH_REPO'), help="root of the authors' repository (env NPH_REPO)")
    return ap


def add_authors_modules(root):
    """Put the authors' Solana detector and real-bot modules on sys.path and return their WSOL mint constant."""
    if not root:
        raise SystemExit("authors' repository not given: pass --nph PATH or set NPH_REPO")
    subs = [os.path.join(root, 'solana', 'detect'), os.path.join(root, 'evm', 'realbots')]
    if not all(os.path.isdir(p) for p in subs):
        subs = [root]       # 그들 모듈 파일을 한 폴더에 모아 둔 경우도 받음
    for p in subs:
        if p not in sys.path:
            sys.path.insert(0, p)
    from run_detection_solana import WSOL_MINT   # 견적 토큰 주소는 그들 탐지기에서 가져옴(이 저장소에는 주소를 적지 않음)
    return WSOL_MINT


def connect(path, args, read_only=False):
    """Open a DuckDB file with the shared settings."""
    import duckdb
    con = duckdb.connect(path, read_only=read_only)
    con.execute(f"SET threads={int(args.threads)}; SET memory_limit='{args.memory}'; SET enable_progress_bar=false; SET preserve_insertion_order=false")
    if getattr(args, 'temp_dir', None):
        con.execute(f"SET temp_directory='{args.temp_dir}'")
    return con


def open_placebo(path, args, read_only=False):
    """Open a placebo DB built by plc_build_db.py, attach its base DB as `base`, and return (con, lo, hi)."""
    con = connect(path, args, read_only=read_only)
    lo, hi, base_db = con.execute("SELECT lo, hi, base_db FROM meta").fetchone()
    con.execute(f"ATTACH '{base_db}' AS base (READ_ONLY)")
    return con, int(lo), int(hi)


def wilson(k, n, z=1.96):
    """Wilson score interval as [p, lo, hi] rounded to 4 places (None when n = 0)."""
    if not n:
        return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(p, 4), round((c - r) / d, 4), round((c + r) / d, 4)]


def synth_trader(name):
    """Synthetic trader label for a variant (44 characters, reserved prefix, not a real address)."""
    return (SYNTH_PREFIX + name + 'x' * 44)[:44]


def synth_front_tx(name, n):
    """tx_sig of the n-th synthetic front leg of a variant."""
    return f'SYN{name}:{n}:F'


def chunk_grid(lo, hi):
    """25,000-slot chunk grid starting at lo (the authors' production grid)."""
    out, s = [], lo
    while s <= hi:
        out.append((s, min(s + CHUNK - 1, hi))); s += CHUNK
    return out


def parse_chunks(spec):
    """'all' or a comma list of chunk ids -> None or a set of ints."""
    return None if spec in (None, '', 'all') else {int(x) for x in spec.split(',')}
