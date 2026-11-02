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
