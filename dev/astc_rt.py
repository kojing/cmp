import astc_encoder as A, numpy as np
def roundtrip(rgba, quality=A.ASTCQualityPreset.THOROUGH, weights=(1,1,1,1)):
    """rgba: HxWx4 uint8 -> ASTC 4x4 LDR -> decoded uint8"""
    h,w,_=rgba.shape
    cfg=A.ASTCConfig(A.ASTCProfile.LDR,4,4,1,quality,A.ASTCConfigFlags.USE_DECODE_UNORM8)
    cfg.cw_r_weight,cfg.cw_g_weight,cfg.cw_b_weight,cfg.cw_a_weight=weights
    ctx=A.ASTCContext(cfg)
    img=A.ASTCImage(A.ASTCType.U8,w,h,1,np.ascontiguousarray(rgba).tobytes())
    sw=A.ASTCSwizzle.from_str('RGBA')
    comp=ctx.compress(img,sw)
    out=A.ASTCImage(A.ASTCType.U8,w,h,1)
    ctx.decompress(comp,out,sw)
    return np.frombuffer(out.data,np.uint8).reshape(h,w,4).copy(), len(comp)


def roundtrip_f16(rgba, quality=A.ASTCQualityPreset.MEDIUM, weights=(1, 1, 1, 1)):
    """実機の多くと同じく、復元を 16bit 浮動小数 (fp16) で行う。戻り値は 0..1 の float32 (h, w, 4)"""
    h, w, _ = rgba.shape
    cfg = A.ASTCConfig(A.ASTCProfile.LDR, 4, 4, 1, quality, 0)
    cfg.cw_r_weight, cfg.cw_g_weight, cfg.cw_b_weight, cfg.cw_a_weight = weights
    ctx = A.ASTCContext(cfg)
    img = A.ASTCImage(A.ASTCType.U8, w, h, 1, np.ascontiguousarray(rgba).tobytes())
    sw = A.ASTCSwizzle.from_str('RGBA')
    comp = ctx.compress(img, sw)
    out = A.ASTCImage(A.ASTCType.F16, w, h, 1)
    ctx.decompress(comp, out, sw)
    return np.frombuffer(out.data, np.float16).reshape(h, w, 4).astype(np.float32)
