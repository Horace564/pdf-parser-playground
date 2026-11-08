# I ask:
目前还在PoC 阶段，我想同时比较一下上述的全部方案可以做到什么效果。

具体来说，我的项目想要前端可以展示pdf, 然后可以分清里面的块，最好是鼠标悬停时可以高亮出来，前端点击某个块后端就可以知道点了文件的哪一个，并完成下游任务。

---

正常来说上述的pdf 解析文件都应该放在后端？能不能写一个极简的前后端，前端展示pdf， 并可以给我选择用哪个工具来解析，然后对应的展示不同工具的效果。

请给我写一个简短的实现思路。

# LLM response:
完全可以，而且我觉得你这个 PoC 很适合做成一个 PDF Parser Playground：上传同一个 PDF，切换不同解析引擎，直观看到各个工具识别出的 Block、Bounding Box 和语义结构。

你的核心目标其实是：

1. PDF 可视化：前端展示原始 PDF。
2. Layout Overlay：在 PDF 上叠加解析工具检测到的区域框。
3. 交互操作：鼠标 Hover 高亮 Block，Click 选中 Block。
4. 解析器对比：切换 PyMuPDF、MinerU、Docling、Marker、Unstructured，比较识别效果。
5. 后端任务：前端传递 `document_id + parser + block_id`，后端能找到对应的内容与位置，执行下游任务。

## 1. 推荐的整体架构

React + PDF.js

PDF 渲染 / 坐标叠加 / Hover / Click

FastAPI

PDF 上传 / Parser 调用 / Block 查询 / 下游任务

PyMuPDF

MinerU

Docling

Marker

Unstructured

统一 JSON Schema

Page / Block / Type / BBox / Text / Metadata

解析工具全部放后端是最合理的。 它们通常依赖 Python、OCR 模型、PDF 原生处理库，有的还需要 GPU。前端只负责显示 PDF 和解析结果。

为了 PoC 简单，不需要微服务、数据库或消息队列。一个 FastAPI 进程加本地文件缓存就够了。

## 2. 前端大概长这样

PDF Parser Playground

PoC UI

Docling

PDF Preview

Page 1

TitleIntroduction to Deep Learning

ParagraphDeep learning is a subset of machine learning...

FigureNeural network architecture diagram

CaptionFigure 1. Model architecture

Detected Blocks

IntroductionTitle · block_001Paragraph 1Paragraph · block_002Figure 1Figure · block_003CaptionCaption · block_004

Selected Block

ID: block_001

Type: Title

Parser: Docling

交互式界面示意，可切换解析器和点击块；目前使用模拟数据，不是真实解析结果。

真正实现时，PDF 是底层 Canvas，Block 是上层透明绝对定位的 HTML 元素。这样 Hover、Click、选中状态都很容易处理。

## 3. 后端 API 设计

建议先做 4 个 API：

| API                                             | 用途                        |
| ----------------------------------------------- | ------------------------- |
| `POST /documents`                               | 上传 PDF，返回 `document_id`   |
| `GET /documents/{id}/file`                      | 返回 PDF 给前端渲染              |
| `POST /documents/{id}/parse?parser=docling`     | 选择解析器、运行解析、缓存 JSON        |
| `POST /documents/{id}/blocks/{block_id}/action` | 根据 Block ID 查询具体内容，触发下游任务 |

解析结果由后端统一转换为：

```
{
  "document_id": "doc_001",
  "parser": "docling",
  "pages": [
    {
      "page_index": 0,
      "width": 595,
      "height": 842,
      "blocks": [
        {
          "id": "block_001",
          "type": "paragraph",
          "text": "Deep learning is...",
          "bbox": [72, 120, 520, 180],
          "coordinate_system": "top-left",
          "confidence": null
        }
      ]
    }
  ]
}
```

建议用 `page_index` 从 0 开始，并把所有 bbox 转换成统一的 PDF 页面坐标。

MinerU 尤其需要注意：当前版本的输出格式已经有变化，不能把旧版 `pdf_info` / `middle.json` 的字段当成所有版本通用的协议。

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub+1



## 4. 极简项目目录

```
pdf-parser-playground/
├── backend/
│   ├── main.py
│   ├── parsers/
│   │   ├── base.py
│   │   ├── pymupdf.py
│   │   ├── docling.py
│   │   ├── mineru.py
│   │   ├── marker.py
│   │   └── unstructured.py
│   └── storage/
│       └── {document_id}/
│           ├── original.pdf
│           └── results/
│               ├── pymupdf.json
│               ├── docling.json
│               └── ...
│
└── frontend/
    └── src/
        ├── App.tsx
        ├── components/
        │   ├── PDFViewer.tsx
        │   ├── BlockOverlay.tsx
        │   ├── ParserSelector.tsx
        │   └── BlockInspector.tsx
        └── api.ts
```

前端用 `react-pdf`（基于 PDF.js）渲染原始 PDF。每一页有一个相对定位容器，里面放 PDF Canvas 和 Overlay：

```
<div className="pdf-page">
  <Page pageNumber={pageNumber} />

  <BlockOverlay
    blocks={blocks}
    onSelect={(block) => {
      setSelectedBlock(block);
    }}
  />
</div>
```

Overlay 根据 bbox 生成 `position: absolute` 的 HTML 元素。建议通过页面原始宽高转换成百分比坐标，这样 PDF 缩放时高亮框也能同步缩放。旋转、CropBox 等特殊情况，则需要通过 PDF.js 的 viewport 变换处理。

## 5. PoC 最重要的设计：保留两份 JSON

不要只保存转换后的统一 JSON。

每种解析器最好都保存：

- `raw.json`：工具原始输出，方便检查不同工具识别了哪些细节。
- `normalized.json`：转换为前端通用结构，供渲染和点击交互使用。

这样不会因为统一 Schema 的字段有限，而丢掉某个解析器独有的能力。

另外，建议各解析器使用相互独立的 `block_id`。例如 `docling:p0:b12` 和 `mineru:p0:b7`，不要默认认为不同工具识别出来的 Block 一一对应。

## 6. 我建议的 PoC 实现顺序

阶段一：打通前后端

PyMuPDF + FastAPI + React PDF.js，完成上传、解析、悬停高亮、点击、Block ID 回传。这一步验证交互可行性。

阶段二：接入全部五种 Parser

实现统一的 Adapter 接口，切换工具时重新渲染 Overlay，保留各自原生解析数据。

阶段三：做解析效果对比

加入显示/隐藏所有 bbox、Block 类型过滤、原生 JSON 查看，以及选中区域的文本详情。比较漏检、误检、框的位置准确度与解析耗时。

有两个非常值得提前设计的细节：

第一，Block 不一定是矩形。 Marker 等工具支持 polygon，所以统一 Schema 最好同时预留 `bbox` 和 `polygon` 字段。

第二，Block 可能存在嵌套。 例如一张表格里有单元格，段落里有行和 Span。前端最好支持按 `block / line / span` 切换高亮粒度，并允许重叠区域选择。

最终的核心思想就是：

后端负责理解 PDF，前端负责在原始 PDF 上可视化这些理解结果。

这个设计能让你的 PoC 从单纯的 PDF Parser 对比工具，直接演进成后续可用的 Document AI 交互系统。