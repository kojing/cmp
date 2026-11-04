# 敷地 (道路で区切られた街区) の形に沿って建物を置く
#   ・建ぺい率は敷地ごとに 45〜70% (最大 70%)。区画の形を相似縮小して合わせる
#   ・1 敷地あたり建物は 1〜3 棟 (敷地の長手方向に分割)
#   ・空き地:敷地まるごと (約 15%) と、分割した区画の一部 (約 20%)。砂利の空き地か駐車場
import numpy as np, math, random, pickle
from PIL import Image, ImageDraw
from scipy import ndimage
from roads import *
rng = random.Random(5)
def fill(poly):
    im = Image.new('L', (N, N), 0); ImageDraw.Draw(im).polygon(poly, fill=255); return np.array(im) > 127
road = np.zeros((N, N), bool)
for r in ELEVATED: road |= fill(band(r, r['w']))
groad = np.zeros((N, N), bool)
for r in GROUND: groad |= fill(band(r, r['w'] + 16 * K))          # 車道 + 歩道
pim = Image.new('L', (N, N), 0); d = ImageDraw.Draw(pim)
pr = 7 * K
for r in ELEVATED:
    for x, y in along(line(r), 118 * K):
        if 10 * K < x < N - 10 * K and 10 * K < y < N - 10 * K: d.ellipse([x - pr, y - pr, x + pr, y + pr], fill=255)
pillar = (np.array(pim) > 127) & road

def crop_edt(m):
    """m の各画素から m の外までの距離 (画像の外は境界にしない)。bbox で切り出して高速化"""
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = max(ys.min() - 2, 0), min(ys.max() + 3, N), max(xs.min() - 2, 0), min(xs.max() + 3, N)
    out = np.zeros(m.shape); sub = m[y0:y1, x0:x1]
    out[y0:y1, x0:x1] = ndimage.distance_transform_edt(sub)
    # bbox の縁が画像の縁でない所は 0 (= m の外) なので正しい。画像の縁では外を見ないので距離が伸びる (ミラー前提)
    return out

lots, nlots = ndimage.label(~groad)
# 敷地まるごと空き地にする区画を先に選ぶ (約 15%、最低 2 区画)
areas = {li: int((lots == li).sum()) for li in range(1, nlots + 1)}
cands = [li for li, a in areas.items() if a >= 600 * K * K]
med = float(np.median([areas[li] for li in cands]))
small = [li for li in cands if areas[li] <= med]            # 大きな街区がまるごと空くのは避ける
VACANT_LOTS = set(rng.sample(small, max(2, round(len(cands) * 0.15))))
LOW  = [32, 36, 40, 48, 56, 64, 72, 80, 88]
MID  = [64, 72, 80, 88, 96, 104, 112]
HIGH = [136, 144, 160, 176, 192]       # 4 の倍数 (ASTC 対策)
label = np.zeros((N, N), np.int32); H = {}; ANG = {}; nid = 2
vacant = np.zeros((N, N), np.uint8)           # 0: なし / 1: 砂利の空き地 / 2: 駐車場
VAC_ANG = {}                                   # 駐車場の線の向き
lot_info = []
K2 = K * K
for li in range(1, nlots + 1):
    m = lots == li; A = int(m.sum())
    if A < 600 * K2: continue
    ys, xs = np.nonzero(m); cx, cy = xs.mean(), ys.mean()
    w_, v = np.linalg.eigh(np.cov(np.vstack([xs - cx, ys - cy])))
    major = v[:, 1]; ang = math.atan2(major[1], major[0])
    # 敷地まるごと空き地
    if li in VACANT_LOTS:
        vacant[m] = rng.choice([1, 2]); VAC_ANG[li] = ang
        lot_info.append((li, A, 0, 0.0)); continue
    n = 1 if A < 5000 * K2 else rng.choice([1, 2, 2, 3] if A < 20000 * K2 else [2, 3, 3])
    axis = major if rng.random() < 0.8 else v[:, 0]
    proj = (xs - cx) * axis[0] + (ys - cy) * axis[1]
    cuts = list(np.quantile(proj, [k / n for k in range(1, n)])) if n > 1 else []
    if n > 1:
        jit = (proj.max() - proj.min()) * 0.08
        cuts = sorted(c + rng.uniform(-jit, jit) for c in cuts)
    gap = rng.uniform(8, 16) * K
    pidx = np.searchsorted(cuts, proj) + 1
    near = np.zeros(len(xs), bool)
    for c in cuts: near |= np.abs(proj - c) < gap / 2
    pidx[near] = 0
    piece = np.zeros((N, N), np.int32); piece[ys, xs] = pidx
    # 区画の一部を空き地にする (少なくとも 1 棟は残す)
    keep = list(range(1, n + 1))
    if n > 1:
        for k in list(keep):
            if len(keep) > 1 and rng.random() < 0.2:
                keep.remove(k); vacant[piece == k] = rng.choice([1, 2])
        VAC_ANG[li] = ang
    target = rng.uniform(0.45, 0.70)
    # 各区画:縁から少し下げた形 (base) を、重心を中心に相似縮小して建ぺい率を合わせる。
    # 一律に下げるだけだと細長い敷地で建物が針のように細くなるので、形の比率を保つ縮小にする
    s0 = 3.0 * K
    bases = {k: crop_edt(piece == k) > s0 for k in keep}
    tot = sum(int(b.sum()) for b in bases.values())
    scale = math.sqrt(min(1.0, target * A / max(tot, 1)))
    for k, base in bases.items():
        if base.sum() < 150 * K2: continue
        ys_, xs_ = np.nonzero(base); y0, y1, x0, x1 = ys_.min(), ys_.max() + 1, xs_.min(), xs_.max() + 1
        sub = base[y0:y1, x0:x1].astype(np.uint8); cy_, cx_ = ys_.mean() - y0, xs_.mean() - x0
        # 出力座標 o → 入力座標 c + (o - c) / scale
        sh = ndimage.affine_transform(sub, np.diag([1 / scale, 1 / scale]),
                                      offset=(cy_ - cy_ / scale, cx_ - cx_ / scale), order=0) > 0
        bm = np.zeros((N, N), bool); bm[y0:y1, x0:x1] = sh & base[y0:y1, x0:x1]
        while bm.sum() > 0 and ((label > 0) | bm)[m].sum() > 0.70 * A:      # 念のため上限 70% を守る
            bm &= crop_edt(bm) > 1
        if bm.sum() < 150 * K2: continue
        lab, nn = ndimage.label(bm)
        if nn > 1:
            sizes = ndimage.sum(bm, lab, range(1, nn + 1)); bm = lab == (1 + int(np.argmax(sizes)))
        area = int(bm.sum()); halfw = crop_edt(bm).max()
        if halfw < 14 * K:                               # 細長い建物は低層に
            label[bm] = nid; H[nid] = rng.choice([32, 36, 40, 48]); ANG[nid] = ang; nid += 1; continue
        if area > 3000 * K2 and rng.random() < 0.35:     # 基壇 + セットバックした高層部
            label[bm] = nid; H[nid] = rng.choice([32, 40, 48]); ANG[nid] = ang
            tm = crop_edt(bm) > rng.uniform(10, 18) * K
            if tm.sum() > 300 * K2:
                nid += 1; label[tm] = nid; H[nid] = rng.choice(HIGH); ANG[nid] = ang
        else:
            label[bm] = nid; ANG[nid] = ang
            H[nid] = rng.choice(HIGH if (area < 2500 * K2 and rng.random() < 0.4) else (MID if rng.random() < 0.6 else LOW))
        nid += 1
    lot_info.append((li, A, len(keep), int(((label > 0) & m).sum()) / A))
print('lots', len(lot_info), 'buildings', len(H), 'vacant lots', sum(1 for l in lot_info if l[2] == 0))
pickle.dump(dict(label=label, road=road, pillar=pillar, H=H, ang=ANG, lots=lots,
                 lot_ids=[l[0] for l in lot_info], vacant=vacant, vac_ang=VAC_ANG), open('layout.pkl', 'wb'))
