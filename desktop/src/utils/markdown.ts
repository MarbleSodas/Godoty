/**
 * Simple Markdown Parser for Godoty
 * Designed to handle streaming content gracefully without external dependencies.
 */

import hljs from 'highlight.js/lib/core'

/**
 * Parses markdown text into HTML.
 * Handles:
 * - Code blocks (with syntax highlighting)
 * - Headers
 * - Bold/Italic
 * - Inline code
 * - Links
 * - Lists
 * - Paragraphs
 */
export function parseMarkdown(text: string): string {
  if (!text) return ''

  // 1. Split code blocks from text to avoid parsing inside code
  // This is a simplified approach: we split by ```
  const parts = text.split(/(```\w*\n?[\s\S]*?```)/g)

  return parts.map(part => {
    if (part.startsWith('```')) {
      return parseCodeBlock(part)
    } else {
      return parseTextContent(part)
    }
  }).join('')
}

function parseCodeBlock(block: string): string {
  // Extract language and code
  const match = block.match(/```(\w+)?\n([\s\S]*?)```/)
  if (!match) return block // Should not happen given the split

  const lang = match[1] || 'gdscript'
  const code = match[2].trim()
  const lineCount = code.split('\n').length
  const artifactId = `artifact-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

  // Determine if this is a large code block (20+ lines)
  const isLarge = lineCount >= 20

  try {
    const highlighted = hljs.highlight(code, { language: lang }).value

    // Build the code block with collapsible wrapper
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
    return `<pre class="bg-[#1a1e29] rounded-lg p-4 my-4 overflow-x-auto border border-[#3b4458] text-sm"><code>${code}</code></pre>`
  }
}

/**
 * Parse markdown tables into HTML tables with proper styling
 * Supports:
 * - Header rows
 * - Alignment indicators (:---, :---:, ---:)
 * - Multi-column tables
 */
function parseTable(text: string): string {
  // Match table pattern: lines starting with | that form a valid table
  const tableRegex = /(?:^|\n)((?:\|[^\n]+\|\n)+)/g

  return text.replace(tableRegex, (match, tableBlock) => {
    const lines = tableBlock.trim().split('\n').filter((line: string) => line.trim())
    if (lines.length < 2) return match // Need at least header + separator

    // Check if second line is a separator (contains only |, -, :, and spaces)
    const separatorLine = lines[1]
    if (!/^\|[\s\-:|]+\|$/.test(separatorLine)) {
      return match // Not a valid table
    }

    // Parse alignment from separator
    const alignments = separatorLine
      .split('|')
      .slice(1, -1) // Remove empty first/last from split
      .map((cell: string) => {
        cell = cell.trim()
        if (cell.startsWith(':') && cell.endsWith(':')) return 'center'
        if (cell.endsWith(':')) return 'right'
        return 'left'
      })

    // Parse header
    const headerCells = lines[0]
      .split('|')
      .slice(1, -1)
      .map((cell: string) => cell.trim())

    // Parse data rows
    const dataRows = lines.slice(2).map((line: string) =>
      line.split('|').slice(1, -1).map((cell: string) => cell.trim())
    )

    // Build HTML table
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
  // First, handle tables before other processing
  let html = parseTable(text)

  // Headers
  html = html.replace(/^### (.*$)/gm, '<h3 class="text-sm font-semibold text-white mt-2 mb-1">$1</h3>')
  html = html.replace(/^## (.*$)/gm, '<h2 class="text-base font-bold text-white mt-3 mb-1.5 border-b border-gray-700 pb-2">$1</h2>')
  html = html.replace(/^# (.*$)/gm, '<h1 class="text-lg font-bold text-white mt-4 mb-2 border-b border-gray-700 pb-2">$1</h1>')

  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-white">$1</strong>')

  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em class="italic text-gray-300">$1</em>')

  // Inline Code
  html = html.replace(/`([^`]+)`/g, '<code class="bg-[#1a1e29] px-1.5 py-0.5 rounded text-[#478cbf] font-mono text-xs border border-[#3b4458]">$1</code>')

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-[#478cbf] hover:underline">$1</a>')

  // Lists (Unordered) - Simple line replacement
  html = html.replace(/^- (.*$)/gm, '<div class="flex gap-2 mb-1 pl-4"><span class="text-gray-400">•</span><span class="text-gray-300 flex-1">$1</span></div>')

  // Lists (Ordered) - Simple line replacement
  html = html.replace(/^(\d+)\. (.*$)/gm, '<div class="flex gap-2 mb-1 pl-4"><span class="text-gray-400 font-mono text-xs pt-1">$1.</span><span class="text-gray-300 flex-1">$2</span></div>')

  // Separator
  html = html.replace(/^---$/gm, '<hr class="my-3 border-gray-700">')

  // Paragraphs / Newlines
  // We use a simplified strategy: existing newlines are respected
  // but we want to avoid double spacing if we replaced block elements
  // This is tricky with regex. A safe bet for basic display:
  // Double newline -> break
  html = html.replace(/\n\n/g, '<div class="h-2"></div>')
  // Single newline -> br, BUT NOT inside our generated HTML tags from listeners?
  // We already replaced headers/lists which swallow the line.
  // So remaining newlines are likely soft breaks
  html = html.replace(/\n/g, '<br>')

  // Cleanup: Remove <br> after block elements if any (hacky)
  html = html.replace(/<\/h[1-3]><br>/g, '</h$1>')
  html = html.replace(/<\/div><br>/g, '</div>')
  
  html = html.replace(/(<br>\s*)+$/g, '')
  html = html.replace(/(<div class="h-2"><\/div>\s*)+$/g, '')

  return html
}
