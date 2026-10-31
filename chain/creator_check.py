"""Creation-slot front legs: is the bot the token creator? For sampled bonding-curve records within two slots of creation, fetch the curve history before the front leg from a public RPC node, identify the signer of the curve's first transaction, and compare with the front-leg signer (Section 3).
usage: creator_check.py CURVE_AGE.json OUT.json"""
import sys, json, time, urllib.request
RPC = 'https://api.mainnet-beta.solana.com'
def rpc(m, p):
    for k in range(8):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            if 'result' in r: return r['result']
        except Exception: pass
        time.sleep(2 * (k + 1))
    return None
R = [r for r in json.load(open(sys.argv[1])) if r['prog'] == 1 and r.get('age_slots') is not None and r['age_slots'] <= 2]
out = []
for n, r in enumerate(R):
    if not r.get('bot'):
        ft = rpc('getTransaction', [r['front_sig'], {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        fk = (ft or {}).get('transaction', {}).get('message', {}).get('accountKeys', [])
        r['bot'] = next((k['pubkey'] for k in fk if k.get('signer')), None)
    sigs = rpc('getSignaturesForAddress', [r['pool'], {"before": r['front_sig'], "limit": 1000}]) or []
    rec = dict(front_slot=r['front_slot'], age=r['age_slots'], n_before=r['n_before'], bot4=(r.get('bot') or '????')[:4])
    if r['n_before'] == 0 or not sigs:
        rec['front_is_first'] = True; rec['creator_is_bot'] = None
    else:
        first = sigs[-1]['signature']
        t = rpc('getTransaction', [first, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        keys = (t or {}).get('transaction', {}).get('message', {}).get('accountKeys', [])
        signer = next((k['pubkey'] for k in keys if k.get('signer')), None)
        rec['front_is_first'] = False; rec['creator4'] = (signer or '????')[:4]; rec['creator_is_bot'] = (signer == r.get('bot')) if signer and r.get('bot') else None
    out.append(rec); time.sleep(0.3)
    if (n + 1) % 25 == 0: print(n + 1, '/', len(R), flush=True)
json.dump(out, open(sys.argv[2], 'w'), indent=0)
k = [o for o in out if o['creator_is_bot'] is not None]
print(f"≤2슬롯 표본 {len(out)} · 앞다리 = 커브 첫 tx(봇이 곧 창작자?) {sum(o['front_is_first'] for o in out)} · 창작자 확인 {len(k)} 중 봇 = 창작자 {sum(o['creator_is_bot'] for o in k)}")
print('DONE')
