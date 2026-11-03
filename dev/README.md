# dev:サンプルの生成と検証用スクリプト

本番の作業には不要です。サンプルの街を作り直したり、ASTC の誤差を測ったりする時に使います。
どれも `dev/` フォルダで実行し、結果は `dev/out/` に出ます。

| スクリプト | 内容 | 必要なもの |
|---|---|---|
| `gen_ab.py [マージン]` | サンプルの街 (タイル A / B が横につながる) と、`city_bake.py` 用の入力画像を作る | numpy, scipy, pillow |
| `astc_ab.py [品質]` | タイルの data / cone を ASTC 4x4 で圧縮 → 復元し、誤差と継ぎ目の一致を調べる | + astc-encoder-py |
| `astc_albedo.py [品質]` | roof / ground / outline を同じく圧縮して、輪郭のずれを調べる (roof の α に入れた場合との比較つき) | + astc-encoder-py |
| `astc_rt.py` | 上の 2 つが使う、圧縮 → 復元の関数 | astc-encoder-py |
| `sheet.py` | タイルのテクスチャをチャンネルごとに並べた図を作る | pillow、日本語フォント (Noto Sans CJK) |

```
pip install numpy scipy pillow astc-encoder-py
python3 gen_ab.py 192
python3 astc_ab.py MEDIUM
```
