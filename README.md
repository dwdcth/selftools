# selftools

个人自用小工具集。当前包含 **mapconv**（思维导图格式转换命令行工具）与 **md2pdf**（Markdown 转 PDF）。

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
- **OCR 自动判型**（`--ocr`）：对每张内嵌图片用 tesseract 识别——纯文字截图自动转成 Markdown 引用文字，K 线/走势等图表仍嵌高清原图；结果按图片哈希缓存，重复转换不耗时。也可用 `--img-map` 手工指定
- **双链**：XMind 关系线（relationship）与 FreeMind arrowlink 转为 Markdown 双向锚点超链接——两端节点各带 `<a id>` 锚点并互相 `↔️ [标题](#anchor)`
- **PDF 排版**：根节点居中、子树左右分栏（按子树高度自动平衡，尊重 FreeMind 的 POSITION 与 XMind 的结构类）、彩色分支、贝塞尔连线、CJK 逐字换行（标点悬挂），超大导图自动等比缩放至 PDF 单页上限
- **中文字体**：自动挑选本机可用字体（微软雅黑 / 文泉驿 / Noto CJK），Noto 的 CFF 轮廓会用 fontTools 自动转 TrueOutline 并缓存

### 安装

依赖用 [uv](https://docs.astral.sh/uv/) 管理（Python ≥3.9；`reportlab`、`pillow`、`fonttools`，见 `pyproject.toml` / `uv.lock` / `requirements.txt`）。OCR 为可选功能，需要系统 tesseract 与中文语言包。

```bash
# 系统依赖 (仅 --ocr 需要): Arch: pacman -S tesseract tesseract-data-chi_sim
#                            Debian: apt install tesseract-ocr tesseract-ocr-chi-sim

git clone https://github.com/dwdcth/selftools.git
cd selftools

# 方式一: uv (推荐)
uv sync                                    # 建虚拟环境并安装依赖 (uv.lock 锁定版本)
uv run bin/mapconv '*.xmind' '*.mm'        # 经 uv 环境运行
./install.sh                               # 或软链命令 (配合系统 python)

# 方式二: pip
pip install -r requirements.txt            # 由 uv export 生成的锁版本清单
./install.sh
```

### 用法

```bash
mapconv '*.xmind' '*.mm'              # 同时生成 .md + .pdf（同名，源文件同目录）
mapconv -t md  a.xmind b.mm           # 只要 Markdown
mapconv -t pdf '*.xmind' -o out/      # 只要 PDF，输出到 out/
mapconv -t md --ocr '*.xmind'         # 文字截图自动 OCR 成文字, 图表嵌原图
```

Markdown 输出会在 `.md` 旁生成 `<名>.assets/` 目录存放高清原图。

### OCR 判型

`--ocr` 对每张图片：tesseract (chi_sim+eng) 识别 + 彩色像素统计 → 有效中文 ≥60 字、中文占比 ≥35% 且彩色像素 <10% 判为**文字截图**（转成 `>` 引用文字，并自动去掉 OCR 加在中文里的空格）；否则视为**图表**（保留高清原图）。识别结果按图片字节哈希缓存于 `~/.cache/mapconv/ocr/`，同一张图只识别一次。

需要手工覆盖判定时用 `--img-map`（优先级高于自动识别）：

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
├── ocr.py      # OCR 判型: 文字截图 -> 文字, 图表 -> 保留原图 (tesseract + 缓存)
└── fonts.py    # PDF 中文字体注册
bin/mapconv     # CLI 入口 (xmind2pdf / map2md 为兼容别名)
```

## md2pdf: Markdown → PDF（远程图片本地化）

单文件脚本 `bin/md2pdf`，把 Markdown 文章转成可读性好的 PDF，同时把远程图片下载到本地：

- **图片下载**：解析 `![…](…)` 及 `[![缩略图](…)](原图…)` 链接式图片，**优先下载原图**（而非缩略图），按 URL 去重、失败重试 3 次，保存到 `<文件名>_images/`
- **中文排版**：A4 版式、微软雅黑/Noto CJK 字体、图片居中带题注、引用块/代码块样式；顺带清理论坛导出残留（空锚点、`\*\*` 转义）
- **矢量 PDF**：Chrome/Chromium headless 打印，文字可选中、缩放不糊；图片与图注以不可分割的原子块排版，不会被拆到两页

```bash
pip install markdown requests          # Python 依赖 (需系统 Chrome/Chromium)

bin/md2pdf '文章.md'                   # -> 文章.pdf + 文章_images/
bin/md2pdf in.md -o out.pdf --keep-html
```

## License

MIT
