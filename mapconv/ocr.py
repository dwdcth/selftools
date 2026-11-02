"""OCR 集成: 自动判断节点图片是「文字截图」还是「图表」, 文字型转成 Markdown 文字。

判型启发式 (基于实际样本标定):
  - 用 tesseract (chi_sim+eng) OCR, 统计有效中文字符数与占比
  - 文字截图: 有足量连续中文 (zh >= 60 且 zh 占比 >= 35%) 且彩色像素占比低
  - K 线/走势图: OCR 输出多为线条碎片与数字, 中文占比低或彩色像素多

结果按图片字节哈希缓存到 ~/.cache/mapconv/ocr/, 同一张图只识别一次。
依赖系统 tesseract 二进制与 chi_sim 语言包 (可选功能, 未安装则全部按图片处理)。
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

CACHE_DIR = os.path.expanduser("~/.cache/mapconv/ocr")
_ZH = re.compile(r"[\u4e00-\u9fff]")
_ZH_SPACE = re.compile(r"(?<=[\u4e00-\u9fff，。、；：]) +(?=[\u4e00-\u9fff])")


def _squeeze(text):
    """去掉 tesseract 加在中文字符间的空格 (保留英文词间空格)。"""
    prev = None
    while prev != text:
        prev = text
        text = _ZH_SPACE.sub("", text)
    return text


def tesseract_available():
    return shutil.which("tesseract") is not None


def _colorful_ratio(img_bytes):
    """明显彩色像素 (红绿蜡烛/彩色均线) 占比; 失败按 0 处理。"""
    try:
        import io
        from PIL import Image
        with Image.open(io.BytesIO(img_bytes)) as im:
            im = im.convert("RGB")
            im.thumbnail((400, 400))
            total = colorful = 0
            for r, g, b in im.getdata():
                total += 1
                mx, mn = max(r, g, b), min(r, g, b)
                if mx > 60 and (mx - mn) / mx > 0.30:
                    colorful += 1
            return colorful / total if total else 0.0
    except Exception:
        return 0.0


def _ocr_text(img_bytes):
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(img_bytes)
            path = f.name
        try:
            out = subprocess.run(
                ["tesseract", path, "-", "-l", "chi_sim+eng", "--psm", "6"],
                capture_output=True, text=True, timeout=120).stdout
        finally:
            os.unlink(path)
        return out
    except Exception:
        return ""


def classify(img_bytes):
    """返回 {'kind': 'text'|'image', 'ocr': str, 'zh': n, 'chars': n,
    'colorful': r}; 图片字节为空返回 image。"""
    if not img_bytes:
        return {"kind": "image", "ocr": "", "zh": 0, "chars": 0,
                "colorful": 0.0}
    key = hashlib.sha1(img_bytes).hexdigest()
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, key + ".json")
    if os.path.exists(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    text = _ocr_text(img_bytes)
    compact = "".join(text.split())
    zh = len(_ZH.findall(compact))
    chars = len(compact)
    colorful = round(_colorful_ratio(img_bytes), 4)
    # 文字截图: 足量中文 + 中文占主导 + 无大量彩色图形
    is_text = (zh >= 60 and chars > 0
               and zh / chars >= 0.35 and colorful < 0.10)
    result = {"kind": "text" if is_text else "image",
              "ocr": _squeeze(text.strip()) if is_text else "",
              "zh": zh, "chars": chars, "colorful": colorful}
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception:
        pass
    return result
