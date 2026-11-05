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

PNG で、マップ全体を 1 枚にします (タイルへの切り出しはツールが行います)。
`--mask` / `--roof` / `--ground` は出力と同じ解像度、**`--top` と `--bottom` だけは出力の N 倍 (2 倍、4 倍…) の解像度でも渡せます**。
N 倍で渡すと、段のある建物 (基壇と塔) や高架の床と柱の境目の輪郭も 1/N テクセルの細かさになります (1 倍だと、その境目は斜めの辺で階段になります)。N は `--mask` との大きさの比から自動で決まります。

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
| `--mirror` | なし | マップが上下左右に鏡に映して繰り返す場合に付ける。出力を鏡に映して並べれば、そのまま繰り返すマップになる (距離も円錐も正しくつながる) |
| `--core` | なし | タイルのコアの幅 (ポリゴンに映る範囲)。付けると `tiles/` にタイルごとの画像も作る |
| `--margin` | 0 | タイルの片側マージン |
| `--dist-scale` | 2 | B が 1 テクセルあたりいくつ増えるか (2 なら最大 127.5 テクセル) |
| `--scale` | 1 | `--mask` を省略した時の `--top` / `--bottom` の倍率 (mask がある時は大きさの比から決まる) |
| `--upsample` | 4 | 輪郭を求めるときの拡大率 |
| `--cone-scale` | 2 | 円錐マップの縮小率 (2 = 半分の解像度) |
| `--cone-reach` | 256 | 円錐で高い建物を探す距離 (縮小後のテクセル)。これより遠くは「この距離にある」とみなす (安全側) |

ASTC 4x4 で圧縮する場合、`--core` は 4 の倍数、`--margin` は 4 × `--cone-scale` の倍数 (既定なら 8 の倍数) にしてください。
外れているとツールが注意を出します。ブロックの位置がそろっていれば、隣のタイルと重なる部分は同じ値に復元されます。

## outline の仕組み (段のある建物)

outline には「テクセルの中心から、一番近い境界までの距離」(符号なし、2 テクセルで飽和) を入れます。
境界は外側の輪郭だけでなく、高さ (data の R, G) が変わる所すべてです。基壇の中の塔、高架の床の中の柱も含みます。

符号はシェーダーが高さ z ごとに付けます。まわりの 4 テクセルそれぞれについて、data の R ≤ z ≤ G なら +、そうでなければ − を付けます。
そして ± 距離を補間し、0 になる所をその高さでの輪郭にします。

- 塔の高さでは、基壇のテクセルは「外」になるので、塔の輪郭がなめらかに出ます。
- 基壇の高さでは、塔も基壇も「中」なので、外側の輪郭が出ます。
- 段の数に制限はなく、8 bit 1 チャンネルのままです。

data の R / G はテクセルの中心で決めます (中心が輪郭の内側なら建物)。以前のように外側へ膨らませることはしません。
B (距離) は、輪郭が隣のテクセルとの間に来る分を見込んで 2.25 テクセル小さく作ります。

## 出力とチャンネルの割り当て

| ファイル | 格納先 | 内容 |
|---|---|---|
| `data_R.png` | data の R | 下端の高さ (255 = 空き地) |
| `data_G.png` | data の G | 上端の高さ (4 の倍数) |
| `data_B.png` | data の B | 同じ高さの領域の境界までの距離 |
| `roof_RGB.png` | roof の RGB | 屋根の色 (`--roof` のとき)。輪郭と、屋根の高さが変わる所から 1.5 テクセル以内は同じ高さの内側の色で塗り直し、建物の外は一番近い屋根の色で埋める (描いた色の縁が輪郭とずれていても、隣の屋根の色がにじまない) |
| `outline.png` | outline (1 チャンネル) | 一番近い境界までの距離 (0〜2 テクセル → 0〜255)。境界は外側の輪郭と段の境目の両方。**ほかのチャンネルと一緒にしないこと** (下の「ASTC」) |
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
| outline (R) | どちらでも (texelFetch で読む) | なし | リニア |
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
- 復元を 16bit 浮動小数で行う GPU (多くの実機) でも、そのまま使えます。サンプルのタイルで測ると、
  高さの誤差は最大 1 コード (4 の倍数に丸めて全部戻る)、距離 B と cone の超過は最大 2 コード、輪郭のずれは最大 0.07 テクセルでした。

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
   - **UV が 16bit (half) の環境**では、関数の中の `SCREEN_W_PX` / `SCREEN_H_PX` (画面の大きさ、ピクセル) に値を入れてください。
     視点の位置を画面の大きさから決めるので、UV の微分の乱れが絵に出なくなります。
     `POLY_PX` (ポリゴン 1 枚の画面上の大きさ、ズーム込み) も入れると、ミップの選び方まで安定します。
   - ポリゴンを画面上で回転させない場合 (`POLY_ROTATED = false`、既定) は、UV の微分は向き (符号) しか使いません。
     視点の位置と高さが同じ比率で動くので、微分の大きさが乱れても視線の向きは変わらないためです。
   - 16bit の UV でも、位置そのものは 1/2048 単位に丸められます。2000 ピクセルのポリゴンで 1 ピクセル程度のずれで、目立つノイズにはなりません。
   - デモの「UV を 16bit で渡す (再現)」と「画面とポリゴンの大きさを渡す」で違いを確かめられます。

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

## PNG から ASTC 4x4 への変換

タイルごとの PNG を 1 枚ずつ変換します (マップ全体を変換してから切り出すと、ブロックの位置がそろいません)。
astcenc の場合 (ARM の公式エンコーダー):

```
# 値をそのまま読むもの:リニア (-cl) で変換する。sRGB (-cs) にしないこと
astcenc -cl tileA_data.png    tileA_data.astc    4x4 -medium
astcenc -cl tileA_cone.png    tileA_cone.astc    4x4 -medium
astcenc -cl tileA_outline.png tileA_outline.astc 4x4 -medium
# 色:sRGB (-cs) でよい
astcenc -cs tileA_roof.png    tileA_roof.astc    4x4 -medium
astcenc -cs tileA_ground.png  tileA_ground.astc  4x4 -medium
```

- data / cone / outline に `-perceptual`、`-normal`、`-esw` (チャンネルの入れ替え)、α の重み付けなどは付けません。
- `-fast` でも許容範囲に収まります (サンプルで確認)。`-fastest` は誤差が増えるので、使う場合は下の確認をしてください。
- エンジンに読み込む時も、data / cone / outline は sRGB をオフ (リニア) にします。
  sRGB で読まれると高さが大きくずれ (サンプルで最大 73 コード)、壁の向き・AO・影の判定が乱れます。

**変換結果の確認**:ASTC を PNG に戻して、`astc_check.py` で元の PNG と比べます。

```
astcenc -dl tileA_data.astc tileA_data_dec.png
python3 astc_check.py --kind data    --orig tileA_data.png    --decoded tileA_data_dec.png
python3 astc_check.py --kind cone    --orig tileA_cone.png    --decoded tileA_cone_dec.png
python3 astc_check.py --kind outline --orig tileA_outline.png --decoded tileA_outline_dec.png
```

高さ・距離・円錐・輪郭がシェーダーの許容範囲に収まっているかを OK / NG で表示します。
全体が一方向にずれている場合は、sRGB で変換・復元している可能性を知らせます。

## ノイズが出る時の切り分け

関数の中の `DEBUG_VIEW` を変えると、入力をそのまま表示できます (デモでは「デバッグ表示」)。

| 値 | 表示 | ざらつく・乱れる時に疑うこと |
|---|---|---|
| 1 / 2 / 3 / 4 | data G / data B / outline / cone を真上から | テクスチャ側:sRGB になっている、圧縮の設定、サンプラーの精度 (lowp)、別の解像度で `TEX_SIZE` が合っていない |
| 5 | 視点のぶれ (黒が正常) | UV・微分:関数を `if` の中や `discard` の後で呼んでいる (微分が不定になる)、UV の精度、ポリゴンが画面に平行でない |
| 6 | レイの歩数 (青 → 赤) | 進み方:点々と赤い所は上限 (160 歩) に達している。距離 B や cone が小さすぎる・壊れている |

1〜4 が滑らかで 5 が黒なのに影や起伏がざらつく場合は、関数の中の計算精度 (`highp` が効いていない) を疑います。

## 試す

`sample/input/` に、デモの街の入力画像 (横 2048 × 縦 1024、上下左右につながる) が入っています。

```
python3 city_bake.py --top sample/input/top.png --mask sample/input/mask.png \
                     --bottom sample/input/bottom.png --roof sample/input/roof_color.png \
                     --out baked --wrap --core 1024 --margin 192
```

手元で 15 秒ほどかかりました (2048 × 1024)。メモリは輪郭の計算を 512 テクセルずつ区切って行うので、大きなマップでも増えにくくしてあります。
