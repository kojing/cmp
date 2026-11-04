"""city_bake.py の出力 (A/B の街) を、シェーダーがそのまま読む形に詰める

  python3 gen_ab.py 192
  python3 ../tools/city_bake.py --top out/input/top4x.png --mask out/input/mask.png --bottom out/input/bottom4x.png \
          --roof out/input/roof_color.png --ground out/map_ground.png --out out/baked --wrap --core 1024 --margin 192
  python3 pack_ab.py [out/baked] [出力先]

出力先 (既定 ../textures):tile{A,B}_{data,roof,ground,cone,outline}.png と map/
out/ には、デモが使う map_*.png (roof の α に outline を入れたもの) と、ASTC 4x4 で圧縮 → 復元した astc{A,B}_*.png も作る
"""
import os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
BK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'out', 'baked')
DST = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, '..', 'textures')
OUT = os.path.join(HERE, 'out')
L = lambda f: np.array(Image.open(os.path.join(BK, f)))
def rgb(n): return np.dstack([L(n + 'data_R.png'), L(n + 'data_G.png'), L(n + 'data_B.png')])
os.makedirs(os.path.join(DST, 'map'), exist_ok=True)
sv = lambda a, *p: Image.fromarray(a.astype(np.uint8)).save(os.path.join(*p))
sv(rgb(''), DST, 'map', 'map_data.png'); sv(L('roof_RGB.png'), DST, 'map', 'map_roof.png')
sv(L('ground_RGB.png'), DST, 'map', 'map_ground.png'); sv(L('cone.png'), DST, 'map', 'map_cone.png')
sv(L('outline.png'), DST, 'map', 'map_outline.png')
# デモ用 (roof の α に outline)
sv(rgb(''), OUT, 'map_data.png'); sv(np.dstack([L('roof_RGB.png'), L('outline.png')]), OUT, 'map_roof.png')
sv(L('ground_RGB.png'), OUT, 'map_ground.png'); sv(L('cone.png'), OUT, 'map_cone.png')
try:
    sys.path.insert(0, HERE); from astc_rt import roundtrip; import astc_encoder as A
except ImportError:
    roundtrip = None; print('astc-encoder-py がないので ASTC の復元版は作りません')
def astc(a):
    g = a.ndim == 2
    x = np.dstack([a, a, a] if g else [a[..., :3]]); x = np.dstack([x, np.full(x.shape[:2], 255, np.uint8)])
    d, _ = roundtrip(x, A.ASTCQualityPreset.MEDIUM)
    return d[..., 0] if g else d[..., :3]
for name, ij in (('A', '0_0'), ('B', '1_0')):
    T = 'tiles/' + ij + '_'
    tex = {'data': rgb(T), 'roof': L(T + 'roof_RGB.png'), 'ground': L(T + 'ground_RGB.png'), 'cone': L(T + 'cone.png'), 'outline': L(T + 'outline.png')}
    for k, a in tex.items():
        sv(a, DST, f'tile{name}_{k}.png')
        if roundtrip: sv(astc(a), OUT, f'astc{name}_{k}.png')
print('出力:', os.path.abspath(DST))
