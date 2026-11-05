"""以前のランダム配置の街 (city-random-textures) の意匠で、今のタイル方式のテクスチャを作る

  python3 1_layout.py          # 敷地・建物の配置 (元の 2 倍の 4096 で作る)
  python3 2_textures_tile.py   # 屋根・地面・壁の色と、city_bake.py の入力 (mask は 2048、top / bottom は 4 倍の 8192)
  python3 build.py             # city_bake.py を --mirror で回し、鏡に映して 4096 × 4096 の繰り返しにしてタイルに分ける

元のマップは「ミラーで繰り返す」前提なので、元 / 左右反転 / 上下反転 / 両方 を並べた 4096 × 4096 を
そのまま繰り返してつながるマップにし、コア 2048 の 4 タイル (0_0 〜 1_1) に分ける。
city_bake.py は鏡のつながりで 2048 のまま計算し (距離も円錐も鏡に映して正しい)、出力を鏡に映して並べる。
"""
import os, subprocess, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BAKE = os.path.join(HERE, '..', '..', 'tools', 'city_bake.py')
CORE, MARGIN = 2048, 192
OUT = os.path.join(HERE, '..', '..', 'textures_random')
for i, a in enumerate(sys.argv[1:]):
    if a == '--bake': BAKE = sys.argv[i + 2]
    if a == '--out': OUT = sys.argv[i + 2]

def mir(a):
    top = np.concatenate([a, a[:, ::-1]], axis=1)
    return np.concatenate([top, top[::-1]], axis=0)
subprocess.check_call([sys.executable, BAKE, '--top', 'input/top4x.png', '--mask', 'input/mask.png',
                       '--bottom', 'input/bottom4x.png', '--roof', 'input/roof_color.png',
                       '--out', 'baked', '--mirror'])
L = lambda f: mir(np.array(Image.open(f)))
B = 'baked/'
# 地面:city_bake の wall_mask (輪郭より 1.5 テクセル内側) の範囲に壁の色を置く
ground = np.where((L(B + 'wall_mask.png') > 127)[..., None], L('input/wall_color.png'), L('input/ground_color.png')).astype(np.uint8)
tex = {'data': np.dstack([L(B + 'data_R.png'), L(B + 'data_G.png'), L(B + 'data_B.png')]),
       'roof': L(B + 'roof_RGB.png'), 'ground': ground, 'cone': L(B + 'cone.png'), 'outline': L(B + 'outline.png')}
os.makedirs(OUT + '/map', exist_ok=True)
for k, a in tex.items():
    Image.fromarray(a.astype(np.uint8)).save(f'{OUT}/map/map_{k}.png')
S = CORE + 2 * MARGIN
def cut(img, ox, oy, s, f=1):
    ys = np.arange(oy // f, (oy + s) // f) % img.shape[0]; xs = np.arange(ox // f, (ox + s) // f) % img.shape[1]
    return img[np.ix_(ys, xs)]
for j in range(2):
    for i in range(2):
        n = f'{i}_{j}'
        for k, a in tex.items():
            f = 2 if k == 'cone' else 1
            Image.fromarray(cut(a, i * CORE - MARGIN, j * CORE - MARGIN, S, f).astype(np.uint8)).save(f'{OUT}/tile{n}_{k}.png')
print('出力:', os.path.abspath(OUT))
