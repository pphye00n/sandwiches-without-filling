# Placebo injection for the Solana sandwich detector

This folder holds the code for the placebo test in our note on Heimbach, Solmaz, Öz and Ferreira Torres, *No Place to Hide* (arXiv 2609.28115). We inject synthetic traders that have no information about any pending transaction into the authors' Solana `swaps` table. Then we run the authors' own pipeline, unmodified and with their production settings, and count how often the synthetic round trips are labelled as sandwiches and whether the synthetic trader passes the real-bot filter (`sw_count >= 100`, `profit_rate >= 0.6`, `sandwich_density >= 0.25`).

Each variant gets its own placebo database, so variants never interact. The authors' database is opened read-only and never written.

## Requirements

- Python 3.12 or newer with `duckdb`, `numpy`, `pyarrow` and `pandas`. `pandas` is needed by the authors' `regate_sandwiches.py`. Our runs used Python 3.13, DuckDB 1.5.6, NumPy 2.5.4, PyArrow 26.0.0 and pandas 3.1.0, on Linux.
- The authors' repository ([source](https://github.com/liobaheimbach/No-Place-to-Hide-An-Analysis-on-Protected-Order-Flow-Sandwich-Attacks)), checked out with its own layout. We tested against commit `f5d2eb7` (2026-09-21). Their code is called without modification:
  - `solana/detect/run_detection_solana.py`: `detect_chunk`, `init_output_table`, `init_runs_table`, `WSOL_MINT` (imported)
  - `solana/detect/enrich_eventual_fill.py` (imported; module constants set, then `main`)
  - `solana/detect/regate_sandwiches.py` and `solana/detect/build_trader_swap_counts.py` (run as scripts)
  - `evm/realbots/build_real_bots.py`: `build` (imported)
- A Solana DuckDB file in the authors' schema covering the window, with their stages 1–6 already run (see below).

### Inputs: the authors' schema only

| Table | Producer | Used by |
|---|---|---|
| `swaps` (14 columns: `slot, block_time, tx_sig, tx_index, swap_index, program, trader, signer, pool, token_in, token_out, amount_in, amount_out, failed`) | their `ingest/fetch_swaps_solana.py` | all scripts |
| `slot_leaders` | their ingest | detector, leader-window tests |
| `token_transfers` | their ingest; if missing, an empty table with their schema is created in the placebo DB | detector (evasive branch) |
| `sandwiches_raw`, `sandwiches`, `trader_swap_counts`, `bot_stats`, `real_bots` | their stages 2–6 on the base DB | generator (gap and in-block position distributions), report (hygiene), baseline, extra |

The code uses no other column or table. It contains no wallet, program or pool addresses and no keys. The quote mint is read from the authors' module (`WSOL_MINT`). Synthetic traders are labelled `SYNTH<variant>xxx…` (44 characters, not base58), and their transactions are labelled `SYN<variant>:<n>:F` (front leg) and `SYN<variant>:<n>:B` (back leg).

### Environment variables

| Variable | Meaning |
|---|---|
| `NPH_REPO` | Root of the authors' repository. Every script also accepts `--nph PATH`. |
| `BASE_DB` | The authors' Solana DuckDB file (read-only). |
| `WORK` | Output folder for synthetic rows, placebo DBs, JSON reports and logs. |
| `LO`, `HI` | First and last slot of the analysis window (front legs). The chunk grid is 25,000 slots from `LO`. |
| `PY` | Python interpreter (default `python3`). |
| `NPC` | Triggers sampled per 25,000-slot chunk (default 800). |
| `SUB` | Chunks used by the REF_MIN sensitivity runs (default `0,3,6,9,12,15,18,21,24,27`). |
| `VARIANTS` | Variants read by `plc3_extra.sh` (default: the ten main variants). |
| `PLC_THREADS`, `PLC_MEMORY`, `PLC_TEMP_DIR` | DuckDB threads (default 2), memory limit (default `6GB`) and optional spill directory. |

## Reproduction order

1. **Build the base DB with the authors' ingest.** Run `solana/ingest/fetch_swaps_solana.py --db swaps_solana.duckdb --start-slot S --slots N …` for the window plus a tail for exits. Our note used slots 462,434,512–463,175,991 (about 44 hours), with swaps through the end of our data as the exit tail.
2. **Run the authors' stages 2–6 on the base DB** with their production settings:
   - `run_detection_solana.py --amount-match-lo 0.5 --chunk-slots 25000`
   - `enrich_eventual_fill.py`
   - `regate_sandwiches.py`
   - `build_trader_swap_counts.py`
   - `evm/realbots/build_real_bots.py`

   Set their window constants to the same `[LO, HI]`. This step produces the `sandwiches` table the generator samples from and the base results the reports compare against.
3. **Inject and re-detect, one variant per DB** (`plc3_chain.sh`). For each variant:
   1. `plc_gen3.py` writes `synth_<V>.parquet`, `synth_<V>_meta.parquet` and `synth_<V>_gen.json`.
   2. `plc_build_db.py` creates `placebo_<V>.duckdb`. The authors' scripts open the database file directly, so each placebo DB is a self-contained file holding:
      - copies of the base `swaps`, `slot_leaders` and `token_transfers` from `LO − 2000` to the end of the data, with the synthetic rows added to `swaps`
      - a `meta` row (`lo`, `hi`, `base_db`)

      One placebo DB is about the size of that slice of the base DB (about 3 GB for our 44-hour window).
   3. `plc_detect3.py` runs the authors' `detect_chunk`, imported unmodified, on every 25,000-slot chunk with production settings: `max_leaders_apart=2`, `amount_match_lo=0.5`, `amount_match_hi=1.01`, `victim_count=1`, `transfer_match 0.95–1.05`, `slot_margin=32`, `victim_floor=0.01`, `require_victim_harm=True`, `min_front_wsol=0.01`.
   4. `plc_gate.py` runs the authors' remaining stages, unmodified:
      - `enrich_eventual_fill.py` with `--recompute-all`
      - `regate_sandwiches.py --db … --slot-lo LO --slot-hi HI --threads … --memory-limit …`
      - `build_trader_swap_counts.py --db … --sandwich-table sandwiches --start-slot LO --end-slot HI --threads … --memory-limit …`
      - `build_real_bots.build`
   5. `plc_report3.py` writes `report_<V>.json`.

   The script then runs the REF_MIN sensitivity variants on the `SUB` chunks.
4. **Real-trader baseline** (`plc3_post2.sh` runs `plc_baseline.py`): the share of real traders' short round trips that the gated detector labels, using the placebo's denominator.
5. **Extra measurements and tables** (`plc3_extra.sh` runs `plc_extra.py`, `plc_f7.py` and `plc3_tables.py`).

```bash
export NPH_REPO=/path/to/No-Place-to-Hide-An-Analysis-on-Protected-Order-Flow-Sandwich-Attacks
export BASE_DB=/path/to/swaps_solana.duckdb WORK=/path/to/work LO=462434512 HI=463175991
./plc3_chain.sh && ./plc3_post2.sh && ./plc3_extra.sh   # tables in $WORK/tables.md, progress in $WORK/chain.log
```

Runs are sequential. On our 44-hour window, one variant took about 15–20 minutes with 2 DuckDB threads and a 6 GB memory limit.

## Variants

All variants place one synthetic round trip per trigger: a buy of `size` WSOL, then a full sell of the tokens `k` slots later. Each pool holds at most one open synthetic position; a trigger that would overlap is skipped. The in-block position of each leg is drawn from the relative in-block positions of the gated front and back legs in the base `sandwiches`.

| Variant | Trigger | Front leg placement | k (back slot − front slot) | Size (WSOL) | Seed | REF_MIN |
|---|---|---|---|---|---|---|
| P1 | another trader's executed buy ≥ 0.1 WSOL | next slot | drawn from the gated `slots_apart` distribution | 0.1 | 31001 | 0.01 |
| P3 | random (pool, slot) with trading, plus 0–10 slots | next slot with swaps | gated distribution | 0.1 | 31003 | 0.01 |
| P2s | first swap of a bonding curve (creation tx) | same slot, right after the trigger tx | gated distribution | 0.1 | 31002 | 0.01 |
| P2n | first swap of a bonding curve | next slot | gated distribution | 0.1 | 31002 | 0.01 |
| H20 | as P1 | next slot | uniform on 1..20 | 0.1 | 31001 | 0.01 |
| H40 | as P1 | next slot | uniform on 1..40 | 0.1 | 31001 | 0.01 |
| K2 | as P1 | next slot | 2 | 0.1 | 31001 | 0.01 |
| K5 | as P1 | next slot | 5 | 0.1 | 31001 | 0.01 |
| K8 | as P1 | next slot | 8 | 0.1 | 31001 | 0.01 |
| S1 | as P1 | next slot | gated distribution | 1.0 | 31001 | 0.01 |
| P1r2, P1r5 | as P1 | as P1 | as P1 | 0.1 | 31001 | 0.02, 0.05 (`SUB` chunks) |
| P3r2, P3r5 | as P3 | as P3 | as P3 | 0.1 | 31003 | 0.02, 0.05 (`SUB` chunks) |
| H20r2, H20r5 | as H20 | as H20 | as H20 | 0.1 | 31001 | 0.02, 0.05 (`SUB` chunks) |

The variant name sets the synthetic trader label. A variant run on a chunk subset keeps every draw of the all-chunk run and only drops rows outside the subset, so the REF_MIN runs differ from the main run only in the pricing rule.

### Pricing

There is no self-impact, so the synthetic trade does not move the pool:

- **Front leg.** Average price of the next real buy on the same pool with at least `REF_MIN` WSOL.
- **Back leg.** Average price of the next real sell with at least `REF_MIN` WSOL.

When that trade does not exist, the fallback chain is: the previous real trade with at least `REF_MIN` WSOL, then the next trade of any size, then the previous trade of any size. Fallback rows are kept and flagged (`ref_f`, `ref_b` in the meta file), so the reports show labelled shares with and without them.

When the front price comes from a later real buy, the synthetic token amount is lowered one `math.nextafter` step at a time until that reference buy no longer passes the authors' victim-harm test in float64. That test requires the victim's price (WSOL paid per token received) to be strictly worse than the front leg's. The reference buy can therefore never be counted as a victim.

### Determinism

- Trigger sampling ranks candidates within each chunk by DuckDB `hash(tx_sig || pool || seed)` for P1, `hash(pool || seed)` for P2 and `hash(pool || slot || seed)` for P3, and keeps the first `NPC`.
- All other draws come from `numpy.random.default_rng(seed)`.
- The distribution arrays are read sorted, and trigger order breaks ties by `swap_index` and `pool`. The same inputs, seed and library versions therefore give the same synthetic rows.
- DuckDB's `hash` is version-specific, so other DuckDB versions sample different (statistically equivalent) triggers.
- The runs in our note read the arrays in storage order and broke trigger ties by `(slot, tx_index)` only. A fresh run with the same seed reproduces them up to the draws affected by that order: 0.1% of round trips or fewer moved between our repeated runs.

## Outputs (in `WORK`)

| File | Content |
|---|---|
| `synth_<V>.parquet` | synthetic rows in the 14-column `swaps` schema |
| `synth_<V>_meta.parquet` | one row per round trip: pool, program, front and back slot/index, k, chunk, prices, fallback flags, reference tx, size |
| `synth_<V>_gen.json` | config, seed, trigger and skip counts, fallback counts, `nextafter` steps |
| `placebo_<V>.duckdb` | copies of the base `swaps` (with the synthetic rows), `slot_leaders`, `token_transfers`; `meta`; the authors' outputs for this variant (`sandwiches_raw`, `detection_runs_solana`, `sandwiches`, `trader_swap_counts`, `bot_stats`, `real_bots`) |
| `placebo_<V>.duckdb.ef_work/` | work files of the authors' `enrich_eventual_fill.py` (deletable once the report is written) |
| `report_<V>.json` | see below |
| `baseline.json`, `extra.json`, `f7.json`, `tables.md` | baseline, extra measurements, curve-selection check, tables |

`report_<V>.json` includes:

- raw and gated labelled shares with Wilson 95% intervals, and the authors' profit flag among labelled round trips
- victims and sandwich type
- the k curve
- the per-chunk spread
- the fallback table and the shares without fallbacks
- the reference-buy-as-victim check
- shares by pool age
- returns before and after standard fees (curve 1.25% per side, PumpSwap 0.30% per side)
- the synthetic trader's `bot_stats` row and the three thresholds, plus a hypothetical density if failed attempts were counted
- hygiene: real sandwiches and real bots in the placebo run against the base run

## Notes

- **Density.** A synthetic trader only does two-swap round trips, so its `sandwich_density` (legs ÷ own swaps) equals its labelled share by arithmetic. The count floor is trivially cleared.
- **The authors' code is called without modification.** This folder contains none of their SQL. `plc_gate.py` drives their scripts as follows:
  - **`enrich_eventual_fill.py`** has no command-line options for the database path, window, work folder or worker resources; they are module constants. `plc_gate.py` imports the module, sets `MAIN`, `WORK`, `WINDOW_LO`, `WINDOW_HI`, `EXTRACT_HI = WINDOW_HI + TAIL` (their 2,600,000-slot `TAIL` unless `--tail` is given) and the worker counts, memory and threads, then calls `main()` with `--recompute-all`.
    - Workers are started with the `fork` method so they see these constants.
    - Their phase 0 and phase 3 keep the DuckDB limits written in their code (60 GB / 6 threads and 40 GB / 10 threads).
  - **`regate_sandwiches.py` and `build_trader_swap_counts.py`** run as scripts with their own options. They put DuckDB temp folders under the repository root (`duckdb_tmp_regate`, `duckdb_tmp_causes`) and keep their disk guards (150 GB free for the enrich work folder, 300 GB for trader counts; override with `--enrich-min-free-gb` and `--counts-min-free-gb`).
- **Failed transactions.** The authors' ingest emits no `swaps` rows for failed transactions, so failed attempts are not in the density denominator. The hypothetical column in the reports only shows what counting them would do. The real failure rates quoted in our note were measured on a raw transaction feed that is not in the authors' schema, and that measurement is not part of this folder.
- **Round 2 CPMM run not included.** The exact-CPMM robustness run of round 2 (bonding curves only, self-impact included) is not part of this release. `plc_f7.py` only measures how much its curve filter (public-constant replay matching ≥ 99% of a curve's buys within 0.1%, at least 3 buys) selects busier curves.

## Files

| File | Role |
|---|---|
| `plc_common.py` | shared helpers: authors' module paths, DuckDB settings, Wilson interval, synthetic labels, chunk grid |
| `plc_gen3.py` | generate one variant |
| `plc_build_db.py` | build one placebo DB (base read-only) |
| `plc_detect3.py` | authors' detector on the placebo DB |
| `plc_gate.py` | eventual fill, re-gate, trader swap counts, real bots |
| `plc_report3.py` | per-variant report |
| `plc_baseline.py` | real-trader baseline |
| `plc_extra.py` | non-bot k curves, in-window shares, real-bot placement |
| `plc_f7.py` | curve-selection check |
| `plc3_tables.py` | markdown tables from the JSON outputs |
| `plc3_chain.sh`, `plc3_post2.sh`, `plc3_extra.sh` | run order |
