"""For sampled tight blocks: Jito tips in the transactions adjacent to the triple, and tip / jitodontfront counts for the whole block, versus random blocks (Section 6).
usage: neighbor_tips.py TIGHT.json RANDOM_SLOTS.json OUT.json"""
import sys, json, time, urllib.request, random
TJ, RJ, OUTJ = sys.argv[1:4]
JITO = {'96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5', 'HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe', 'Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY', 'ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49',
        'DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh', 'ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt', 'DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL', '3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT'}
RPC = 'https://api.mainnet-beta.solana.com'
def rpc(m, p):
    for k in range(8):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=90).read())
            if 'result' in r: return r['result']
            if r.get('error', {}).get('code') in (-32009, -32007, -32004): return None
        except Exception: pass
        time.sleep(2 * (k + 1))
    return None
def txinfo(t):
    keys = t['transaction']['message']['accountKeys'] + t['meta'].get('loadedAddresses', {}).get('writable', []) + t['meta'].get('loadedAddresses', {}).get('readonly', [])
    pre, post = t['meta']['preBalances'], t['meta']['postBalances']
    tip = sum(max(0, post[a] - pre[a]) for a, kk in enumerate(keys[:len(pre)]) if kk in JITO)
    return dict(sig=t['transaction']['signatures'][0], payer=keys[0], tip=tip, dontfront=any(str(kk).startswith('jitodontfront') for kk in keys), err=t['meta']['err'] is not None)
def block_scan(slot):
    b = rpc('getBlock', [slot, {"encoding": "json", "transactionDetails": "full", "maxSupportedTransactionVersion": 0, "rewards": True}])
    if not b: return None
    infos = [txinfo(t) for t in b['transactions']]
    fee = [x['pubkey'] for x in b.get('rewards', []) if x.get('rewardType') == 'Fee']
    return dict(n=len(infos), n_tip=sum(i['tip'] > 0 for i in infos), tip_sum=sum(i['tip'] for i in infos), n_dontfront=sum(i['dontfront'] for i in infos), leader=fee[0] if fee else None, infos=infos)
T = json.load(open(TJ)); out = {'tight': [], 'random': []}
for n, r in enumerate(T):
    s = block_scan(r['slot'])
    if not s: out['tight'].append(dict(slot=r['slot'], block=None)); continue
    pos = {i['sig']: k for k, i in enumerate(s['infos'])}
    f, v, b = pos.get(r['front']), pos.get(r['victim']), pos.get(r['back'])
    nb = []
    if f is not None and b is not None:
        for k in range(max(0, f - 3), min(s['n'], b + 4)):
            if k in (f, v, b): continue
            i = s['infos'][k]; nb.append(dict(off=k - f, tip=i['tip'], payer4=i['payer'][:4], same_payer_as_bot=i['payer'] == s['infos'][f]['payer'], dontfront=i['dontfront']))
    out['tight'].append(dict(slot=r['slot'], leader4=(s['leader'] or '')[:4], n=s['n'], n_tip=s['n_tip'], tip_sum=s['tip_sum'], n_dontfront=s['n_dontfront'], f=f, v=v, b=b, neighbors=nb))
    print('tight', n + 1, '/', len(T), 'block tips', s['n_tip'], flush=True)
R = json.load(open(RJ)); rs = [int(k) for k, val in R['random'].items() if val not in (None, 'SKIPPED', 'NOFEE')]
rng = random.Random(3); rs = rng.sample(rs, 25)
for n, slot in enumerate(rs):
    s = block_scan(slot)
    if not s: out['random'].append(dict(slot=slot, block=None)); continue
    out['random'].append(dict(slot=slot, leader4=(s['leader'] or '')[:4], n=s['n'], n_tip=s['n_tip'], tip_sum=s['tip_sum'], n_dontfront=s['n_dontfront']))
    print('random', n + 1, '/', len(rs), 'block tips', s['n_tip'], flush=True)
json.dump(out, open(OUTJ, 'w'), indent=0)
tt = [x for x in out['tight'] if x.get('n')]; rr = [x for x in out['random'] if x.get('n')]
import statistics as st
print(f"\nV1 tight 블록 {len(tt)}: 블록당 팁 tx 중앙 {st.median([x['n_tip'] for x in tt]):.0f} (팁 tx 0 인 블록 {sum(x['n_tip']==0 for x in tt)}) · 팁 tx 몫 중앙 {st.median([x['n_tip']/x['n'] for x in tt]):.2%} · dontfront 몫 중앙 {st.median([x['n_dontfront']/x['n'] for x in tt]):.1%}")
print(f"무작위 블록 {len(rr)}: 블록당 팁 tx 중앙 {st.median([x['n_tip'] for x in rr]):.0f} (팁 0 블록 {sum(x['n_tip']==0 for x in rr)}) · 팁 tx 몫 중앙 {st.median([x['n_tip']/x['n'] for x in rr]):.2%} · dontfront 몫 중앙 {st.median([x['n_dontfront']/x['n'] for x in rr]):.1%}")
nbs = [nb for x in tt for nb in x['neighbors']]
print(f"이웃 tx(±3 · 세 거래 제외) {len(nbs)}: 팁 있음 {sum(n['tip']>0 for n in nbs)} · 봇과 같은 서명자 {sum(n['same_payer_as_bot'] for n in nbs)} · 바로 앞(off −1) 팁 {sum(n['tip']>0 for n in nbs if n['off']==-1)} · 바로 뒤(뒷다리+1) 팁 {sum(n['tip']>0 for n in nbs if n['off']==3)}")
print('DONE')
