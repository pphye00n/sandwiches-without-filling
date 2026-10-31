"""Per-quarter tight-sandwich counts and bot concentration; share of a given bot list (Section 6).
usage: tight_concentration.py DEC_DIR BOTS_FILE"""
import sys, glob, datetime
import numpy as np
DEC, BF = sys.argv[1], sys.argv[2]
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    return n.to_bytes(32, 'big')
kb = np.load(f'{DEC}/keys_bot.npy'); idx = {bytes(k): i for i, k in enumerate(kb)}
targets = [idx[b58dec(s)] for s in open(BF).read().split() if b58dec(s) in idx]
A = np.concatenate([np.load(f, mmap_mode='r')[['day', 'type', 'bot', 'program', 'n_victims']] for f in sorted(glob.glob(f'{DEC}/rec_*.npy'))])
d0 = datetime.date(2023, 1, 1)
def qq(x):
    d = d0 + datetime.timedelta(days=int(x)); return f'{d.year}Q{(d.month - 1) // 3 + 1}'
qmap = np.array([qq(x) for x in range(int(A['day'].max()) + 1)]); q = qmap[A['day']]
T = A['type'] == 0
print('분기 | tight 건수 | tight 봇 수 | 위 1봇 몫 | 위 5봇 몫 | 표본 두 봇 몫')
for k in sorted(set(q.tolist())):
    m = (q == k) & T
    if not m.any(): continue
    b, c = np.unique(A['bot'][m], return_counts=True); o = np.argsort(-c)
    two = np.isin(A['bot'][m], targets).mean()
    print(f"{k} | {m.sum():>9,} | {len(b):>5,} | {c[o[0]] / m.sum():5.1%} | {c[o[:5]].sum() / m.sum():5.1%} | {two:5.1%}")
m = np.isin(q, ['2025Q4', '2026Q1', '2026Q2']) & T
print(f"2025Q4~2026Q2 tight {m.sum():,} · 표본 두 봇 몫 {np.isin(A['bot'][m], targets).mean():.1%}")
