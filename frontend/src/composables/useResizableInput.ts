import { ref } from 'vue'

/**
 * useResizableInput - 提供通过拉动输入框上边界调节高度/尺寸的交互能力
 * @param defaultHeight 默认高度（px），对应默认 3 行文本区
 * @param minHeight 最小高度限制（px）
 * @param maxHeight 最大高度限制（px）
 */
export function useResizableInput(defaultHeight = 76, minHeight = 56, maxHeight = 500) {
  const inputHeight = ref(defaultHeight)
  const isDraggingInput = ref(false)

  function handleResizeStart(e: MouseEvent) {
    e.preventDefault()
    isDraggingInput.value = true
    const startY = e.clientY
    const startHeight = inputHeight.value

    document.body.classList.add('is-resizing-input')
    document.body.style.cursor = 'row-resize'
    document.body.style.userSelect = 'none'

    let rafId: number | null = null
    const onMouseMove = (moveEvent: MouseEvent) => {
      if (rafId !== null) return
      rafId = requestAnimationFrame(() => {
        // 往上拉动（moveEvent.clientY < startY）=> deltaY > 0 => 高度增加
        const deltaY = startY - moveEvent.clientY
        const newHeight = Math.max(minHeight, Math.min(maxHeight, Math.round(startHeight + deltaY)))
        inputHeight.value = newHeight
        rafId = null
      })
    }

    const onMouseUp = () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId)
        rafId = null
      }
      isDraggingInput.value = false
      document.body.classList.remove('is-resizing-input')
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }

    window.addEventListener('mousemove', onMouseMove, { passive: true })
    window.addEventListener('mouseup', onMouseUp)
  }

  function resetInputHeight() {
    inputHeight.value = defaultHeight
  }

  return {
    inputHeight,
    isDraggingInput,
    handleResizeStart,
    resetInputHeight,
  }
}
