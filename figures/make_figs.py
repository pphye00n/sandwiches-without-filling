"""Figures 1-3 of the note from the JSON outputs. Set SWF_OUT to the folder that holds quarters.json, probe_age3_{a,b}.json and placebo2/ (default ../out)."""
import json, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
H = os.path.dirname(os.path.abspath(__file__)); O = os.environ.get('SWF_OUT', os.path.join(H, '..', 'out'))  # folder holding quarters.json, probe_age3_*.json, placebo2/
BLUE, ORANGE, GRAY, INK, INK2, GRID = '#2a78d6', '#eb6834', '#b9b8b3', '#0b0b0b', '#52514e', '#e6e5e1'
plt.rcParams.update({'font.size': 9, 'font.family': 'DejaVu Sans', 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2,
                     'axes.spines.top': False, 'axes.spines.right': False, 'figure.facecolor': 'white', 'axes.facecolor': 'white', 'savefig.dpi': 200})

# Fig 1 — composition by quarter
Q = json.load(open(os.path.join(O, 'quarters.json'))); ks = [k for k in sorted(Q) if Q[k]['total'] > 1000]
cur = np.array([Q[k]['curve'] for k in ks]) / 1e6; ps = np.array([Q[k]['pumpswap'] for k in ks]) / 1e6; ot = np.array([Q[k]['other'] for k in ks]) / 1e6
fig, ax = plt.subplots(figsize=(6.5, 3.0)); x = np.arange(len(ks)); w = 0.72
ax.bar(x, ot, w, color=GRAY, edgecolor='white', linewidth=1.5, label='other venues (mostly Raydium)')
ax.bar(x, cur, w, bottom=ot, color=BLUE, edgecolor='white', linewidth=1.5, label='pump.fun bonding curve')
ax.bar(x, ps, w, bottom=ot + cur, color=ORANGE, edgecolor='white', linewidth=1.5, label='PumpSwap')
for i, k in enumerate(ks):
    sh = (Q[k]['curve'] + Q[k]['pumpswap']) / Q[k]['total']
    if sh >= 0.05: ax.text(i, ot[i] + cur[i] + ps[i] + 0.08, f'{sh:.0%}', ha='center', va='bottom', fontsize=7.5, color=INK2)
ax.set_xticks(x, [k.replace('Q', '\nQ') for k in ks], fontsize=7.5); ax.set_ylabel('detected sandwiches (millions)'); ax.set_ylim(0, 6.0)
ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=7.5, loc='upper left')
fig.tight_layout(); fig.savefig(os.path.join(H, 'fig1_composition.png')); plt.close(fig)

# Fig 2 — bonding-curve front leg: slots after token creation (ECDF)
fig, ax = plt.subplots(figsize=(6.5, 3.0))
for f, lab, col in (('probe_age3_a.json', '2024Q2–2025Q1', BLUE), ('probe_age3_b.json', '2025Q2–2026Q2', ORANGE)):
    a = np.sort([r['age_slots'] for r in json.load(open(os.path.join(O, f))) if r.get('age_slots') is not None and r['prog'] == 1]).astype(float)
    y = np.arange(1, len(a) + 1) / len(a); ax.step(a + 1, y, where='post', color=col, linewidth=2)
    j = np.searchsorted(a, 150, side='right') - 1
    ax.text(a[min(j, len(a) - 1)] + 1, y[j] - 0.06, f'  {lab} (n={len(a)}): median {np.median(a):.0f} slots', color=INK, fontsize=7.5, va='top')
ax.set_xscale('log'); ticks = [0, 2, 10, 150, 1000, 10000]; ax.set_xticks([t + 1 for t in ticks], [str(t) for t in ticks]); ax.minorticks_off()
for t, lab in ((2, '2 slots'), (150, '≈1 min')):
    ax.axvline(t + 1, color=INK2, linewidth=0.8, linestyle=(0, (3, 3))); ax.text(t + 1, 1.02, lab, ha='center', va='bottom', fontsize=7.5, color=INK2)
ax.set_ylim(0, 1.0); ax.set_xlim(0.9, 3e4); ax.set_ylabel('share of front legs'); ax.set_xlabel('slots between token creation and front leg (log scale)')
ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
fig.tight_layout(); fig.savefig(os.path.join(H, 'fig2_curve_timing.png')); plt.close(fig)

# Fig 3 — placebo: share of zero-information round trips labelled as sandwiches
names = {'P1': 'follow an executed buy, next slot (base)', 'Pa': 'follow an executed buy, same slot', 'Pb': 'follow an executed buy, top of next slot',
         'K2': 'base, hold exactly 2 slots', 'K5': 'base, hold exactly 5 slots', 'K8': 'base, hold exactly 8 slots', 'S1': 'base, 1 SOL front leg',
         'P2': 'buy right after token creation (priced launches)', 'Pn': 'buy one slot after token creation', 'P3': 'random time in an active pool'}
rows = []
for f in ('report_main.json', 'report_sens.json'):
    d = json.load(open(os.path.join(O, 'placebo', f)))
    share = {v['variant']: v['gated_share'] for v in d['per_variant']}
    for st in d['synth_bot_stats']:
        k = st[0].replace('SYNTH', ''); rows.append((k, share[k], bool(st[11])))
rows = sorted({r[0]: r for r in rows}.values(), key=lambda r: r[1])
fig, ax = plt.subplots(figsize=(6.5, 3.6)); y = np.arange(len(rows)) + 2
for yi, (k, v, rb) in zip(y, rows):
    ax.barh(yi, v * 100, 0.66, color=ORANGE if rb else BLUE); ax.text(v * 100 + 0.6, yi, f'{v:.1%}', va='center', fontsize=7.5, color=INK)
ref = [('all buys in the market', 0.0089), ("real bots' buys (selected on density)", 0.41)]
for yi, (lab, v) in zip((0, 1), ref):
    ax.barh(yi, v * 100, 0.66, color=GRAY); ax.text(v * 100 + 0.6, yi, f'{v:.2%}' if v < 0.01 else f'{v:.0%}', va='center', fontsize=7.5, color=INK)
ax.set_yticks(list(y) + [0, 1], [names[r[0]] for r in rows] + [r[0] for r in ref], fontsize=7.5)
ax.axvline(25, color=INK2, linewidth=0.9, linestyle=(0, (3, 3))); ax.text(25.4, len(rows) + 1.7, 'real-bot density floor (25%)', fontsize=7.5, color=INK2, va='center'); ax.set_ylim(-0.6, len(rows) + 2.2)
ax.set_xlim(0, 58); ax.set_xlabel('round trips labelled as sandwiches (%)'); ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=ORANGE, label='passes all real-bot thresholds'), Patch(color=BLUE, label='fails the density floor only'), Patch(color=GRAY, label='reference')],
          frameon=False, fontsize=7.5, loc='lower right', bbox_to_anchor=(1.0, 0.2))
fig.tight_layout(); fig.savefig(os.path.join(H, 'fig3_placebo.png')); plt.close(fig)
print('figs ok')
