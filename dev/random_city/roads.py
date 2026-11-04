# 道路の定義 (1_layout.py と 2_textures.py で共有)
# 座標は 1024 基準で書き、K 倍してテクスチャ解像度 N に合わせる
import math, numpy as np
N = 4096   # 元の 2048 の 2 倍で作り、輪郭の細かさ (アンチエイリアス) を残して 2048 に縮める
K = N / 1024
def _c(a, b, period):   # a + b*cos(2π t / period) を N 基準で
    return lambda t: K * (a + b * math.cos(2 * math.pi * (t / K) / period))
# kind 'h': y = f(x) / kind 'v': x = f(y)。端で接線が端に垂直なのでミラーで滑らかにつながる
ELEVATED = [
    dict(kind='h', f=_c(520, 150, 1024), w=46 * K),
    dict(kind='v', f=_c(740, 90, 1024), w=46 * K),
]
GROUND = [
    # 高架の下を走る広い道路 (中央分離帯に橋脚が立つ)
    dict(kind='h', f=ELEVATED[0]['f'], w=66 * K, median=20 * K),
    dict(kind='v', f=ELEVATED[1]['f'], w=66 * K, median=20 * K),
    # 曲がった一般道
    dict(kind='v', f=_c(300, 120, 2048), w=40 * K),
    dict(kind='h', f=_c(230, -90, 2048), w=40 * K),
    dict(kind='h', f=_c(840, 60, 2048), w=40 * K),
    # 追加した一般道 (道路量 1.25 倍)
    dict(kind='v', f=_c(560, 70, 2048), w=40 * K),
    dict(kind='h', f=_c(400, 40, 2048), w=40 * K),
    dict(kind='v', f=_c(120, 50, 2048), w=36 * K),
    # タイルの端に沿った道路 (半分ずつ。ミラーで1本の道路になる)
    dict(kind='h', f=lambda x: 0.0, w=44 * K),
    dict(kind='h', f=lambda x: float(N), w=44 * K),
    dict(kind='v', f=lambda y: 0.0, w=44 * K),
    dict(kind='v', f=lambda y: float(N), w=44 * K),
]
def line(r, off=0.0, step=2.0):
    """中心線から off だけ横にずらした折れ線"""
    f = r['f']; pts = []
    for t in np.arange(-12 * K, N + 13 * K, step):
        a = f(t); da = (f(t + 0.5) - f(t - 0.5))
        l = math.hypot(da, 1.0)
        if r['kind'] == 'h': pts.append((t - da / l * off, a + off / l))
        else:                pts.append((a + off / l, t - da / l * off))
    return pts
def band(r, w, step=2.0):
    return line(r, w / 2, step) + line(r, -w / 2, step)[::-1]
def along(pts, sp):
    out = []; acc = sp * 0.5
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        while acc <= L:
            t = acc / L; out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)); acc += sp
        acc -= L
    return out
def dashes(pts, on, off):
    segs = []; cur = []; acc = 0; state = True; lim = on
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if state: cur.append((x0, y0))
        acc += math.hypot(x1 - x0, y1 - y0)
        if acc >= lim:
            if state: cur.append((x1, y1)); segs.append(cur); cur = []
            state = not state; acc = 0; lim = on if state else off
    return segs
