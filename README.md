# 俯瞰シティ:ポリゴンタイル版

2.5D のハイトフィールドを、画面に平行な四角ポリゴンを敷き詰めて描くレイマーチのシェーダーと、
そのテクスチャを作るツールです。

- ポリゴン UV がテクスチャのコア (`TEX_CORE`) に対応する。ポリゴンの大きさとテクスチャの解像度は別に決められ、ズームはポリゴンの拡大縮小で行う (デモは 1 枚 2000 × 2000)
- ポリゴン 1 枚 = タイル 1 枚 = テクスチャ 5 枚 (data / roof / ground / cone / outline)。テクスチャ配列は使わない
- 視差で隣から倒れ込む建物や影のために、各テクスチャはコアの周りにマージンを持つ
- ASTC 4x4 で圧縮しても形が崩れないように作ってある

## 中身

| フォルダ | 内容 |
|---|---|
| `shader/city_tile_fn.glsl` | 描画関数 `cityTile(screenUV, polyUV)`。引数は 2 つの UV だけ、サンプラーは外のコードで宣言する |
| `tools/city_bake.py` | 高さの画像と建物マスクから、各チャンネル (data R/G/B、outline、cone ほか) を作るツール。numpy だけで動く (Houdini の Python でも可) |
| `tools/astc_check.py` | ASTC に変換したテクスチャが、シェーダーの許容範囲に収まっているかを調べる |
| `tools/README.md` | ツールの使い方、入力画像の描き方、チャンネルの割り当て、シェーダーへの組み込み方 |
| `tools/sample/input/` | サンプルの入力画像 (横 2048 × 縦 1024、上下左右につながる街) |
| `demo/city_polytile.html` | ブラウザで開けるデモ (テクスチャ埋め込み済み、WebGL2) |
| `docs/tile*_textures.png` | サンプルのタイル A / B のテクスチャを、チャンネルごとに並べた図 |
| `dev/` | サンプルの街の生成と、ASTC の検証に使ったスクリプト |

## すぐ試す

```
cd tools
python3 city_bake.py --top sample/input/top.png --mask sample/input/mask.png \
                     --bottom sample/input/bottom.png --roof sample/input/roof_color.png \
                     --out baked --wrap --core 1024 --margin 192
```

詳しくは [tools/README.md](tools/README.md) を見てください。
