"""mapconv: 思维导图转换工具包 (XMind / FreeMind -> Markdown / PDF)。

- parser:  统一解析层 (三种格式 -> 同一 Node 树), md/pdf 输出共用
- mdout:   Markdown 输出器 (大纲 + 高清图片资产 + 双向锚点链接)
- pdfout:  PDF 输出器 (单页大画布思维导图渲染)
- fonts:   PDF 中文字体注册 (TrueType 优先, Noto CFF 自动转换)
"""

__version__ = "1.0.0"
