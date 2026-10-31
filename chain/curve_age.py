"""Bonding-curve age at the front leg: sample records from given parts, fetch the pool owner and the curve history before the front-leg signature from a public RPC node, report prior transaction counts and slots since the first curve transaction (Figure 2). Env PROGS selects programs (1 = bonding curve).
usage: curve_age.py OUT.json N_PER_PART_PER_PROG part..."""
import sys, os, json, time, struct, random, subprocess, hashlib, urllib.request
import numpy as np
OUTJ, NPP, PARTS = sys.argv[1], int(sys.argv[2]), [int(x) for x in sys.argv[3:]]
URL = 'https://huggingface.co/datasets/Lioba/solana_sandwich_attack_dataset/resolve/main/data_v3'
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58enc(b):
    n = int.from_bytes(b, 'big'); s = ''
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return '1' * (len(b) - len(b.lstrip(b'\0'))) + s
RPC = 'https://api.mainnet-beta.solana.com'
def rpc(m, p):
    for k in range(8):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if 'result' in r: return r['result']
        except Exception: pass
        time.sleep(1.5 * (k + 1))
    return None
HDR = struct.Struct('<BBHIIHBBBB'); rng = random.Random(7); picks = []
PROGS = tuple(int(x) for x in os.environ.get('PROGS', '1,2').split(','))
for pn in PARTS:
    name = f'part-{pn:04d}.bin'; tmp = f'/tmp/{name}'
    subprocess.run(['curl', '-sfL', '-o', tmp, f'{URL}/{name}'], check=True)
    buf = open(tmp, 'rb').read(); os.remove(tmp); i = 0; res = {1: [], 2: []}; seen = {1: 0, 2: 0}
    while i < len(buf):
        nf, nb, nv, fs, bs, day, ty, fl, prog, _ = HDR.unpack_from(buf, i); j = i + 18
        pool = buf[j + 32:j + 64]; j += 128 + (32 if fl & 2 else 0) + 40
        ns = nf + nb + nv; fsig = buf[j:j + 64]; j += 64 * ns + 4 * ns
        if prog in PROGS:
            seen[prog] += 1; rec = dict(part=pn, prog=prog, pool=b58enc(pool), front_sig=b58enc(fsig), front_slot=fs, back_slot=bs, day=day, type=ty, n_victims=nv)
            if len(res[prog]) < NPP: res[prog].append(rec)
            else:
                k = rng.randrange(seen[prog])
                if k < NPP: res[prog][k] = rec
        i = j
    for p in PROGS: picks += res[p]
    print(f'part {pn} · pump 기록 {seen} · 뽑음 {len(res[1])}+{len(res[2])}', flush=True)
OWN = {'6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P': 'pump_curve', 'pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA': 'pumpswap_amm'}
done_own = {1: 0, 2: 0}
for n, r in enumerate(picks):
    if done_own[r['prog']] < 10:
        ai = rpc('getAccountInfo', [r['pool'], {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}])
        v = (ai or {}).get('value') or {}; r['owner'] = OWN.get(v.get('owner'), v.get('owner')); done_own[r['prog']] += 1
    s = rpc('getSignaturesForAddress', [r['pool'], {"before": r['front_sig'], "limit": 1000}])
    if s is None: r['n_before'] = None
    else:
        r['n_before'] = len(s); r['first_slot'] = s[-1]['slot'] if s else r['front_slot']; r['first_complete'] = len(s) < 1000
        r['age_slots'] = r['front_slot'] - r['first_slot'] if r['first_complete'] else None
        r['n_before_failed'] = sum(1 for x in s if x.get('err'))
    if (n + 1) % 25 == 0: print('질의', n + 1, '/', len(picks), flush=True)
json.dump(picks, open(OUTJ, 'w'), ensure_ascii=False, indent=1)
for prog in PROGS:
    X = [r for r in picks if r['prog'] == prog and r.get('n_before') is not None]
    own = {}
    for r in X:
        if 'owner' in r: own[r['owner']] = own.get(r['owner'], 0) + 1
    nb = np.array([r['n_before'] for r in X]); ages = np.array([r['age_slots'] for r in X if r.get('age_slots') is not None], float)
    print(f'\nprogram {prog}: 표본 {len(X)} · 계좌 주인 {own}')
    print(f'   앞다리 전에 그 풀 거래 수: 0개 {np.mean(nb==0):.0%} · ≤2 {np.mean(nb<=2):.0%} · ≤10 {np.mean(nb<=10):.0%} · ≤100 {np.mean(nb<=100):.0%} · 1000↑ {np.mean(nb>=1000):.0%} · 중앙 {np.median(nb):.0f}')
    if len(ages):
        print(f'   풀 첫 거래 뒤 앞다리까지 슬롯: 같은 슬롯 {np.mean(ages<=0):.0%} · ≤2 {np.mean(ages<=2):.0%} · ≤10 {np.mean(ages<=10):.0%} · ≤150(≈1분) {np.mean(ages<=150):.0%} · ≤750(≈5분) {np.mean(ages<=750):.0%} · 분위 10/50/90 {np.quantile(ages,[.1,.5,.9]).round(0).tolist()}')
