import numpy as np
from PIL import Image, ImageDraw, ImageFont
O='out/'; M=192; C=1024
FP='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
F=ImageFont.truetype(FP, 26); Fs=ImageFont.truetype(FP, 19)
T=440
def lab(im, title, sub):
    c=Image.new('RGB',(T, T+78),(31,39,43)); c.paste(im.resize((T,T), Image.LANCZOS).convert('RGB'),(0,78))
    d=ImageDraw.Draw(c); d.text((10,6),title,font=F,fill=(235,238,236)); d.text((10,44),sub,font=Fs,fill=(170,182,183))
    k=T/(C+2*M); a=M*k; b=(M+C)*k
    for x in np.arange(a,b,10):
        d.line([(x,78+a),(x+5,78+a)],fill=(242,182,50),width=2); d.line([(x,78+b),(x+5,78+b)],fill=(242,182,50),width=2)
        d.line([(a,78+x),(a,78+x+5)],fill=(242,182,50),width=2); d.line([(b,78+x),(b,78+x+5)],fill=(242,182,50),width=2)
    return c
gray=lambda a: Image.fromarray(a.astype(np.uint8))
for t in 'AB':
    d=np.array(Image.open(O+f'tile{t}_data.png').convert('RGB')); r=np.array(Image.open(O+f'tile{t}_roof.png').convert('RGBA'))
    g=Image.open(O+f'tile{t}_ground.png').convert('RGB'); c=np.array(Image.open(O+f'tile{t}_cone.png'))
    R=d[...,0]; Rv=np.where(R==255,30,np.where(R==56,150,255))
    Gv=np.clip(d[...,1].astype(int)*255//192,0,255)
    comp=g.copy(); comp.paste(Image.fromarray(r[...,:3]),(0,0),Image.fromarray(((r[...,3]>127)*255).astype(np.uint8)))
    panels=[lab(gray(Rv),'data R:下端の高さ','白 = 地面から (0) / 灰 = 高架 (56) / 黒 = 空き地'),
      lab(gray(Gv),'data G:上端の高さ','明るいほど高い (4 の倍数、最大 192)'),
      lab(gray(d[...,2]),'data B:境界までの距離','同じ高さの領域の境目まで (2 / テクセル)'),
      lab(gray(c).resize((C+2*M,C+2*M)),'cone (半分の解像度)','円錐ステップ値。暗いほど近くに高い建物'),
      lab(Image.fromarray(r[...,:3]),'roof RGB:屋根の色','建物の外は一番近い屋根の色で埋めてある'),
      lab(gray(r[...,3]),'outline:なめらかな輪郭','1 チャンネル。0.5 の所が輪郭 (±2 テクセルで 0→1)'),
      lab(g,'ground:地面 + 壁の色','建物の中 (輪郭の 1.5 テクセル内側) は壁の色'),
      lab(comp,'真上から見た合成','ground の上に roof (outline ≥ 0.5) を重ねたもの')]
    sheet=Image.new('RGB',(4*(T+12)+12, 2*(T+78+12)+72),(22,28,31)); dd=ImageDraw.Draw(sheet)
    dd.text((14,12),f'タイル {t} のテクスチャ (1408 × 1408 = コア 1024 + 片側マージン 192。黄色の破線がコア = ポリゴンに映る範囲)',font=F,fill=(235,238,236))
    for i,p in enumerate(panels): sheet.paste(p,(12+(i%4)*(T+12), 72+(i//4)*(T+78+12)))
    sheet.save(f'out/tile{t}_textures.png')
