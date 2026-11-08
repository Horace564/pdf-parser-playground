# PDF Parser Playground

一个本地 PoC：上传 PDF，在原页上显示解析块；切换 PyMuPDF、Docling、MinerU、Marker、Unstructured；点击块后，后端根据 `document_id + parser + block_id` 找回文本与坐标。解析结果保存在 `backend/storage/{document_id}/results/{parser}/raw.json` 和 `normalized.json`。

五种解析器在同一页上的 JSON 和框选对照见 [第 8 页图解](docs/parser-json-comparison.md)。

当前界面一次显示一种解析器的叠框。切换解析器时仍使用同一份 PDF；每种解析器只在首次选择时运行，之后读取各自的本地缓存。暂未提供五种结果并排显示或“一键全部解析”。
安装新数据包或更改解析设置后，可按“重跑当前解析器”跳过旧缓存。

## 安装

请在 PowerShell 中执行。后端使用已有的 `llm-dev` conda 环境：

```powershell
conda activate <your virtual env>
python -m pip install -r requirements.txt
cd frontend
npm install
```

这会安装全部依赖，部分工具需要torch/transformer等深度学习依赖库，可能安装较久


Unstructured的相关依赖没有安装完整，可能需要额外步骤安装。也可以先试试其他四个工具。

如果 Unstructured 首次运行提示缺少 NLTK 数据，在 `llm-dev` 中运行：

```powershell
python -m nltk.downloader punkt_tab averaged_perceptron_tagger_eng
```

这些解析器依赖更重，首次运行可能下载模型。Docling 使用布局/表格模型；Marker 在本 PoC 中使用 `fast` 模式并关闭 OCR，但布局检测仍使用模型；MinerU 固定使用 `flash` 档；Unstructured 使用 `fast` 文本提取。当前 PyMuPDF 代码调用 `page.get_text("blocks")` 并保留图片元信息，不调用 `Page.find_tables()`；新版 PyMuPDF 包本身也会依赖 ONNX Runtime，供其其他布局分析功能使用。扫描版 PDF 建议先用 Docling 或 MinerU 检查 OCR 效果。MinerU 适配器针对 4.x 的 Middle JSON。

## 启动

两个 PowerShell 窗口，均从项目根目录开始：

```powershell
conda activate <your virtual env>
cd backend
uvicorn main:app --reload
```

```powershell
cd frontend
npm run dev
```

打开 <http://127.0.0.1:5173>。后端 API 文档在 <http://127.0.0.1:8000/docs>。

## 当前范围

- 前端支持显示/隐藏区域、类型过滤和 Block/Line/Span 粒度选择；具体粒度取决于解析器是否提供子块。
- `action` API 现在是下游任务的接入点：验证并返回所点块的文本、类型、页码和 bbox。要执行项目自己的下游任务，可以在 `backend/main.py` 的 `block_action` 中接入。
- 叠框按页面百分比缩放；旋转、裁切页，以及部分解析器的坐标约定可能需要用具体 PDF 再校准。
- 为保持极简，解析请求同步执行并写本地缓存。首次模型加载可能花较长时间；上传同一文件会生成新 ID。
