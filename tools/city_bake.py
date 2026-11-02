#!/usr/bin/env python3
"""
city_bake.py ― 高さの画像と建物マスクから、cityTile() 用の各チャンネルを作る

人が用意するもの (すべて同じ解像度のグレースケール PNG。マップ全体 1 枚)
  --top     上端の高さ。0 = 何もない、1..255 = 建物の上端 (アンチエイリアスなし)
  --mask    建物マスク。白 = 建物 (アンチエイリアスあり。縁の灰色から輪郭をテクセルより細かく求める)
            省略すると --top > 0 を白黒マスクとして使う (斜めの辺は階段になる)
  --bottom  下端の高さ (省略可)。0 = 地面から立つ、高架などは床の下端の高さ
  --roof    屋根の色 (RGB、省略可)。渡すと建物の外側を一番近い屋根の色で埋めた画像も作る
  --ground  地面と壁の色 (RGB、省略可)。渡すとほかと同じマージンでタイルに切り出す

作るもの (--out のフォルダに、1 チャンネルずつのグレースケール PNG)
  data_R.png    下端の高さ (255 = 空き地)                → data テクスチャの R
  data_G.png    上端の高さ (4 の倍数)                    → data テクスチャの G
  data_B.png    同じ高さの領域の境界までの距離            → data テクスチャの B
  roof_A.png    なめらかな輪郭 (0.5 = 輪郭)               → roof テクスチャの A
  cone.png      円錐ステップ値 (半分の解像度)             → cone テクスチャ (R8)
  wall_mask.png 地面テクスチャに壁の色を置く範囲 (白)     → ground の RGB を作るときの目安
  roof_RGB.png  建物の外を埋めた屋根の色 (--roof のとき)  → roof テクスチャの RGB
  bake_info.txt シェーダーの定数に入れる値

  --core と --margin を渡すと、各画像をタイルに切り出したもの (tiles/タイル名_*.png) も作る。

例
  python3 city_bake.py --top top.png --mask mask.png --bottom bottom.png --roof roof_color.png \\
                       --out baked --wrap --core 1024 --margin 192
"""
import argparse, os, sys, struct, zlib
import numpy as np

# ---------------------------------------------------------------
# 計算の道具:scipy と Pillow があればそれを使い、なければ numpy だけの実装を使う
# (Houdini の Python には numpy しか入っていないことが多いので、そのままで動くように)
# 環境変数 CITY_BAKE_PURE=1 で、numpy だけの実装を強制できる
# ---------------------------------------------------------------
BACKEND = 'numpy'
if not os.environ.get('CITY_BAKE_PURE'):
    try:
        from PIL import Image as _PIL
        from scipy.ndimage import distance_transform_edt as _sp_edt, zoom as _sp_zoom
        BACKEND = 'scipy'
    except ImportError:
        pass

EMPTY = 255
_INF = 1e20


def _dt_axis0(f):
    """1 次元の二乗距離変換 (Felzenszwalb) を、配列 f (n × m) の各列に同時にかける。
    f = 0 が「点がある」、_INF が「ない」。戻り値は (二乗距離, 一番近い点の行番号)。"""
    n, m = f.shape
    cols = np.arange(m)
    v = np.zeros((n, m), np.int64)           # 下側包絡線の放物線の頂点 (行番号)
    z = np.full((n + 1, m), _INF)            # 放物線の境目
    k = np.zeros(m, np.int64)
    has = np.zeros(m, bool)                  # その列に点が 1 つでもあったか
    qq = np.arange(n, dtype=np.float64) ** 2
    for q in range(n):
        fq = f[q]
        ok = fq < _INF
        if not ok.any():
            continue
        first = ok & ~has                     # その列で最初の点
        if first.any():
            c = cols[first]
            v[0, c] = q; z[0, c] = -_INF; z[1, c] = _INF; k[c] = 0
            has[c] = True
        rest = ok & ~first
        if not rest.any():
            continue
        c = cols[rest]
        while True:                           # 新しい放物線より上にある放物線を取り除く
            vk = v[k[c], c]
            s = ((fq[c] + qq[q]) - (f[vk, c] + qq[vk])) / (2.0 * q - 2.0 * vk)
            pop = (s <= z[k[c], c]) & (k[c] > 0)
            if not pop.any():
                break
            k[c[pop]] -= 1
        vk = v[k[c], c]
        s = ((fq[c] + qq[q]) - (f[vk, c] + qq[vk])) / (2.0 * q - 2.0 * vk)
        k[c] += 1
        v[k[c], c] = q; z[k[c], c] = s; z[k[c] + 1, c] = _INF
    d = np.full((n, m), _INF); arg = np.zeros((n, m), np.int64)
    k[:] = 0
    c = cols[has]
    for q in range(n):
        while True:
            adv = z[k[c] + 1, c] < q
            if not adv.any():
                break
            k[c[adv]] += 1
        vk = v[k[c], c]
        d[q, c] = (q - vk) ** 2 + f[vk, c]
        arg[q, c] = vk
    return d, arg


def edt(mask, return_indices=False):
    """scipy の distance_transform_edt と同じ:mask が True の所から、一番近い False の所までの距離"""
    if BACKEND == 'scipy':
        return _sp_edt(mask, return_indices=return_indices)
    f = np.where(mask, _INF, 0.0)
    d1, r1 = _dt_axis0(f)                     # 列ごと (縦)
    d2, c2 = _dt_axis0(np.ascontiguousarray(d1.T))   # 行ごと (横)
    d2 = d2.T; c2 = c2.T
    dist = np.sqrt(np.minimum(d2, _INF))
    if not return_indices:
        return dist
    rows = np.take_along_axis(r1, c2, axis=1)
    return dist, (rows, c2)


def zoom_lin(a, up):
    """up 倍に線形補間で拡大 (scipy の zoom(order=1, mode='nearest', grid_mode=True) 相当)"""
    if BACKEND == 'scipy':
        return _sp_zoom(a, up, order=1, mode='nearest', grid_mode=True)
    def along(x, axis):
        n = x.shape[axis]
        pos = (np.arange(n * up) + 0.5) / up - 0.5
        i0 = np.clip(np.floor(pos).astype(np.int64), 0, n - 1)
        i1 = np.clip(i0 + 1, 0, n - 1)
        w = np.clip(pos - np.floor(pos), 0, 1)
        w = np.where(pos < 0, 0.0, np.where(pos > n - 1, 0.0, w))
        shape = [1] * x.ndim; shape[axis] = -1
        return np.take(x, i0, axis) * (1 - w.reshape(shape)) + np.take(x, i1, axis) * w.reshape(shape)
    return along(along(a.astype(np.float64), 0), 1)


# ---- PNG の読み書き (Pillow がない時。8 / 16 bit、グレー / RGB / パレット / α、インターレースなし) ----
def _png_read(path):
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(path + ' は PNG ではありません')
    pos, idat, plte = 8, [], None
    while pos < len(data):
        ln, = struct.unpack('>I', data[pos:pos + 4]); typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]; pos += 12 + ln
        if typ == b'IHDR':
            W, H, bd, ct, _, _, il = struct.unpack('>IIBBBBB', body)
        elif typ == b'PLTE':
            plte = np.frombuffer(body, np.uint8).reshape(-1, 3)
        elif typ == b'IDAT':
            idat.append(body)
        elif typ == b'IEND':
            break
    if il:
        raise ValueError(path + ':インターレースの PNG には対応していません')
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    if bd < 8 and ct != 3:
        raise ValueError(path + ':8 bit 未満のグレーには対応していません')
    bpp = max(1, ch * bd // 8)
    stride = (W * ch * bd + 7) // 8
    raw = np.frombuffer(zlib.decompress(b''.join(idat)), np.uint8).reshape(H, stride + 1)
    ft = raw[:, 0].astype(np.int32)
    U = stride // bpp                          # 1 行の画素数 (bpp バイトずつ)
    line = raw[:, 1:].reshape(H, U, bpp).astype(np.int32)
    cur = np.zeros((H, U, bpp), np.int32)
    if (ft == 0).all():
        cur = line
    else:
        # 各画素は「左・上・左上」に依存するので、斜めの列 (x + y が同じ画素) ごとにまとめて復元する
        for d in range(H + U - 1):
            y = np.arange(max(0, d - U + 1), min(H - 1, d) + 1); x = d - y
            z = np.zeros((len(y), bpp), np.int32)
            left = np.where((x > 0)[:, None], cur[y, np.maximum(x - 1, 0)], z)
            up_ = np.where((y > 0)[:, None], cur[np.maximum(y - 1, 0), x], z)
            ul = np.where(((x > 0) & (y > 0))[:, None], cur[np.maximum(y - 1, 0), np.maximum(x - 1, 0)], z)
            p = left + up_ - ul
            pa, pb, pc = np.abs(p - left), np.abs(p - up_), np.abs(p - ul)
            paeth = np.where((pa <= pb) & (pa <= pc), left, np.where(pb <= pc, up_, ul))
            f = ft[y][:, None]
            pred = np.where(f == 1, left, np.where(f == 2, up_, np.where(f == 3, (left + up_) >> 1, np.where(f == 4, paeth, 0))))
            cur[y, x] = (line[y, x] + pred) & 255
    out = cur.reshape(H, stride).astype(np.uint8)
    if bd == 16:
        img = out.view('>u2').reshape(H, W, ch).astype(np.float64) / 257.0
    elif bd == 8:
        img = out.reshape(H, W, ch).astype(np.float64)
    else:                                     # パレットの 1/2/4 bit
        bits = np.unpackbits(out, axis=1).reshape(H, -1, bd)
        idx = np.zeros(bits.shape[:2], np.int64)
        for b in range(bd):
            idx = idx * 2 + bits[..., b]
        img = idx[:, :W, None].astype(np.float64)
    if ct == 3:
        img = plte[img[..., 0].astype(np.int64)].astype(np.float64)
    return img                                # (H, W, ch) 0..255


def _png_write(path, arr):
    a = np.clip(np.round(arr), 0, 255).astype(np.uint8)
    if a.ndim == 2:
        ct, ch = 0, 1
    else:
        ch = a.shape[2]; ct = {1: 0, 3: 2, 4: 6}[ch]
    H, W = a.shape[:2]
    rows = np.concatenate([np.zeros((H, 1), np.uint8), a.reshape(H, W * ch)], axis=1)   # フィルターなし
    def chunk(t, b):
        return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, ct, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(rows.tobytes(), 6)) + chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def read_image(path):
    """(H, W, ch) の 0..255 の配列 (16 bit は 8 bit の範囲に直す)"""
    if BACKEND == 'scipy':
        im = _PIL.open(path)
        if im.mode in ('I;16', 'I;16B', 'I'):
            return (np.array(im).astype(np.float64) / 257.0)[..., None]
        if im.mode == 'P':
            im = im.convert('RGBA')
        a = np.array(im).astype(np.float64)
        return a[..., None] if a.ndim == 2 else a
    return _png_read(path)


def write_image(path, arr):
    if BACKEND == 'scipy':
        _PIL.fromarray(np.clip(np.round(arr), 0, 255).astype(np.uint8)).save(path)
    else:
        _png_write(path, arr)


def load_gray(path):
    a = read_image(path)
    if a.shape[2] >= 3:                       # カラーなら輝度 (R=G=B のグレー画像ならそのまま)
        a = a[..., :3] @ np.array([0.299, 0.587, 0.114])
        return a.astype(np.float32)
    return a[..., 0].astype(np.float32)


def pad(a, p, wrap):
    return np.pad(a, p, mode='wrap' if wrap else 'edge')


def fine_sdf(cov, wrap, up=4, chunk=512, limit=4.0):
    """建物マスク (0..1、アンチエイリアスあり) から、テクセルより細かい符号付き距離 (内側が負、テクセル単位) を作る。
    マスクを up 倍に線形補間して 0.5 で切り、その解像度で距離変換してから戻す。
    使うのは輪郭の近く (±limit テクセル) だけなので、ブロックごとに処理してメモリを抑える。"""
    H, W = cov.shape
    P = int(np.ceil(limit)) + 2
    cp = pad(cov, P, wrap)
    sd = np.empty((H, W), np.float32)
    for y0 in range(0, H, chunk):
        for x0 in range(0, W, chunk):
            h = min(chunk, H - y0); w = min(chunk, W - x0)
            blk = cp[y0:y0 + h + 2 * P, x0:x0 + w + 2 * P]
            hi = zoom_lin(blk, up) >= 0.5
            d_out = edt(~hi); d_in = edt(hi)
            s = np.where(hi, -(d_in - 0.5), d_out - 0.5) / up           # 画素の中心どうしの距離 → 境界までの距離
            # テクセルの中心は up×up の中央 → 中央の 2×2 (up が偶数) を平均
            s = s.reshape(blk.shape[0], up, blk.shape[1], up)
            c0 = up // 2 - 1 if up % 2 == 0 else up // 2
            c1 = up // 2 + 1
            s = s[:, c0:c1, :, c0:c1].mean(axis=(1, 3))
            sd[y0:y0 + h, x0:x0 + w] = s[P:P + h, P:P + w]
    return np.clip(sd, -limit, limit)


def nearest_fill(values, valid, wrap, P=64):
    """valid でない所を、一番近い valid の値で埋める"""
    H, W = valid.shape
    vp = pad(valid, P, wrap)
    _, (iy, ix) = edt(~vp, return_indices=True)
    iy = iy[P:P + H, P:P + W] - P; ix = ix[P:P + H, P:P + W] - P
    if wrap:
        iy %= H; ix %= W
    else:
        iy = np.clip(iy, 0, H - 1); ix = np.clip(ix, 0, W - 1)
    out = values.copy()
    m = ~valid
    out[m] = values[iy[m], ix[m]]
    return out


def main(argv=None):
    """コマンドラインと同じ引数のリストで呼べる (Houdini から呼ぶ時など)。argv を省略すると sys.argv"""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--top', required=True)
    ap.add_argument('--mask')
    ap.add_argument('--bottom')
    ap.add_argument('--roof')
    ap.add_argument('--ground', help='地面と壁の色 (RGB)。渡すとタイルに切り出す (中身は変えない)')
    ap.add_argument('--out', default='baked')
    ap.add_argument('--wrap', action='store_true', help='マップが上下左右にそのまま繰り返してつながる (距離をまたいで計算する)')
    ap.add_argument('--dist-scale', type=float, default=2.0, help='B が 1 テクセルあたりいくつ増えるか (既定 2 → 最大 127.5 テクセル)')
    ap.add_argument('--alpha-width', type=float, default=2.0, help='roof_A が 0→1 に変わる片側の幅 (テクセル、既定 2)')
    ap.add_argument('--upsample', type=int, default=4, help='輪郭を求めるときの拡大率 (既定 4)')
    ap.add_argument('--cone-scale', type=int, default=2, help='円錐マップの縮小率 (既定 2 = 半分の解像度)')
    ap.add_argument('--cone-reach', type=int, default=256, help='円錐で探す距離 (縮小後のテクセル、既定 256)')
    ap.add_argument('--core', type=int, help='タイルのコアの幅 (テクセル)。渡すとタイルに切り出す')
    ap.add_argument('--margin', type=int, default=0, help='タイルの片側マージン (テクセル)')
    a = ap.parse_args(argv)
    print('計算:', 'scipy + Pillow' if BACKEND == 'scipy' else 'numpy だけ (scipy / Pillow なし)')
    os.makedirs(a.out, exist_ok=True)

    top = load_gray(a.top)
    H, W = top.shape
    bottom = load_gray(a.bottom) if a.bottom else np.zeros_like(top)
    cov = load_gray(a.mask) / 255.0 if a.mask else (top > 0).astype(np.float32)
    for name, arr in (('bottom', bottom), ('mask', cov)):
        if arr.shape != top.shape:
            sys.exit(f'{name} の大きさ {arr.shape[::-1]} が top {top.shape[::-1]} と違います')
    if not a.mask:
        print('注意: --mask がないので、輪郭はテクセル単位の階段になります')

    # ---- 1. 高さを 4 の倍数にそろえる (ASTC で ±1 ずれても、読むときに丸めて戻せる) ----
    def snap4(v):
        return np.clip(np.round(v / 4) * 4, 0, 252)
    topq = np.where(top > 0, np.maximum(snap4(top), 4), 0)
    botq = np.where(top > 0, snap4(bottom), 0)
    botq = np.minimum(botq, np.maximum(topq - 4, 0))
    moved = int(((top > 0) & (topq != np.round(top))).sum())
    if moved:
        print(f'高さを 4 の倍数にそろえました ({moved} テクセル)')

    # ---- 2. なめらかな輪郭 (符号付き距離、テクセル単位) ----
    sd = fine_sdf(cov, a.wrap, up=a.upsample)

    # ---- 3. data の R / G:輪郭に少しでもかかるテクセルを建物にする (外側 0.75 テクセルまで) ----
    solid = sd < 0.75
    has = topq > 0
    if not has.any():
        sys.exit('top に建物がありません')
    topf = nearest_fill(topq, has, a.wrap)          # 広げたテクセルには一番近い建物の高さを入れる
    botf = nearest_fill(botq, has, a.wrap)
    R = np.where(solid, botf, EMPTY).astype(np.int32)
    G = np.where(solid, topf, 0).astype(np.int32)

    # ---- 4. data の B:同じ (R, G) の領域ごとに、境界までの距離 ----
    key = R * 256 + G
    maxd = 255.0 / a.dist_scale
    P = int(maxd) + 2
    kp = pad(key, P, a.wrap)
    dist = np.zeros((H, W), np.float32)
    for k in np.unique(key):
        d = edt(kp == k)[P:P + H, P:P + W]
        m = key == k
        dist[m] = d[m]
    B = np.clip(np.floor(np.maximum(dist - 1.0, 0) * a.dist_scale), 0, 255)   # 少し小さめ (安全側)

    # ---- 5. 円錐マップ:自分より高い建物までの距離 ÷ 高さの差 の最小 (縮小した解像度) ----
    F = a.cone_scale
    if H % F or W % F:
        sys.exit(f'マップの大きさが --cone-scale {F} で割り切れません')
    nh, nw = H // F, W // F
    topz = np.where(R < EMPTY, G, 0)
    base = topz.reshape(nh, F, nw, F).min(axis=(1, 3)) / 255.0          # 区画の中の一番低い所
    reach = a.cone_reach
    kmin = np.full((nh, nw), np.inf)
    for lv in np.unique(G[R < EMPTY]):
        feat = ((R < EMPTY) & (G == lv)).reshape(nh, F, nw, F).any(axis=(1, 3))
        fp = pad(feat, reach, a.wrap) if a.wrap else np.pad(feat, reach)
        d = edt(~fp)[reach:reach + nh, reach:reach + nw]
        d = np.minimum(d, reach)                                          # 探す範囲の外は「その距離にある」とみなす (安全側)
        dh = lv / 255.0 - base
        dd = np.maximum(d - 1.5, 0) * F / W                               # マップ幅を 1 とする距離
        k = np.where(dh > 0, dd / np.maximum(dh, 1e-6), np.inf)
        kmin = np.minimum(kmin, k)
    kf = np.where(np.isinf(kmin), 0.0, kmin)
    cone = np.where(np.isinf(kmin), 254, np.minimum(np.floor(255 * kf / (kf + 0.1)), 254))

    # ---- 6. roof の A (なめらかな輪郭) と、壁の色を置く範囲 ----
    A = np.clip(0.5 - sd / (2 * a.alpha_width), 0, 1) * 255
    wall = (sd < -1.5) & (R == 0)                                        # 地面から立つ物の、輪郭より 1.5 テクセル内側

    outs = {'data_R': R, 'data_G': G, 'data_B': B, 'roof_A': A, 'cone': cone, 'wall_mask': wall * 255}

    # ---- 7. 屋根の色:建物の外を一番近い屋根の色で埋める (ミップと ASTC で縁がにじまないように) ----
    if a.roof:
        rc = read_image(a.roof)[..., :3].astype(np.float32)
        if rc.shape[2] == 1: rc = np.repeat(rc, 3, axis=2)
        if rc.shape[:2] != (H, W):
            sys.exit('roof の大きさが top と違います')
        inside = sd < 0.0
        filled = np.stack([nearest_fill(rc[..., c], inside, a.wrap) for c in range(3)], -1)
        outs['roof_RGB'] = filled

    if a.ground:
        gc = read_image(a.ground)[..., :3].astype(np.float32)
        if gc.shape[2] == 1: gc = np.repeat(gc, 3, axis=2)
        if gc.shape[:2] != (H, W):
            sys.exit('ground の大きさが top と違います')
        outs['ground_RGB'] = gc

    def save(arr, path):
        write_image(path, arr)

    for n, arr in outs.items():
        save(arr, os.path.join(a.out, n + '.png'))

    # ---- 8. タイルに切り出す (任意) ----
    info = [f'map_size        = {W} x {H}',
            f'DIST_SCALE      = {a.dist_scale}   (シェーダーの DIST_SCALE)',
            f'CONE_MAP_W      = {W}.0   (シェーダーの CONE_MAP_W)',
            f'cone の解像度   = {nw} x {nh} (1/{F})',
            f'建物の高さの段  = {sorted(set(np.unique(G[R < EMPTY]).tolist()))}']
    if a.core:
        C, M = a.core, a.margin
        warn = []
        if C % 4: warn.append('コアが 4 の倍数ではありません (ASTC のブロックがそろわない)')
        if M % (4 * F): warn.append(f'マージンが {4 * F} の倍数ではありません (cone も含めて ASTC のブロックがそろわない)')
        if W % C or H % C: warn.append('マップの大きさがコアで割り切れません')
        for w_ in warn: print('注意:', w_)
        S = C + 2 * M
        td = os.path.join(a.out, 'tiles'); os.makedirs(td, exist_ok=True)

        def cut(img, ox, oy, s, f=1):
            hh, ww = img.shape[:2]
            ys = np.arange(oy // f, oy // f + s // f); xs = np.arange(ox // f, ox // f + s // f)
            ys = ys % hh if a.wrap else np.clip(ys, 0, hh - 1)
            xs = xs % ww if a.wrap else np.clip(xs, 0, ww - 1)
            return img[np.ix_(ys, xs)]
        for j in range(H // C):
            for i in range(W // C):
                name = f'{i}_{j}'
                for n, arr in outs.items():
                    f = F if n == 'cone' else 1
                    save(cut(arr, i * C - M, j * C - M, S, f), os.path.join(td, f'{name}_{n}.png'))
        info += [f'CORE            = {C}.0   (シェーダーの CORE)', f'MARGIN          = {M}  (タイルの幅 {S}、cone は {S // F})',
                 f'タイル          = {W // C} x {H // C} 枚 (tiles/横_縦_*.png、画像の左上が 0_0)']
    open(os.path.join(a.out, 'bake_info.txt'), 'w', encoding='utf-8').write('\n'.join(info) + '\n')
    print('\n'.join(info))
    print('出力:', os.path.abspath(a.out))


run = main

if __name__ == '__main__':
    main()
