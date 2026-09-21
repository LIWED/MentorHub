<template>
  <div class="md-content" ref="contentRef" v-html="rendered" @click="handleContentClick" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { ElMessage } from 'element-plus'

const props = withDefaults(
  defineProps<{
    content?: string
  }>(),
  {
    content: '',
  }
)
const contentRef = ref<HTMLElement>()

const md: MarkdownIt = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
})

// 自定义代码块 (fence) 渲染规则，彻底解决默认 fence 外层包裹多余 <pre><code> 导致的空白与对齐异常
md.renderer.rules.fence = function (tokens, idx) {
  const token = tokens[idx]
  const info = token.info ? token.info.trim() : ''
  const lang = info ? info.split(/\s+/g)[0] : ''
  const str = token.content

  let codeHtml = ''
  if (lang && hljs.getLanguage(lang)) {
    try {
      codeHtml = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
    } catch {
      codeHtml = md.utils.escapeHtml(str)
    }
  } else {
    codeHtml = md.utils.escapeHtml(str)
  }

  const encoded = encodeURIComponent(str)
  const langDisplay = (lang || 'code').toUpperCase()

  return `<div class="code-card"><div class="code-header"><div class="code-header-left"><span class="mac-dot red"></span><span class="mac-dot yellow"></span><span class="mac-dot green"></span><span class="code-lang-label">${langDisplay}</span></div><button class="copy-code-btn" type="button" data-code="${encoded}"><svg class="copy-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span class="copy-text">复制</span></button></div><pre class="code-body"><code>${codeHtml}</code></pre></div>`
}

// 自定义表格渲染规则：为表格包裹响应式横向滚动容器，并注入拟物风格 class
md.renderer.rules.table_open = () => '<div class="table-wrapper"><table class="nm-table">'
md.renderer.rules.table_close = () => '</table></div>'

// 数学公式 KaTeX 解析插件（支持块级公式与行内公式，兼顾行内 $$...$$ 与 $...$ 及 LaTeX 转义）
function setupMathPlugin(mdInstance: MarkdownIt) {
  // 块级公式: $$ ... $$ 或 \[ ... \]
  mdInstance.block.ruler.before('fence', 'math_block', (state, startLine, endLine, silent) => {
    const pos = state.bMarks[startLine] + state.tShift[startLine]
    const max = state.eMarks[startLine]
    const openMarker = state.src.slice(pos, pos + 2)
    if (openMarker !== '$$' && openMarker !== '\\[') return false
    const closeMarker = openMarker === '$$' ? '$$' : '\\]'
    const firstLine = state.src.slice(pos + 2, max)

    if (silent) return true

    let haveEndMarker = false
    if (firstLine.trim().endsWith(closeMarker) && firstLine.trim().length >= 2) {
      const content = firstLine.trim().slice(0, -closeMarker.length)
      const token = state.push('math_block', 'math', 0)
      token.block = true
      token.content = content
      token.map = [startLine, startLine + 1]
      state.line = startLine + 1
      return true
    }

    let nextLine = startLine
    const lines: string[] = []
    while (nextLine < endLine) {
      nextLine++
      if (nextLine >= endLine) break
      const curPos = state.bMarks[nextLine] + state.tShift[nextLine]
      const curMax = state.eMarks[nextLine]
      const line = state.src.slice(curPos, curMax)
      if (line.trim().endsWith(closeMarker)) {
        haveEndMarker = true
        const lastContent = line.trim().slice(0, -closeMarker.length)
        if (lastContent) lines.push(lastContent)
        break
      }
      lines.push(line)
    }

    if (!haveEndMarker) return false

    state.line = nextLine + 1
    const token = state.push('math_block', 'math', 0)
    token.block = true
    token.content = (firstLine ? firstLine + '\n' : '') + lines.join('\n')
    token.map = [startLine, state.line]
    return true
  })

  // 行内公式: $$...$$, $...$, \(...\), \[...\]
  mdInstance.inline.ruler.before('escape', 'math_inline', (state, silent) => {
    const start = state.pos
    const max = state.posMax
    const ch = state.src.charCodeAt(start)

    let isDouble = false
    let isBracket = false
    let openLen = 1
    let closeMarker = '$'

    if (ch === 0x24 /* $ */) {
      if (start + 1 < max && state.src.charCodeAt(start + 1) === 0x24) {
        isDouble = true
        openLen = 2
        closeMarker = '$$'
      } else {
        openLen = 1
        closeMarker = '$'
      }
    } else if (ch === 0x5C /* \ */ && start + 1 < max) {
      const nextCh = state.src.charAt(start + 1)
      if (nextCh === '(') {
        isBracket = true
        openLen = 2
        closeMarker = '\\)'
      } else if (nextCh === '[') {
        isDouble = true
        isBracket = true
        openLen = 2
        closeMarker = '\\]'
      } else {
        return false
      }
    } else {
      return false
    }

    const matchStart = start + openLen
    let matchEnd = -1

    for (let i = matchStart; i < max; i++) {
      if (state.src.charCodeAt(i) === 0x5C /* \ */ && !isBracket) {
        i++
        continue
      }
      if (state.src.slice(i, i + closeMarker.length) === closeMarker) {
        matchEnd = i
        break
      }
    }

    if (matchEnd === -1) return false
    if (!silent) {
      const content = state.src.slice(matchStart, matchEnd)
      const token = state.push(isDouble ? 'math_display_inline' : 'math_inline', 'math', 0)
      token.content = content
      token.markup = closeMarker
    }
    state.pos = matchEnd + closeMarker.length
    return true
  })

  mdInstance.renderer.rules.math_block = (tokens, idx) => {
    return `<div class="math-block">${katex.renderToString(tokens[idx].content, { displayMode: true, throwOnError: false })}</div>`
  }
  mdInstance.renderer.rules.math_display_inline = (tokens, idx) => {
    return `<span class="math-display-inline">${katex.renderToString(tokens[idx].content, { displayMode: true, throwOnError: false })}</span>`
  }
  mdInstance.renderer.rules.math_inline = (tokens, idx) => {
    return `<span class="math-inline">${katex.renderToString(tokens[idx].content, { displayMode: false, throwOnError: false })}</span>`
  }
}

setupMathPlugin(md)

const rendered = computed(() => {
  try {
    return md.render(props.content || '')
  } catch (err) {
    console.error('[MarkdownRenderer render error]', err)
    return md.utils.escapeHtml(props.content || '')
  }
})

function handleContentClick(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest('.copy-code-btn') as HTMLButtonElement | null
  if (!target) return

  const encodedCode = target.getAttribute('data-code')
  if (!encodedCode) return

  const rawCode = decodeURIComponent(encodedCode)
  navigator.clipboard.writeText(rawCode).then(() => {
    const textSpan = target.querySelector('.copy-text')
    if (textSpan) {
      const orig = textSpan.textContent
      textSpan.textContent = '已复制 ✓'
      target.classList.add('copied')
      setTimeout(() => {
        textSpan.textContent = orig
        target.classList.remove('copied')
      }, 1500)
    }
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}
</script>

<style scoped>
.md-content :deep(p) {
  margin: 0 0 10px;
}

.md-content :deep(p:last-child) {
  margin-bottom: 0;
}

/* 标题层次与高对比度排版增强 */
.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3),
.md-content :deep(h4) {
  color: var(--nm-text-primary);
  font-weight: 700;
  margin: 18px 0 10px;
  line-height: 1.4;
}

.md-content :deep(h1) {
  font-size: 18px;
  border-bottom: 2px solid rgba(203, 213, 225, 0.5);
  padding-bottom: 6px;
}

.md-content :deep(h2) {
  font-size: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.md-content :deep(h2)::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 15px;
  border-radius: 2px;
  background: var(--nm-primary-gradient);
}

.md-content :deep(h3) {
  font-size: 14.5px;
  margin-top: 14px;
}

.md-content :deep(h4) {
  font-size: 13.5px;
}

.md-content :deep(strong) {
  color: #0f172a;
  font-weight: 700;
}

/* 拟物风格现代化代码块卡片 */
.md-content :deep(.code-card) {
  margin: 14px 0;
  border-radius: var(--nm-radius-md);
  background: #111827;
  overflow: hidden;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.25), 4px 4px 12px rgba(166, 180, 200, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: var(--nm-transition);
}

.md-content :deep(.code-card:hover) {
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.32), 6px 6px 16px rgba(166, 180, 200, 0.4);
}

/* 代码头部栏 */
.md-content :deep(.code-header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: #1e293b;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  user-select: none;
}

.md-content :deep(.code-header-left) {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 经典 macOS 视窗三色点 */
.md-content :deep(.mac-dot) {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.md-content :deep(.mac-dot.red)    { background: #ef4444; }
.md-content :deep(.mac-dot.yellow) { background: #f59e0b; }
.md-content :deep(.mac-dot.green)  { background: #10b981; }

.md-content :deep(.code-lang-label) {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 700;
  letter-spacing: 0.5px;
  margin-left: 8px;
}

/* 完美居中的复制按钮 */
.md-content :deep(.copy-code-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 26px;
  padding: 0 10px;
  line-height: 1;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  color: #cbd5e1;
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-sizing: border-box;
}

.md-content :deep(.copy-code-btn:hover) {
  background: rgba(255, 255, 255, 0.18);
  color: #ffffff;
  transform: translateY(-1px);
  border-color: rgba(255, 255, 255, 0.25);
}

.md-content :deep(.copy-code-btn:active) {
  transform: translateY(1px);
}

.md-content :deep(.copy-code-btn.copied) {
  background: #10b981 !important;
  border-color: #10b981 !important;
  color: #ffffff !important;
}

.md-content :deep(.copy-svg) {
  flex-shrink: 0;
}

.md-content :deep(.copy-text) {
  display: inline-block;
  line-height: 1;
}

/* 代码主体：无冗余空隙，精美字号与行高 */
.md-content :deep(pre.code-body) {
  margin: 0;
  padding: 14px 16px;
  overflow-x: auto;
  font-size: 13.5px;
  font-family: var(--nm-font-mono);
  line-height: 1.6;
  background: #111827;
  color: #f3f4f6;
  border: none;
}

.md-content :deep(pre.code-body code) {
  font-family: inherit;
  font-size: inherit;
  background: transparent !important;
  padding: 0 !important;
  border: none !important;
  box-shadow: none !important;
  color: inherit !important;
  white-space: pre;
}

/* 行内代码 */
.md-content :deep(code:not(pre code)) {
  background: var(--nm-bg);
  color: var(--nm-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: var(--nm-font-mono);
  box-shadow: inset 1px 1px 2px rgba(166, 180, 200, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.6);
}

.md-content :deep(ul),
.md-content :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.md-content :deep(li) {
  margin-bottom: 4px;
}

.md-content :deep(blockquote) {
  margin: 12px 0;
  padding: 10px 16px;
  border-left: 4px solid var(--nm-primary);
  background: rgba(59, 130, 246, 0.07);
  border-radius: 0 var(--nm-radius-sm) var(--nm-radius-sm) 0;
  color: var(--nm-text-regular);
}

/* 拟物风格现代化表格 (解决图 2 无边框问题) */
.md-content :deep(.table-wrapper) {
  margin: 16px 0;
  overflow-x: auto;
  border-radius: var(--nm-radius-md);
  box-shadow: 3px 3px 10px rgba(166, 180, 200, 0.35), -2px -2px 8px rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(203, 213, 225, 0.6);
  background: #ffffff;
}

.md-content :deep(.nm-table) {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13.5px;
  line-height: 1.6;
  text-align: left;
}

.md-content :deep(.nm-table th) {
  background: linear-gradient(180deg, #f8fafc 0%, #edf2f7 100%);
  color: var(--nm-text-primary);
  font-weight: 700;
  padding: 12px 16px;
  border-bottom: 2px solid #cbd5e1;
  border-right: 1px solid rgba(203, 213, 225, 0.5);
  white-space: nowrap;
  letter-spacing: 0.3px;
}

.md-content :deep(.nm-table th:last-child) {
  border-right: none;
}

.md-content :deep(.nm-table td) {
  padding: 11px 16px;
  color: var(--nm-text-regular);
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
  border-right: 1px solid rgba(226, 232, 240, 0.6);
  vertical-align: top;
  transition: background 0.15s ease;
}

.md-content :deep(.nm-table td:last-child) {
  border-right: none;
}

.md-content :deep(.nm-table tr:last-child td) {
  border-bottom: none;
}

.md-content :deep(.nm-table tr:nth-child(even) td) {
  background: rgba(248, 250, 252, 0.7);
}

.md-content :deep(.nm-table tr:hover td) {
  background: rgba(59, 130, 246, 0.06);
}

.md-content :deep(.nm-table td:first-child) {
  font-weight: 600;
  color: #1e293b;
}

/* 数学公式 KaTeX 拟物渲染 (解决图 1 公式无法渲染问题) */
.md-content :deep(.math-block) {
  margin: 14px 0;
  padding: 12px 18px;
  overflow-x: auto;
  border-radius: var(--nm-radius-sm);
  background: rgba(241, 245, 249, 0.6);
  border: 1px solid rgba(226, 232, 240, 0.8);
  box-shadow: inset 1px 1px 3px rgba(166, 180, 200, 0.2);
  text-align: center;
}

.md-content :deep(.math-display-inline) {
  display: block;
  margin: 10px 0;
  padding: 8px 14px;
  overflow-x: auto;
  border-radius: var(--nm-radius-sm);
  background: rgba(241, 245, 249, 0.5);
  border: 1px solid rgba(226, 232, 240, 0.7);
  text-align: center;
}

.md-content :deep(.math-inline) {
  padding: 0 4px;
  display: inline-block;
  vertical-align: middle;
}

.md-content :deep(.katex) {
  font-size: 1.05em;
  text-rendering: auto;
}

.md-content :deep(.katex-display) {
  margin: 0.4em 0;
  overflow-x: auto;
  overflow-y: hidden;
}
</style>
