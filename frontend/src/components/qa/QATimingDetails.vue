<template>
  <div class="qa-timing">
    <button
      type="button"
      class="timing-summary"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="timing-main">
        <el-icon class="timing-icon"><Timer /></el-icon>
        <span>总耗时 {{ formatDuration(timing.total_ms) }}</span>
      </span>
      <span class="timing-detail-toggle">
        {{ expanded ? '收起详情' : '查看耗时详情' }}
        <el-icon class="toggle-icon" :class="{ expanded }"><ArrowDown /></el-icon>
      </span>
    </button>

    <div v-if="expanded" class="timing-details">
      <div
        v-for="node in timing.nodes"
        :key="node.name"
        class="timing-row"
      >
        <span class="node-label">{{ node.label }}</span>
        <span class="node-duration">{{ formatDuration(node.elapsed_ms) }}</span>
      </div>

      <div v-if="!timing.nodes.length" class="timing-empty">
        暂无节点耗时明细
      </div>

      <div class="timing-note">
        节点耗时为实际执行阶段；总耗时还包含请求准备、流式传输和会话保存等开销。
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ArrowDown, Timer } from '@element-plus/icons-vue'
import type { QATiming } from '@/api/qa'

defineProps<{
  timing: QATiming
}>()

const expanded = ref(false)

function formatDuration(ms: number) {
  if (!Number.isFinite(ms)) return '--'
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`
  return `${(ms / 1000).toFixed(ms >= 10_000 ? 1 : 2)} s`
}
</script>

<style scoped>
.qa-timing {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
}

.timing-summary {
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: var(--nm-text-secondary);
  cursor: pointer;
  font: inherit;
}

.timing-main,
.timing-detail-toggle {
  display: inline-flex;
  align-items: center;
}

.timing-main {
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
}

.timing-icon {
  color: var(--nm-primary);
  font-size: 14px;
}

.timing-detail-toggle {
  gap: 4px;
  color: var(--nm-text-light);
  font-size: 11px;
  transition: color 0.2s ease;
}

.timing-summary:hover .timing-detail-toggle {
  color: var(--nm-primary);
}

.toggle-icon {
  transition: transform 0.2s ease;
}

.toggle-icon.expanded {
  transform: rotate(180deg);
}

.timing-details {
  margin-top: 9px;
  padding: 9px 10px;
  border-radius: var(--nm-radius-sm);
  background: rgba(241, 245, 249, 0.72);
  box-shadow: inset 1px 1px 3px rgba(148, 163, 184, 0.14);
}

.timing-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 26px;
  border-bottom: 1px dashed rgba(148, 163, 184, 0.2);
  font-size: 12px;
}

.timing-row:last-of-type {
  border-bottom: 0;
}

.node-label {
  color: var(--nm-text-secondary);
}

.node-duration {
  flex-shrink: 0;
  color: var(--nm-text-primary);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.timing-empty {
  padding: 4px 0;
  color: var(--nm-text-light);
  font-size: 12px;
}

.timing-note {
  margin-top: 7px;
  color: var(--nm-text-light);
  font-size: 10.5px;
  line-height: 1.45;
}
</style>
