"""Aggregate the decoded dataset: per-program counts, per-quarter composition, slot gaps, victims, per-bot and per-pool statistics (Sections 3 of the note).
usage: aggregate.py DEC_DIR OUT.json"""
import sys, glob, json, datetime, collections
import numpy as np
DEC, OUTJ = sys.argv[1], sys.argv[2]
A = np.concatenate([np.load(f) for f in sorted(glob.glob(f'{DEC}/rec_*.npy'))])
km = np.load(f'{DEC}/keys_mint.npy')
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    b = n.to_bytes(32, 'big'); return b
WSOL = b58dec('So11111111111111111111111111111111111111112'); USDC = b58dec('EPjFWdd5AufqSSqeM2qofmpZnoUmrPkTtHbxYTXK3EL7')
idx = {bytes(k): i for i, k in enumerate(km)}
sol_id = idx.get(WSOL, -1); usdc_id = idx.get(USDC, -1)
PROG = {0: 'raydium_v4', 1: 'pump_amm', 2: 'pump_amm_v2', 3: 'raydium_cpmm', 4: 'raydium_launchpad_cpmm', 5: 'raydium_clmm', 6: 'orca_whirlpool', 7: 'meteora_dlmm_v2', 8: 'obric_v2', 9: 'solfi'}
TYPE = {0: 'tight', 1: 'within_slot_wide', 2: 'cross_slot_wide'}
N = len(A); out = {'n': int(N), 'sol_mint_id': int(sol_id), 'usdc_mint_id': int(usdc_id)}
print(f'기록 {N:,} · 봇 {len(np.unique(A["bot"])):,} · 풀 {len(np.unique(A["pool"])):,} · wSOL id {sol_id}')
solin = A['mint_in'] == sol_id
# A
rowsA = {}
for p in sorted(np.unique(A['program'])):
    m = A['program'] == p; ms = m & solin
    rowsA[PROG.get(int(p), str(p))] = dict(n=int(m.sum()), share=float(m.mean()), bots=int(len(np.unique(A['bot'][m]))), pools=int(len(np.unique(A['pool'][m]))),
        sol_front_share=float(ms.sum() / max(m.sum(), 1)), profit_sol_sum=float(A['profit'][ms].sum()), profit_sol_med=float(np.median(A['profit'][ms])) if ms.any() else None,
        tight=float((A['type'][m] == 0).mean()), within=float((A['type'][m] == 1).mean()), cross=float((A['type'][m] == 2).mean()),
        evasive=float(((A['flags'][m] & 2) > 0).mean()), profitable=float(((A['flags'][m] & 1) > 0).mean()))
out['by_program'] = rowsA
print('\n[A] 프로그램별')
for k, v in sorted(rowsA.items(), key=lambda kv: -kv[1]['n']):
    print(f"  {k:24s} n {v['n']:>11,} ({v['share']:.1%}) · 봇 {v['bots']:>5,} · 풀 {v['pools']:>9,} · 앞다리 SOL {v['sol_front_share']:.0%} · 수익 SOL 합 {v['profit_sol_sum']:>12,.0f} · tight/within/cross {v['tight']:.0%}/{v['within']:.0%}/{v['cross']:.0%} · evasive {v['evasive']:.1%}")
# B 분기별
d0 = datetime.date(2023, 1, 1)
q = np.array([(d0 + datetime.timedelta(days=int(x))).strftime('%Y') + 'Q' + str((d0 + datetime.timedelta(days=int(x))).month // 4 + 1) for x in range(int(A['day'].max()) + 1)])
qa = q[A['day']]
pump = np.isin(A['program'], [1, 2])
out['by_quarter'] = {}
print('\n[B] 분기별(전체 · pump 계열 몫 · cross 몫)')
for qq in sorted(set(qa.tolist())):
    m = qa == qq
    r = dict(n=int(m.sum()), pump_share=float(pump[m].mean()), cross=float((A['type'][m] == 2).mean()), tight=float((A['type'][m] == 0).mean()), bots=int(len(np.unique(A['bot'][m]))))
    out['by_quarter'][qq] = r
    print(f"  {qq} n {r['n']:>10,} · pump 계열 {r['pump_share']:.0%} · tight {r['tight']:.0%} · cross {r['cross']:.0%} · 봇 {r['bots']:,}")
# C 간격 · 피해자
gap = (A['back_slot'].astype(np.int64) - A['front_slot'].astype(np.int64))
def dist(x, edges):
    return {f'{lo}-{hi}': float(((x >= lo) & (x <= hi)).mean()) for lo, hi in edges}
out['gap_all'] = dist(gap, [(0, 0), (1, 1), (2, 2), (3, 4), (5, 8), (9, 10**9)]); out['gap_pump'] = dist(gap[pump], [(0, 0), (1, 1), (2, 2), (3, 4), (5, 8), (9, 10**9)])
out['victims_pump'] = dist(A['n_victims'][pump].astype(np.int64), [(1, 1), (2, 2), (3, 5), (6, 10), (11, 10**9)])
print('\n[C] 앞→뒤 슬롯 간격 전체', {k: f'{v:.0%}' for k, v in out['gap_all'].items()}, '\n    pump 계열', {k: f'{v:.0%}' for k, v in out['gap_pump'].items()}, '\n    pump 피해자 수', {k: f'{v:.0%}' for k, v in out['victims_pump'].items()})
# D pump 계열 봇
P = A[pump]
if len(P):
    bots, inv, cnt = np.unique(P['bot'], return_inverse=True, return_counts=True)
    bp = np.unique(P['bot'].astype(np.int64) * (1 << 32) + P['pool'].astype(np.int64)); npools = np.bincount(np.searchsorted(bots, (bp >> 32).astype(P['bot'].dtype)), minlength=len(bots))
    top = np.argsort(-cnt)
    out['pump_bots'] = dict(n_bots=int(len(bots)), rec_per_bot_q=[float(x) for x in np.quantile(cnt, [.1, .5, .9, .99])], top10_share=float(cnt[top[:10]].sum() / cnt.sum()), top100_share=float(cnt[top[:100]].sum() / cnt.sum()))
    if npools is not None:
        rpp = cnt / np.maximum(npools, 1)
        out['pump_bots'].update(pools_per_bot_q=[float(x) for x in np.quantile(npools, [.1, .5, .9])], rec_per_pool_per_bot_q=[float(x) for x in np.quantile(rpp, [.1, .5, .9])],
            rec_weighted_rec_per_pool_med=float(np.median(np.repeat(rpp, cnt))))
    print('\n[D] pump 계열 봇', out['pump_bots'])
    # E 풀 생애(자료 안 첫 기록 대비)
    pools, pinv = np.unique(P['pool'], return_inverse=True)
    first = np.full(len(pools), np.iinfo(np.int64).max, np.int64); last = np.zeros(len(pools), np.int64)
    np.minimum.at(first, pinv, P['front_slot'].astype(np.int64)); np.maximum.at(last, pinv, P['front_slot'].astype(np.int64))
    age = P['front_slot'].astype(np.int64) - first[pinv]
    pc = np.bincount(pinv)
    out['pump_pool_age'] = dict(n_pools=int(len(pools)), rec_per_pool_q=[float(x) for x in np.quantile(pc, [.1, .5, .9, .99])],
        pool_span_slots_q=[float(x) for x in np.quantile(last - first, [.1, .5, .9])],
        rec_within_first={str(s): float((age <= s).mean()) for s in (0, 10, 75, 150, 750, 3000, 9000, 150000)})
    print('[E] pump 계열 풀(자료 안 첫 기록 대비)', out['pump_pool_age'])
    # F 방향
    fbuy = P['mint_in'] == sol_id
    out['pump_front_buys_token'] = float(fbuy.mean())
    print('[F] pump 계열 앞다리가 SOL→토큰(산 뒤 판다) 몫', f"{fbuy.mean():.1%}")
json.dump(out, open(OUTJ, 'w'), ensure_ascii=False, indent=1)
print('저장', OUTJ)
