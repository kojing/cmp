import numpy as np, math, random, pickle
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage
from roads import *
L = pickle.load(open('layout.pkl', 'rb'))
label, road, pillar, H, ANG = L['label'], L['road'], L['pillar'], L['H'], L['ang']
lots, lot_ids, vacant, VAC_ANG = L['lots'], L['lot_ids'], L['vacant'], L['vac_ang']
rng = random.Random(11); SS = 1; S = N * SS
OUT = N // 2          # 出力の解像度 (2048)
DIST_SCALE = 2          # B は 1px あたり 2 (最大 127.5px)。2048 でも 1024 版と同じ UV 範囲
def sc(p): return [(x * SS, y * SS) for x, y in p]

# ---------------- city_bake.py の入力 ----------------
data = np.zeros((N, N, 3), np.int32); data[..., 0] = 255
for i, h in H.items(): m = label == i; data[m, 0] = 0; data[m, 1] = h
data[road, 0] = 56; data[road, 1] = 72; data[pillar, 0] = 0; data[pillar, 1] = 72
solid = data[..., 0] < 253
def half_mean(a): return a.reshape(OUT, 2, OUT, 2).mean(axis=(1, 3))
def half_pick(a):                                   # 2×2 の中で建物が一番多い値 (高さを混ぜない)
    b = a.reshape(OUT, 2, OUT, 2).transpose(0, 2, 1, 3).reshape(OUT, OUT, 4)
    return np.max(b, axis=2)
cov = half_mean(solid.astype(np.float32))           # アンチエイリアスつきの建物マスク (0, .25, .5, .75, 1)
top = half_pick(np.where(solid, data[..., 1], 0))
bot = half_pick(np.where(solid & (data[..., 0] > 0), data[..., 0], 0))
import os; os.makedirs('input', exist_ok=True)
Image.fromarray((cov * 255 + 0.5).astype(np.uint8)).save('input/mask.png')
Image.fromarray(top.astype(np.uint8)).save('input/top.png')
Image.fromarray(bot.astype(np.uint8)).save('input/bottom.png')
# 2 倍の解像度の top / bottom (段の輪郭をテクセルより細かくするため。mask は 1 倍のまま)
Image.fromarray(np.where(solid, data[..., 1], 0).astype(np.uint8)).save('input/top2x.png')
Image.fromarray(np.where(solid & (data[..., 0] > 0), data[..., 0], 0).astype(np.uint8)).save('input/bottom2x.png')
print('input ok')

# ---------------- 屋根 ----------------
ROOF = [(184,198,190),(220,184,106),(149,181,190),(212,180,160),(171,186,180),(180,188,204),
        (185,177,200),(196,190,154),(170,190,205),(196,178,158),(160,190,176),(206,196,176)]
cols = {i: ROOF[rng.randrange(len(ROOF))] for i in H}
def wall_of(c): r, g, b = c; return (int(r*0.62+8), int(g*0.6+6), int(b*0.62+10))
roof = Image.new('RGBA', (S, S), (0, 0, 0, 0))
for i in sorted(H, key=lambda k: H[k]):
    bm = label == i
    ys, xs = np.nonzero(bm); x0, x1, y0, y1 = xs.min() - 2, xs.max() + 3, ys.min() - 2, ys.max() + 3
    sub = bm[y0:y1, x0:x1]
    dt = ndimage.distance_transform_edt(np.pad(sub, 1))[1:-1, 1:-1]
    c = cols[i]; dark = tuple(int(v * 0.78) for v in c)
    img = np.zeros(sub.shape + (4,), np.uint8)
    img[sub] = c + (255,)
    img[sub & (dt > 3 * K) & (dt <= 5 * K)] = dark + (255,)          # 縁取り
    tile = Image.fromarray(img).resize((sub.shape[1] * SS, sub.shape[0] * SS), Image.NEAREST)
    core = np.kron(dt > 11 * K, np.ones((SS, SS), bool))
    a = ANG[i]; cx, cy = xs.mean() - x0, ys.mean() - y0
    d = ImageDraw.Draw(tile); win = tuple(int(v * 0.62) for v in c) + (255,)
    for gx in range(-12, 13):
        for gy in range(-12, 13):
            px = cx + gx*36*K*math.cos(a) - gy*44*K*math.sin(a); py = cy + gx*36*K*math.sin(a) + gy*44*K*math.cos(a)
            box = [(px + x*math.cos(a) - y*math.sin(a), py + x*math.sin(a) + y*math.cos(a)) for x, y in [(-8*K,-4*K),(8*K,-4*K),(8*K,4*K),(-8*K,4*K)]]
            if all(0 <= int(bx*SS) < core.shape[1] and 0 <= int(by*SS) < core.shape[0] and core[int(by*SS), int(bx*SS)] for bx, by in box + [(px, py)]):
                d.polygon([(bx*SS, by*SS) for bx, by in box], fill=win)
    roof.alpha_composite(tile, (x0 * SS, y0 * SS))
dr = ImageDraw.Draw(roof)
for r in ELEVATED: dr.polygon(sc(band(r, r['w'], 1)), fill=(166,180,182,255))
for r in ELEVATED:
    for off in (-r['w']/2 + 6*K, r['w']/2 - 6*K): dr.line(sc(line(r, off, 1)), fill=(186,200,202,255), width=int(3*K*SS))
    for sg in dashes(line(r, 0, 1), 20*K, 20*K): dr.line(sc(sg), fill=(231,210,135,255), width=int(4*K*SS))
roof = roof.resize((OUT, OUT), Image.LANCZOS); Image.fromarray(np.array(roof)[..., :3]).save('input/roof_color.png'); print('roof ok')

# ---------------- 壁 ----------------
regcol = np.zeros((N, N, 3), np.uint8)
for i in H: regcol[label == i] = wall_of(cols[i])
regcol[road] = (92, 118, 122)
dist, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
wall = regcol[iy, ix]                                 # 建物の外も一番近い建物の壁の色で埋める
Image.fromarray(wall).resize((OUT, OUT), Image.NEAREST).save('input/wall_color.png'); print('wall ok')

# ---------------- 地面 ----------------
BLOCK, PLATE, PLATE_EDGE = (60, 70, 74), (74, 84, 88), (90, 100, 102)
WALK, CURB, ASPHALT = (98, 108, 110), (120, 128, 128), (38, 46, 51)
LANE, CENTER, MEDIAN = (200, 204, 196), (214, 190, 120), (112, 120, 120)
GRAVEL, PARK = (112, 106, 92), (52, 60, 65)
up = lambda m: Image.fromarray(m.astype(np.uint8) * 255).resize((S, S), Image.NEAREST)
ground = Image.new('RGB', (S, S), BLOCK); dg = ImageDraw.Draw(ground)
lotm = np.isin(lots, lot_ids)
ground.paste(PLATE, (0, 0), up(lotm))
ground.paste(PLATE_EDGE, (0, 0), up(ndimage.binary_dilation(label > 0, iterations=int(3 * K)) & lotm))
# 空き地:砂利 (ざらついた明るい土) / 駐車場 (舗装 + 白線)
gr = vacant == 1
if gr.any():
    noise = np.random.default_rng(3).normal(0, 7, (N, N, 1))
    tex = np.clip(np.array(GRAVEL)[None, None, :] + noise, 0, 255).astype(np.uint8)
    edge = gr & ~ndimage.binary_erosion(gr, iterations=int(2 * K))
    tex[edge] = (88, 84, 74)
    gimg = Image.fromarray(tex).resize((S, S), Image.NEAREST)
    ground.paste(gimg, (0, 0), up(gr))
pk = vacant == 2
if pk.any():
    ground.paste(PARK, (0, 0), up(pk))
    lab, nn = ndimage.label(pk)
    for j in range(1, nn + 1):
        m = lab == j; ys, xs = np.nonzero(m)
        li = int(np.bincount(lots[m]).argmax()); a = VAC_ANG.get(li, 0.0)
        inner = ndimage.binary_erosion(m, iterations=int(10 * K))
        cx, cy = xs.mean(), ys.mean(); ca, sa = math.cos(a), math.sin(a)
        stripe = Image.new('L', (S, S), 0); ds = ImageDraw.Draw(stripe)
        R_ = max(xs.max() - xs.min(), ys.max() - ys.min())
        # 区画線 (白線を等間隔に) と通路
        for u in np.arange(-R_, R_, 12 * K):
            for v0, v1 in ((-30 * K, -6 * K), (6 * K, 30 * K)):
                for vv in np.arange(-R_, R_, 64 * K):
                    p0 = (cx + u * ca - (vv + v0) * sa, cy + u * sa + (vv + v0) * ca)
                    p1 = (cx + u * ca - (vv + v1) * sa, cy + u * sa + (vv + v1) * ca)
                    ds.line([(p0[0]*SS, p0[1]*SS), (p1[0]*SS, p1[1]*SS)], fill=255, width=max(1, int(1.2*K*SS)))
        stripe = Image.fromarray(np.minimum(np.array(stripe), np.array(up(inner))))
        ground.paste((170, 176, 170), (0, 0), stripe)
# 歩道 → 縁石 → 車道
for r in GROUND: dg.polygon(sc(band(r, r['w'] + 16 * K, 1)), fill=WALK)
for r in GROUND: dg.polygon(sc(band(r, r['w'] + 2 * K, 1)), fill=CURB)
for r in GROUND: dg.polygon(sc(band(r, r['w'], 1)), fill=ASPHALT)
# 交差点
cnt = np.zeros((S // 2, S // 2), np.uint8)
for r in GROUND:
    im = Image.new('L', (S // 2, S // 2), 0)
    ImageDraw.Draw(im).polygon([(x * SS / 2, y * SS / 2) for x, y in band(r, r['w'] + 4 * K, 1)], fill=1)
    cnt += np.array(im)
cross = Image.fromarray(((cnt >= 2) * 255).astype(np.uint8)).resize((S, S), Image.NEAREST)
cross = cross.filter(ImageFilter.MaxFilter(int(4 * K * SS) | 1))
asph = Image.new('L', (S, S), 0); da = ImageDraw.Draw(asph)
for r in GROUND: da.polygon(sc(band(r, r['w'], 1)), fill=255)
cross = Image.fromarray(np.minimum(np.array(cross), np.array(asph)))
lw = int(2 * K * SS)
for r in GROUND:
    w = r['w']
    for off in (-w/2 + 4*K, w/2 - 4*K): dg.line(sc(line(r, off, 1)), fill=LANE, width=lw)
    if r.get('median'):
        dg.polygon(sc(band(r, r['median'], 1)), fill=MEDIAN)
        for side in (-1, 1):
            o = side * (r['median']/2 + (w/2 - r['median']/2) / 2)
            for sg in dashes(line(r, o, 1), 14*K, 18*K): dg.line(sc(sg), fill=LANE, width=lw)
    else:
        for sg in dashes(line(r, 0, 1), 18*K, 16*K): dg.line(sc(sg), fill=CENTER, width=lw)
ground.paste(ASPHALT, (0, 0), cross)
cm = np.array(cross.resize((N, N), Image.NEAREST)) > 127
for r in GROUND:
    pts = line(r, 0, 1)
    inside = [0 <= int(y) < N and 0 <= int(x) < N and cm[int(y), int(x)] for x, y in pts]
    for k in range(1, len(pts)):
        if inside[k] != inside[k-1]:
            j = k if not inside[k] else k - 1; step = 1 if not inside[k] else -1
            j2 = min(max(j + step * int(10 * K), 0), len(pts) - 1)
            (x0, y0), (x1, y1) = pts[j2], pts[min(max(j2 + step, 0), len(pts)-1)]
            tx, ty = x1 - x0, y1 - y0; l = math.hypot(tx, ty) or 1; tx, ty = tx/l, ty/l; nx, ny = -ty, tx
            for s_ in np.arange(-r['w']/2 + 5*K, r['w']/2 - 4*K, 6*K):
                cxp, cyp = x0 + nx * s_, y0 + ny * s_; hw, hl = 1.6*K, 5*K
                quad = [(cxp - nx*hw - tx*hl, cyp - ny*hw - ty*hl), (cxp + nx*hw - tx*hl, cyp + ny*hw - ty*hl),
                        (cxp + nx*hw + tx*hl, cyp + ny*hw + ty*hl), (cxp - nx*hw + tx*hl, cyp - ny*hw + ty*hl)]
                dg.polygon(sc(quad), fill=LANE)
ground = ground.resize((OUT, OUT), Image.LANCZOS); ground.save('input/ground_color.png'); print('ground ok')

# ---------------- 検証 ----------------
for li in lot_ids:
    m = lots == li; A = m.sum(); b = (label > 0) & m
    nb = ndimage.label(b)[1]
    assert b.sum() / A <= 0.70 + 1e-9, (li, b.sum() / A)
    assert nb <= 3, (li, nb)
cov = [((label > 0) & (lots == li)).sum() / (lots == li).sum() for li in lot_ids]
print('coverage max %.2f mean %.2f, vacant area %.1f%% of lots' % (max(cov), np.mean(cov), (vacant > 0).sum() / lotm.sum() * 100))

