"""タイル A / B を 1 枚ずつ ASTC 4x4 で圧縮 → 復元 (デモの比較用)。品質は引数 (既定 MEDIUM)"""
import sys, numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from astc_rt import roundtrip
import astc_encoder as A
from PIL import Image
Q = getattr(A.ASTCQualityPreset, sys.argv[1] if len(sys.argv) > 1 else 'MEDIUM')
for t in 'AB':
    d = np.array(Image.open(f'out/tile{t}_data.png').convert('RGB')); c = np.array(Image.open(f'out/tile{t}_cone.png').convert('L'))
    dd = roundtrip(np.dstack([d, np.full(d.shape[:2], 255, np.uint8)]), Q)[0][..., :3]
    cd = roundtrip(np.dstack([c, c, c, np.full(c.shape, 255, np.uint8)]), Q)[0][..., 0]
    e = dd.astype(int) - d
    print(t, 'R±', np.abs(e[..., 0]).max(), 'G±', np.abs(e[..., 1]).max(), 'B 超過', e[..., 2].max(), 'cone 超過', (cd.astype(int) - c).max())
    Image.fromarray(dd).save(f'out/astc{t}_data.png'); Image.fromarray(cd).save(f'out/astc{t}_cone.png')
# 継ぎ目:A の右マージンと B の左側コア (同じ場所) が同じ値に戻るか
a = np.array(Image.open('out/astcA_data.png')).astype(int); b = np.array(Image.open('out/astcB_data.png')).astype(int)
M = 192; C = 1024
print('A と B の重なりの食い違い', (a[:, C:C + 2 * M] != b[:, 0:2 * M]).any(-1).sum())
