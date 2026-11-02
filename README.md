# selftools

个人自用小工具集。当前包含 **mapconv** —— 思维导图格式转换命令行工具。

## mapconv: XMind / FreeMind → Markdown / PDF

一个工具覆盖四种转换组合，任意输入格式 × 任意输出格式：

| 输入格式 | → Markdown | → PDF |
|---|---|---|
| XMind 8 (content.xml) | ✔ | ✔ |
| XMind Zen / 2020+ (content.json) | ✔ | ✔ |
| FreeMind (.mm) | ✔ | ✔ |

### 特性

- **文字**：节点标题按 H1–H6 层级展开（更深层用列表），备注转 `>` 引用块，标签转行内代码，概要（大括号）节点以 `〔概要〕` 前缀保留
- **图片**：PDF 中渲染进节点框；Markdown 中把原始字节无损拷贝到 `<文件名>.assets/` 并引用（高清原图，不压缩）；20px 级装饰小图标自动跳过
- **双链**：XMind 关系线（relationship）与 FreeMind arrowlink 转为 Markdown 双向锚点超链接——两端节点各带 `<a id>` 锚点并互相 `↔️ [标题](#anchor)`
- **PDF 排版**：根节点居中、子树左右分栏（按子树高度自动平衡，尊重 FreeMind 的 POSITION 与 XMind 的结构类）、彩色分支、贝塞尔连线、CJK 逐字换行（标点悬挂），超大导图自动等比缩放至 PDF 单页上限
- **中文字体**：自动挑选本机可用字体（微软雅黑 / 文泉驿 / Noto CJK），Noto 的 CFF 轮廓会用 fontTools 自动转 TrueOutline 并缓存

### 安装

依赖：Python 3.8+，`reportlab`，`Pillow`（PDF 输出）；Markdown 输出零第三方依赖（Pillow 可选，用于跳过小图标）。`fontTools` 可选（仅 Noto CJK 转换时需要）。

```bash
pip install reportlab pillow
git clone https://github.com/dwdcth/selftools.git
cd selftools && ./install.sh     # 软链 mapconv 到 ~/.local/bin
```

### 用法

```bash
mapconv '*.xmind' '*.mm'              # 同时生成 .md + .pdf（同名，源文件同目录）
mapconv -t md  a.xmind b.mm           # 只要 Markdown
mapconv -t pdf '*.xmind' -o out/      # 只要 PDF，输出到 out/
```

Markdown 输出会在 `.md` 旁生成 `<名>.assets/` 目录存放高清原图。

可选 `--img-map`：默认所有内嵌图片按高清原图嵌入；如果某张图其实是**文字截图**，想转成文字而不是图片，可以提供清单：

```json
{
  "screenshot.png": {"type": "text", "ocr": "识别出的文字内容"},
  "icon.png": {"type": "icon"}
}
```

```bash
mapconv -t md --img-map imgs.json '*.xmind'
```

（清单 key 可以是 `图名` 或 `源文件名:图名`。识别可以先用任意 OCR 工具完成。）

### 架构

md 和 pdf 输出**共用同一解析层** `mapconv/parser.py`：三种格式解析成统一的 `Node` 树（含图片字节与尺寸、关系线端点），`mdout.py` 与 `pdfout.py` 各自只负责渲染输出，格式特有信息（FreeMind 左右位置、XMind 概要/游离标记、结构类）都挂在节点属性上，因此新增输出格式只需再写一个输出器。

```
mapconv/
├── parser.py   # 统一解析: XMind 8 / XMind Zen / FreeMind -> Node 树
├── mdout.py    # Markdown 输出 (大纲/图片资产/双向锚点链接)
├── pdfout.py   # PDF 输出 (树形布局渲染)
└── fonts.py    # PDF 中文字体注册
bin/mapconv     # CLI 入口
```

## License

MIT
