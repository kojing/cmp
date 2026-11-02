"""
2 種類のタイル A / B が「A B A B …」と横につながる街のテクスチャを作る

  マップ全体は 横 2048 × 縦 1024 で、上下左右にそのまま周期的につながる (ミラーなし)。
  左半分 = タイル A、右半分 = タイル B (それぞれ 1024 × 1024)。
    横:A の右に B、B の右に A
    縦:A の上下は A、B の上下は B
  建物や道路はタイルの継ぎ目をまたぐように置いてある (継ぎ目の確認用)。

出力 (out/)
  map_data.png / map_roof.png / map_ground.png / map_cone.png : マップ全体 (デモが実行時に切り出す)
  tileA_*.png / tileB_*.png : マージン付きで切り出したタイル (片側 MARGIN、幅 1024 + 2 × MARGIN)

roof : α = 建物の輪郭 (符号付き距離 sd → α = 0.5 − sd/4、線形補間して 0.5 が輪郭)
data : R = 下端の高さ (0 / 56 = 高架 / 255 = 空き地)  G = 上端 (4 の倍数)  B = 境界までの距離 (2 / テクセル)
cone : u = k / (k + 0.1)、k = 自分より高い建物までの距離 (マップ幅 2048 を 1 とする) ÷ 高さの差 (G/255)。半分の解像度
"""
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt as edt
import os, sys

W, H, CORE = 2048, 1024, 1024
MARGIN = int(sys.argv[1]) if len(sys.argv) > 1 else 192
DIST_SCALE = 2
rng = np.random.default_rng(7)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)

Y, X = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5

def wrapd(a, p):           # 周期 p の差を -p/2..p/2 に
    return (a + p / 2) % p - p / 2

# ---------------- 道路 ----------------
VROADS = [(300, 24), (770, 18), (1350, 24), (1790, 18)]      # (x 中心, 半幅)
HROADS = [(190, 22), (690, 18)]
def curve(x):              # 高架道路の中心線 (横に周期 2048)
    t = 2 * np.pi * x / W
    return 470 + 150 * np.sin(t) + 45 * np.sin(2 * t + 1.0)
def curve_d(x):
    t = 2 * np.pi * x / W
    return (150 * np.cos(t) + 90 * np.cos(2 * t + 1.0)) * 2 * np.pi / W

dV = np.min([np.abs(wrapd(X - cx, W)) - hw for cx, hw in VROADS], axis=0)
dH = np.min([np.abs(wrapd(Y - cy, H)) - hw for cy, hw in HROADS], axis=0)
dC = np.abs(wrapd(Y - curve(X), H)) / np.sqrt(1 + curve_d(X) ** 2)   # 高架の中心からの距離
road = (dV <= 0) | (dH <= 0)
DECK_HW = 22
deck = dC <= DECK_HW
under = dC <= DECK_HW + 6                                         # 高架の下も道路
side = ((dV <= 12) | (dH <= 12) | (dC <= DECK_HW + 16)) & ~road & ~under   # 歩道

# ---------------- 建物 ----------------
LEVELS = np.array([32, 36, 40, 48, 64, 72, 80, 88, 96, 104, 112, 144, 160, 176, 192])
LW = np.array([3, 3, 3, 4, 4, 3, 3, 3, 2, 2, 2, 1.5, 1.2, 1, 0.8]); LW /= LW.sum()
blocked = road | under | side
occ = blocked.copy()
bid = np.full((H, W), -1, np.int32)
bld = []
def rect_mask(cx, cy, w, h, ang, pad=0.0):
    r = int(np.ceil(0.5 * np.hypot(w, h) + pad)) + 2
    ys = (np.arange(int(cy) - r, int(cy) + r) % H); xs = (np.arange(int(cx) - r, int(cx) + r) % W)
    yy, xx = np.meshgrid(np.arange(int(cy) - r, int(cy) + r) + 0.5 - cy, np.arange(int(cx) - r, int(cx) + r) + 0.5 - cx, indexing='ij')
    c, s = np.cos(ang), np.sin(ang)
    u = c * xx + s * yy; v = -s * xx + c * yy
    m = (np.abs(u) <= w / 2 + pad) & (np.abs(v) <= h / 2 + pad)
    return ys, xs, m, u, v
# 継ぎ目の確認用:タイルの継ぎ目 (x = 0, 1024 / y = 0) をまたぐ建物を先に置く
FORCED = [(1024, 600, 150, 90, 0.0, 176), (1024, 880, 120, 120, 0.35, 144), (0, 880, 130, 110, 0.0, 160),
          (560, 1024, 160, 100, 0.0, 112), (1560, 1024, 110, 140, -0.3, 144), (1024, 300, 90, 150, 0.0, 96)]
tries = 0
while tries < 40000:
    tries += 1
    if FORCED:
        cx, cy, w, h, ang, gf = FORCED.pop(0)
    else:
        gf = None
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        w, h = rng.uniform(40, 170), rng.uniform(40, 150)
        ang = 0.0 if rng.random() < 0.7 else rng.uniform(-0.5, 0.5)
    ys, xs, m, _, _ = rect_mask(cx, cy, w, h, ang, pad=5)
    if (occ[np.ix_(ys, xs)] & m).any():
        continue
    ys, xs, m, u, v = rect_mask(cx, cy, w, h, ang)
    i = len(bld)
    g = gf if gf else int(rng.choice(LEVELS, p=LW))
    sub = occ[np.ix_(ys, xs)]; sub |= m; occ[np.ix_(ys, xs)] = sub
    bld.append(dict(g=g, cx=cx, cy=cy, w=w, h=h, ang=ang))
print('建物', len(bld))

# ---- なめらかな輪郭:建物の形の符号付き距離 (内側が負、テクセル) を解析的に求める ----
#   屋根テクスチャの α に入れ、シェーダーは線形補間した α = 0.5 を輪郭として使う (テクセルより細かい)
#   data のほうは輪郭に少しでもかかるテクセルを建物にする (0.75 テクセル外側まで) ので、
#   data だけで進むレイが建物を見落とすことはない
sdAll = np.full((H, W), 1e3, np.float32)
for i, b in enumerate(bld):
    ys, xs, _, u, v = rect_mask(b['cx'], b['cy'], b['w'], b['h'], b['ang'], pad=4)
    q1 = np.abs(u) - b['w'] / 2; q2 = np.abs(v) - b['h'] / 2
    sd = np.hypot(np.maximum(q1, 0), np.maximum(q2, 0)) + np.minimum(np.maximum(q1, q2), 0)
    sub = sdAll[np.ix_(ys, xs)]; sb = bid[np.ix_(ys, xs)]
    better = sd < sub
    sub[better] = sd[better]; sb[better & (sd < 0.75)] = i
    sdAll[np.ix_(ys, xs)] = sub; bid[np.ix_(ys, xs)] = sb
sdDeck = (dC - DECK_HW).astype(np.float32)
deck = sdDeck < 0.75
sdAll = np.minimum(sdAll, sdDeck)

# ---------------- data ----------------
R = np.full((H, W), 255, np.int32); G = np.zeros((H, W), np.int32)
m = bid >= 0
R[m] = 0; G[m] = np.array([b['g'] for b in bld])[bid[m]]
R[deck] = 56; G[deck] = 64
# 柱:高架の中心線上に 150 px おき
pillar = np.zeros((H, W), bool)
for px in np.arange(40, W, 150):
    py = curve(px)
    pillar |= (wrapd(X - px, W) ** 2 + wrapd(Y - py, H) ** 2) <= 7.5 ** 2
R[pillar] = 0; G[pillar] = 64

key = R * 256 + G
PAD = 140
dist = np.zeros((H, W), np.float32)
kp = np.pad(key, PAD, mode='wrap')
for k in np.unique(key):
    mk = kp == k
    d = edt(mk)[PAD:-PAD, PAD:-PAD]
    sel = key == k
    dist[sel] = d[sel]
B = np.clip(np.floor(np.maximum(dist - 1.0, 0) * DIST_SCALE), 0, 255).astype(np.uint8)
data = np.dstack([R, G, B]).astype(np.uint8)

# ---------------- 円錐マップ (半分の解像度、周期的) ----------------
F = 2; n_h, n_w = H // F, W // F
top = np.where(R < 255, G, 0)
base = top.reshape(n_h, F, n_w, F).min(axis=(1, 3)) / 255.0
kmin = np.full((n_h, n_w), 1e9)
for lv in np.unique(G[R < 255]):
    feat = ((R < 255) & (G == lv)).reshape(n_h, F, n_w, F).any(axis=(1, 3))
    fp = np.tile(feat, (3, 3))
    d = edt(~fp)[n_h:2 * n_h, n_w:2 * n_w]
    dh = lv / 255.0 - base
    dd = np.maximum(d - 1.5, 0) * F / W          # マップ幅 2048 を 1 とする距離
    k = np.where(dh > 0, dd / np.maximum(dh, 1e-6), 1e9)
    kmin = np.minimum(kmin, k)
cone = np.where(kmin > 1e8, 254, np.minimum(np.floor(255 * kmin / (kmin + 0.1)), 254)).astype(np.uint8)

# ---------------- アルベド ----------------
PAL = np.array([[150, 188, 205], [160, 200, 183], [222, 182, 150], [226, 206, 166], [182, 172, 206],
                [226, 196, 112], [196, 204, 200], [210, 160, 160]], np.float32)
ground = np.zeros((H, W, 3), np.float32)
ground[:] = (124, 129, 128)                                        # 敷地 (舗装)
noise = rng.normal(0, 1, (H // 8 + 1, W // 8 + 1))
noise = np.kron(noise, np.ones((8, 8)))[:H, :W]
park = (np.sin(X / 130 + 1.3) * np.sin(Y / 110) + 0.25 * noise) > 0.72
ground[park & ~blocked] = (104, 134, 100)
SIDE_C = np.array([104, 109, 112], np.float32); ASPH_C = np.array([50, 55, 60], np.float32)
ground[side] = SIDE_C
asphalt = road | under
ground[asphalt] = ASPH_C
# 高架に沿った曲線の歩道・車道は、面積の割合で塗ってなめらかに (階段にならないように)
zone = (dC < DECK_HW + 18) & ~road
cu = np.clip(DECK_HW + 6 - dC + 0.5, 0, 1)                       # 車道 (高架の下)
cs = np.maximum(np.clip(DECK_HW + 16 - dC + 0.5, 0, 1), ((dV <= 12) | (dH <= 12)).astype(np.float32))   # 歩道
g0 = np.where((park & ~blocked)[..., None], np.array([104, 134, 100], np.float32), np.array([124, 129, 128], np.float32))
gz = g0 * (1 - cs[..., None]) + SIDE_C * cs[..., None]
gz = gz * (1 - cu[..., None]) + ASPH_C * cu[..., None]
ground[zone] = gz[zone]
# 車線の線 (直線道路:黄色の破線)
for cx, hw in VROADS:
    l = (np.abs(wrapd(X - cx, W)) < 1.4) & ((Y % 36) < 20) & road & ~under
    ground[l] = (214, 186, 92)
for cy, hw in HROADS:
    l = (np.abs(wrapd(Y - cy, H)) < 1.4) & ((X % 36) < 20) & road & ~under
    ground[l] = (214, 186, 92)
# 横断歩道:交差点の手前
for cx, hw in VROADS:
    for cy, hh in HROADS:
        zone = (np.abs(wrapd(Y - cy, H)) > hh + 2) & (np.abs(wrapd(Y - cy, H)) < hh + 12) & (np.abs(wrapd(X - cx, W)) < hw - 2)
        ground[zone & ((X % 6) < 3)] = (222, 224, 220)
        zone = (np.abs(wrapd(X - cx, W)) > hw + 2) & (np.abs(wrapd(X - cx, W)) < hw + 12) & (np.abs(wrapd(Y - cy, H)) < hh - 2)
        ground[zone & ((Y % 6) < 3)] = (222, 224, 220)

roof = np.zeros((H, W, 4), np.float32)
cols = PAL[rng.integers(0, len(PAL), len(bld))] * rng.uniform(0.9, 1.05, (len(bld), 1))
bc = cols[np.clip(bid, 0, None)]
# 建物の縁からの距離 (屋根の縁取り用)
rc = bc.copy()
# 縁取り:輪郭から 4 テクセル内側まで少し暗く (境目もなめらかに)
rimk = 1.0 - 0.18 * np.clip(sdAll + 4.5, 0, 1)
rc = rc * np.where(m, rimk, 1.0)[..., None]
# 屋上の設備:小さな暗い四角
for i, b in enumerate(bld):
    for _ in range(rng.integers(0, 4)):
        ox, oy = rng.uniform(-0.3, 0.3) * b['w'], rng.uniform(-0.3, 0.3) * b['h']
        c, s = np.cos(b['ang']), np.sin(b['ang'])
        cx, cy = b['cx'] + c * ox - s * oy, b['cy'] + s * ox + c * oy
        uw, uh = rng.uniform(10, 24), rng.uniform(8, 20)
        ys, xs, _, u, v = rect_mask(cx, cy, uw, uh, b['ang'], pad=2)
        q1 = np.abs(u) - uw / 2; q2 = np.abs(v) - uh / 2
        sdu = np.hypot(np.maximum(q1, 0), np.maximum(q2, 0)) + np.minimum(np.maximum(q1, q2), 0)
        cov = (np.clip(0.5 - sdu, 0, 1) * (bid[np.ix_(ys, xs)] == i))[..., None]   # 面積の割合でなめらかに
        sub = rc[np.ix_(ys, xs)]; sub[:] = sub * (1 - cov) + cols[i] * 0.55 * cov; rc[np.ix_(ys, xs)] = sub
roof[..., :3] = rc; roof[..., 3] = np.clip(0.5 - sdAll / 4.0, 0, 1) * 255   # α = なめらかな輪郭 (±2 テクセルで 0→1)
# 建物の外側の RGB は一番近い屋根の色で埋める (ミップで縁が別の色ににじまないように)
# 高架の路面
dk = deck | pillar
roof[dk, :3] = (78, 84, 90)                # α は上で作ったなめらかな輪郭のまま (ここで 255 にしない)
# 路面の線も面積の割合で塗る (曲線が階段にならないように)
def paint(cov, col):
    cov = np.clip(cov, 0, 1)[..., None] * dk[..., None]
    roof[..., :3] = roof[..., :3] * (1 - cov) + np.array(col, np.float32) * cov
dLane = np.abs(wrapd(Y - curve(X), H)) / np.sqrt(1 + curve_d(X) ** 2)
dash = np.clip(np.minimum(X % 40, 22 - X % 40) + 0.5, 0, 1)
paint((1.4 - dLane + 0.5) * dash, (226, 228, 222))                 # 中央の破線
paint(1.0 - np.abs(dC - (DECK_HW - 4)) + 0.5, (200, 202, 198))      # 端の白線
paint(dC - (DECK_HW - 2.5) + 0.5, (150, 156, 160))                  # 欄干
has = (bid >= 0) | dk                     # 屋根の色を塗った所 (建物と高架)
_, (iy, ix) = edt(~np.pad(has, PAD, mode='wrap'), return_indices=True)
iy = (iy[PAD:-PAD, PAD:-PAD] - PAD) % H; ix = (ix[PAD:-PAD, PAD:-PAD] - PAD) % W
roof[..., :3] = np.where(has[..., None], roof[..., :3], roof[iy, ix, :3])
# 地面テクスチャの建物の中 (R=0) は壁の色
wall = np.array([0.72, 0.72, 0.75]) * bc + 18
mIn = m & (sdAll < -1.5)          # 壁の色は輪郭より 1.5 テクセル以上内側だけ (外側の地面ににじまない)
ground[mIn] = wall[mIn]
ground[pillar] = (150, 152, 150)

def save(a, name, mode=None):
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), mode).save(os.path.join(OUT, name))
# city_bake.py の入力の例 (人が用意する画像に相当するもの)
os.makedirs(os.path.join(OUT, 'input'), exist_ok=True)
inside = sdAll < 0.0
Image.fromarray(np.where(inside, np.clip(G, 0, 255), 0).astype(np.uint8)).save(os.path.join(OUT, 'input', 'top.png'))      # 上端の高さ (AA なし)
Image.fromarray(np.where(inside & (R == 56), 56, 0).astype(np.uint8)).save(os.path.join(OUT, 'input', 'bottom.png'))       # 下端の高さ (高架だけ 56)
Image.fromarray((np.clip(0.5 - sdAll, 0, 1) * 255).astype(np.uint8)).save(os.path.join(OUT, 'input', 'mask.png'))        # 建物マスク (AA あり)
Image.fromarray(np.clip(roof[..., :3], 0, 255).astype(np.uint8)).save(os.path.join(OUT, 'input', 'roof_color.png'))       # 屋根の色
save(data, 'map_data.png'); save(roof, 'map_roof.png'); save(ground, 'map_ground.png'); save(cone, 'map_cone.png')

# ---------------- タイル A / B (マージン付き) ----------------
def cut(img, ox, oy, s, f=1):
    hh, ww = img.shape[:2]
    ys = np.arange(oy // f, oy // f + s // f) % hh; xs = np.arange(ox // f, ox // f + s // f) % ww
    return img[np.ix_(ys, xs)]
S = CORE + 2 * MARGIN
for name, ox in (('A', 0), ('B', CORE)):
    save(cut(data, ox - MARGIN, -MARGIN, S), f'tile{name}_data.png')
    save(cut(roof, ox - MARGIN, -MARGIN, S), f'tile{name}_roof.png')
    save(cut(ground, ox - MARGIN, -MARGIN, S), f'tile{name}_ground.png')
    save(cut(cone, ox - MARGIN, -MARGIN, S, 2), f'tile{name}_cone.png')
print('G の段', np.unique(G[R < 255]), 'B 最大', B.max(), 'タイル', S, '×', S)
