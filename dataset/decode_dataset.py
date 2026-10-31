"""Decode the released dataset (Hugging Face Lioba/solana_sandwich_attack_dataset, data_v3): download each part, verify sha256, decode the binary records into a structured numpy array (rec_XXXX.npy) plus key tables (keys_bot/pool/mint/wallet2.npy), then delete the part.
usage: decode_dataset.py MANIFEST.tsv OUT_DIR"""
import sys, os, struct, glob, hashlib, subprocess
import numpy as np
MAN, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True); TMP = f'{OUT}/tmp'; os.makedirs(TMP, exist_ok=True)
URL = 'https://huggingface.co/datasets/Lioba/solana_sandwich_attack_dataset/resolve/main/data_v3'
man = [l.rstrip('\n').split('\t') for l in open(MAN)][1:]
parts = [(f'{TMP}/{n}', n, h) for n, b, h in man]
HDR = struct.Struct('<BBHIIHBBBB'); F5 = struct.Struct('<5d')
dt = np.dtype([('n_front', 'u1'), ('n_back', 'u1'), ('n_victims', 'u2'), ('front_slot', 'u4'), ('back_slot', 'u4'), ('day', 'u2'), ('type', 'u1'), ('flags', 'u1'), ('program', 'u1'),
               ('bot', 'u4'), ('pool', 'u4'), ('mint_in', 'u4'), ('mint_out', 'u4'), ('back_wallet', 'i4'),
               ('fa_in', 'f8'), ('fa_out', 'f8'), ('ba_in', 'f8'), ('ba_out', 'f8'), ('profit', 'f8'),
               ('front_last_off', 'i2'), ('front_first_pos', 'u2'), ('back_first_off', 'i2'), ('back_last_off', 'i2'),
               ('vic_min_off', 'i2'), ('vic_max_off', 'i2'), ('vic_first_pos', 'u2')])
POS = np.dtype([('off', '<i2'), ('pos', '<u2')])
# 키 → 번호(부분 사이 공유 · 끝에 키 표 저장)
keymaps = {k: {} for k in ('bot', 'pool', 'mint', 'wallet2')}
kmf = f'{OUT}/keys_progress.npz'
def kid(m, b):
    v = m.get(b)
    if v is None: v = len(m); m[b] = v
    return v
for p, name, sha in parts:
    pn = int(name[-8:-4]); outp = f'{OUT}/rec_{pn:04d}.npy'
    for _ in range(3):
        subprocess.run(['curl', '-sfL', '--retry', '3', '-o', p, f'{URL}/{name}'], check=False)
        buf = open(p, 'rb').read() if os.path.exists(p) else b''
        if hashlib.sha256(buf).hexdigest() == sha: break
    else: raise SystemExit(f'sha 불일치 {name}')
    os.remove(p); n = len(buf); i = 0; rows = []
    while i < n:
        nf, nb, nv, fs, bs, day, ty, fl, prog, _ = HDR.unpack_from(buf, i); j = i + 18
        bot = buf[j:j + 32]; pool = buf[j + 32:j + 64]; mi = buf[j + 64:j + 96]; mo = buf[j + 96:j + 128]; j += 128
        bw = -1
        if fl & 2: bw = kid(keymaps['wallet2'], buf[j:j + 32]); j += 32
        fa_in, fa_out, ba_in, ba_out, prof = F5.unpack_from(buf, j); j += 40
        ns = nf + nb + nv; j += 64 * ns
        pa = np.frombuffer(buf, dtype=POS, count=ns, offset=j); j += 4 * ns
        off = pa['off']; pos = pa['pos']
        fo = off[:nf]; bo = off[nf:nf + nb]; vo = off[nf + nb:]; vp = pos[nf + nb:]
        rows.append((nf, nb, nv, fs, bs, day, ty, fl, prog, kid(keymaps['bot'], bot), kid(keymaps['pool'], pool), kid(keymaps['mint'], mi), kid(keymaps['mint'], mo), bw,
                     fa_in, fa_out, ba_in, ba_out, prof,
                     int(fo.max()) if nf else 0, int(pos[0]) if nf else 0, int(bo.min()) if nb else 0, int(bo.max()) if nb else 0,
                     int(vo.min()) if nv else 0, int(vo.max()) if nv else 0, int(vp[0]) if nv else 0))
        i = j
    a = np.array(rows, dtype=dt); np.save(outp, a)
    print(f'part {pn:04d} · 기록 {len(a):,} · 봇 {len(keymaps["bot"]):,} · 풀 {len(keymaps["pool"]):,} · 민트 {len(keymaps["mint"]):,}', flush=True)
for k, m in keymaps.items():
    ks = np.frombuffer(b''.join(sorted(m, key=m.get)), dtype='S32') if m else np.zeros(0, 'S32')
    np.save(f'{OUT}/keys_{k}.npy', ks)
print('끝 · 키 표 저장', {k: len(m) for k, m in keymaps.items()})
