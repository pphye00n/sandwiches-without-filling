"""Per-quarter counts by venue (Raydium v4 / bonding curve / PumpSwap / other) and type (tight / within-block / cross-block), and pool-side profit in SOL (records whose front leg spends wSOL) -> JSON (Section 3).
usage: venue_quarter.py DEC_DIR OUT.json"""
import sys, glob, json, datetime
import numpy as np
A = np.concatenate([np.load(f, mmap_mode='r')[['day', 'program', 'type', 'profit', 'mint_in']] for f in sorted(glob.glob(f'{sys.argv[1]}/rec_*.npy'))])
d0 = datetime.date(2023, 1, 1)
def qq(x):
    d = d0 + datetime.timedelta(days=int(x)); return f'{d.year}Q{(d.month - 1) // 3 + 1}'
q = np.array([qq(x) for x in range(int(A['day'].max()) + 1)])[A['day']]
venue = np.where(A['program'] == 0, 'raydium_v4', np.where(A['program'] == 1, 'curve', np.where(A['program'] == 2, 'pumpswap', 'other')))
sol = A['mint_in'] == 0
out = {}
for k in sorted(set(q.tolist())):
    m = q == k; row = {}
    for v in ('raydium_v4', 'curve', 'pumpswap', 'other'):
        mv = m & (venue == v); t = A['type'][mv]
        row[v] = dict(n=int(mv.sum()), tight=int((t == 0).sum()), within=int((t == 1).sum()), cross=int((t == 2).sum()), profit_sol=float(A['profit'][mv & sol].sum()), n_sol=int((mv & sol).sum()))
    row['all'] = dict(n=int(m.sum()), profit_sol=float(A['profit'][m & sol].sum()))
    out[k] = row
json.dump(out, open(sys.argv[2], 'w'), indent=1)
tot = sum(r['all']['profit_sol'] for r in out.values()); late = [k for k in out if k >= '2025Q2']
print(f"전체 풀 쪽 수익 {tot:,.0f} SOL · 2025Q2~ 몫 {sum(out[k]['all']['profit_sol'] for k in late) / tot:.1%} · 2025Q2~ 건수 몫 {sum(out[k]['all']['n'] for k in late) / len(A):.1%}")
print('분기 | Raydium v4 n · tight% | 본딩커브 n · tight% | PumpSwap n · tight%')
for k in sorted(out):
    r = out[k]; f = lambda v: f"{r[v]['n']:,} · {(r[v]['tight'] / r[v]['n'] if r[v]['n'] else 0):.0%}"
    print(f"{k} | {f('raydium_v4')} | {f('curve')} | {f('pumpswap')}")
