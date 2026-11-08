export type Block = {
  id: string
  type: string
  text: string
  bbox: [number, number, number, number]
  coordinate_system: 'top-left'
  confidence: number | null
  level: string
  polygon?: [number, number][]
  source_id?: string
}

export type ParsedPage = {
  page_index: number
  width: number
  height: number
  blocks: Block[]
}

export type ParseResult = {
  document_id: string
  parser: string
  elapsed_seconds: number
  pages: ParsedPage[]
}

export type ParserInfo = {
  id: string
  name: string
  installed: boolean
  package: string
}

async function json<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail || response.statusText)
  return body as T
}

export async function listParsers() {
  return json<ParserInfo[]>(await fetch('/api/parsers'))
}

export async function upload(file: File) {
  const form = new FormData()
  form.append('file', file)
  return json<{ document_id: string; filename: string; page_count: number }>(
    await fetch('/api/documents', { method: 'POST', body: form }),
  )
}

export async function parse(documentId: string, parser: string, force = false) {
  return json<ParseResult>(await fetch(`/api/documents/${documentId}/parse?parser=${parser}&force=${force}`, { method: 'POST' }))
}

export async function act(documentId: string, parser: string, blockId: string) {
  return json<{ page_index: number; block: Block }>(
    await fetch(`/api/documents/${documentId}/blocks/${encodeURIComponent(blockId)}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parser }),
    }),
  )
}
