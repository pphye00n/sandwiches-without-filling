"""Per-program bot and pool statistics from the decoded dataset.
usage: per_program.py DEC_DIR"""
import sys, glob, datetime
import numpy as np
A = np.concatenate([np.load(f) for f in sorted(glob.glob(f'{sys.argv[1]}/rec_*.npy'))])
d0 = datetime.date(2023, 1, 1)
for prog, nm in ((1, '본딩커브(그들 표기 pump_amm)'), (2, 'PumpSwap AMM(그들 표기 pump_amm_v2)')):
    P = A[A['program'] == prog]
    bots, cnt = np.unique(P['bot'], return_counts=True)
    bp = np.unique(P['bot'].astype(np.int64) * (1 << 32) + P['pool'].astype(np.int64))
    npools = np.bincount(np.searchsorted(bots, (bp >> 32).astype(P['bot'].dtype)), minlength=len(bots))
    rpp = cnt / np.maximum(npools, 1); rw = np.repeat(rpp, cnt)
    pools, pc = np.unique(P['pool'], return_counts=True)
    gap = P['back_slot'].astype(np.int64) - P['front_slot'].astype(np.int64)
    days = [d0 + datetime.timedelta(days=int(x)) for x in (P['day'].min(), P['day'].max())]
    print(f"== {nm}: 기록 {len(P):,} · 기간 {days[0]}~{days[1]} · 봇 {len(bots):,} · 풀 {len(pools):,} · 풀당 기록 중앙 {np.median(pc):.0f} p90 {np.quantile(pc, .9):.0f} p99 {np.quantile(pc, .99):.0f} · 기록 가중 풀당 기록 중앙 {np.median(np.repeat(pc, pc)):.0f}")
    print(f"   봇당 풀 수 중앙 {np.median(npools):.0f} p90 {np.quantile(npools, .9):.0f} · 봇이 같은 풀 친 횟수(기록 가중) 중앙 {np.median(rw):.2f} p90 {np.quantile(rw, .9):.2f} · 상위 100 봇 몫 {np.sort(cnt)[::-1][:100].sum() / cnt.sum():.0%}")
    print(f"   tight {np.mean(P['type'] == 0):.0%} · 블록 걸침 {np.mean(P['type'] == 2):.0%} · 앞→뒤 슬롯 중앙 {np.median(gap):.0f} · 피해자 ≥2 {np.mean(P['n_victims'] >= 2):.0%} · 수익 표시 {np.mean((P['flags'] & 1) > 0):.0%} · 수익 SOL 합 {P['profit'][P['mint_in'] == 0].sum():,.0f}")
