// =============================================================
// cityTile(screenUV, polyUV)  ―  ポリゴンタイリング用 2.5D シティ・レイマーチ
//
// 引数はスクリーン UV とポリゴン UV の 2 つだけ。
//   screenUV : 画面全体で 0..1 (左下 0、gl_FragCoord.xy / 解像度)
//   polyUV   : タイルのポリゴンの上で 0..1 (左下 0)。ポリゴンが映すのはタイルの「コア」
//
// 視点・ズーム・解像度は、この 2 つの UV の画面上の微分 (dFdx / dFdy) から求める。
//   ・ポリゴンは画面に平行な四角 (回転していてもよい)。1 ピクセルあたりのポリゴン UV から
//     ズーム (1 ピクセルあたりのテクセル数) がわかる → ズームはポリゴンの拡大縮小だけでよい。
//   ・視点は画面に固定:画面の (0.5, 0.5 + EYE_OFFSET / 2) の真上、高さは画角で決まる。
//   ・それ以外の値 (画角・光・建物の高さ・フラグ) は関数の中の変数。サンプラーだけは外のコードで宣言する。
//   ・計算はすべて highp。screenUV と polyUV も highp で渡すこと (varying も highp で宣言する)。
//     half / mediump の UV では位置と微分が粗くなり、影や起伏にノイズが出る。
//   ・ポリゴン UV と TEX_CORE / TEX_SIZE の対応だけでマッピングする (テクスチャの実際の解像度には依存しない)。
//   ・ポリゴンごとにそのタイルのテクスチャ 5 枚をバインドする (テクスチャ配列は使わない)。
//
// テクスチャ (コアの周りに片側マージンを足して切り出したもの。TEX_SIZE = TEX_CORE + 2 × マージン)
//   data   (RGBA8, NEAREST)  R = 下端の高さ (0 / 56 = 高架 / 255 = 空き地) / G = 上端 (4 の倍数) /
//                            B = 同じ高さ領域の境界までの距離 (1 テクセルあたり DIST_SCALE)
//   roof   (RGB,  ミップあり) 屋根のアルベド (建物の外は一番近い屋根の色で埋めておく)
//   outline(R8,   LINEAR、ミップなし) なめらかな輪郭:符号付き距離 sd (内側が負) から
//                            v = 0.5 − sd / 4。線形補間した v = 0.5 を輪郭として使う (テクセルより細かい)。
//                            data のほうは輪郭に少しでもかかるテクセルを建物にしておく (外側 0.75 テクセルまで)。
//                            ASTC では 1 チャンネルだけのテクスチャにすること。色と一緒に圧縮すると
//                            色の模様に引きずられて輪郭がずれる (実測で最大 0.9 テクセル → 1 チャンネルなら 0.1 以下)
//   ground (RGB,  ミップあり) 地面のアルベド。地面から立つ建物の中 (R=0) は壁の色
//   cone   (R8, NEAREST、data の半分の解像度でよい)
//                            u = k / (k + 0.1)、k = 自分より高い建物までの水平距離 ÷ 高さの差
//                            (距離はマップ幅 CONE_MAP_W を 1、高さは G/255)
//
// 必要なマージン (片側、テクセル) は次の大きい方。足りないと継ぎ目で建物や影が欠ける
//   視差:最大の建物の高さ × (画面上で視点の真下からタイルの端までの距離 ÷ 視点の高さ)
//   影  :最大の建物の高さ × 光の水平成分 ÷ 光の垂直成分 (影は地面にだけ落とす)
//
// ASTC 4x4
//   ・コアとマージンは (実際のテクセルで) 4 の倍数 (cone が半分の解像度ならマージンは 8 の倍数)。
//     ブロックがそろっていれば、隣のタイルとの重なりは同じ値に復元される。
//   ・高さ (R/G) は 4 の倍数で作り、読むときに丸める。
//   ・距離 B と円錐は 6 コード小さく読み、進む距離にだけ使う (実測の超過は最大 3 コード)。
//     当たった位置・法線・AO は R/G と輪郭だけで決めるので、圧縮のノイズが絵に出ない。
//   ・輪郭 (outline) は 1 チャンネルだけのテクスチャにする。
//   ・data / cone / outline は sRGB にしないこと (値がそのまま読まれる前提)。
// =============================================================

// ---- サンプラー ----
// この関数は次の 5 つのサンプラーを名前で参照する。宣言は外のコードで行う。
// 外のコードで名前が違う場合は、このファイルの中の名前を一括置換する
//   uCityData   : data   R 下端 / G 上端 / B 境界までの距離 (NEAREST)
//   uCityRoof   : roof   RGB 屋根の色 (LINEAR, ミップ)
//   uCityOutline: outline R なめらかな輪郭 (LINEAR, ミップなし)
//   uCityGround : ground RGB 地面と壁の色 (LINEAR, ミップ)
//   uCityCone   : cone   R 円錐ステップ値 (NEAREST)

highp vec4 cityTile(highp vec2 screenUV, highp vec2 polyUV)
{
    // ---- 調整する値 (シーンに合わせてここを書き換える) ----
    highp float FOV_DEG      = 20.0;    // 画角 (度)。視点の高さ = 画面の高さ ÷ 2 ÷ tan(画角 ÷ 2)
    highp float EYE_OFFSET   = -0.4;    // 視点の真下の位置 (画面中央からの縦のずれ、画面の半分 = 1)
    highp float HEIGHT_SCALE = 0.25;    // 建物の高さ:G = 255 のときの高さ ÷ CONE_MAP_W
    highp float LIGHT_AZ_DEG = 241.0;   // 光の方位 (度、0 = ポリゴン UV の +u、90 = +v)
    highp float LIGHT_EL_DEG = 65.0;    // 光の高さ (度、地面からの角度)
    bool  DROP_SHADOW  = true;    // 落ち影 (地面だけ)
    bool  SIDE_SHADE   = true;    // 側面の陰影
    bool  ASTC_SAFE    = true;    // ASTC 対策:距離 B と円錐を 6 コード小さく読む
    bool  HEIGHT_SNAP  = true;    // ASTC 対策:高さ R/G を 4 の倍数に丸めて読む
    bool  SHOW_STARVED = false;   // デバッグ:マージン不足の所を赤く
    int   DEBUG_VIEW   = 0;       // デバッグ表示 (ノイズの出所を探す):0 = 通常
                                  //   1 = data G (上端の高さ)  2 = data B (距離)  3 = outline  4 = cone
                                  //      ※1〜4 はポリゴンの地面の位置をそのまま真上から見た値。ここがざらつけばテクスチャ側の問題
                                  //   5 = 視点のぶれ (黒なら正常)。白っぽければ UV か微分の問題 (関数を if の中で呼んでいる、UV の精度など)
                                  //   6 = レイの歩数 (青 = 少ない → 赤 = 上限)。点々と赤ければ進み方の問題

    // ---- マッピング (ポリゴンとテクスチャの対応) ----
    // ポリゴン UV 0..1 が、テクスチャのうちマージンを除いた TEX_CORE の範囲に対応する。
    // 単位は「テクセル」だが、実際のテクスチャの解像度とは別に決めてよい
    // (実際の解像度が違っても、TEX_SIZE 全体に引き伸ばして読む。高さ・距離・円錐もこの単位で扱う)
    highp float TEX_CORE     = 1024.0;  // ポリゴンに映る範囲 (マージンを除いた大きさ)
    highp float TEX_SIZE     = 1408.0;  // マージン込みのテクスチャ全体の大きさ (= TEX_CORE + 2 × 片側マージン)

    // ---- 画面とポリゴンの大きさ (省略可) ----
    // 0 のままなら UV の画面上の微分から求める。UV の精度が低い (16bit) と微分が乱れる。
    //   SCREEN_*_PX:16bit の UV では必ず入れる (視点の位置が画面の大きさで決まるため)
    //   POLY_PX     :入れるとミップの選び方も安定する (入れなくても形は崩れない)
    highp float SCREEN_W_PX  = 0.0;     // 画面の幅 (ピクセル)
    highp float SCREEN_H_PX  = 0.0;     // 画面の高さ (ピクセル)
    highp float POLY_PX      = 0.0;     // ポリゴン 1 枚の画面上の大きさ (ピクセル、ズーム込み。回転なしの正方形)
    bool  POLY_ROTATED = false;   // ポリゴンを画面上で回転させる時だけ true。false なら UV の微分は向き (符号) だけを使い、
                                  // 視線の向きを画面の位置だけから決める (UV が 16bit でも視線がぶれない)

    // ---- 定数 (タイルの作り方に合わせる。city_bake.py の出力に表示される値) ----
    const highp float DIST_SCALE   = 2.0;            // data の B が 1 テクセルあたりいくつ増えるか
    highp float DIST_TEX     = 255.0 / DIST_SCALE;            // B = 1 のときの距離 (data のテクセル)
    const highp float CONE_MAP_W   = 2048.0;         // 円錐マップを作ったマップ全体の幅 (マッピングの単位)
    const int   STEPS        = 160;
    const int   SHADOW_STEPS = 96;
    const highp float EPS          = 0.6;            // 境界を越える最小の歩幅 (テクセル)
    const highp float CONE_C       = 0.1;
    const highp float EMPTY_R      = 250.0 / 255.0;  // R がこれ以上なら空き地 (255 が 254 に化けても・丸めても空き地)

    DIST_TEX /= float(textureSize(uCityData, 0).x) / TEX_SIZE;     // → マッピングの単位
    int   flags     = (DROP_SHADOW ? 1 : 0) | (SIDE_SHADE ? 2 : 0) | (SHOW_STARVED ? 4 : 0)
                    | (ASTC_SAFE ? 8 : 0) | (HEIGHT_SNAP ? 16 : 0);
    highp float heightTex = HEIGHT_SCALE * CONE_MAP_W;                   // G = 255 のときの高さ (テクセル)
    highp float laz = radians(LIGHT_AZ_DEG), lel = radians(LIGHT_EL_DEG);
    highp vec3  toLight   = vec3(cos(lel) * cos(laz), cos(lel) * sin(laz), sin(lel));

    // ---- スクリーン UV とポリゴン UV の微分から、ズームと視点を求める ----
    // (分岐より前で微分を取る。ポリゴンは画面に平行なので、この微分はポリゴン内で一定)
    highp vec2 sdx = dFdx(screenUV), sdy = dFdy(screenUV);
    highp vec2 pdx = dFdx(polyUV),   pdy = dFdy(polyUV);
    highp vec2 res = vec2(1.0 / max(abs(sdx.x), 1e-9), 1.0 / max(abs(sdy.y), 1e-9));   // 画面の解像度 (px)
    highp mat2 J   = mat2(pdx, pdy);                                     // 1 ピクセル動いた時のポリゴン UV の変化
    if (SCREEN_W_PX > 0.0) res = vec2(SCREEN_W_PX, SCREEN_H_PX);
    // 1 ピクセルあたりのポリゴン UV の大きさ。分かっていれば POLY_PX から、なければ微分から
    highp float sc = POLY_PX > 0.0 ? 1.0 / POLY_PX : 0.5 * (abs(pdx.x) + abs(pdy.y));
    if (!POLY_ROTATED) {
        // 回転なし:向き (符号) だけを微分から取る。視点の位置と高さはどちらも sc に比例するので、
        // 視線の向き (= 絵) は sc に依存しない。sc の乱れが効くのはミップの選び方だけになる
        J = mat2(pdx.x < 0.0 ? -sc : sc, 0.0, 0.0, pdy.y < 0.0 ? -sc : sc);
    } else if (POLY_PX > 0.0) {
        J *= sc / sqrt(abs(determinant(J)));
    }
    highp float texPerPx = sqrt(abs(determinant(J))) * TEX_CORE;             // 1 ピクセルあたりのテクセル数 (= 1 / ズーム)
    highp float lod      = max(log2(texPerPx), 0.0);

    highp vec2  S      = vec2(TEX_SIZE);                                 // 以下の計算の単位 (マッピングのテクセル)
    highp float MARGIN = 0.5 * (TEX_SIZE - TEX_CORE);                    // 片側マージン
    highp vec2  P      = MARGIN + polyUV * TEX_CORE;                     // 地面上の位置
    // data の実際の解像度への変換 (TEX_SIZE と同じなら 1)。読む時だけ使う
    highp vec2  dRes   = vec2(textureSize(uCityData, 0));
    highp vec2  dSc    = dRes / S;

    highp float fov    = radians(FOV_DEG);
    highp vec2  eyePx  = vec2(0.5, 0.5 + 0.5 * EYE_OFFSET) * res;      // 視点の真下 (画面のピクセル)
    highp vec2  fragPx = screenUV * res;
    highp vec2  eyeUV  = polyUV + J * (eyePx - fragPx);                  // 視点の真下 (ポリゴン UV)
    highp float eyeH   = 0.5 * res.y / tan(0.5 * fov);                   // 視点の高さ (画面のピクセル)
    highp vec3  eye    = vec3(MARGIN + eyeUV * TEX_CORE, eyeH * texPerPx);   // 視点 (テクセル)
    highp float eyeJitter = length(fwidth(eye));                    // デバッグ用:視点は 1 枚の中で一定のはず (隣のピクセルとの差)

    // ---- ASTC 4x4 対策 ----
    // 距離 B と円錐は「大きく復元」されると建物を飛び越えるので、6 コード小さく読む
    //   (実測の超過は B 最大 2、円錐最大 3 コード。圧縮しないときは歩数が少し増えるだけ)
    // 高さ R/G は ±1 ずれる。data を 4 の倍数で作っておき、読むときに 4 の倍数へ丸めると元に戻る
    bool  safeRead = (flags & 8) != 0;
    highp float SNAP     = (flags & 16) != 0 ? 1.0 : 0.0;
    highp float B_MARGIN = safeRead ? 6.0 / 255.0 : 0.0;
    highp float C_MARGIN = safeRead ? 6.0 / 255.0 : 0.0;
    highp float KEY_TOL  = SNAP > 0.5 ? 0.5 / 255.0 : safeRead ? 1.5 / 255.0 : 0.5 / 255.0;

    highp float coneSc = float(textureSize(uCityCone, 0).x) / S.x;
    // ---- デバッグ表示 1〜5 (レイを飛ばさずに入力をそのまま見る) ----
    if (DEBUG_VIEW >= 1 && DEBUG_VIEW <= 5) {
        highp vec4 dd = texelFetch(uCityData, ivec2(clamp(floor(P * dSc), vec2(0.0), dRes - 1.0)), 0);
        highp float v = DEBUG_VIEW == 1 ? dd.g * (255.0 / 192.0) : DEBUG_VIEW == 2 ? dd.b
                      : DEBUG_VIEW == 3 ? textureLod(uCityOutline, P / S, 0.0).r
                      : texelFetch(uCityCone, ivec2(clamp(floor(P * coneSc), vec2(0.0), S * coneSc - 1.0)), 0).r;
        if (DEBUG_VIEW == 5) return vec4(vec3(clamp(eyeJitter * 10.0, 0.0, 1.0)), 1.0);   // 黒 = 一定、白 = 0.1 テクセル以上ぶれる
        return vec4(vec3(v), 1.0);
    }
    int stepsUsed = 0;
    bool starved = false;                       // マージンが足りず、視線の始まりがテクスチャの外
    highp vec3 col;
    {
        highp vec2  Ps     = P;                           // 地面上の位置
        highp vec3  D      = vec3(Ps, 0.0) - eye;         // 視点 → 地面の点。t = 0..1 で進む (t = 1 が地面)
        highp float xyLen  = max(length(D.xy), 1e-6);

        // ---- 開始位置:最大の高さの平面と、テクスチャの範囲に入る所の遅い方 ----
        highp float t = eye.z > heightTex ? 1.0 - heightTex / eye.z : 0.0;
        {
            highp vec2 dd  = vec2(abs(D.x) < 1e-6 ? 1e-6 : D.x, abs(D.y) < 1e-6 ? 1e-6 : D.y);
            highp vec2 inv = 1.0 / dd;
            highp vec2 t0 = (vec2(0.0) - eye.xy) * inv, t1 = (S - eye.xy) * inv;
            highp float tEnter = max(min(t0.x, t1.x), min(t0.y, t1.y));
            if (tEnter > t) { starved = true; t = tEnter; }
        }

        // ---- 一次レイ:距離 B と円錐で進む ----
        // B と円錐は「どこまで安全に進めるか」にだけ使う。当たった位置・法線・AO は
        // 高さ R/G (丸めれば ASTC でも元の値に戻る) だけで決めるので、圧縮のノイズが絵に出ない
        int  face = 1;                              // 1 = 地面, 2 = 屋根, 3 = 壁
        highp vec3 hit  = vec3(Ps, 0.0);
        highp float tPrev = t;                            // 直前の (外側だった) 位置
        for (int i = 0; i < STEPS; i++) {
            stepsUsed = i;
            if (t >= 1.0) break;
            highp vec3 p  = eye + D * t;
            highp vec4 d  = texelFetch(uCityData, ivec2(clamp(floor((p.xy) * dSc), vec2(0.0), dRes - 1.0)), 0);
            d.rg = mix(d.rg, round(d.rg * 63.75) / 63.75, SNAP);
            bool solid = d.r < EMPTY_R;
            highp float bot  = d.r * heightTex, top = d.g * heightTex;
            highp float dt   = max(max(d.b - B_MARGIN, 0.0) * DIST_TEX, EPS) / xyLen;   // この間は同じ領域
            if (solid) {
                // data で中にいる時だけ、なめらかな輪郭 (屋根の α) を読む (毎ステップ読むと重い)
                bool inData = p.z >= bot && p.z <= top;
                if (inData) inData = textureLod(uCityOutline, p.xy / S, 0.0).r > 0.5;
                if (inData) {                                                      // 中に入った (なめらかな輪郭の内側)
                    // 外側 (tPrev) と内側 (t) の間を二分法で詰めて、入った所を求める
                    highp float tA = tPrev, tB = t;
                    for (int k = 0; k < 10; k++) {
                        highp float tm = 0.5 * (tA + tB);
                        highp vec3  q  = eye + D * tm;
                        highp vec4  e  = texelFetch(uCityData, ivec2(clamp(floor((q.xy) * dSc), vec2(0.0), dRes - 1.0)), 0);
                        e.rg = mix(e.rg, round(e.rg * 63.75) / 63.75, SNAP);
                        bool inside = e.r < EMPTY_R && q.z >= e.r * heightTex && q.z <= e.g * heightTex;
                        if (inside) inside = textureLod(uCityOutline, q.xy / S, 0.0).r > 0.5;
                        if (inside) tB = tm; else tA = tm;
                    }
                    // 入る直前の点の真下が建物 (屋根より上) なら屋根の面から、そうでなければ側面から入った
                    highp vec3 qa = eye + D * tA;
                    highp vec4 ea = texelFetch(uCityData, ivec2(clamp(floor((qa.xy) * dSc), vec2(0.0), dRes - 1.0)), 0);
                    ea.rg = mix(ea.rg, round(ea.rg * 63.75) / 63.75, SNAP);
                    if (ea.r < EMPTY_R && qa.z > ea.g * heightTex && textureLod(uCityOutline, (qa.xy) / S, 0.0).r > 0.5) { face = 2; hit = eye + D * (1.0 - ea.g * heightTex / eye.z); }
                    else                                           { face = 3; hit = eye + D * tB; }
                    break;
                }
                if (p.z > top) {                                                   // 屋根面に届くか
                    highp float tt = 1.0 - top / eye.z;
                    if (tt <= t + dt) {
                        if (textureLod(uCityOutline, (eye.xy + D.xy * tt) / S, 0.0).r > 0.5) { face = 2; hit = eye + D * tt; break; }
                    }
                }
                // p.z < bot は高架の下をくぐる
            }
            highp float base = solid ? top : 0.0;                                        // 円錐ステップ
            if (p.z > base) {
                highp float u = texelFetch(uCityCone, ivec2(clamp(floor(p.xy * coneSc), vec2(0.0), S * coneSc - 1.0)), 0).r;
                // 254 以上は「高い建物なし」。安全読みでは 6 コード引くので、この特別扱いは起きない
                u = u >= 253.5 / 255.0 && !safeRead ? 0.999 : max(u - C_MARGIN, 0.0);
                highp float k = CONE_C * u / (1.0 - u) * CONE_MAP_W / heightTex;          // 水平距離 ÷ 高さ (テクセル同士)
                dt = max(dt, k * (p.z - base) / (xyLen + k * eye.z));
            }
            // 高架の床の上にいる時は、床の下端の高さを飛び越さないように一度そこで止まる
            // (薄い床の側面を歩幅で飛び越すと、側面の下端が階段状になる)
            if (solid && bot > 0.0 && p.z > bot) {
                highp float tBotP = 1.0 - bot / eye.z;
                if (tBotP > t + 1e-6 && t + dt > tBotP) dt = tBotP - t;
            }
            tPrev = t;
            t += dt;
        }

        // ---- 足元の取りこぼし:地面に着いた点が建物の中なら、最後の 1 歩の間に壁へ入っている ----
        // 壁の下の方は、1 歩で縦に何テクセルも下がるので、中の点を一度も踏まずに地面まで来ることがある。
        // その幅が視点の動きで変わり、地面と壁の境目がちらつく。地面の点で判定して二分法で詰め直す
        if (face == 1) {
            highp vec4 e = texelFetch(uCityData, ivec2(clamp(floor((Ps) * dSc), vec2(0.0), dRes - 1.0)), 0);
            e.rg = mix(e.rg, round(e.rg * 63.75) / 63.75, SNAP);
            bool groundIn = e.r < EMPTY_R && e.r * heightTex <= 0.5;               // 地面から立つ物の中
            if (groundIn) groundIn = textureLod(uCityOutline, Ps / S, 0.0).r > 0.5;
            if (groundIn) {
                highp float tA = tPrev, tB = 1.0;
                for (int k = 0; k < 10; k++) {
                    highp float tm = 0.5 * (tA + tB);
                    highp vec3  q  = eye + D * tm;
                    highp vec4  f  = texelFetch(uCityData, ivec2(clamp(floor((q.xy) * dSc), vec2(0.0), dRes - 1.0)), 0);
                    f.rg = mix(f.rg, round(f.rg * 63.75) / 63.75, SNAP);
                    bool inside = f.r < EMPTY_R && q.z >= f.r * heightTex && q.z <= f.g * heightTex;
                    if (inside) inside = textureLod(uCityOutline, q.xy / S, 0.0).r > 0.5;
                    if (inside) tB = tm; else tA = tm;
                }
                highp vec3 qa = eye + D * tA;
                highp vec4 ea = texelFetch(uCityData, ivec2(clamp(floor((qa.xy) * dSc), vec2(0.0), dRes - 1.0)), 0);
                ea.rg = mix(ea.rg, round(ea.rg * 63.75) / 63.75, SNAP);
                if (ea.r < EMPTY_R && qa.z > ea.g * heightTex && textureLod(uCityOutline, qa.xy / S, 0.0).r > 0.5) { face = 2; hit = eye + D * (1.0 - ea.g * heightTex / eye.z); }
                else { face = 3; hit = eye + D * tB; }
            }
        }

        // ---- 壁の法線:周りの 16 点のうち「同じ建物でない」点の方向を足す ----
        // (B の勾配は ASTC の誤差で向きがぶれるので使わない)
        highp vec2 n = vec2(0.0, 1.0);
        if (face == 3) {
            highp vec2 c0 = hit.xy + normalize(D.xy) * 0.3;                              // 少し内側 (視線の進む側) を中心に
            highp vec4 dc = texelFetch(uCityData, ivec2(clamp(floor((c0) * dSc), vec2(0.0), dRes - 1.0)), 0);
            dc.rg = mix(dc.rg, round(dc.rg * 63.75) / 63.75, SNAP);
            highp vec2 g = vec2(0.0);
            for (int k = 0; k < 16; k++) {
                highp float a = 6.2831853 * (float(k) + 0.5) / 16.0;
                highp vec2 o = vec2(cos(a), sin(a));
                highp vec4 dn = texelFetch(uCityData, ivec2(clamp(floor((c0 + o * 2.5) * dSc), vec2(0.0), dRes - 1.0)), 0);
                dn.rg = mix(dn.rg, round(dn.rg * 63.75) / 63.75, SNAP);
                bool same = all(lessThan(abs(dn.rg - dc.rg), vec2(KEY_TOL)));
                if (!same) g += o;
            }
            if (length(g) > 1e-5) n = normalize(g);
            // なめらかな輪郭 (屋根の α) の勾配が取れる所はそちらを使う (斜めの建物でも向きが正確)
            highp vec2 ga = vec2(textureLod(uCityOutline, (hit.xy + vec2(1.0, 0.0)) / S, 0.0).r - textureLod(uCityOutline, (hit.xy - vec2(1.0, 0.0)) / S, 0.0).r,
                           textureLod(uCityOutline, (hit.xy + vec2(0.0, 1.0)) / S, 0.0).r - textureLod(uCityOutline, (hit.xy - vec2(0.0, 1.0)) / S, 0.0).r);
            if (length(ga) > 0.05) n = -normalize(ga);
        }

        // ---- 落ち影:地面にだけ落とす (屋根・側面には落とさない) ----
        highp float lit = 1.0;
        if ((flags & 1) != 0 && face == 1 && toLight.z > 1e-4) {
            highp vec3 o = hit + vec3(0.0, 0.0, 1e-3);
            highp float lxy = max(length(toLight.xy), 1e-6);
            highp float sl = 0.0, sEnd = (heightTex - o.z) / toLight.z;
            for (int i = 0; i < SHADOW_STEPS; i++) {
                if (sl > sEnd) break;
                highp vec3 p = o + toLight * sl;
                if (any(lessThan(p.xy, vec2(0.0))) || any(greaterThanEqual(p.xy, S))) { starved = true; break; }
                highp vec4 d = texelFetch(uCityData, ivec2(clamp(floor((p.xy) * dSc), vec2(0.0), dRes - 1.0)), 0);
                d.rg = mix(d.rg, round(d.rg * 63.75) / 63.75, SNAP);
                bool solid = d.r < EMPTY_R;
                highp float bot = d.r * heightTex, top = d.g * heightTex;
                highp float ds = max(max(d.b - B_MARGIN, 0.0) * DIST_TEX, EPS) / lxy;
                highp float base = solid ? top : 0.0;
                if (p.z > base) {
                    highp float u = texelFetch(uCityCone, ivec2(clamp(floor(p.xy * coneSc), vec2(0.0), S * coneSc - 1.0)), 0).r;
                    u = u >= 253.5 / 255.0 && !safeRead ? 0.999 : max(u - C_MARGIN, 0.0);
                    highp float k = CONE_C * u / (1.0 - u) * CONE_MAP_W / heightTex;
                    highp float den = lxy - k * toLight.z;
                    if (den <= 0.0) break;                                         // 円錐より急に昇る:もう当たらない
                    ds = max(ds, k * (p.z - base) / den);
                }
                if (solid) {
                    if (p.z >= bot && p.z <= top && textureLod(uCityOutline, (p.xy) / S, 0.0).r > 0.5) { lit = 0.0; break; }
                    highp float sb = (bot - o.z) / toLight.z;                               // 高架の裏の面に届く所
                    if (p.z < bot && sb <= sl + ds) {
                        highp vec2 pb = o.xy + toLight.xy * sb;                              // そこが輪郭の内側なら影
                        highp vec4 eb = texelFetch(uCityData, ivec2(clamp(floor((pb) * dSc), vec2(0.0), dRes - 1.0)), 0);
                        if (eb.r < EMPTY_R && abs(eb.r - d.r) < KEY_TOL + 1.0 / 255.0 && textureLod(uCityOutline, pb / S, 0.0).r > 0.5) { lit = 0.0; break; }
                    }
                }
                sl += ds;
            }
        }

        // ---- 色 ----
        highp vec2 uv = hit.xy / S;
        if (face == 1) {                                                           // 地面
            highp vec4 d = texelFetch(uCityData, ivec2(clamp(floor((hit.xy) * dSc), vec2(0.0), dRes - 1.0)), 0);
            d.rg = mix(d.rg, round(d.rg * 63.75) / 63.75, SNAP);
            col = textureLod(uCityGround, uv, lod).rgb;
            // 地面の AO:半径 4 と 10 テクセルの円周 8 点ずつで、建物が占める割合を見る (B は使わない)
            highp float occ = 0.0;
            for (int k = 0; k < 16; k++) {
                highp float a = 6.2831853 * (float(k) + 0.5) / 8.0;
                highp vec2 o = vec2(cos(a), sin(a)) * (k < 8 ? 4.0 : 10.0);
                highp vec4 e = texelFetch(uCityData, ivec2(clamp(floor((hit.xy + o) * dSc), vec2(0.0), dRes - 1.0)), 0);
                occ += (e.r < EMPTY_R ? 1.0 : 0.0) * (k < 8 ? 0.6 : 0.4) / 8.0;
            }
            bool underDeck = d.r < EMPTY_R && d.r > 0.1 && textureLod(uCityOutline, (hit.xy) / S, 0.0).r > 0.5;                  // 高架の床の下
            highp float ao = underDeck ? 0.55 : 1.0 - 0.38 * clamp(occ * 2.0, 0.0, 1.0);
            col *= ao * mix(0.68, 1.0, lit);
        } else if (face == 2) {                                                    // 屋根
            col = textureLod(uCityRoof, uv, lod).rgb;
        } else {                                                                   // 壁
            highp vec4 d = texelFetch(uCityData, ivec2(clamp(floor((hit.xy - n * 0.5) * dSc), vec2(0.0), dRes - 1.0)), 0);
            d.rg = mix(d.rg, round(d.rg * 63.75) / 63.75, SNAP);
            highp float bot = d.r * heightTex, top = d.g * heightTex;
            highp vec2 wuv = (hit.xy - n * 2.0) / S;                                     // 壁の色は建物の内側に置いてある
            col = bot > 0.0 ? textureLod(uCityRoof, wuv, 0.0).rgb * 0.6              // 高架の床の側面
                            : textureLod(uCityGround, wuv, 0.0).rgb;
            highp float shade = 0.85;
            if ((flags & 2) != 0) {
                shade = 0.62 + 0.5 * max(dot(vec3(n, 0.0), toLight), 0.0);
                highp float k = clamp((hit.z - bot) / max(top - bot, 1e-4), 0.0, 1.0);
                shade *= mix(0.78, 1.04, smoothstep(0.0, 0.5, k));                 // 足元を暗く
            }
            col *= shade;
        }

    }
    if ((flags & 4) != 0 && starved) col = mix(col, vec3(0.9, 0.15, 0.1), 0.45);
    if (DEBUG_VIEW == 6) {
        highp float k = float(stepsUsed) / float(STEPS - 1);
        col = mix(vec3(0.1, 0.2, 0.9), vec3(0.95, 0.15, 0.1), k) * (0.4 + 0.6 * k) + 0.05;
    }
    return vec4(col, 1.0);
}
