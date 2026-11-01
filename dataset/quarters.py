"""Exact per-quarter counts by venue (bonding curve / PumpSwap / other) and type (tight / within-block / cross-block), and distinct bots -> quarters.json (Table 1, Figure 1).
usage: quarters.py DEC_DIR OUT.json"""
import sys, glob, json, datetime
import numpy as np
A = np.concatenate([np.load(f, mmap_mode='r')[['day', 'program', 'type', 'bot']] for f in sorted(glob.glob(f'{sys.argv[1]}/rec_*.npy'))])
d0 = datetime.date(2023, 1, 1)
def qq(x):
    d = d0 + datetime.timedelta(days=int(x)); return f'{d.year}Q{(d.month - 1) // 3 + 1}'
q = np.array([qq(x) for x in range(int(A['day'].max()) + 1)])[A['day']]
out = {}
for k in sorted(set(q.tolist())):
    m = q == k; p = A['program'][m]; t = A['type'][m]
    out[k] = dict(total=int(m.sum()), curve=int((p == 1).sum()), pumpswap=int((p == 2).sum()), other=int(((p != 1) & (p != 2)).sum()),
                  tight=int((t == 0).sum()), within=int((t == 1).sum()), cross=int((t == 2).sum()), bots=int(len(np.unique(A['bot'][m]))))
json.dump(out, open(sys.argv[2], 'w'), indent=1); print(json.dumps(out))
