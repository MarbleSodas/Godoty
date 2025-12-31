import { safeHighlight } from './highlight'
import DOMPurify from 'dompurify'

// Configure DOMPurify with allowed tags and attributes for our markdown rendering
const DOMPURIFY_CONFIG = {
  ALLOWED_TAGS: [
    'h1', 'h2', 'h3', 'p', 'code', 'pre', 'strong', 'em', 'a', 'div', 'span',
    'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'button', 'svg', 'path'
  ],
  ALLOWED_ATTR: [
    'class', 'style', 'href', 'target', 'title',
    'data-artifact-id', 'data-lang', 'data-code', 'data-collapsed',
    'viewBox', 'fill', 'stroke', 'stroke-linecap', 'stroke-linejoin', 'stroke-width', 'd'
  ],
  FORBID_ATTR: ['onerror', 'onclick', 'onload', 'onmouseover', 'onfocus', 'onblur'],
  ALLOW_DATA_ATTR: true,
}

const MARKDOWN_CACHE_MAX_SIZE = 100
const markdownCache = new Map<string, string>()

export function parseMarkdown(text: string): string {
  if (!text) return ''

  const cached = markdownCache.get(text)
  if (cached !== undefined) return cached

  const codeBlockRegex = /(```[\w]*[\s\S]*?```)/g
  const parts = text.split(codeBlockRegex)

  const rawHtml = parts.map(part => {
    if (part.startsWith('```')) {
      return parseCodeBlock(part)
    } else {
      return parseTextContent(part)
    }
  }).join('')

  // Sanitize the final HTML output to prevent XSS attacks
  const sanitized = DOMPurify.sanitize(rawHtml, DOMPURIFY_CONFIG)

  if (markdownCache.size >= MARKDOWN_CACHE_MAX_SIZE) {
    const firstKey = markdownCache.keys().next().value
    if (firstKey) markdownCache.delete(firstKey)
  }
  markdownCache.set(text, sanitized)

  return sanitized
}

function parseCodeBlock(block: string): string {
  const match = block.match(/```(\w*)\n?([\s\S]*?)```/)
  if (!match) {
    return renderIncompleteCodeBlock(block)
  }

  const lang = match[1] || 'gdscript'
  const code = match[2].trim()
  
  if (!code) {
    return ''
  }
  
  const lineCount = code.split('\n').length
  const artifactId = `artifact-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
  const isLarge = lineCount >= 20

  try {
    const highlighted = safeHighlight(code, lang)

    return `<div class="code-block-wrapper my-2 rounded-lg overflow-hidden border border-[#3b4458] bg-[#1a1e29]" data-artifact-id="${artifactId}" data-lang="${lang}" data-code="${encodeURIComponent(code)}">
              <div class="code-block-header flex items-center justify-between px-3 py-2 bg-[#2d3546] border-b border-[#3b4458]">
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-400 font-mono">${lang}</span>
                  <span class="text-xs text-gray-600">${lineCount} lines</span>
                </div>
                <div class="flex items-center gap-1">
                  ${isLarge ? `<button class="code-view-panel-btn px-2 py-1 text-[10px] text-[#478cbf] hover:bg-[#478cbf]/10 rounded transition-colors" data-artifact-id="${artifactId}" title="View in panel">
                    <svg class="w-3.5 h-3.5 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                    </svg>
                    Expand
                  </button>` : ''}
                  <button class="code-collapse-btn px-2 py-1 text-[10px] text-gray-400 hover:text-white hover:bg-[#3b4458] rounded transition-colors" data-collapsed="false" title="Collapse code">
                    <svg class="collapse-icon w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  <button class="code-copy-btn px-2 py-1 text-[10px] text-gray-400 hover:text-white hover:bg-[#3b4458] rounded transition-colors flex items-center gap-1" title="Copy code">
                    <svg class="copy-icon w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <span class="copy-text">Copy</span>
                  </button>
                </div>
              </div>
              <div class="code-block-content transition-all duration-200 overflow-hidden" style="max-height: 600px;">
                <pre class="p-4 overflow-x-auto text-sm m-0"><code class="hljs language-${lang}">${highlighted}</code></pre>
              </div>
            </div>`
  } catch {
    return `<pre class="bg-[#1a1e29] rounded-lg p-4 my-4 overflow-x-auto border border-[#3b4458] text-sm"><code>${escapeHtml(code)}</code></pre>`
  }
}

function renderIncompleteCodeBlock(block: string): string {
  const langMatch = block.match(/```(\w*)/)
  const lang = langMatch?.[1] || ''
  const codeStart = block.indexOf('\n')
  const code = codeStart > 0 ? block.slice(codeStart + 1) : block.slice(3 + lang.length)
  
  if (!code.trim()) {
    return `<div class="code-block-wrapper my-2 rounded-lg overflow-hidden border border-[#3b4458] bg-[#1a1e29] animate-pulse">
              <div class="code-block-header flex items-center gap-2 px-3 py-2 bg-[#2d3546] border-b border-[#3b4458]">
                <span class="text-xs text-gray-400 font-mono">${lang || 'code'}</span>
                <span class="text-xs text-gray-600">streaming...</span>
              </div>
              <div class="p-4 h-8"></div>
            </div>`
  }
  
  const highlighted = safeHighlight(code, lang || 'plaintext')
  
  return `<div class="code-block-wrapper my-2 rounded-lg overflow-hidden border border-[#3b4458] bg-[#1a1e29]">
            <div class="code-block-header flex items-center gap-2 px-3 py-2 bg-[#2d3546] border-b border-[#3b4458]">
              <span class="text-xs text-gray-400 font-mono">${lang || 'code'}</span>
              <span class="text-xs text-gray-600 animate-pulse">streaming...</span>
            </div>
            <div class="code-block-content">
              <pre class="p-4 overflow-x-auto text-sm m-0"><code class="hljs language-${lang || 'plaintext'}">${highlighted}</code></pre>
            </div>
          </div>`
}

function parseTable(text: string): string {
  const tableRegex = /(?:^|\n)((?:\|[^\n]+\|\n)+)/g

  return text.replace(tableRegex, (match, tableBlock) => {
    const lines = tableBlock.trim().split('\n').filter((line: string) => line.trim())
    if (lines.length < 2) return match

    const separatorLine = lines[1]
    if (!/^\|[\s\-:|]+\|$/.test(separatorLine)) {
      return match
    }

    const alignments = separatorLine
      .split('|')
      .slice(1, -1)
      .map((cell: string) => {
        cell = cell.trim()
        if (cell.startsWith(':') && cell.endsWith(':')) return 'center'
        if (cell.endsWith(':')) return 'right'
        return 'left'
      })

    const headerCells = lines[0]
      .split('|')
      .slice(1, -1)
      .map((cell: string) => cell.trim())

    const dataRows = lines.slice(2).map((line: string) =>
      line.split('|').slice(1, -1).map((cell: string) => cell.trim())
    )

    let html = `<div class="overflow-x-auto my-2">
            <table class="min-w-full border-collapse border border-[#3b4458] rounded-lg overflow-hidden">
                <thead class="bg-[#2d3546]">
                    <tr>`

    headerCells.forEach((cell: string, i: number) => {
      const align = alignments[i] || 'left'
      html += `<th class="px-4 py-2 text-${align} text-sm font-semibold text-white border-b border-[#3b4458]">${cell}</th>`
    })

    html += `</tr></thead><tbody>`

    dataRows.forEach((row: string[], rowIndex: number) => {
      const rowBg = rowIndex % 2 === 0 ? 'bg-[#1a1e29]' : 'bg-[#202531]'
      html += `<tr class="${rowBg}">`
      row.forEach((cell: string, i: number) => {
        const align = alignments[i] || 'left'
        html += `<td class="px-4 py-2 text-${align} text-sm text-gray-300 border-b border-[#3b4458]/50">${cell}</td>`
      })
      html += `</tr>`
    })

    html += `</tbody></table></div>`

    return (match.startsWith('\n') ? '\n' : '') + html
  })
}

function parseTextContent(text: string): string {
  let html = parseTable(text)

  html = html.replace(/^### (.*$)/gm, '<h3 class="text-sm font-semibold text-white mt-2 mb-1">$1</h3>')
  html = html.replace(/^## (.*$)/gm, '<h2 class="text-base font-bold text-white mt-3 mb-1.5 border-b border-gray-700 pb-2">$1</h2>')
  html = html.replace(/^# (.*$)/gm, '<h1 class="text-lg font-bold text-white mt-4 mb-2 border-b border-gray-700 pb-2">$1</h1>')

  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-white">$1</strong>')

  html = html.replace(/\*([^*]+)\*/g, '<em class="italic text-gray-300">$1</em>')

  html = html.replace(/`([^`]+)`/g, '<code class="bg-[#1a1e29] px-1.5 py-0.5 rounded text-[#478cbf] font-mono text-xs border border-[#3b4458]">$1</code>')

  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, linkText, url) => {
    const normalizedUrl = url.toLowerCase().trim()
    if (normalizedUrl.startsWith('javascript:') || normalizedUrl.startsWith('data:')) {
      return escapeHtml(linkText)
    }
    return `<a href="${escapeHtml(url)}" target="_blank" class="text-[#478cbf] hover:underline">${escapeHtml(linkText)}</a>`
  })

  html = html.replace(/^- (.*$)/gm, '<div class="flex gap-2 mb-1 pl-4"><span class="text-gray-400">•</span><span class="text-gray-300 flex-1">$1</span></div>')

  html = html.replace(/^(\d+)\. (.*$)/gm, '<div class="flex gap-2 mb-1 pl-4"><span class="text-gray-400 font-mono text-xs pt-1">$1.</span><span class="text-gray-300 flex-1">$2</span></div>')

  html = html.replace(/^---$/gm, '<hr class="my-3 border-gray-700">')

  html = html.replace(/\n\n/g, '<div class="h-2"></div>')
  html = html.replace(/\n/g, '<br>')

  html = html.replace(/<\/(h1)><br>/g, '</h1>')
  html = html.replace(/<\/(h2)><br>/g, '</h2>')
  html = html.replace(/<\/(h3)><br>/g, '</h3>')
  html = html.replace(/<\/div><br>/g, '</div>')
  
  html = html.replace(/(<br>\s*)+$/g, '')
  html = html.replace(/(<div class="h-2"><\/div>\s*)+$/g, '')

  return html
}

function escapeHtml(text: string): string {
  const htmlEntities: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }
  return text.replace(/[&<>"']/g, char => htmlEntities[char])
}
