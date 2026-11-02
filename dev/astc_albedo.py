"""roof (RGBA) / ground (RGB) をタイルごとに ASTC 4x4 で圧縮 → 復元し、輪郭 (α) と色の誤差を測る"""
import sys, numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from astc_rt import roundtrip
import astc_encoder as A
from PIL import Image
Q = getattr(A.ASTCQualityPreset, sys.argv[1] if len(sys.argv) > 1 else 'MEDIUM')
for t in 'AB':
    r = np.array(Image.open(f'out/tile{t}_roof.png').convert('RGBA'))
    g = np.array(Image.open(f'out/tile{t}_ground.png').convert('RGB'))
    rd = roundtrip(r, Q)[0]
    gd = roundtrip(np.dstack([g, np.full(g.shape[:2], 255, np.uint8)]), Q)[0][..., :3]
    a0 = r[..., 3].astype(int); a1 = rd[..., 3].astype(int)
    band = (a0 > 0) & (a0 < 255)
    ea = np.abs(a1 - a0)[band]
    # α = 0.5 の輪郭がずれる量 (テクセル) = α の誤差 ÷ 傾き (1 テクセルあたり 63.75 コード)
    print(t, 'roof α 誤差 (輪郭付近) 平均', round(ea.mean(), 2), '99%', np.percentile(ea, 99), '最大', ea.max(),
          '→ 輪郭のずれ 最大', round(ea.max() / 63.75, 3), 'テクセル')
    # 屋根の内側と外側の判定が入れ替わったテクセル
    flip = ((a0 >= 128) != (a1 >= 128)).sum()
    print('  α 0.5 をまたいで判定が変わったテクセル', flip)
    ec = np.abs(rd[..., :3].astype(int) - r[..., :3]).max(-1)
    print('  roof RGB 誤差 平均', round(ec.mean(), 2), '最大', ec.max())
    eg = np.abs(gd.astype(int) - g).max(-1)
    print('  ground 誤差 平均', round(eg.mean(), 2), '99%', np.percentile(eg, 99), '最大', eg.max())
    Image.fromarray(rd).save(f'out/astc{t}_roof.png'); Image.fromarray(gd).save(f'out/astc{t}_ground.png')
