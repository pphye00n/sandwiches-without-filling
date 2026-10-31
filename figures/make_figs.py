"""Figures for the note (draft v0). Reads ../out/*.json → fig1_composition.png · fig2_curve_timing.png · fig3_placebo.png"""
import json, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
H = os.path.dirname(os.path.abspath(__file__)); O = os.environ.get('SWF_OUT', os.path.join(H, '..', 'out'))  # folder holding quarters.json, probe_age3_*.json, placebo2/, placebo3/
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

# Fig 3 — placebo (3rd run, all chunks): in-window labelled share per setting + real-trader baseline
names = {'P1': 'follow an executed buy, next slot (base)', 'P2s': 'buy in the creation slot', 'P2n': 'buy one slot after creation',
         'P3': 'random time in an active pool', 'H20': 'base, hold 1–20 slots', 'H40': 'base, hold 1–40 slots',
         'K2': 'base, hold exactly 2 slots', 'K5': 'base, hold exactly 5 slots', 'K8': 'base, hold exactly 8 slots', 'S1': 'base, 1 SOL front leg',
         'Y5': 'base, pools < 150 slots old, hold 5', 'Y8': 'base, pools < 150 slots old, hold 8'}
P2 = os.path.join(O, 'placebo2'); P3 = os.path.join(O, 'placebo3'); ew = json.load(open(os.path.join(P2, 'extra.json')))['placebo_in_window']
rows = []
for k in names:
    src = P3 if k.startswith('Y') else P2
    r = json.load(open(os.path.join(src, f'report_{k}.json'))); inw = r['gated_share_ci'][0] if k.startswith('Y') else ew[k]['hit_in_window_ci'][0]
    rows.append((k, inw, r['gated_share_ci'][0] >= 0.25))
rows.sort(key=lambda r: r[1])
bl = json.load(open(os.path.join(P2, 'baseline.json')))
ref = [("real traders' short round trips, not detected bots", bl['in_window_realbot_vs_other']['other']['hit_ci'][0]), ("all real traders' short round trips", bl['short_rt_in_window']['hit_ci'][0])]
fig, ax = plt.subplots(figsize=(6.5, 4.0)); y = np.arange(len(rows))
for yi, (k, v, rb) in zip(y, rows):
    ax.barh(yi, v * 100, 0.66, color=ORANGE if rb else BLUE); ax.text(v * 100 + 0.6, yi, f'{v:.1%}', va='center', fontsize=7.5, color=INK)
for j, (lab, v) in enumerate(ref):
    yi = len(rows) + 0.6 + j; ax.barh(yi, v * 100, 0.66, color=GRAY); ax.text(v * 100 + 0.6, yi, f'{v:.1%}', va='center', fontsize=7.5, color=INK)
ax.set_yticks(list(y) + [len(rows) + 0.6, len(rows) + 1.6], [names[r[0]] for r in rows] + [r[0] for r in ref], fontsize=7.5)
ax.axvline(25, color=INK2, linewidth=0.9, linestyle=(0, (3, 3))); ax.text(25.4, len(rows) + 2.35, 'density floor (25%)', fontsize=7.5, color=INK2, va='center'); ax.set_ylim(-0.6, len(rows) + 2.8)
ax.set_xlim(0, 64); ax.set_xlabel('short in-window round trips labelled as sandwiches (%)'); ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=ORANGE, label='placebo: density clears the floor'), Patch(color=BLUE, label='placebo: density below the floor'), Patch(color=GRAY, label='real traders, same definition')],
          frameon=False, fontsize=7.5, loc='lower right', bbox_to_anchor=(1.0, 0.0))
fig.tight_layout(); fig.savefig(os.path.join(H, 'fig3_placebo.png')); plt.close(fig)
print('figs ok')
