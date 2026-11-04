# city_bake ― cityTile() 用テクスチャの生成

高さの画像と建物マスクから、`city_tile_fn.glsl` の `cityTile()` が使う各チャンネルを作ります。
出力は **1 チャンネルずつのグレースケール PNG** です。テクスチャへのチャンネルの格納は手元で行ってください。

## 準備

必要なのは **numpy だけ** です (Houdini に付いている Python でそのまま動きます)。

- scipy と Pillow が入っていれば自動でそちらを使い、速くなります (2048 × 1024 で約 15 秒)。
- なければ numpy だけで同じ計算をします (同じ大きさで約 55 秒)。出力は scipy 版と 1 画素も違いません。
- ふつうの Python で速く回したい時は `pip install numpy scipy pillow`。
- 環境変数 `CITY_BAKE_PURE=1` を付けると、scipy があっても numpy だけで計算します (確認用)。

numpy だけの時に読める PNG は、8 / 16 bit のグレー・RGB・RGBA・パレット (インターレースなし) です。
出力は 8 bit の PNG です。

## 用意する画像

すべて **同じ解像度** の PNG で、マップ全体を 1 枚にします (タイルへの切り出しはツールが行います)。

| 引数 | 内容 | 描き方 |
|---|---|---|
| `--top` (必須) | 上端の高さ。0 = 何もない、1〜255 = 建物の屋根の高さ | **アンチエイリアスなし**。縁で高さが混ざると中間の高さができてしまう。4 の倍数で描くのがおすすめ (ずれていても 4 の倍数にそろえる) |
| `--mask` | 建物マスク。白 = 建物、黒 = 何もない | **アンチエイリアスあり**。縁の灰色の濃さから、輪郭をテクセルより細かく求める。省略すると `--top` の白黒になり、斜めの辺は階段になる |
| `--bottom` | 下端の高さ。0 = 地面から立つ、高架などは床の下端の高さ | アンチエイリアスなし。省略すると全部 0 |
| `--roof` | 屋根の色 (RGB) | 建物の外側の色は何でもよい (ツールが一番近い屋根の色で埋める) |
| `--ground` | 地面と壁の色 (RGB) | `wall_mask.png` を見ながら手で作ったもの。ほかと同じマージンでタイルに切り出すだけ |

- `--top` と `--mask` の建物の範囲はそろえてください。マスクの輪郭 (灰色 50%) の内側に、`--top` の高さが入っている必要があります。
- 高架の柱のように、高架の床の下にあって地面から立つ物は、`--top` = 床の上端、`--bottom` = 0 にします。

## 実行

```
python3 city_bake.py --top top.png --mask mask.png --bottom bottom.png --roof roof_color.png \
                     --out baked --wrap --core 1024 --margin 192
```

| 引数 | 既定 | 内容 |
|---|---|---|
| `--out` | `baked` | 出力するフォルダ |
| `--wrap` | なし | マップが上下左右にそのまま繰り返してつながる場合に付ける。距離をマップの端の向こう側までつなげて計算する |
| `--core` | なし | タイルのコアの幅 (ポリゴンに映る範囲)。付けると `tiles/` にタイルごとの画像も作る |
| `--margin` | 0 | タイルの片側マージン |
| `--dist-scale` | 2 | B が 1 テクセルあたりいくつ増えるか (2 なら最大 127.5 テクセル) |
| `--alpha-width` | 2 | outline が 0 → 1 に変わる片側の幅 (テクセル) |
| `--upsample` | 4 | 輪郭を求めるときの拡大率 |
| `--cone-scale` | 2 | 円錐マップの縮小率 (2 = 半分の解像度) |
| `--cone-reach` | 256 | 円錐で高い建物を探す距離 (縮小後のテクセル)。これより遠くは「この距離にある」とみなす (安全側) |

ASTC 4x4 で圧縮する場合、`--core` は 4 の倍数、`--margin` は 4 × `--cone-scale` の倍数 (既定なら 8 の倍数) にしてください。
外れているとツールが注意を出します。ブロックの位置がそろっていれば、隣のタイルと重なる部分は同じ値に復元されます。

## 出力とチャンネルの割り当て

| ファイル | 格納先 | 内容 |
|---|---|---|
| `data_R.png` | data の R | 下端の高さ (255 = 空き地) |
| `data_G.png` | data の G | 上端の高さ (4 の倍数) |
| `data_B.png` | data の B | 同じ高さの領域の境界までの距離 |
| `roof_RGB.png` | roof の RGB | 建物の外を一番近い屋根の色で埋めた屋根の色 (`--roof` のとき) |
| `outline.png` | outline (1 チャンネル) | なめらかな輪郭 (0.5 = 輪郭)。**ほかのチャンネルと一緒にしないこと** (下の「ASTC」) |
| `cone.png` | cone (1 チャンネル) | 円錐ステップ値 (`--cone-scale` 分の 1 の解像度) |
| `ground_RGB.png` | ground の RGB | `--ground` をそのまま (タイルに切り出すため) |
| `wall_mask.png` | (ground を作るときの目安) | 白の範囲に壁の色を置く。輪郭より 1.5 テクセル内側の、地面から立つ物の中 |
| `bake_info.txt` | — | シェーダーの定数に入れる値 |

`--core` を付けた場合は、同じものが `tiles/横_縦_名前.png` (画像の左上が `0_0`) にタイルごとに出ます。
タイルの幅は `コア + 2 × マージン`、cone はその `1 / --cone-scale` です。

ground テクスチャは手で作ります。地面の色を描き、`wall_mask.png` の白の範囲に壁の色を置いてください
(壁の色は建物の中に置いておくと、シェーダーが壁を描くときに輪郭の 2 テクセル内側から読みます)。

## マージンはすべてのテクスチャに要る

ポリゴンに映る建物のうち、視差で隣のタイルから倒れ込んでくるものは、マージンの中にあるデータで描きます。
そのため data と cone だけでなく、roof と ground にも同じマージンが要ります。
シェーダーも 5 枚が同じ並び (コア + 片側マージン) である前提で読んでいます。

| テクスチャ | マージンで使われるもの | 必要な幅 (片側) |
|---|---|---|
| data / cone | 倒れ込んでくる建物の形、隣から伸びる影 | 視差と影の大きい方 |
| roof / outline | 倒れ込んでくる建物の屋根の色と輪郭 | 視差 |
| ground | 倒れ込んでくる建物の壁の色 (建物の中に置いてある) | 視差 |

並びをそろえるため、ツールはどれも同じマージンで切り出します。

## テクスチャの設定

| テクスチャ | フィルター | ミップ | 色空間 |
|---|---|---|---|
| data (RGB) | NEAREST | なし | リニア |
| cone (R) | NEAREST | なし | リニア |
| roof (RGB) | LINEAR | あり | sRGB でよい |
| outline (R) | LINEAR | なし | リニア |
| ground (RGB) | LINEAR | あり | sRGB でよい |

ラップはどれも CLAMP にします (マージンがあるので繰り返しは不要)。
data / cone / outline は **sRGB にしない** でください。値がそのまま読まれる前提で、sRGB で読まれると高さも距離も輪郭も別の値になります。

## ASTC 4x4

- **outline は 1 チャンネルだけのテクスチャにします。** 以前は roof の A に入れていましたが、ASTC はブロックの全チャンネルをまとめて圧縮するので、
  屋根の色に模様があると輪郭が引きずられてずれます。模様のある屋根で測ると、roof の A では輪郭が最大 0.9 テクセル (99% で 0.36) ずれました。
  1 チャンネルだけなら最大 0.08 テクセル (99% で 0.03) です。
- data (RGB) は 1 枚のまま圧縮してかまいません。高さは 4 の倍数なので ±1 のずれはシェーダーで丸めて戻せます。
  距離 B と cone は、大きく戻った所で建物を飛び越さないように、シェーダーが 6 コード小さく読みます (実測の超過は最大 3 コード)。
- data に別のチャンネル (輪郭や cone) を足して RGBA にすると、高さの誤差が ±12 程度に増えて丸めで戻せなくなります。足さないでください。
- コアとマージンを 4 の倍数 (cone が半分なら 8 の倍数) にすると、隣のタイルとの重なりが同じ値に戻ります。

## シェーダー側

`city_tile_fn.glsl` の `cityTile(screenUV, polyUV)` を使います。

1. サンプラーは外のコードで `uCityData` / `uCityRoof` / `uCityGround` / `uCityCone` / `uCityOutline` の名前で宣言します。名前が違う場合は、glsl の中のこの 5 つの名前を一括置換します (glsl の中に `#define` はありません)。
2. 関数の先頭の「調整する値」(画角、光の向き、建物の高さ、フラグ) をシーンに合わせて書き換えます。
3. 「マッピング」の `TEX_CORE` (ポリゴンに映る範囲) と `TEX_SIZE` (マージン込みの全体)、「定数」の `DIST_SCALE` / `CONE_MAP_W` を `bake_info.txt` の値に合わせます。
   - ポリゴン UV 0..1 が `TEX_CORE` の範囲に対応します。ポリゴンの大きさ (画面のピクセル数) は自由で、ズームはポリゴンの拡大縮小で決まります。
   - テクスチャの実際の解像度が `TEX_SIZE` と違っても、`TEX_SIZE` 全体に引き伸ばして読みます (例えば半分の解像度のテクスチャに差し替えても位置は合う)。
     高さ・距離・円錐はこの単位で扱うので、`HEIGHT_SCALE` と `CONE_MAP_W` もこの単位で考えます。

4. **精度はすべて highp にします。** 影や起伏にノイズが出る場合、まずここを確認してください。
   - 関数の中の計算は highp で宣言してありますが、入力と読み込みは外のコード次第です。
   - `polyUV` の varying は頂点シェーダーとフラグメントシェーダーの両方で `highp` で宣言します。half / mediump の UV では、
     位置が 1/2048 単位に丸められ、さらに UV の微分 (ズームと視点の位置を求めている) が大きく乱れます。
   - サンプラーも `highp` にします (`precision highp sampler2D;` または `uniform highp sampler2D ...`)。
     フラグメントシェーダーのサンプラーの既定は lowp で、輪郭の線形補間や距離の精度が落ちます。
   - エンジンの都合で UV の精度を上げられない場合は、関数の中の `SCREEN_W_PX` / `SCREEN_H_PX` / `POLY_PX`
     (画面の大きさと、ポリゴン 1 枚の画面上の大きさ) に値を入れてください。微分を使わなくなり、ノイズの大部分が消えます。

```glsl
precision highp float;
precision highp sampler2D;
uniform sampler2D uCityData, uCityRoof, uCityGround, uCityCone, uCityOutline;   // 外のコードでの宣言
#include "city_tile_fn.glsl"                                      // (または中身を貼り付ける)

in highp vec2 vPolyUV;           // ポリゴンの UV (0..1、コアの範囲)。頂点シェーダー側も highp
uniform vec2 uScreenSize;
out vec4 fragColor;
void main() {
    fragColor = cityTile(gl_FragCoord.xy / uScreenSize, vPolyUV);
}
```

## Houdini から使う

**hython (コマンドライン)**

```
hython city_bake.py --top top.png --mask mask.png --out baked --wrap --core 1024 --margin 192
```

`hython` は Houdini のインストール先の `bin` にあります。

**Python シェル・シェルフツール・TOPs の Python Script など (Houdini の中)**

```python
import sys, importlib
sys.path.append(r'C:/tools/city-bake')          # city_bake.py を置いたフォルダ
import city_bake
importlib.reload(city_bake)                     # スクリプトを書き換えた時に読み直す
city_bake.run([
    '--top',    hou.text.expandString('$HIP/tex/top.png'),
    '--mask',   hou.text.expandString('$HIP/tex/mask.png'),
    '--bottom', hou.text.expandString('$HIP/tex/bottom.png'),
    '--out',    hou.text.expandString('$HIP/tex/baked'),
    '--wrap', '--core', '1024', '--margin', '192',
])
```

`run()` にはコマンドラインと同じ引数をリストで渡します。

**COP と組み合わせる流れ**

1. COP で `top` (アンチエイリアスなし) と `mask` (アンチエイリアスあり) を作り、PNG に書き出す
2. 上のどちらかの方法で `city_bake.py` を実行する
3. 出力の PNG を COP のファイル読み込みノードで読み、チャンネルを組んでテクスチャにする

Houdini の画面の中で実行すると、計算が終わるまで (numpy だけなら 1 分ほど) 操作が止まります。
大きなマップは hython か TOPs で回すのがおすすめです。

## 試す

`sample/input/` に、デモの街の入力画像 (横 2048 × 縦 1024、上下左右につながる) が入っています。

```
python3 city_bake.py --top sample/input/top.png --mask sample/input/mask.png \
                     --bottom sample/input/bottom.png --roof sample/input/roof_color.png \
                     --out baked --wrap --core 1024 --margin 192
```

手元で 15 秒ほどかかりました (2048 × 1024)。メモリは輪郭の計算を 512 テクセルずつ区切って行うので、大きなマップでも増えにくくしてあります。
