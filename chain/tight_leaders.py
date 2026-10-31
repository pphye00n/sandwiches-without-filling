"""(공개 RPC) tight 표본의 블록 리더 = 블록 수수료 보상(rewardType 'Fee') 받은 주소. tight_slot_probe.py 산출에 'leader' 칸을 붙인다(§6 · 10-31 에 인라인으로 돌린 것을 코드로).
usage: tight_leaders.py TIGHT_PROBE.json"""
import sys, json, time, urllib.request, collections
RPC = 'https://api.mainnet-beta.solana.com'
def rpc(m, p):
    for k in range(6):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if 'result' in r: return r['result']
        except Exception: pass
        time.sleep(2 * (k + 1))
    return None
R = json.load(open(sys.argv[1]))
for r in R:
    b = rpc('getBlock', [r['slot'], {"transactionDetails": "none", "rewards": True, "maxSupportedTransactionVersion": 0}])
    fee = [x['pubkey'] for x in (b or {}).get('rewards', []) if x.get('rewardType') == 'Fee']
    r['leader'] = fee[0] if fee else None
json.dump(R, open(sys.argv[1], 'w'), ensure_ascii=False, indent=1)
c = collections.Counter(r['leader'] for r in R); print('리더 앎', sum(1 for r in R if r['leader']), '/', len(R), '· 서로 다른 리더', len([k for k in c if k]), '· 위:', [((k or 'None')[:6], v) for k, v in c.most_common(5)])
