"""PDF 输出器: 思维导图 -> 单页大画布 PDF。

树形布局: 根节点居中, 子树左右分栏, 彩色节点框 + 贝塞尔连线 + 内嵌图片,
超过 PDF 单页上限 (14000pt) 时整体等比缩放。
"""

import io
import os

from reportlab.lib.colors import HexColor, Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT_COLOR = "#2b2f3a"
BRANCH_COLORS = ["#d94f43", "#0f9d58", "#2f6fd8", "#e0940a",
                 "#8a5cd8", "#0fa8a0", "#d8609c", "#687a1e"]

MAX_PAGE = 14000.0            # PDF 单页物理上限 (200 inch)
MARGIN = 30.0
LINE_H = 1.35
IMG_GAP = 6.0
MAX_IMG_W_DEFAULT = 250.0

# depth -> (字号, 加粗, 最大文字宽pt, 水平pad, 垂直pad, 圆角)
STYLE = {0: (20.0, True, 400.0, 16, 12, 12),
         1: (13.5, True, 330.0, 11, 8, 8),
         2: (12.0, False, 290.0, 9, 6, 6)}
STYLE_DEFAULT = (11.0, False, 260.0, 8, 5, 5)

V_GAP = {0: 20.0, 1: 14.0, 2: 10.0}    # 兄弟节点垂直间距
V_GAP_DEFAULT = 7.0
H_GAP = {0: 62.0, 1: 44.0, 2: 36.0}    # 父子水平间距
H_GAP_DEFAULT = 30.0

# 行首禁排字符 (标点不落行首)
NO_START = set("，。、；：？！）】》」』”’·…%,.:;?!)]}>")


def _mix_white(hexstr, t):
    c = HexColor(hexstr)
    return Color(c.red + (1 - c.red) * t, c.green + (1 - c.green) * t,
                 c.blue + (1 - c.blue) * t)


def _wrap(text, font, size, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if cur and pdfmetrics_string_width(cur + ch, font, size) > max_w:
                if ch in NO_START and pdfmetrics_string_width(
                        cur + ch, font, size) <= max_w * 1.08:
                    lines.append(cur + ch)
                    cur = ""
                else:
                    lines.append(cur)
                    cur = ch
            else:
                cur += ch
        lines.append(cur.rstrip())
    return lines or [""]


def pdfmetrics_string_width(s, font, size):
    from reportlab.pdfbase import pdfmetrics
    return pdfmetrics.stringWidth(s, font, size)


class Renderer:
    def __init__(self, max_img_w=MAX_IMG_W_DEFAULT):
        self.max_img_w = max_img_w

    # ------------------------------------------------ 布局

    def prepare(self, node, depth=0, branch=ROOT_COLOR):
        node.depth = depth
        node.color = branch
        size, bold, maxw, hpad, vpad, _ = STYLE.get(depth, STYLE_DEFAULT)
        font = "MapConvSansB" if bold else "MapConvSans"
        if node.svg_w:
            try:
                maxw = min(float(node.svg_w), 480.0)
            except ValueError:
                pass

        title = ("〔概要〕" if node.is_summary else
                 "〔游离〕" if node.is_detached else "") + \
            (node.title or "")
        node.lines = _wrap(title, font, size, maxw)
        node.note_lines = _wrap(node.note, "MapConvSans", 8.5, 320.0) \
            if node.note else []

        node.disp_w = node.disp_h = 0.0
        if node.img_bytes:
            k = min(self.max_img_w / node.img_w, 1.0)
            node.disp_w, node.disp_h = node.img_w * k, node.img_h * k

        text_w = max((pdfmetrics_string_width(l, font, size)
                      for l in node.lines), default=0.0)
        if node.disp_w:
            text_w = max(text_w, node.disp_w)

        line_h = size * LINE_H
        note_h = len(node.note_lines) * 8.5 * 1.3 + 5 if node.note_lines else 0
        node.box_w = text_w + hpad * 2
        node.box_h = vpad * 2 + len(node.lines) * line_h + note_h + \
            (IMG_GAP + node.disp_h if node.disp_h else 0)

        for i, c in enumerate(node.children):
            self.prepare(c, depth + 1,
                         BRANCH_COLORS[i % len(BRANCH_COLORS)]
                         if depth == 0 else branch)

    def subtree_h(self, node, depth):
        if not node.children:
            return node.box_h
        gap = V_GAP.get(depth, V_GAP_DEFAULT)
        total = sum(self.subtree_h(c, depth + 1) for c in node.children) \
            + gap * (len(node.children) - 1)
        return max(node.box_h, total)

    def place(self, node, x_lead, y_center, direction):
        """x_lead: 朝父侧前导边 x; 布局 y 向下为正。"""
        node.x = x_lead if direction == "R" else x_lead - node.box_w
        node.y = y_center
        if not node.children:
            return
        gap = V_GAP.get(node.depth, V_GAP_DEFAULT)
        hgap = H_GAP.get(node.depth, H_GAP_DEFAULT)
        total = sum(self.subtree_h(c, node.depth + 1)
                    for c in node.children) + gap * (len(node.children) - 1)
        child_lead = x_lead + (node.box_w + hgap) * \
            (1 if direction == "R" else -1)
        cy = y_center - total / 2
        for c in node.children:
            sh = self.subtree_h(c, node.depth + 1)
            self.place(c, child_lead, cy + sh / 2, direction)
            cy += sh + gap

    def layout(self, root, structure):
        self.prepare(root)
        if structure == "freemind":
            sides = ["L" if (c.fm_pos or "right").lower() == "left" else "R"
                     for c in root.children]
        elif "logic.left" in structure:
            sides = ["L"] * len(root.children)
        elif "logic.right" in structure:
            sides = ["R"] * len(root.children)
        else:  # 脑图式左右分布, 按子树高度贪心平衡
            sides, loads = [], {"L": 0.0, "R": 0.0}
            for c in root.children:
                sh = self.subtree_h(c, 1)
                side = "L" if loads["L"] <= loads["R"] else "R"
                sides.append(side)
                loads[side] += sh

        for direction in ("R", "L"):
            group = [c for c, s in zip(root.children, sides) if s == direction]
            if not group:
                continue
            lead = H_GAP[0] * (1 if direction == "R" else -1)
            gap = V_GAP[0]
            total = sum(self.subtree_h(c, 1) for c in group) + \
                gap * (len(group) - 1)
            cy = -total / 2
            for c in group:
                sh = self.subtree_h(c, 1)
                self.place(c, lead, cy + sh / 2, direction)
                cy += sh + gap

        root.x, root.y = -root.box_w / 2, 0.0
        bounds = {"x0": 0.0, "x1": 0.0, "y0": 0.0, "y1": 0.0}

        def walk(n):
            bounds["x0"] = min(bounds["x0"], n.x)
            bounds["x1"] = max(bounds["x1"], n.x + n.box_w)
            bounds["y0"] = min(bounds["y0"], n.y - n.box_h / 2)
            bounds["y1"] = max(bounds["y1"], n.y + n.box_h / 2)
            for c in n.children:
                walk(c)
        walk(root)
        return bounds


# ------------------------------------------------ 绘制

def _draw_link(cv, parent, child, ox, oy):
    """ox/oy: 布局(x 右, y 下) -> PDF 坐标平移, py = oy - y。"""
    cv.setStrokeColor(HexColor(child.color))
    cv.setLineWidth(max(0.8, 2.4 - parent.depth * 0.55))
    py, cy = oy - parent.y, oy - child.y
    if child.x + child.box_w / 2 < parent.x + parent.box_w / 2:
        px, cx2 = parent.x, child.x + child.box_w
    else:
        px, cx2 = parent.x + parent.box_w, child.x
    mid = (px + cx2) / 2
    cv.bezier(px + ox, py, mid + ox, py, mid + ox, cy, cx2 + ox, cy)


def _draw_box(cv, n, ox, oy):
    size, bold, _, hpad, vpad, rad = STYLE.get(n.depth, STYLE_DEFAULT)
    font = "MapConvSansB" if bold else "MapConvSans"
    x0 = n.x + ox
    top = oy - n.y + n.box_h / 2

    if n.depth == 0:
        cv.setFillColor(HexColor(ROOT_COLOR))
    elif n.depth == 1:
        cv.setFillColor(_mix_white(n.color, 0.86))
    elif n.depth == 2:
        cv.setFillColor(_mix_white(n.color, 0.94))
    else:
        cv.setFillColor(_mix_white(n.color, 0.965))
    if n.depth:
        cv.setStrokeColor(HexColor(n.color))
        cv.setLineWidth(1.3 if n.depth == 1 else 0.8)
        cv.roundRect(x0, top - n.box_h, n.box_w, n.box_h, rad, stroke=1, fill=1)
    else:
        cv.roundRect(x0, top - n.box_h, n.box_w, n.box_h, rad,
                     stroke=0, fill=1)

    line_h = size * LINE_H
    ty = top - vpad - size
    cv.setFillColor(HexColor("#ffffff") if n.depth == 0 else
                    HexColor("#1d2330") if n.depth == 1 else
                    HexColor("#333a45"))
    cv.setFont(font, size)
    for ln in n.lines:
        lw = pdfmetrics_string_width(ln, font, size)
        cv.drawString(x0 + (n.box_w - lw) / 2, ty, ln)
        ty -= line_h

    if n.img_bytes:
        try:
            img = ImageReader(io.BytesIO(n.img_bytes))
            cv.drawImage(img, x0 + (n.box_w - n.disp_w) / 2,
                         ty - IMG_GAP - n.disp_h + 2,
                         n.disp_w, n.disp_h, mask="auto")
        except Exception:
            pass


def _draw_note(cv, n, ox, oy):
    if not n.note_lines:
        return
    ny = oy - n.y - n.box_h / 2 - 12
    cv.setFont("MapConvSans", 8.5)
    cv.setFillColor(HexColor("#8a8f98"))
    for ln in n.note_lines:
        cv.drawString(n.x + ox, ny, ln)
        ny -= 8.5 * 1.3


def _render_sheet(cv, root, bounds):
    w = bounds["x1"] - bounds["x0"] + MARGIN * 2
    h = bounds["y1"] - bounds["y0"] + MARGIN * 2
    s = min(1.0, MAX_PAGE / w, MAX_PAGE / h)
    cv.setPageSize((w * s, h * s))
    cv.saveState()
    cv.scale(s, s)
    ox = MARGIN - bounds["x0"]
    oy = bounds["y1"] + MARGIN

    stack = [root]
    while stack:  # 先画所有连线
        n = stack.pop()
        for c in n.children:
            _draw_link(cv, n, c, ox, oy)
            stack.append(c)
    stack = [root]
    while stack:  # 再画节点框与备注
        n = stack.pop()
        _draw_box(cv, n, ox, oy)
        _draw_note(cv, n, ox, oy)
        stack.extend(n.children)
    cv.restoreState()
    cv.showPage()


def convert(path, out_path, sheets, max_img_w=MAX_IMG_W_DEFAULT):
    """生成 PDF; 返回页数 (每 sheet 一页)。"""
    ren = Renderer(max_img_w)
    cv = canvas.Canvas(out_path)
    cv.setTitle(os.path.splitext(os.path.basename(path))[0])
    for _title, root, structure in sheets:
        if not root.title:
            root.title = os.path.splitext(os.path.basename(path))[0]
        _render_sheet(cv, root, ren.layout(root, structure))
    cv.save()
    return len(sheets)
