"""共用 CLI 入口: mapconv / xmind2pdf / map2md 三个命令都走这里。"""

import argparse
import glob
import os
import sys

from . import parser
from .mdout import convert as md_convert, load_img_map
from .pdfout import MAX_IMG_W_DEFAULT, convert as pdf_convert


def collect_text(node):
    return node.title + "".join(node.labels) + node.note + \
        "".join(collect_text(c) for c in node.children)


def run(argv, to="both"):
    ap = argparse.ArgumentParser(
        prog=os.environ.get("MAPCONV_PROG", "mapconv"),
        description="思维导图转换: XMind / FreeMind(.mm) -> Markdown / PDF"
                    " (支持通配符、多文件、内嵌图片、关系线)")
    ap.add_argument("patterns", nargs="+",
                    help="文件或通配符, 如 '*.xmind' '*.mm'")
    ap.add_argument("-t", "--to", choices=["md", "pdf", "both"], default=to,
                    help="输出类型 (默认 %(default)s)")
    ap.add_argument("-o", "--outdir", help="输出目录 (默认与源文件同目录)")
    ap.add_argument("--img-map",
                    help="JSON: {'图名': {'type':'image|text|icon','ocr':..}}")
    ap.add_argument("--ocr", action="store_true",
                    help="自动 OCR 判型: 文字截图转成 Markdown 文字, "
                         "图表仍嵌高清原图 (需要系统 tesseract + chi_sim)")
    ap.add_argument("--max-img-width", type=float, default=MAX_IMG_W_DEFAULT,
                    help="PDF 节点内图片最大宽度 pt (默认 %(default)s)")
    args = ap.parse_args(argv)

    files = []
    for pat in args.patterns:
        hit = glob.glob(pat)
        if hit:
            files.extend(hit)
        elif os.path.exists(pat):
            files.append(pat)
        else:
            print("警告: 没有匹配到文件: %s" % pat, file=sys.stderr)
    files = sorted(set(files))
    if not files:
        sys.exit("错误: 没有输入文件")

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)

    parsed = []
    for f in files:
        try:
            sheets, rels = parser.load(f)
            parsed.append((f, sheets, rels))
        except Exception as e:
            print("跳过 %s: %s" % (f, e), file=sys.stderr)
    if not parsed:
        sys.exit("错误: 没有可解析的文件")

    if args.to in ("pdf", "both"):
        from .fonts import register_fonts
        register_fonts("".join(
            collect_text(root) for _, sheets, _ in parsed
            for _, root, _ in sheets))
    img_map = load_img_map(args.img_map) if args.to in ("md", "both") else None
    if args.ocr and args.to not in ("md", "both"):
        print("提示: --ocr 只影响 Markdown 输出", file=sys.stderr)
    if args.ocr and args.to in ("md", "both"):
        from .ocr import tesseract_available
        if not tesseract_available():
            print("警告: 未找到 tesseract, --ocr 失效, 图片将按原图嵌入",
                  file=sys.stderr)
            args.ocr = False

    ok = 0
    for f, sheets, rels in parsed:
        stem = os.path.splitext(os.path.basename(f))[0]
        outdir = args.outdir or os.path.dirname(os.path.abspath(f))
        try:
            results = []
            if args.to in ("md", "both"):
                out = os.path.join(outdir, stem + ".md")
                n, stats = md_convert(f, out, sheets, rels, img_map,
                                      ocr_enabled=args.ocr)
                extra = ""
                if args.ocr and (stats["text"] or stats["image"]):
                    extra = " [OCR: %d 转文字, %d 保留原图]" % (
                        stats["text"], stats["image"])
                results.append("%s (%d sheet)%s" % (out, n, extra))
            if args.to in ("pdf", "both"):
                out = os.path.join(outdir, stem + ".pdf")
                results.append("%s (%d 页)"
                               % (out, pdf_convert(f, out, sheets,
                                                   args.max_img_width)))
            ok += 1
            print("✔ %s -> %s" % (os.path.basename(f), "; ".join(results)))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("失败 %s: %s" % (f, e), file=sys.stderr)
    print("完成: %d/%d" % (ok, len(files)))
    sys.exit(0 if ok == len(files) else 1)
