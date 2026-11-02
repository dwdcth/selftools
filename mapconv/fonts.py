"""PDF 输出的中文字体注册: 优先可直接使用的 TrueType 中文字体,
Noto CJK (CFF 轮廓) 经 fontTools 转 TrueType 后使用(带缓存)。
"""

import os
import sys

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_CANDIDATES = [
    ("/usr/share/fonts/msyh/msyh.ttc",
     "/usr/share/fonts/msyh/msyhbd.ttc"),
    (os.path.expanduser("~/.local/share/fonts/msyh.ttc"),
     os.path.expanduser("~/.local/share/fonts/msyhbd.ttc")),
    ("/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc", None),
    ("/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc", None),
]
NOTO_DIRS = ["/usr/share/fonts/noto-cjk", "/usr/share/fonts/opentype/noto"]
NOTO_REG, NOTO_BOLD = "NotoSansCJK-Regular.ttc", "NotoSansCJK-Bold.ttc"
CACHE_DIR = os.path.expanduser("~/.cache/mapconv")


def pick_subfont(ttc_path, chars):
    """在 .ttc 里选对所用字符覆盖最好的子字体 (Noto ttc 含 JP/KR/SC/TC/HK)。"""
    try:
        from fontTools.ttLib import TTCollection
        best, best_hit = 0, -1
        for i, font in enumerate(TTCollection(ttc_path).fonts):
            cmap = font.getBestCmap()
            hit = sum(1 for c in chars if ord(c) in cmap)
            if hit > best_hit:
                best, best_hit = i, hit
        return best
    except Exception:
        return 0


def _try_register(name, path, idx):
    try:
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
        return True
    except Exception:
        return False


def cff_to_ttf(src, font_number, dst):
    """CFF/OTF 轮廓转 TrueType 二次曲线 (reportlab 只支持后者)。"""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib import TTFont as FT
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    f = FT(src, fontNumber=font_number)
    gs = f.getGlyphSet()
    order = f.getGlyphOrder()
    glyphs = {}
    for gname in order:
        pen = TTGlyphPen(gs)
        try:
            gs[gname].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
            glyphs[gname] = pen.glyph()
        except Exception:
            glyphs[gname] = pen.glyph()
    fb = FontBuilder(f["head"].unitsPerEm, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(f.getBestCmap())
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(dict(f["hmtx"].metrics))
    hh, os2 = f["hhea"], f["OS/2"]
    fb.setupHorizontalHeader(ascent=hh.ascent, descent=hh.descent)
    fb.setupOS2(sTypoAscender=os2.sTypoAscender,
                sTypoDescender=os2.sTypoDescender,
                usWinAscent=os2.usWinAscent, usWinDescent=os2.usWinDescent)
    fb.setupNameTable({"familyName": "NotoCJK-TTF", "styleName": "Regular"})
    fb.setupDummyDSIG()
    fb.setupPost()
    fb.save(dst)


def _noto_ttf(chars):
    ndir = next((d for d in NOTO_DIRS
                 if os.path.exists(os.path.join(d, NOTO_REG))), None)
    if not ndir:
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    out = []
    for fname in (NOTO_REG, NOTO_BOLD):
        src = os.path.join(ndir, fname)
        if not os.path.exists(src):
            src = os.path.join(ndir, NOTO_REG)
        idx = pick_subfont(src, chars)
        dst = os.path.join(
            CACHE_DIR, "%s.%d.ttf" % (os.path.splitext(fname)[0], idx))
        if not os.path.exists(dst) or \
                os.path.getmtime(dst) < os.path.getmtime(src):
            cff_to_ttf(src, idx, dst)
        out.append(dst)
    return out


def register_fonts(all_text):
    chars = {c for c in all_text if ord(c) > 0x2E7F}
    for reg, bold in FONT_CANDIDATES:
        if not os.path.exists(reg):
            continue
        idx = pick_subfont(reg, chars)
        if _try_register("MapConvSans", reg, idx):
            bold_ok = bool(bold) and os.path.exists(bold) and \
                _try_register("MapConvSansB", bold, pick_subfont(bold, chars))
            if not bold_ok:
                pdfmetrics.registerFont(TTFont("MapConvSansB", reg,
                                               subfontIndex=idx))
            return
    pair = _noto_ttf(chars)
    if pair:
        pdfmetrics.registerFont(TTFont("MapConvSans", pair[0]))
        try:
            pdfmetrics.registerFont(TTFont("MapConvSansB", pair[1]))
        except Exception:
            pdfmetrics.registerFont(TTFont("MapConvSansB", pair[0]))
        return
    sys.exit("错误: 找不到可用的中文字体 (msyh / 文泉驿 / noto-cjk)")
