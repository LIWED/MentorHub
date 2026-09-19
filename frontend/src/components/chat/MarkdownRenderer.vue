<template>
  <div class="md-content" ref="contentRef" v-html="rendered" @click="handleContentClick" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { ElMessage } from 'element-plus'

const props = defineProps<{ content: string }>()
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

const rendered = computed(() => md.render(props.content))

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
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
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
  font-family: ui-monospace, Consolas, monospace;
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
  margin: 10px 0;
  padding: 8px 14px;
  border-left: 4px solid var(--nm-primary);
  background: rgba(59, 130, 246, 0.06);
  border-radius: 0 var(--nm-radius-sm) var(--nm-radius-sm) 0;
  color: var(--nm-text-regular);
}
</style>
