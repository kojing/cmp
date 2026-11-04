# dev:サンプルの生成と検証用スクリプト

本番の作業には不要です。サンプルの街を作り直したり、ASTC の誤差を測ったりする時に使います。
どれも `dev/` フォルダで実行し、結果は `dev/out/` に出ます。

| スクリプト | 内容 | 必要なもの |
|---|---|---|
| `gen_ab.py [マージン]` | サンプルの街 (タイル A / B が横につながる) と、`city_bake.py` 用の入力画像を作る (top / bottom は 4 倍の解像度も) | numpy, scipy, pillow |
| `pack_ab.py [baked] [出力先]` | `city_bake.py` の出力を `textures/` の形に詰める (ASTC の復元版も `out/` に) | numpy, pillow (+ astc-encoder-py) |
| `astc_ab.py [品質]` | タイルの data / cone を ASTC 4x4 で圧縮 → 復元し、誤差と継ぎ目の一致を調べる | + astc-encoder-py |
| `astc_albedo.py [品質]` | roof / ground / outline を同じく圧縮して、輪郭のずれを調べる (roof の α に入れた場合との比較つき) | + astc-encoder-py |
| `astc_rt.py` | 上の 2 つが使う、圧縮 → 復元の関数 | astc-encoder-py |
| `sheet.py` | タイルのテクスチャをチャンネルごとに並べた図を作る | pillow、日本語フォント (Noto Sans CJK) |

```
pip install numpy scipy pillow astc-encoder-py
python3 gen_ab.py 192
python3 ../tools/city_bake.py --top out/input/top4x.png --mask out/input/mask.png --bottom out/input/bottom4x.png \
        --roof out/input/roof_color.png --ground out/map_ground.png --out out/baked --wrap --core 1024 --margin 192
python3 pack_ab.py
python3 astc_ab.py MEDIUM
```
