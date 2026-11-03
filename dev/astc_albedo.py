"""roof (RGB) / ground (RGB) / outline (1 チャンネル) をタイルごとに ASTC 4x4 で圧縮 → 復元し、誤差を測る。
   輪郭を屋根の α に入れた場合 (前の方式) との比較もする。屋根の色には本番の絵を想定した細かい模様を足して測る。
   使い方:python3 astc_albedo.py [品質]   (dev/out/ のタイルを読む)"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from astc_rt import roundtrip
import astc_encoder as A
from PIL import Image
Q = getattr(A.ASTCQualityPreset, sys.argv[1] if len(sys.argv) > 1 else 'MEDIUM')
one = lambda a: np.dstack([a, a, a, np.full(a.shape, 255, np.uint8)])
rng = np.random.default_rng(0)
for t in 'AB':
    r = np.array(Image.open(f'out/tile{t}_roof.png').convert('RGBA'))
    g = np.array(Image.open(f'out/tile{t}_ground.png').convert('RGB'))
    rgb, a = r[..., :3], r[..., 3]
    band = (a > 0) & (a < 255)
    # 輪郭:1 チャンネルだけで圧縮 (今の方式)
    od = roundtrip(one(a), Q)[0][..., 0]
    e1 = np.abs(od.astype(int) - a)[band]
    # 比較:模様のある屋根の色の α に入れた場合 (前の方式)
    tex = np.clip(rgb.astype(int) + rng.normal(0, 18, rgb.shape), 0, 255).astype(np.uint8)
    e2 = np.abs(roundtrip(np.dstack([tex, a]), Q)[0][..., 3].astype(int) - a)[band]
    print(f'{t} 輪郭のずれ (1 テクセル = 63.75 コード)  1 チャンネル: 99% {np.percentile(e1, 99) / 63.75:.3f} 最大 {e1.max() / 63.75:.3f} テクセル'
          f' | 模様のある屋根の α: 99% {np.percentile(e2, 99) / 63.75:.3f} 最大 {e2.max() / 63.75:.3f} テクセル')
    rd = roundtrip(np.dstack([rgb, np.full(a.shape, 255, np.uint8)]), Q)[0][..., :3]
    gd = roundtrip(np.dstack([g, np.full(g.shape[:2], 255, np.uint8)]), Q)[0][..., :3]
    Image.fromarray(od).save(f'out/astc{t}_outline.png')
    Image.fromarray(np.dstack([rd, np.full(a.shape, 255, np.uint8)])).save(f'out/astc{t}_roof.png')
    Image.fromarray(gd).save(f'out/astc{t}_ground.png')
