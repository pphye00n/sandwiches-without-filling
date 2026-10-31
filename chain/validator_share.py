"""Dataset checks (every bot has >= 100 records; slots per day by quarter) and the block producer (fee-reward recipient) of sampled tight-sandwich slots versus random slots in the same period (Section 6).
usage: validator_share.py DEC_DIR BOTS_FILE V1_FILE OUT.json"""
import sys, glob, json, time, random, datetime, urllib.request
import numpy as np
DEC, BF, VF, OUTJ = sys.argv[1:5]
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    return n.to_bytes(32, 'big')
kb = np.load(f'{DEC}/keys_bot.npy'); idx = {bytes(k): i for i, k in enumerate(kb)}
two = [idx[b58dec(s)] for s in open(BF).read().split()]
V1 = open(VF).read().strip()
A = np.concatenate([np.load(f, mmap_mode='r')[['day', 'type', 'bot', 'front_slot']] for f in sorted(glob.glob(f'{DEC}/rec_*.npy'))])
cnt = np.bincount(A['bot']); cnt = cnt[cnt > 0]
print(f'① 봇 {len(cnt):,} · 봇당 기록 최소 {cnt.min()} · 100 미만 봇 {np.sum(cnt < 100)}', flush=True)
d0 = datetime.date(2023, 1, 1)
def q(x):
    d = d0 + datetime.timedelta(days=int(x)); return f'{d.year}Q{(d.month - 1) // 3 + 1}'
days = np.unique(A['day']); med = {}
for d in days:
    s = A['front_slot'][A['day'] == d]
    if len(s) > 200: med[int(d)] = float(np.median(s))
ks = sorted(med); per_q = {}
for a, b in zip(ks, ks[1:]):
    if b - a == 1: per_q.setdefault(q(a), []).append(med[b] - med[a])
print('② 분기별 하루 슬롯 수(중앙) → 슬롯 초:', {k: (round(float(np.median(v))), round(86400 / float(np.median(v)), 3)) for k, v in sorted(per_q.items())}, flush=True)
d_lo = (datetime.date(2025, 10, 1) - d0).days; d_hi = (datetime.date(2026, 7, 1) - d0).days
P = (A['day'] >= d_lo) & (A['day'] < d_hi)
T = P & (A['type'] == 0); TB = T & np.isin(A['bot'], two)
lo, hi = int(A['front_slot'][P].min()), int(A['front_slot'][P].max())
rng = random.Random(11)
s_two = rng.sample(sorted(set(A['front_slot'][TB].tolist())), 150)
s_rand = [rng.randrange(lo, hi + 1) for _ in range(300)]
print(f'③ 기간 슬롯 {lo:,}~{hi:,} · tight {T.sum():,} · 두 봇 tight {TB.sum():,}', flush=True)
RPC = 'https://api.mainnet-beta.solana.com'
def leader(slot):
    for k in range(8):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBlock", "params": [slot, {"transactionDetails": "none", "rewards": True, "maxSupportedTransactionVersion": 0}]}).encode(), headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if 'result' in r:
                fee = [x['pubkey'] for x in (r['result'] or {}).get('rewards', []) if x.get('rewardType') == 'Fee']
                return fee[0] if fee else 'NOFEE'
            if r.get('error', {}).get('code') in (-32007, -32009, -32004): return 'SKIPPED'
        except Exception: pass
        time.sleep(2 * (k + 1))
    return None
out = {'two_bot_tight': {}, 'random': {}}
for name, ss in (('two_bot_tight', s_two), ('random', s_rand)):
    for n, s in enumerate(ss):
        out[name][s] = leader(s); time.sleep(0.2)
        if (n + 1) % 50 == 0: print(f'   {name} {n + 1}/{len(ss)}', flush=True)
json.dump({k: {str(a): b for a, b in v.items()} for k, v in out.items()}, open(OUTJ, 'w'), indent=0)
for name in out:
    v = [x for x in out[name].values() if x not in (None, 'SKIPPED', 'NOFEE')]
    k = sum(x == V1 for x in v); n = len(v)
    print(f'③ {name}: 만들어진 블록 {n} · V1 {k} ({k / max(n, 1):.1%}) · 건너뜀 {sum(x == "SKIPPED" for x in out[name].values())} · 실패 {sum(x is None for x in out[name].values())}', flush=True)
print('DONE')
