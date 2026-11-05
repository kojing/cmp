#!/usr/bin/env python3
"""
city_bake.py ― 高さの画像と建物マスクから、cityTile() 用の各チャンネルを作る

人が用意するもの (グレースケール PNG。マップ全体 1 枚。top / bottom だけ出力の N 倍の解像度でもよい)
  --top     上端の高さ。0 = 何もない、1..255 = 建物の上端 (アンチエイリアスなし)
            N 倍 (2 倍、4 倍など) の解像度で渡すと、段 (基壇と塔、高架の床と柱) の輪郭も 1/N テクセルの細かさになる
  --mask    建物マスク。白 = 建物 (アンチエイリアスあり。縁の灰色から外側の輪郭をテクセルより細かく求める)
            出力の解像度で渡す。top がその N 倍なら N を自動で決める
            省略すると --top > 0 から作る (top が N 倍なら N×N の割合がアンチエイリアスになる。1 倍なら階段)
  --bottom  下端の高さ (省略可)。0 = 地面から立つ、高架などは床の下端の高さ
  --roof    屋根の色 (RGB、省略可)。渡すと建物の外側を一番近い屋根の色で埋めた画像も作る
  --ground  地面と壁の色 (RGB、省略可)。渡すとほかと同じマージンでタイルに切り出す

作るもの (--out のフォルダに、1 チャンネルずつのグレースケール PNG)
  data_R.png    下端の高さ (255 = 空き地)                → data テクスチャの R
  data_G.png    上端の高さ (4 の倍数)                    → data テクスチャの G
  data_B.png    同じ高さの領域の境界までの距離            → data テクスチャの B
  outline.png   一番近い境界までの距離 (0〜2 テクセル)    → outline テクスチャ (1 チャンネル)
                境界は外側の輪郭と段の境目の両方。シェーダーが高さごとに符号を付けて輪郭にする
  cone.png      円錐ステップ値 (半分の解像度)             → cone テクスチャ (R8)
  wall_mask.png 地面テクスチャに壁の色を置く範囲 (白)     → ground の RGB を作るときの目安
  roof_RGB.png  屋根の色。縁と建物の外を内側の色で埋めたもの (--roof のとき) → roof テクスチャの RGB
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
    """wrap: True = そのまま繰り返す、'mirror' = 鏡に映して繰り返す、False = 端を伸ばす"""
    return np.pad(a, p, mode='symmetric' if wrap == 'mirror' else 'wrap' if wrap else 'edge')


def wrap_idx(i, n, wrap):
    """マップの外の添字を、マップの中に戻す (pad と同じつながり方)"""
    if wrap == 'mirror':
        j = i % (2 * n)
        return np.where(j >= n, 2 * n - 1 - j, j)
    return i % n if wrap else np.clip(i, 0, n - 1)


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


def tier_dist(topq, botq, N, wrap, limit=2.0, chunk=256):
    """建物どうしで (下端, 上端) が変わる境目までの距離 (出力のテクセル単位、テクセルの中心から)。
    topq / botq は出力の N 倍の解像度。境目に接する画素までの距離変換を N 倍の解像度で行い、テクセルの中心で読む。
    使うのは境目の近く (limit テクセル) だけなので、ブロックごとに処理してメモリを抑える"""
    Hh, Wh = topq.shape
    H, W = Hh // N, Wh // N
    P = (int(np.ceil(limit)) + 2) * N
    out = np.full((H, W), limit + 1.0, np.float32)
    c = N // 2
    for y0 in range(0, H, chunk):
        for x0 in range(0, W, chunk):
            h = min(chunk, H - y0); w = min(chunk, W - x0)
            ys = np.arange(y0 * N - P, (y0 + h) * N + P); xs = np.arange(x0 * N - P, (x0 + w) * N + P)
            ys = wrap_idx(ys, Hh, wrap); xs = wrap_idx(xs, Wh, wrap)
            t = topq[np.ix_(ys, xs)]; b = botq[np.ix_(ys, xs)]
            key = np.where(t > 0, b * 256 + t, -1)
            edge = np.zeros(key.shape, bool)
            for sl0, sl1 in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                             ((slice(None), slice(1, None)), (slice(None), slice(None, -1)))):
                k0 = key[sl0]; k1 = key[sl1]
                e = (k0 >= 0) & (k1 >= 0) & (k0 != k1)
                edge[sl0] |= e; edge[sl1] |= e
            if not edge.any():
                continue
            d = edt(~edge)                                   # 境目に接する画素の中心までの距離 (N 倍の画素)
            d = d[P:P + h * N, P:P + w * N].reshape(h, N, w, N)
            if N % 2 == 0:
                s = d[:, c - 1:c + 1, :, c - 1:c + 1].mean(axis=(1, 3))   # 中心はちょうど画素の角 → まわりの 4 画素の平均
            else:
                s = d[:, c, :, c]
            # 自分の側の、境目に接する画素の中心は境目から 0.5 画素内側 → 0.5 足すと境目までの距離
            out[y0:y0 + h, x0:x0 + w] = np.minimum((s + 0.5) / N, limit + 1.0)
    return out


def nearest_idx(valid, wrap, P=64):
    """各画素から一番近い valid の画素の添字 (iy, ix)"""
    H, W = valid.shape
    vp = pad(valid, P, wrap)
    _, (iy, ix) = edt(~vp, return_indices=True)
    iy = iy[P:P + H, P:P + W] - P; ix = ix[P:P + H, P:P + W] - P
    return wrap_idx(iy, H, wrap), wrap_idx(ix, W, wrap)


def nearest_fill(values, valid, wrap, P=64):
    """valid でない所を、一番近い valid の値で埋める"""
    H, W = valid.shape
    vp = pad(valid, P, wrap)
    _, (iy, ix) = edt(~vp, return_indices=True)
    iy = iy[P:P + H, P:P + W] - P; ix = ix[P:P + H, P:P + W] - P
    iy = wrap_idx(iy, H, wrap); ix = wrap_idx(ix, W, wrap)
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
    ap.add_argument('--mirror', action='store_true', help='マップが上下左右に鏡に映して繰り返してつながる (出力も鏡に映して並べれば、そのまま繰り返すマップになる)')
    ap.add_argument('--dist-scale', type=float, default=2.0, help='B が 1 テクセルあたりいくつ増えるか (既定 2 → 最大 127.5 テクセル)')
    ap.add_argument('--scale', type=int, default=1, help='--mask がない時の top / bottom の倍率 (mask がある時は大きさの比から決める)')
    ap.add_argument('--upsample', type=int, default=4, help='輪郭を求めるときの拡大率 (既定 4)')
    ap.add_argument('--cone-scale', type=int, default=2, help='円錐マップの縮小率 (既定 2 = 半分の解像度)')
    ap.add_argument('--cone-reach', type=int, default=256, help='円錐で探す距離 (縮小後のテクセル、既定 256)')
    ap.add_argument('--core', type=int, help='タイルのコアの幅 (テクセル)。渡すとタイルに切り出す')
    ap.add_argument('--margin', type=int, default=0, help='タイルの片側マージン (テクセル)')
    a = ap.parse_args(argv)
    if a.mirror:
        a.wrap = 'mirror'
    print('計算:', 'scipy + Pillow' if BACKEND == 'scipy' else 'numpy だけ (scipy / Pillow なし)')
    os.makedirs(a.out, exist_ok=True)

    top = load_gray(a.top)
    bottom = load_gray(a.bottom) if a.bottom else np.zeros_like(top)
    if bottom.shape != top.shape:
        sys.exit(f'bottom の大きさ {bottom.shape[::-1]} が top {top.shape[::-1]} と違います')
    # 出力の解像度と、top / bottom の倍率 N (top / bottom だけ N 倍の解像度で渡せる。段の輪郭が 1/N テクセルの細かさになる)
    if a.mask:
        cov = load_gray(a.mask) / 255.0
        H, W = cov.shape
        N = top.shape[0] // H
        if N < 1 or top.shape != (H * N, W * N):
            sys.exit(f'top {top.shape[::-1]} が mask {cov.shape[::-1]} の整数倍になっていません')
    else:
        N = a.scale
        if top.shape[0] % N or top.shape[1] % N:
            sys.exit(f'top の大きさが --scale {N} で割り切れません')
        H, W = top.shape[0] // N, top.shape[1] // N
        cov = (top > 0).reshape(H, N, W, N).mean(axis=(1, 3)).astype(np.float32)    # N 倍なら縁の割合がアンチエイリアスになる
        if N == 1:
            print('注意: --mask がないので、外側の輪郭はテクセル単位の階段になります')
    if N > 1:
        print(f'top / bottom は出力の {N} 倍の解像度として読みます ({W * N} x {H * N} → {W} x {H})')

    # ---- 1. 高さを 4 の倍数にそろえる (ASTC で ±1 ずれても、読むときに丸めて戻せる) ----
    def snap4(v):
        return np.clip(np.round(v / 4) * 4, 0, 252)
    topq = np.where(top > 0, np.maximum(snap4(top), 4), 0).astype(np.int32)
    botq = np.where(top > 0, snap4(bottom), 0).astype(np.int32)
    botq = np.minimum(botq, np.maximum(topq - 4, 0))
    moved = int(((top > 0) & (topq != np.round(top))).sum())
    del top, bottom
    if moved:
        print(f'高さを 4 の倍数にそろえました ({moved} 画素)')

    # ---- 2. 外側の輪郭 (符号付き距離、テクセル単位。マスクのアンチエイリアスから) ----
    sd = fine_sdf(cov, a.wrap, up=a.upsample)

    # ---- 3. data の R / G:テクセルの中心で決める (膨らませない) ----
    #   中心が外側の輪郭の内側なら建物。高さは中心の画素の値 (外れていれば一番近い建物の値)
    solid = sd < 0.0
    c = N // 2
    topc = topq[c::N, c::N]; botc = botq[c::N, c::N]
    has = topc > 0
    if not has.any():
        sys.exit('top に建物がありません')
    topf = nearest_fill(topc, has, a.wrap)
    botf = nearest_fill(botc, has, a.wrap)
    R = np.where(solid, botf, EMPTY).astype(np.int32)
    G = np.where(solid, topf, 0).astype(np.int32)

    # ---- 4. 段の境目 (建物どうしで (R, G) が変わる所) までの距離 (テクセル単位、N 倍の解像度で求める) ----
    dtier = tier_dist(topq, botq, N, a.wrap)
    del topq, botq

    # ---- 5. data の B:同じ (R, G) の領域ごとに、境界までの距離 ----
    key = R * 256 + G
    maxd = 255.0 / a.dist_scale
    P = int(maxd) + 2
    kp = pad(key, P, a.wrap)
    dist = np.zeros((H, W), np.float32)
    for k in np.unique(key):
        d = edt(kp == k)[P:P + H, P:P + W]
        m = key == k
        dist[m] = d[m]
    # 少し小さめ (安全側)。輪郭はテクセルの中心どうしの間 (隣のテクセルとの補間) にあるので、その分 (√2 + 0.7) を引く
    B = np.clip(np.floor(np.maximum(dist - 2.25, 0) * a.dist_scale), 0, 255)

    # ---- 6. 円錐マップ:自分より高い建物までの距離 ÷ 高さの差 の最小 (縮小した解像度) ----
    F = a.cone_scale
    if H % F or W % F:
        sys.exit(f'マップの大きさが --cone-scale {F} で割り切れません')
    nh, nw = H // F, W // F
    topz = np.where(R < EMPTY, G, 0)
    base = topz.reshape(nh, F, nw, F).min(axis=(1, 3)) / 255.0          # 区画の中の一番低い所
    reach = a.cone_reach
    kmin = np.full((nh, nw), np.inf)
    # 建物は中心から最大 0.71 テクセル外まで広がるので、1 テクセル膨らませてから探す (安全側)
    for lv in np.unique(G[R < EMPTY]):
        lvm = (R < EMPTY) & (G == lv)
        lvm = lvm | pad(lvm, 1, a.wrap)[:-2, 1:-1] | pad(lvm, 1, a.wrap)[2:, 1:-1] | pad(lvm, 1, a.wrap)[1:-1, :-2] | pad(lvm, 1, a.wrap)[1:-1, 2:]
        feat = lvm.reshape(nh, F, nw, F).any(axis=(1, 3))
        fp = pad(feat, reach, a.wrap) if a.wrap else np.pad(feat, reach)
        d = edt(~fp)[reach:reach + nh, reach:reach + nw]
        d = np.minimum(d, reach)                                          # 探す範囲の外は「その距離にある」とみなす (安全側)
        dh = lv / 255.0 - base
        dd = np.maximum(d - 1.5, 0) * F / W                               # マップ幅を 1 とする距離
        k = np.where(dh > 0, dd / np.maximum(dh, 1e-6), np.inf)
        kmin = np.minimum(kmin, k)
    kf = np.where(np.isinf(kmin), 0.0, kmin)
    cone = np.where(np.isinf(kmin), 254, np.minimum(np.floor(255 * kf / (kf + 0.1)), 254))

    # ---- 7. 輪郭 (outline、1 チャンネル):一番近い境界までの距離 (符号なし、0〜2 テクセル → 0〜255) ----
    #   境界は外側の輪郭と、段の境目 (塔と基壇、高架の床と柱など) のどちらも。
    #   符号はシェーダーが高さごとに data から付けるので、どの高さでもその高さの輪郭がなめらかに出る
    v = np.minimum(np.abs(sd), dtier)
    A = np.clip(v / 2.0, 0, 1) * 255
    wall = (sd < -1.5) & (R == 0)                                        # 地面から立つ物の、輪郭より 1.5 テクセル内側

    outs = {'data_R': R, 'data_G': G, 'data_B': B, 'outline': A, 'cone': cone, 'wall_mask': wall * 255}

    # ---- 7. 屋根の色:建物の外を一番近い屋根の色で埋める (ミップと ASTC で縁がにじまないように) ----
    if a.roof:
        rc = read_image(a.roof)[..., :3].astype(np.float32)
        if rc.shape[2] == 1: rc = np.repeat(rc, 3, axis=2)
        if rc.shape[:2] != (H, W):
            sys.exit('roof の大きさが top と違います')
        # 境界の近く (1.5 テクセル以内) の色は、同じ領域 (同じ高さ) の内側の一番近い色に置き換える。
        # 描いた屋根の色の縁は輪郭とずれていたり (階段・縮小のにじみ)、段の境目で隣の屋根の色が混ざったりするため。
        # 建物の外は、一番近い屋根の色で埋める (ミップと ASTC で縁がにじまないように)
        # (領域は屋根の高さ G で分ける。高架の床と柱のように屋根の高さが同じなら、上から見える屋根は 1 枚なので分けない)
        filled = rc.copy()
        core = np.zeros((H, W), bool)
        Pg = 4
        for g in np.unique(G[solid]):
            m = solid & (G == g)
            dg = edt(pad(m, Pg, a.wrap))[Pg:Pg + H, Pg:Pg + W]          # 屋根の高さが変わる所までの距離 (中心どうし)
            core |= m & (dg >= 2.0) & (sd <= -1.5)
        for g in np.unique(G[solid]):
            m = solid & (G == g)
            src = m & core
            if not src.any():
                continue
            iy, ix = nearest_idx(src, a.wrap)
            t = m & ~core
            filled[t] = rc[iy[t], ix[t]]
        iy, ix = nearest_idx(core if core.any() else solid, a.wrap)
        filled[~solid] = filled[iy[~solid], ix[~solid]]
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
            ys = wrap_idx(ys, hh, a.wrap); xs = wrap_idx(xs, ww, a.wrap)
            return img[np.ix_(ys, xs)]
        for j in range(H // C):
            for i in range(W // C):
                name = f'{i}_{j}'
                for n, arr in outs.items():
                    f = F if n == 'cone' else 1
                    save(cut(arr, i * C - M, j * C - M, S, f), os.path.join(td, f'{name}_{n}.png'))
        info += [f'TEX_CORE        = {C}.0   (シェーダーの TEX_CORE)', f'TEX_SIZE        = {S}.0   (シェーダーの TEX_SIZE = コア + 2 × マージン {M}、cone は {S // F})',
                 f'タイル          = {W // C} x {H // C} 枚 (tiles/横_縦_*.png、画像の左上が 0_0)']
    open(os.path.join(a.out, 'bake_info.txt'), 'w', encoding='utf-8').write('\n'.join(info) + '\n')
    print('\n'.join(info))
    print('出力:', os.path.abspath(a.out))


run = main

if __name__ == '__main__':
    main()
