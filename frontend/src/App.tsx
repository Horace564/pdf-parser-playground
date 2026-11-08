import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { act, listParsers, parse, upload, type Block, type ParseResult, type ParserInfo } from './api'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

const choices = ['pymupdf', 'docling', 'mineru', 'marker', 'unstructured']

function BlockOverlay({ page, blocks, hovered, selected, onHover, onSelect }: {
  page: { width: number; height: number }
  blocks: Block[]
  hovered: string | null
  selected: string | null
  onHover: (id: string | null) => void
  onSelect: (block: Block) => void
}) {
  return <div className="overlay">
    {blocks.map((block) => {
      const [x0, y0, x1, y1] = block.bbox
      return <button
        key={block.id}
        className={`block-box ${selected === block.id ? 'selected' : ''} ${hovered === block.id ? 'hovered' : ''}`}
        style={{ left: `${x0 / page.width * 100}%`, top: `${y0 / page.height * 100}%`, width: `${(x1 - x0) / page.width * 100}%`, height: `${(y1 - y0) / page.height * 100}%` }}
        title={`${block.type} · ${block.id}\n${block.text.slice(0, 160)}`}
        aria-label={`${block.type}: ${block.text.slice(0, 80)}`}
        onMouseEnter={() => onHover(block.id)}
        onMouseLeave={() => onHover(null)}
        onClick={() => onSelect(block)}
      />
    })}
  </div>
}

export default function App() {
  const [parsers, setParsers] = useState<ParserInfo[]>([])
  const [documentId, setDocumentId] = useState('')
  const [filename, setFilename] = useState('')
  const [parser, setParser] = useState('pymupdf')
  const [result, setResult] = useState<ParseResult | null>(null)
  const [pageCount, setPageCount] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [hovered, setHovered] = useState<string | null>(null)
  const [selected, setSelected] = useState<{ page_index: number; block: Block } | null>(null)
  const [showBoxes, setShowBoxes] = useState(true)
  const [kind, setKind] = useState('all')
  const [level, setLevel] = useState('block')
  const stageRef = useRef<HTMLDivElement>(null)
  const requestRef = useRef(0)
  const [pageWidth, setPageWidth] = useState(700)

  useEffect(() => {
    listParsers().then(setParsers).catch((err) => setError(`无法连接后端：${err.message}`))
  }, [])

  useEffect(() => {
    if (!stageRef.current) return
    const observer = new ResizeObserver(([entry]) => setPageWidth(Math.max(200, Math.min(850, entry.contentRect.width - 40))))
    observer.observe(stageRef.current)
    return () => observer.disconnect()
  }, [])

  async function runParse(id: string, nextParser: string, force = false) {
    const request = ++requestRef.current
    setBusy(true)
    setError('')
    setResult(null)
    setSelected(null)
    setHovered(null)
    setKind('all')
    setLevel('block')
    try {
      const data = await parse(id, nextParser, force)
      if (request === requestRef.current) setResult(data)
    } catch (err) {
      if (request === requestRef.current) setError((err as Error).message)
    } finally {
      if (request === requestRef.current) setBusy(false)
    }
  }

  async function onUpload(file?: File) {
    if (!file) return
    ++requestRef.current
    setBusy(true)
    setError('')
    setResult(null)
    setSelected(null)
    setDocumentId('')
    setPageCount(0)
    try {
      const doc = await upload(file)
      setDocumentId(doc.document_id)
      setFilename(doc.filename)
      setPageCount(doc.page_count)
      await runParse(doc.document_id, parser)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  async function onSelect(block: Block) {
    if (!documentId || !result) return
    setError('')
    try {
      const data = await act(documentId, parser, block.id)
      setSelected(data)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const types = useMemo(() => [...new Set(result?.pages.flatMap((page) => page.blocks.map((block) => block.type)) || [])].sort(), [result])
  const visible = (blocks: Block[]) => blocks.filter((block) => (kind === 'all' || block.type === kind) && (level === 'all' || block.level === level))
  const allBlocks = result?.pages.flatMap((page) => visible(page.blocks).map((block) => ({ page_index: page.page_index, block }))) || []
  const fileUrl = documentId ? `/api/documents/${documentId}/file` : ''

  return <div className="app">
    <header className="topbar">
      <div><h1>PDF Parser Playground</h1><span>同一份 PDF，对比不同解析器识别的区域</span></div>
      <label className="upload-button">上传 PDF<input type="file" accept=".pdf,application/pdf" onChange={(event) => { void onUpload(event.target.files?.[0]); event.target.value = '' }} /></label>
    </header>

    <div className="toolbar">
      <div className="tool"><label htmlFor="parser">解析器</label><select id="parser" value={parser} onChange={(event) => { const next = event.target.value; setParser(next); if (documentId) void runParse(documentId, next) }}>
        {choices.map((id) => { const info = parsers.find((item) => item.id === id); return <option key={id} value={id}>{info?.name || id}{info && !info.installed ? ' · 未安装' : ''}</option> })}
      </select></div>
      {documentId && <button className="rerun-button" disabled={busy} onClick={() => { void runParse(documentId, parser, true) }}>重跑当前解析器</button>}
      <label className="check"><input type="checkbox" checked={showBoxes} onChange={(event) => setShowBoxes(event.target.checked)} />显示区域框</label>
      <div className="tool"><label htmlFor="type">类型</label><select id="type" value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">全部</option>{types.map((type) => <option key={type}>{type}</option>)}</select></div>
      <div className="tool"><label htmlFor="level">粒度</label><select id="level" value={level} onChange={(event) => setLevel(event.target.value)}><option value="block">Block</option><option value="line">Line</option><option value="span">Span</option><option value="all">全部</option></select></div>
      {result && <span className="metrics">{result.pages.reduce((sum, page) => sum + page.blocks.length, 0)} 块 · {result.elapsed_seconds}s</span>}
    </div>

    {error && <div className="error" role="alert">{error}</div>}
    <main className="workspace">
      <section className="preview" ref={stageRef}>
        {!documentId ? <div className="empty"><strong>选择一份 PDF 开始</strong><p>上传后自动使用 PyMuPDF 解析；也可以切换其他解析器。</p></div> : <>
          <div className="section-heading"><strong>{filename}</strong><span>{pageCount} 页 {busy && '· 解析中…'}</span></div>
          <Suspense fallback={<p className="loading">正在加载 PDF…</p>}>
            <Document file={fileUrl} onLoadSuccess={({ numPages }) => setPageCount(numPages)} onLoadError={(err) => setError(`PDF 加载失败：${err.message}`)} loading={<p className="loading">正在加载 PDF…</p>}>
              {Array.from({ length: pageCount }, (_, i) => {
                const page = result?.pages[i]
                return <div className="page-section" key={i} id={`page-${i}`}>
                  <div className="page-label">第 {i + 1} 页</div>
                  <div className="page-frame" style={{ width: pageWidth }}>
                    <Page pageNumber={i + 1} width={pageWidth} renderTextLayer={false} renderAnnotationLayer={false} />
                    {showBoxes && page && <BlockOverlay page={page} blocks={visible(page.blocks)} hovered={hovered} selected={selected?.block.id || null} onHover={setHovered} onSelect={(block) => { void onSelect(block) }} />}
                  </div>
                </div>
              })}
            </Document>
          </Suspense>
        </>}
      </section>

      <aside className="sidebar">
        <div className="panel-heading"><h2>识别块</h2><span>{allBlocks.length}</span></div>
        <div className="block-list">
          {allBlocks.length ? allBlocks.map(({ page_index, block }) => <button key={block.id} className={`block-item ${selected?.block.id === block.id ? 'active' : ''}`} onMouseEnter={() => setHovered(block.id)} onMouseLeave={() => setHovered(null)} onClick={() => { document.getElementById(`page-${page_index}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); void onSelect(block) }}>
            <span className="item-meta">第 {page_index + 1} 页 · {block.type} · {block.level}</span>
            <span className="item-text">{block.text || '（无文本）'}</span>
          </button>) : <p className="muted">{busy ? '正在解析…' : result ? result.pages.every((page) => page.blocks.length === 0) ? '解析器没有返回可显示的块；请查看原始 JSON，或重跑当前解析器。' : '当前筛选条件下没有块' : '解析后显示区域列表'}</p>}
        </div>
        <div className="inspector">
          <h2>选中区域</h2>
          {selected ? <>
            <dl><dt>Block ID</dt><dd>{selected.block.id}</dd><dt>解析器</dt><dd>{parser}</dd><dt>页码</dt><dd>{selected.page_index + 1}</dd><dt>类型</dt><dd>{selected.block.type}</dd><dt>BBox</dt><dd>[{selected.block.bbox.join(', ')}]</dd></dl>
            <p className="selected-text">{selected.block.text || '（无文本）'}</p>
            <p className="muted">已通过 action API 回传并由后端按 ID 查到此块。</p>
          </> : <p className="muted">点击 PDF 上的区域框或列表项。</p>}
          {result && <a className="raw-link" href={`/api/documents/${documentId}/results/${parser}/raw`} target="_blank" rel="noreferrer">查看原始 JSON ↗</a>}
        </div>
      </aside>
    </main>
  </div>
}
