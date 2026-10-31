"""Open the blocks of sampled tight (front-victim-back adjacent) sandwiches with getBlock: positions in the block, Jito tip transfers, jitodontfront on the victim, signers (Section 6).
usage: tight_blocks.py DATA_V3_DIR OUT.json N part..."""
import sys, os, json, time, struct, random, urllib.request
DATA, OUTJ, N, PARTS = sys.argv[1], sys.argv[2], int(sys.argv[3]), [int(x) for x in sys.argv[4:]]
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58enc(b):
    n = int.from_bytes(b, 'big'); s = ''
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return '1' * (len(b) - len(b.lstrip(b'\0'))) + s
JITO = {'96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5', 'HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe', 'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY', 'ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49',
        'DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh', 'ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt', 'DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL', '3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT'}
RPC = 'https://api.mainnet-beta.solana.com'
def rpc(m, p):
    for k in range(8):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            if 'result' in r: return r['result']
            if r.get('error', {}).get('code') in (-32009, -32007, -32004): return None   # 건너뛴 슬롯·없는 블록
        except Exception: pass
        time.sleep(2 * (k + 1))
    return None
HDR = struct.Struct('<BBHIIHBBBB'); rng = random.Random(5); picks = []
for pn in PARTS:
    buf = open(f'{DATA}/part-{pn:04d}.bin', 'rb').read(); i = 0; res = []; seen = 0
    while i < len(buf):
        nf, nb, nv, fs, bs, day, ty, fl, prog, _ = HDR.unpack_from(buf, i); j = i + 18
        bot = buf[j:j + 32]; j += 128 + (32 if fl & 2 else 0) + 40; ns = nf + nb + nv
        sigs = [buf[j + 64 * k:j + 64 * (k + 1)] for k in range(ns)]; j += 64 * ns + 4 * ns
        if ty == 0 and nf == 1 and nb == 1 and nv == 1:
            seen += 1; rec = dict(part=pn, prog=prog, slot=fs, bot=b58enc(bot), front=b58enc(sigs[0]), back=b58enc(sigs[1]), victim=b58enc(sigs[2]), day=day)
            if len(res) < N: res.append(rec)
            else:
                k = rng.randrange(seen)
                if k < N: res[k] = rec
        i = j
    picks += res; print(f'part {pn} · tight(1·1·1) {seen} · 뽑음 {len(res)}', flush=True)
out = []
for n, r in enumerate(picks):
    b = rpc('getBlock', [r['slot'], {"encoding": "json", "transactionDetails": "full", "maxSupportedTransactionVersion": 0, "rewards": False}])
    if not b: r['block'] = None; out.append(r); continue
    txs = b['transactions']; idx = {}
    for k, t in enumerate(txs):
        s0 = t['transaction']['signatures'][0]
        if s0 in (r['front'], r['back'], r['victim']): idx[s0] = (k, t)
    r['n_txs'] = len(txs)
    def info(sig):
        if sig not in idx: return None
        k, t = idx[sig]; keys = t['transaction']['message']['accountKeys']
        keys = keys + (t['meta'].get('loadedAddresses', {}).get('writable', []) + t['meta'].get('loadedAddresses', {}).get('readonly', []))
        pre, post = t['meta']['preBalances'], t['meta']['postBalances']
        tip = sum(max(0, post[a] - pre[a]) for a, kk in enumerate(keys[:len(pre)]) if kk in JITO)
        return dict(pos=k, payer=keys[0], fee=t['meta']['fee'], jito_tip=tip, dontfront=any(str(kk).startswith('jitodontfront') for kk in keys), err=t['meta']['err'] is not None)
    r['f'], r['v'], r['b'] = info(r['front']), info(r['victim']), info(r['back'])
    if r['f'] and r['v'] and r['b']: r['consecutive'] = (r['v']['pos'] == r['f']['pos'] + 1 and r['b']['pos'] == r['v']['pos'] + 1)
    out.append(r)
    if (n + 1) % 10 == 0: print('블록', n + 1, '/', len(picks), flush=True)
json.dump(out, open(OUTJ, 'w'), ensure_ascii=False, indent=1)
ok = [r for r in out if r.get('f') and r.get('v') and r.get('b')]
print(f'\n열린 블록 {len(ok)} / {len(out)}')
if ok:
    print(f" 세 거래 정확히 연달아 {sum(r['consecutive'] for r in ok)}/{len(ok)}")
    print(f" 앞다리 Jito 팁 {sum(r['f']['jito_tip'] > 0 for r in ok)} · 뒷다리 Jito 팁 {sum(r['b']['jito_tip'] > 0 for r in ok)} · 둘 중 하나 {sum((r['f']['jito_tip'] > 0) or (r['b']['jito_tip'] > 0) for r in ok)} · 피해자 Jito 팁 {sum(r['v']['jito_tip'] > 0 for r in ok)}")
    print(f" 피해자 jitodontfront {sum(r['v']['dontfront'] for r in ok)} · 그중 연달아 감싸임 {sum(r['v']['dontfront'] and r['consecutive'] for r in ok)}")
    print(f" 앞·뒤 서명자 같음 {sum(r['f']['payer'] == r['b']['payer'] for r in ok)} · 블록 안 거래 수 중앙 {sorted(r['n_txs'] for r in ok)[len(ok)//2]} · 앞다리 순번 중앙 {sorted(r['f']['pos'] for r in ok)[len(ok)//2]}")
