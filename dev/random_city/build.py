"""以前のランダム配置の街 (city-random-textures) の意匠で、今のタイル方式のテクスチャを作る

  python3 1_layout.py          # 敷地・建物の配置 (元の 2 倍の 4096 で作る)
  python3 2_textures_tile.py   # 屋根・地面・壁の色と、city_bake.py の入力 (2048 に縮める)
  python3 build.py             # ミラーで 4096 × 4096 の繰り返しにして、city_bake.py でタイルに分ける

元のマップは「ミラーで繰り返す」前提なので、元 / 左右反転 / 上下反転 / 両方 を並べた 4096 × 4096 を
そのまま繰り返してつながるマップにし、コア 2048 の 4 タイル (0_0 〜 1_1) に分ける。
"""
import os, subprocess, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
BAKE = os.path.join(HERE, '..', '..', 'tools', 'city_bake.py')
CORE, MARGIN = 2048, 192
OUT = os.path.join(HERE, '..', '..', 'textures_random')

def mir(a):
    top = np.concatenate([a, a[:, ::-1]], axis=1)
    return np.concatenate([top, top[::-1]], axis=0)
os.makedirs('input4096', exist_ok=True)
for f in ['mask', 'top', 'bottom', 'top2x', 'bottom2x', 'roof_color', 'ground_color', 'wall_color']:
    Image.fromarray(mir(np.array(Image.open(f'input/{f}.png')))).save(f'input4096/{f}.png')
subprocess.check_call([sys.executable, BAKE, '--top', 'input4096/top2x.png', '--mask', 'input4096/mask.png',
                       '--bottom', 'input4096/bottom2x.png', '--roof', 'input4096/roof_color.png',
                       '--out', 'baked', '--wrap', '--core', str(CORE), '--margin', str(MARGIN)])
L = lambda f: np.array(Image.open(f))
B = 'baked/'
# 地面:city_bake の wall_mask (輪郭より 1.5 テクセル内側) の範囲に壁の色を置く
ground = np.where((L(B + 'wall_mask.png') > 127)[..., None], L('input4096/wall_color.png'), L('input4096/ground_color.png')).astype(np.uint8)
os.makedirs(OUT + '/map', exist_ok=True)
Image.fromarray(np.dstack([L(B + 'data_R.png'), L(B + 'data_G.png'), L(B + 'data_B.png')])).save(OUT + '/map/map_data.png')
Image.fromarray(L(B + 'roof_RGB.png')).save(OUT + '/map/map_roof.png')
Image.fromarray(ground).save(OUT + '/map/map_ground.png')
Image.fromarray(L(B + 'cone.png')).save(OUT + '/map/map_cone.png')
Image.fromarray(L(B + 'outline.png')).save(OUT + '/map/map_outline.png')
S = CORE + 2 * MARGIN
def cut(img, ox, oy, s):
    ys = np.arange(oy, oy + s) % img.shape[0]; xs = np.arange(ox, ox + s) % img.shape[1]
    return img[np.ix_(ys, xs)]
for j in range(2):
    for i in range(2):
        n = f'{i}_{j}'; T = B + 'tiles/' + n + '_'
        Image.fromarray(np.dstack([L(T + 'data_R.png'), L(T + 'data_G.png'), L(T + 'data_B.png')])).save(f'{OUT}/tile{n}_data.png')
        Image.fromarray(L(T + 'roof_RGB.png')).save(f'{OUT}/tile{n}_roof.png')
        Image.fromarray(cut(ground, i * CORE - MARGIN, j * CORE - MARGIN, S)).save(f'{OUT}/tile{n}_ground.png')
        Image.fromarray(L(T + 'cone.png')).save(f'{OUT}/tile{n}_cone.png')
        Image.fromarray(L(T + 'outline.png')).save(f'{OUT}/tile{n}_outline.png')
print('出力:', os.path.abspath(OUT))
