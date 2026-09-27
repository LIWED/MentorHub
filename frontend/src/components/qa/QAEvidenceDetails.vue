<template>
  <div class="evidence-box">
    <el-collapse class="evidence-collapse">
      <el-collapse-item name="evidence">
        <template #title>
          <div class="evidence-title">
            <span>📎 证据（{{ citations.length }} 条）</span>
          </div>
        </template>

        <div class="evidence-list">
          <div
            v-for="citation in citations"
            :key="`${citation.citation_id}-${citation.document_id}-${citation.chunk_index}`"
            class="evidence-card"
          >
            <div class="evidence-head">
              <div class="evidence-source">
                <span class="citation-id">【{{ citation.citation_id }}】</span>
                <span class="source-name">{{ citation.source_name }}</span>
              </div>
              <el-tag size="small" effect="plain">
                {{ scoreText(citation.score) }}
              </el-tag>
            </div>

            <div class="evidence-meta">
              <span v-if="citation.relative_path">{{ citation.relative_path }}</span>
              <span v-if="citation.section">· {{ citation.section }}</span>
              <span>· Chunk {{ citation.chunk_index }}</span>
              <span v-if="citation.chunk_type">· {{ citation.chunk_type }}</span>
            </div>

            <div class="evidence-excerpt">{{ citation.excerpt }}</div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import type { QACitation } from '@/api/qa'

defineProps<{
  citations: QACitation[]
}>()

function scoreText(score: number) {
  return `相关性 ${(score * 100).toFixed(1)}%`
}
</script>

<style scoped>
.evidence-box {
  margin-top: 8px;
}

.evidence-collapse {
  border: none !important;
  background: transparent !important;
}

.evidence-collapse :deep(.el-collapse-item__header) {
  height: 32px;
  padding: 0 12px;
  border: 1px solid rgba(59, 130, 246, 0.12);
  border-radius: var(--nm-radius-sm);
  background: rgba(59, 130, 246, 0.05);
  color: var(--nm-text-secondary);
  font-size: 12px;
}

.evidence-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}

.evidence-collapse :deep(.el-collapse-item__content) {
  padding: 8px 0 0;
}

.evidence-title {
  font-weight: 600;
}

.evidence-list {
  display: grid;
  gap: 8px;
}

.evidence-card {
  padding: 10px 12px;
  border-radius: var(--nm-radius-sm);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset);
}

.evidence-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.evidence-source {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.citation-id {
  color: var(--nm-primary);
  font-weight: 700;
  flex-shrink: 0;
}

.source-name {
  color: var(--nm-text-primary);
  font-size: 12.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.evidence-meta {
  margin-top: 5px;
  color: var(--nm-text-secondary);
  font-size: 11px;
  word-break: break-all;
}

.evidence-excerpt {
  margin-top: 7px;
  max-height: 120px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 7px;
  background: rgba(148, 163, 184, 0.08);
  color: var(--nm-text-secondary);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
}
</style>
