"""Markdown 输出器: 思维导图 -> Markdown 大纲。

- 文字节点 -> 标题层级 (H1..H6, 更深用列表)
- 图片: 默认拷贝高清原图到 <名>.assets/ 并引用;
  通过 img_map 可指定某些图为 {"type":"text","ocr":...}(转文字) 或 {"type":"icon"}(跳过)
- XMind relationship / FreeMind arrowlink -> 双向锚点超链接
"""

import json
import os
import re


def esc_title(t):
    return t.replace("\n", " ").strip()


class MdWriter:
    def __init__(self, assets_dir, rel_out, img_map, ocr_enabled=False):
        self.assets_dir = assets_dir
        self.rel_out = rel_out          # md -> assets 的相对路径
        self.img_map = img_map or {}
        self.ocr_enabled = ocr_enabled  # 自动 OCR 判型 (文字截图 -> 引用文字)
        self.ocr_stats = {"text": 0, "image": 0}
        self.lines = []
        self.anchors = {}               # node id -> anchor
        self.backlinks = {}             # node id -> [(anchor, title)]

    # ------------------------------------------------ 图片

    def _image_entry(self, node, source_name):
        base = os.path.basename(node.image or "")
        entry = self.img_map.get(
            "%s:%s" % (source_name, base)) or self.img_map.get(base)
        if entry:
            if entry.get("type") == "icon":
                return "icon", None
            if entry.get("type") == "text":
                return "text", entry.get("ocr", "")
            return "image", None         # 显式清单优先
        if self.ocr_enabled:
            from . import ocr
            r = ocr.classify(node.img_bytes)
            self.ocr_stats[r["kind"]] += 1
            if r["kind"] == "text":
                return "text", r["ocr"]
            return "image", None
        return "image", None             # 默认: 高清原图

    def emit_image(self, node, source_name):
        if not node.image or not node.img_bytes:
            return
        kind, payload = self._image_entry(node, source_name)
        if kind == "icon":
            return
        if kind == "text":
            for ln in payload.splitlines():
                ln = ln.rstrip()
                self.lines.append("> " + ln if ln else ">")
            self.lines.append("")
            return
        os.makedirs(self.assets_dir, exist_ok=True)
        base = os.path.basename(node.image)
        dst = os.path.join(self.assets_dir, base)
        if not os.path.exists(dst):
            with open(dst, "wb") as f:
                f.write(node.img_bytes)
        self.lines.append("![%s](%s/%s)"
                          % (esc_title(node.title) or "image",
                             self.rel_out, base))
        self.lines.append("")

    # ------------------------------------------------ 关系线 -> 双向链接

    def prepare_anchors(self, root, rels):
        byid = {}

        def walk(n):
            if n.id:
                byid[n.id] = n
            for c in n.children:
                walk(c)
        walk(root)
        for i, (a, b) in enumerate(rels):
            if a not in byid or b not in byid:
                continue    # 悬空引用(端点节点已删)跳过
            aa = "n-%d-%s" % (i, re.sub(r"\W", "", a or "")[:8])
            ab = "n-%d-%s" % (i, re.sub(r"\W", "", b or "")[:8])
            self.anchors[a] = aa
            self.anchors[b] = ab
            ta = esc_title(byid[a].title) or "(无标题)"
            tb = esc_title(byid[b].title) or "(无标题)"
            self.backlinks.setdefault(a, []).append((ab, tb))
            self.backlinks.setdefault(b, []).append((aa, ta))

    # ------------------------------------------------ 节点

    def write_node(self, node, depth, source_name):
        title = esc_title(node.title) or "(无标题)"
        if node.is_summary:
            title = "〔概要〕" + title
        elif node.is_detached:
            title = "〔游离〕" + title
        anchor = ('<a id="%s"></a>' % self.anchors[node.id]
                  if node.id and node.id in self.anchors else "")
        links = ""
        if node.id and node.id in self.backlinks:
            links = "  " + " ".join(
                "↔️ [%s](#%s)" % (t[:24], a)
                for a, t in self.backlinks[node.id])

        if depth < 6:
            self.lines += ["", "%s %s%s%s"
                           % ("#" * (depth + 1), anchor, title, links)]
        else:
            self.lines += ["%s- **%s%s**%s"
                           % ("  " * (depth - 6), anchor, title, links)]

        if node.labels:
            self.lines += ["", " ".join("`%s`" % l for l in node.labels)]
        if node.note:
            self.lines.append("")
            self.lines += ["> " + ln.strip() for ln in node.note.splitlines()]
        self.emit_image(node, source_name)

        for c in node.children:
            self.write_node(c, depth + 1, source_name)


def convert(path, out_path, sheets, rels, img_map=None, ocr_enabled=False):
    """生成 Markdown; 返回 (sheet 数, OCR 统计)。"""
    base = os.path.splitext(os.path.basename(out_path))[0]
    assets_dir = os.path.join(os.path.dirname(out_path), base + ".assets")
    source_name = os.path.basename(path)

    w = MdWriter(assets_dir, base + ".assets", img_map, ocr_enabled)
    for i, (stitle, root, _structure) in enumerate(sheets):
        if not root.title:
            root.title = base
        if i > 0:
            w.lines += ["", "---", ""]
        if len(sheets) > 1 and stitle:
            w.lines += ["<!-- sheet: %s -->" % stitle]
        w.prepare_anchors(root, rels if i == 0 else [])
        w.write_node(root, 0, source_name)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(w.lines).strip()) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return len(sheets), w.ocr_stats


def load_img_map(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
