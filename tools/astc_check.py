#!/usr/bin/env python3
"""
astc_check.py ― ASTC に変換したテクスチャが、シェーダーの許容範囲に収まっているかを調べる

ASTC を PNG に戻したもの (astcenc -dl で復元したもの) と、変換前の PNG を比べる。

  astcenc -cl tileA_data.png tileA_data.astc 4x4 -medium      # 変換
  astcenc -dl tileA_data.astc tileA_data_dec.png              # 確認用に PNG へ戻す
  python3 astc_check.py --kind data --orig tileA_data.png --decoded tileA_data_dec.png

--kind
  data     R 下端 / G 上端 / B 距離 (city_bake.py の data_R/G/B を格納したもの)
  cone     円錐ステップ値 (1 チャンネル)
  outline  なめらかな輪郭 (1 チャンネル)

シェーダー (city_tile_fn.glsl) が許せる範囲
  data R : 空き地 (255) が 250 以上のまま、それ以外は ±1 以内
  data G : ±1 以内 (4 の倍数に丸めて元に戻る)
  data B : 大きく戻る量が 6 コード以内 (ASTC_SAFE で 6 コード小さく読むため)
  cone   : 大きく戻る量が 6 コード以内
  outline: 輪郭のずれが 0.25 テクセル以内 (目安。1 テクセル = 63.75 コード)
"""
import argparse, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from city_bake import read_image      # PNG の読み込み (numpy だけでも動く)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kind', required=True, choices=['data', 'cone', 'outline'])
    ap.add_argument('--orig', required=True, help='変換前の PNG')
    ap.add_argument('--decoded', required=True, help='ASTC を PNG に戻したもの')
    a = ap.parse_args(argv)
    o = read_image(a.orig); d = read_image(a.decoded)
    if o.shape[:2] != d.shape[:2]:
        sys.exit(f'大きさが違います:{o.shape[1]}x{o.shape[0]} と {d.shape[1]}x{d.shape[0]}')
    ok = True

    def report(name, good, text):
        nonlocal ok
        ok &= good
        print(('  OK   ' if good else '  NG   ') + name + ':' + text)

    if a.kind == 'data':
        if o.shape[2] < 3 or d.shape[2] < 3:
            sys.exit('data は RGB の画像を渡してください')
        R0, G0, B0 = (o[..., i] for i in range(3)); R1, G1, B1 = (d[..., i] for i in range(3))
        empty = R0 >= 255
        minEmpty = R1[empty].min() if empty.any() else 255
        eR = np.abs(R1 - R0)[~empty].max() if (~empty).any() else 0
        report('R 空き地', minEmpty >= 250, f'255 の所は最小 {minEmpty:.0f} に戻った (250 以上が必要)')
        report('R 下端の高さ', eR <= 1.5, f'最大 {eR:.1f} コードずれた (1 以内が必要)')
        solid = ~empty
        eG = np.abs(G1 - G0)[solid].max() if solid.any() else 0
        not4 = int((np.round(G0[solid]) % 4 != 0).sum())
        back = int((np.round(G1[solid] / 4) * 4 != np.round(G0[solid])).sum())
        report('G 上端の高さ', eG <= 1.5 and back == 0,
               f'最大 {eG:.1f} コードずれた、4 の倍数に丸めて戻らないテクセル {back}' + (f' (元の G で 4 の倍数でないもの {not4})' if not4 else ''))
        over = (B1 - B0).max()
        report('B 距離', over <= 6, f'大きく戻った量 最大 {over:.1f} コード (6 以内が必要)')
    else:
        v0 = o[..., 0]; v1 = d[..., 0]
        if a.kind == 'cone':
            over = (v1 - v0).max()
            report('cone', over <= 6, f'大きく戻った量 最大 {over:.1f} コード (6 以内が必要)')
        else:
            band = (v0 > 0) & (v0 < 255)
            e = np.abs(v1 - v0)[band] / 63.75 if band.any() else np.zeros(1)
            report('outline', e.max() <= 0.25, f'輪郭のずれ 99% {np.percentile(e, 99):.3f} / 最大 {e.max():.3f} テクセル (0.25 以内が目安)')

    # よくある原因の見分け:全体が一方向にずれている → sRGB で変換・復元している
    ch = 1 if a.kind == 'data' else 0                    # data は G (高さ) で見る
    mid = (o[..., ch] > 60) & (o[..., ch] < 200)
    if mid.any() and abs((d[..., ch] - o[..., ch])[mid].mean()) > 8:
        print('  注意 中間の値が全体に {:+.1f} ずれています。sRGB で変換・復元していないか確認してください'
              ' (data / cone / outline は astcenc -cl / -dl、エンジンでは sRGB オフ)'.format((d[..., ch] - o[..., ch])[mid].mean()))
    print('結果:', '許容範囲に収まっています' if ok else '許容範囲を超えています')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
