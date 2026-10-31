"""Print the placebo result tables (markdown) from the JSON files in a work folder, so no number is copied by hand."""
# 읽는 것: report_<V>.json(10 변형 + 있으면 REF 민감도 <V>r2 · <V>r5) · baseline.json · extra.json · f7.json(있으면).
# 쓰기: python plc3_tables.py WORK > tables.md
import json, os, sys

O = sys.argv[1] if len(sys.argv) > 1 else '.'
J = lambda f: json.load(open(os.path.join(O, f)))
has = lambda f: os.path.exists(os.path.join(O, f))
V10 = [v for v in ('P1', 'P3', 'P2s', 'P2n', 'H20', 'H40', 'K2', 'K5', 'K8', 'S1', 'Y5', 'Y8', 'Yb') if has(f'report_{v}.json')]
R = {v: J(f'report_{v}.json') for v in V10}
E = J('extra.json') if has('extra.json') else None
B = J('baseline.json') if has('baseline.json') else None
F7 = J('f7.json') if has('f7.json') else None
CURVE, PUMPSWAP = 'pump_amm', 'pump_amm_v2'
pc = lambda x: f'{100 * x:.1f}%'
ci = lambda c: f'{100 * c[0]:.1f}% [{100 * c[1]:.1f}–{100 * c[2]:.1f}]'
DESC = {'P1': 'after an executed buy ≥ 0.1 WSOL, next slot · k from gated gaps', 'P3': 'random (pool, slot) · k from gated gaps',
        'P2s': 'right after the curve-creation tx, same slot · k from gated gaps', 'P2n': 'slot after curve creation · k from gated gaps',
        'H20': 'P1 trigger · k ~ U{1..20}', 'H40': 'P1 trigger · k ~ U{1..40}', 'K2': 'P1 trigger · k = 2', 'K5': 'P1 trigger · k = 5',
        'K8': 'P1 trigger · k = 8', 'S1': 'as P1 · 1 WSOL', 'Y5': 'P1 trigger on young pools (≤ 150 slots) · k = 5', 'Y8': 'P1 trigger on young pools (≤ 150 slots) · k = 8', 'Yb': 'P1 trigger on young pools (≤ 150 slots) · k from real bots'}

print('### Table A. Variants (each alone over the whole window · 0.1 WSOL, S1 = 1 WSOL · REF_MIN 0.01)\n')
print('| variant | trigger · placement · k | round trips | gated labelled [95%] | in-window share → labelled in window | per-chunk sd (min–max) | '
      'their profit flag among labelled [95%] | front · back price fallback | synthetic bot sw · profit rate [95%] · density | thresholds |')
print('|---|---|---|---|---|---|---|---|---|---|')
for v in V10:
    r = R[v]; b = r['synth_bot']; p = r['per_chunk']
    w = E['placebo_in_window'].get(v) if E else None
    th = ' · '.join(['sw ✓' if b['sw_ok'] else 'sw ✗', 'rate ✓' if b['rate_ok'] else 'rate ✗', 'density ✓' if b['dens_ok'] else 'density ✗'])
    th += ' → **real bot**' if b['is_real_bot'] else ''
    win = f"{pc(w['in_window_frac'])} → {ci(w['hit_in_window_ci'])}" if w else '—'
    print(f"| {v} | {DESC[v]} | {r['n_rt']:,} | {ci(r['gated_share_ci'])} | {win} | {100 * p['sd']:.1f} pp ({pc(p['min'])}–{pc(p['max'])}) | "
          f"{ci(r['prof_flag_among_gated_ci'])} | {pc(r['front_fallback_share'])} · {pc(r['back_fallback_share'])} | {b['sw_count']:,} · {ci(b['profit_rate_ci'])} · {b['density']:.3f} | {th} |")

ks = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 20]
print('\n### Table B. k curve (% labelled · k = back slot − front slot · "real" = short round trips of traders that are not real bots, all windows)\n')
print('| | ' + ' | '.join(f'k={k}' for k in ks) + ' |'); print('|---' * (len(ks) + 1) + '|')
row = lambda nm, d: print(f'| {nm} | ' + ' | '.join((f'{100 * d[k][1]:.0f}' if k in d and d[k][0] >= 100 else '·') for k in ks) + ' |')
for v in [x for x in ('P1', 'P3', 'P2s', 'P2n', 'H20', 'S1') if x in R]:
    row(v, {k: (n, s) for k, n, s in R[v]['by_k']})
if E:
    row('real, not bot', {k: (n, s) for k, n, s in E['base_by_k_other']})
    row('real, not bot, 0.05–0.2 WSOL', {k: (n, s) for k, n, s in E['base_by_k_other_0.05-0.2']})
    row('real, not bot, curve', {k: (n, s) for k, n, s in E['base_by_k_other_venue'][CURVE]})
    row('real, not bot, PumpSwap', {k: (n, s) for k, n, s in E['base_by_k_other_venue'][PUMPSWAP]})
if B:
    d = {k: w for k, n, s, w in B['by_k_all']}
    print('| real round trips inside the window (%) | ' + ' | '.join((f'{100 * d[k]:.0f}' if k in d else '·') for k in ks) + ' |')


def rew(tab, byk):
    t = {k: s for k, n, s in tab}; num = den = 0
    for k, n, s in byk:
        kk = min(k, 41)
        if kk in t:
            num += n * t[kk]; den += n
    return num / den if den else float('nan')


if E:
    print('\n### Table C. Real short round trips reweighted to each variant\'s k distribution, against the placebo\n')
    print('| variant | placebo | real, all | real, not bot | not bot, 0.05–0.2 WSOL | not bot curve / placebo curve | not bot PumpSwap / placebo PumpSwap | placebo ÷ not bot |')
    print('|---|---|---|---|---|---|---|---|')
    for v in V10:
        r = R[v]; byk = r['by_k']; vv = {p_: s for p_, n, s in r['by_venue']}
        o = rew(E['base_by_k_other'], byk)
        c = rew(E['base_by_k_other_venue'][CURVE], byk); s_ = rew(E['base_by_k_other_venue'][PUMPSWAP], byk)
        print(f"| {v} | {pc(r['gated_share_ci'][0])} | {pc(rew(E['base_by_k_all'], byk))} | {pc(o)} | {pc(rew(E['base_by_k_other_0.05-0.2'], byk))} | "
              f"{pc(c)} / {pc(vv[CURVE]) if CURVE in vv else '—'} | {pc(s_)} / {pc(vv[PUMPSWAP]) if PUMPSWAP in vv else '—'} | {r['gated_share_ci'][0] / o:.2f} |")

if B:
    print('\n### Table D. Real short round trips inside the two-leader window (baseline)\n')
    print('| cell | round trips | labelled [95%] | their profit flag among labelled |'); print('|---|---|---|---|')
    LBL = {'lt0.05': '< 0.05', '0.05-0.2': '0.05–0.2', '0.2-1': '0.2–1', 'ge1': '≥ 1'}
    rows = [('all', B['short_rt_in_window']), ('real bots, own round trips', B['in_window_realbot_vs_other']['realbot']),
            ('not real bots', B['in_window_realbot_vs_other']['other']), ('not real bots · 0.05–0.2 WSOL', B['in_window_0.05-0.2_other'])]
    rows += [(f'all · {LBL[k]} WSOL', v) for k, v in B['in_window_by_size'].items()]
    rows += [('all · curve', B['in_window_by_venue'][CURVE]), ('all · PumpSwap', B['in_window_by_venue'][PUMPSWAP])]
    if E:
        rows += [('not real bots · curve', E['base_in_window_other_by_venue'][CURVE]), ('not real bots · PumpSwap', E['base_in_window_other_by_venue'][PUMPSWAP])]
    for nm, x in rows:
        print(f"| {nm} | {x['n']:,} | {ci(x['hit_ci'])} | {ci(x['prof_among_hit_ci']) if x.get('prof_among_hit_ci') else '—'} |")
    tot = sum(n for k, n, s, w in B['by_k_all'])
    line = f"\nAll short round trips {tot:,}"
    if E:
        line += f"; inside the window {pc(E['base_in_window_frac'][0])} (not real bots {pc(E['base_in_window_frac'][1])})"
    print(line + f"; k ≤ 20, all windows {ci(B['k_le_20_all_windows']['hit_ci'])}; k ≤ 40 {ci(B['k_le_40_all_windows']['hit_ci'])}; "
          f"gated sandwiches whose front is such a round trip {B['gated_explained'][0]:,} / {B['gated_explained'][1]:,}")

print('\n### Table E. Price fallbacks (front and back legs) and the runs without them\n')
print('| variant | front fallback | back fallback | labelled among front-fallback rows | without front fallback: round trips · labelled [95%] · profit flag [95%] | without either fallback: labelled [95%] |')
print('|---|---|---|---|---|---|')
for v in V10:
    r = R[v]; ft = r['fallback_table']
    nf = sum(x[2] for x in ft if x[0] != 'next'); hf = sum(x[2] * x[3] for x in ft if x[0] != 'next')
    a = r['no_front_fallback']; bb = r['no_fallback_both']
    print(f"| {v} | {pc(r['front_fallback_share'])} | {pc(r['back_fallback_share'])} | {pc(hf / nf) if nf else '—'} (n {nf:,}) | "
          f"{a['n_rt']:,} · {ci(a['gated_share_ci'])} · {ci(a['prof_flag_ci'])} | {ci(bb['gated_share_ci'])} |")

SUBS = [v for v in ('P1', 'P3', 'H20') if v in R and has(f'report_{v}r2.json') and has(f'report_{v}r5.json')]
if SUBS:
    sub = {int(x) for x in J(f'report_{SUBS[0]}r2.json')['chunks'].split(',')}
    print(f'\n### Table F. REF_MIN sensitivity (same chunks {sorted(sub)} · same seed, triggers, placement and k)\n')
    print('| variant | REF 0.01 | 0.02 | 0.05 | profit flag 0.01 / 0.02 / 0.05 | front · back fallback 0.02 | 0.05 | density 0.02 / 0.05 |')
    print('|---|---|---|---|---|---|---|---|')
    for v in SUBS:
        rows_ = [x for x in R[v]['per_chunk']['rows'] if x[0] in sub]
        n = sum(x[1] for x in rows_); h = sum(x[3] for x in rows_); pf = sum(x[4] for x in rows_)
        r2 = J(f'report_{v}r2.json'); r5 = J(f'report_{v}r5.json')
        rb = lambda r: ' (real bot)' if r['synth_bot']['is_real_bot'] else ''
        print(f"| {v} | {pc(h / n)} ({h:,}/{n:,}) | {ci(r2['gated_share_ci'])} | {ci(r5['gated_share_ci'])} | {pc(pf / h)} / {pc(r2['prof_flag_among_gated_ci'][0])} / "
              f"{pc(r5['prof_flag_among_gated_ci'][0])} | {pc(r2['front_fallback_share'])} · {pc(r2['back_fallback_share'])} | {pc(r5['front_fallback_share'])} · "
              f"{pc(r5['back_fallback_share'])} | {r2['synth_bot']['density']:.3f}{rb(r2)} / {r5['synth_bot']['density']:.3f}{rb(r5)} |")

print('\n### Table G. Density if failed attempts were counted as swaps (hypothetical: density × (1 − f); the authors\' ingest emits no rows for failed txs)\n')
print('| | f = 0 | 5% | 10% | 15% |'); print('|---|---|---|---|---|')
mk = lambda x: f"**{x:.3f}**" if x >= 0.25 else f"{x:.3f}"
for v in V10:
    b = R[v]['synth_bot']; d = b['density_if_failed_counted']
    print(f"| {v} | {mk(b['density'])} | {mk(d['0.05'])} | {mk(d['0.1'])} | {mk(d['0.15'])} |")
if E:
    st = E['realbot_dist']['stay_if_density_times']
    print(f"| real bots still ≥ 0.25 (of {E['realbot_dist']['n']}) | {E['realbot_dist']['n']} | {st['0.05']} | {st['0.1']} | {st['0.15']} |")

if F7:
    print('\n### Table H. Curve selection (F7): labelled share of price-rule placebo curve round trips by CPMM-replay group\n')
    vs = [v for v in ('P1', 'P3', 'P2s', 'P2n') if v in F7['by_variant']]
    print('| group | curves · swaps mean (median) | ' + ' | '.join(vs) + ' |'); print('|---' * (len(vs) + 2) + '|')
    cur = {g: (n, m, md) for g, n, m, md in F7['curves']}
    for g, nm in (('a_cpmm_kept', 'replay matches (≥ 99% of buys within 0.1%, ≥ 3 buys)'), ('b_full_history_not_kept', 'full history, replay does not match'),
                  ('c_history_cut', 'history starts before the data')):
        if g not in cur:
            continue
        cells = []
        for v in vs:
            x = F7['by_variant'][v].get(g)
            cells.append(f"{ci(x['hit_ci'])} (n {x['n']:,})" if x else '—')
        n, m, md = cur[g]
        print(f"| {nm} | {n:,} · {m:.0f} ({md:.0f}) | " + ' | '.join(cells) + ' |')

if E:
    rd = E['realbot_dist']
    print('\n### Table I. Real-bot distribution and the synthetic traders\n')
    print(f"Real bots {rd['n']}: density p5/p10/p25/p50/p75/p90 = " + ' / '.join(f'{x:.3f}' for x in rd['density_q_05_10_25_50_75_90'])
          + ' · profit rate = ' + ' / '.join(f'{x:.3f}' for x in rd['profit_rate_q_05_10_25_50_75_90'])
          + ' · sw = ' + ' / '.join(f'{x:.0f}' for x in rd['sw_count_q_05_10_25_50_75_90'])
          + f" · density in [0.25, 0.26) / [0.25, 0.27) / [0.25, 0.30) = {' / '.join(str(x) for x in rd['density_within_0.25_0.26_0.27_0.30'])}"
          + f" · profit rate < 0.70: {rd['profit_rate_below_0.70']}\n")
    print('| variant | synthetic density | synthetic profit rate | real bots with lower density | real bots with lower profit rate | real bots lower on both |')
    print('|---|---|---|---|---|---|')
    for v in V10:
        s = E['synth_vs_realbots'].get(v)
        if s:
            print(f"| {v} | {s['density']:.3f} | {s['profit_rate']:.3f} | {pc(s['realbots_with_lower_density'])} | {pc(s['realbots_with_lower_profit_rate'])} | {s['realbots_lower_on_both']} |")
