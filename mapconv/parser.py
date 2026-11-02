"""统一思维导图解析层: XMind 8 (content.xml) / XMind Zen (content.json) / FreeMind (.mm).

输出统一的 Node 树 (含图片字节与尺寸), 供 md / pdf 两个输出器共用。
"""

import io
import json
import os
import xml.etree.ElementTree as ET
import zipfile

NS = "{urn:xmind:xmap:xmlns:content:2.0}"
XLINK = "{http://www.w3.org/1999/xlink}"
XHTML = "{http://www.w3.org/1999/xhtml}"

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class Node:
    """统一节点模型。"""

    def __init__(self):
        self.id = None
        self.title = ""
        self.labels = []          # list[str]
        self.note = ""
        self.image = None         # zip 内路径
        self.img_bytes = None     # 原始图片字节 (解析时读入)
        self.img_w = self.img_h = 0
        self.children = []
        self.arrow_dests = []     # FreeMind arrowlink 目标 id
        self.fm_pos = None        # FreeMind POSITION: left/right
        self.is_summary = False   # XMind 概要(大括号)节点
        self.is_detached = False  # XMind 游离节点
        # PDF 布局用
        self.depth = 0
        self.color = "#2b2f3a"
        self.svg_w = None


def _clean(t):
    return " ".join((t or "").split())


def _load_image(n, src, zf):
    """读入节点图片字节并测尺寸; 小于 64px 视为装饰图标(置空)。"""
    try:
        n.img_bytes = zf.read(src)
        if HAS_PIL:
            with Image.open(io.BytesIO(n.img_bytes)) as im:
                n.img_w, n.img_h = im.size
    except Exception:
        n.image = None
        return
    if n.img_w < 64 or n.img_h < 64:   # marker 小图标
        n.image, n.img_bytes = None, None


def _find_own_image(tel, zf):
    """只取 topic 直接子元素的 <xhtml:img>, 不递归后代(避免重复挂载)。"""
    for child in list(tel):
        if child.tag == XHTML + "img":
            src = (child.get(XLINK + "href") or child.get(XHTML + "src") or "")
            src = src.replace("xap:", "")
            if src and src in zf.namelist():
                return src
    return None


def _parse_common(n, tel):
    t = tel.find(NS + "title")
    if t is not None:
        n.title = "".join(t.itertext()).strip()
        n.svg_w = t.get("{http://www.w3.org/2000/svg}width")
    lab = tel.find(NS + "labels")
    if lab is not None:
        n.labels = [_clean(e.text) for e in lab.findall(NS + "label")
                    if _clean(e.text)]
    note = tel.find(NS + "notes")
    if note is not None:
        pe = note.find(NS + "plain")
        if pe is not None:
            n.note = "".join(pe.itertext()).strip()


def parse_xmind_topic(tel, zf):
    n = Node()
    n.id = tel.get("id")
    _parse_common(n, tel)
    src = _find_own_image(tel, zf)
    if src:
        n.image = src
        _load_image(n, src, zf)
    ch = tel.find(NS + "children")
    if ch is not None:
        for topics in ch.findall(NS + "topics"):
            ttype = topics.get("type", "attached")
            for c in topics.findall(NS + "topic"):
                child = parse_xmind_topic(c, zf)
                if ttype == "summary":
                    child.is_summary = True
                elif ttype == "detached":
                    child.is_detached = True
                n.children.append(child)
    return n


def parse_zen_topic(t):
    n = Node()
    n.id = t.get("id")
    n.title = str(t.get("title", "")).strip()
    n.labels = [str(x) for x in t.get("labels", []) if str(x).strip()]
    n.note = str((t.get("notes") or {}).get("plain", "")).strip()
    for c in ((t.get("children") or {}).get("attached") or []):
        n.children.append(parse_zen_topic(c))
    return n


def parse_freemind(nel):
    n = Node()
    n.id = nel.get("ID")
    n.title = _clean(nel.get("TEXT"))
    n.fm_pos = nel.get("POSITION")
    for rc in nel.findall("richcontent"):
        txt = " ".join(" ".join(rc.itertext()).split())
        if txt:
            n.title = (n.title + "\n" + txt).strip() if n.title else txt
    for al in nel.findall("arrowlink"):
        d = al.get("DESTINATION")
        if d:
            n.arrow_dests.append(d)
    for c in nel.findall("node"):
        n.children.append(parse_freemind(c))
    return n


def load(path):
    """解析文件, 返回 (sheets, relationships)。

    sheets: [(sheet标题, root Node, structure_class)]
    relationships: [(end1_id, end2_id)]
    """
    if path.lower().endswith(".mm"):
        rt = ET.parse(path).getroot().find("node")
        if rt is None:
            raise ValueError("无效的 FreeMind 文件")
        root = parse_freemind(rt)
        byid = {}
        _collect_ids(root, byid)
        rels = [(s, d) for s, node in byid.items()
                for d in node.arrow_dests if d in byid]
        return [("", root, "freemind")], rels

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        sheets, rels = [], []
        if "content.xml" in names:
            x = ET.fromstring(zf.read("content.xml"))
            for sh in x.iter(NS + "sheet"):
                st = sh.find(NS + "title")
                tel = sh.find(NS + "topic")
                if tel is not None:
                    sheets.append((_clean(st.text if st is not None else None),
                                   parse_xmind_topic(tel, zf),
                                   tel.get("structure-class", "")))
            for r in x.iter(NS + "relationship"):
                e1, e2 = r.get("end1"), r.get("end2")
                if e1 and e2:
                    rels.append((e1, e2))
        elif "content.json" in names:
            data = json.loads(zf.read("content.json").decode("utf-8"))
            for sh in data:
                rt = sh.get("rootTopic")
                if rt:
                    sheets.append((sh.get("title", ""), parse_zen_topic(rt), ""))
                for r in sh.get("relationships", []) or []:
                    e1, e2 = r.get("end1"), r.get("end2")
                    if e1 and e2:
                        rels.append((e1, e2))
        else:
            raise ValueError("不是有效的 XMind 文件 (缺少 content.xml/content.json)")
        return sheets, rels


def _collect_ids(n, byid):
    if n.id:
        byid[n.id] = n
    for c in n.children:
        _collect_ids(c, byid)
