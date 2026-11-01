# Sandwiches Without Filling — reproduction code

Code for the note *Sandwiches Without Filling: Launch Sniping, Momentum, and One Validator in Solana's "Sandwich Attack" Counts* (J. Park, 2026), which re-examines the Solana results of Heimbach, Solmaz, Öz and Ferreira Torres, *No Place to Hide* (arXiv:2609.28115).

Everything here uses only (a) the authors' released dataset and code and (b) public Solana RPC data. No private data is required.

## Layout

| Folder | What | Section of the note |
|---|---|---|
| `dataset/` | decode the released dataset, aggregate it, per-quarter composition, tight-sandwich concentration | §3, §6 |
| `chain/` | public-RPC probes: bonding-curve age at the front leg, blocks of tight sandwiches, block producer shares, neighbouring tips | §3, §6 |
| `placebo/` | zero-information placebo traders injected into a `swaps` table in the authors' schema, run through their unmodified pipeline (their scripts are called, not copied) | §4 |
| `figures/` | Figures 1–3 | — |

## Reproduction

1. **Dataset.** Build a manifest (part file name, sha256) from the Hugging Face listing of `data_v3`, then `python dataset/decode_dataset.py MANIFEST.tsv dec/`. This produces one `rec_XXXX.npy` per part and the key tables. Expect 28,042,725 records and 8,631 bots.
2. **Composition.** `python dataset/quarters.py dec/ quarters.json` (Table 1, Figure 1); `python dataset/venue_quarter.py dec/ venue_quarter.json` (per-venue shares and profit, §3); `python dataset/aggregate.py dec/ agg.json`.
3. **Bonding-curve age.** `PROGS=1 python chain/curve_age.py curve_age.json 30 82 83 ... 151` (one public RPC call per sampled record; the public endpoint rate-limits, so allow an hour).
4. **Tight sandwiches.** `python dataset/tight_concentration.py dec/ bots.txt`; `python chain/tight_blocks.py data_v3/ tight.json 10 120 128 134 139 145`; `python chain/validator_share.py dec/ bots.txt v1.txt v1_share.json`; `python chain/neighbor_tips.py tight.json v1_share.json neighbors.json`.
5. **Placebo.** See `placebo/README_placebo.md`. The injector reads only the `swaps` table (the authors' schema) and the `sandwiches` table produced by their detector; it works on any database built with their ingest code.
6. **Figures.** `SWF_OUT=<folder with the JSON outputs> python figures/make_figs.py`.

Validator and bot identities are not named in the note; the scripts above recover them from the public data.

## Third-party code

The detection, eventual-fill, regate, trader-count and real-bot steps are the authors' own scripts from their repository (commit f5d2eb7), executed unmodified; nothing from that repository is copied here. Clone it next to this one and point `NPH_REPO` at it (see `placebo/README_placebo.md`).

## Citation

J. Park, *Sandwiches Without Filling: Launch Sniping, Momentum, and One Validator in Solana's "Sandwich Attack" Counts*, 2026. arXiv: [to be added].

## Requirements

Python 3.11+, numpy, matplotlib; `duckdb` for the placebo pipeline; the authors' repository checked out next to `placebo/` (their `run_detection_solana.py`, `enrich_eventual_fill.py`, `regate_sandwiches.py`, `build_real_bots.py` are imported unmodified).
