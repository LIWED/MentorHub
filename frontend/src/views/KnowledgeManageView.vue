<template>
  <div class="knowledge-page">
    <div class="page-header">
      <div>
        <h1>知识库管理</h1>
        <p>按课程组织文档，支持单文件、多文件和完整网页文件夹入库。</p>
      </div>
      <el-button type="primary" @click="createDialogVisible = true">
        <el-icon><Plus /></el-icon>
        创建课程
      </el-button>
    </div>

    <div class="knowledge-layout">
      <aside class="nm-card course-panel">
        <div class="panel-title">课程</div>
        <div v-if="coursesLoading" class="panel-loading">加载中...</div>
        <div v-else-if="!courses.length" class="course-empty">
          暂无课程，先创建一个课程。
        </div>
        <button
          v-for="course in courses"
          :key="course.id"
          type="button"
          class="course-item"
          :class="{ active: course.id === selectedCourseId }"
          @click="selectCourse(course.id)"
        >
          <div class="course-name">{{ course.name }}</div>
          <div class="course-meta">
            {{ course.document_count }} 文档 · {{ course.chunk_count }} Chunk
          </div>
        </button>
      </aside>

      <main class="nm-card detail-panel">
        <template v-if="selectedCourse">
          <div class="detail-header">
            <div>
              <div class="detail-title-row">
                <h2>{{ selectedCourse.name }}</h2>
                <el-tag size="small" effect="plain">
                  {{ selectedCourse.completed_count }}/{{ selectedCourse.document_count }} 已完成
                </el-tag>
              </div>
              <p>{{ selectedCourse.description || '暂无课程描述' }}</p>
            </div>
            <div class="detail-actions">
              <el-button @click="openRetrievalTest">
                检索测试
              </el-button>
              <el-tooltip
                :disabled="!hasProcessingDocuments"
                content="课程下有文档正在上传或解析，完成后才能删除课程"
                placement="top"
              >
                <span>
                  <el-button
                    type="danger"
                    plain
                    :loading="deletingCourse"
                    :disabled="hasProcessingDocuments || uploading"
                    @click="removeCourse"
                  >
                    删除课程
                  </el-button>
                </span>
              </el-tooltip>
              <el-button @click="openFilePicker">上传文件</el-button>
              <el-button type="primary" @click="openFolderPicker">上传文件夹</el-button>
              <el-button circle :loading="documentsLoading" @click="refreshSelectedCourse">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </div>

          <el-alert
            class="folder-tip"
            type="info"
            :closable="false"
            show-icon
            title="网页课程请上传完整文件夹"
            description="系统会保留相对目录，HTML 可继续访问 img/assets；存在 sitemap.xml 时优先按 sitemap 识别正文页面。"
          />

          <input
            ref="fileInput"
            class="hidden-input"
            type="file"
            multiple
            @change="onPicked($event, 'files')"
          />
          <input
            ref="folderInput"
            class="hidden-input"
            type="file"
            multiple
            webkitdirectory
            directory
            @change="onPicked($event, 'folder')"
          />

          <div class="summary-grid">
            <div class="summary-card">
              <span>文档</span>
              <strong>{{ selectedCourse.document_count }}</strong>
            </div>
            <div class="summary-card">
              <span>已完成</span>
              <strong>{{ selectedCourse.completed_count }}</strong>
            </div>
            <div class="summary-card">
              <span>Chunk</span>
              <strong>{{ selectedCourse.chunk_count }}</strong>
            </div>
          </div>

          <el-table
            v-loading="documentsLoading || uploading"
            :data="documents"
            class="document-table"
            empty-text="当前课程还没有文档"
          >
            <el-table-column label="文档" min-width="300">
              <template #default="{ row }">
                <div class="document-name">{{ row.filename }}</div>
                <div class="document-path">{{ row.relative_path }}</div>
              </template>
            </el-table-column>

            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tooltip
                  :disabled="!row.error_msg"
                  :content="row.error_msg || ''"
                  placement="top"
                >
                  <el-tag :type="statusType(row.status)" size="small">
                    {{ statusText(row.status) }}
                  </el-tag>
                </el-tooltip>
              </template>
            </el-table-column>

            <el-table-column label="解析" width="120">
              <template #default="{ row }">
                {{ row.parser || '-' }}
              </template>
            </el-table-column>

            <el-table-column label="字符" width="100" align="right">
              <template #default="{ row }">
                {{ formatNumber(row.extracted_chars) }}
              </template>
            </el-table-column>

            <el-table-column label="Chunk" width="90" align="right">
              <template #default="{ row }">
                {{ row.chunk_count }}
              </template>
            </el-table-column>

            <el-table-column label="图片" width="130">
              <template #default="{ row }">
                <span v-if="row.image_count">
                  {{ row.image_enriched_count }}/{{ row.image_count }} 成功
                </span>
                <span v-else>-</span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="210" fixed="right">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  :disabled="row.status !== 'completed'"
                  @click="previewChunks(row)"
                >
                  Chunk
                </el-button>
                <el-button
                  link
                  type="primary"
                  :disabled="row.status === 'parsing'"
                  @click="reparse(row)"
                >
                  重新解析
                </el-button>
                <el-button
                  link
                  type="danger"
                  :disabled="row.status === 'parsing'"
                  @click="removeDocument(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <div v-else class="select-placeholder">
          <el-icon :size="42"><FolderOpened /></el-icon>
          <h3>选择一个课程</h3>
          <p>课程用于把相关文档归到同一个 course_id 下。</p>
        </div>
      </main>
    </div>

    <el-dialog v-model="createDialogVisible" title="创建课程" width="440px">
      <el-form label-position="top">
        <el-form-item label="课程名称" required>
          <el-input
            v-model="courseForm.name"
            maxlength="128"
            placeholder="例如：大模型应用开发"
          />
        </el-form-item>
        <el-form-item label="课程描述">
          <el-input
            v-model="courseForm.description"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="可选，用于说明课程内容"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createCourse">
          创建
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="chunkDialogVisible"
      :title="chunkDialogTitle"
      width="900px"
      top="6vh"
    >
      <div v-loading="chunksLoading" class="chunk-preview-list">
        <el-empty v-if="!chunksLoading && !chunkPreview.length" description="暂无 Chunk" />
        <div
          v-for="chunk in chunkPreview"
          :key="chunk.id || chunk.chunk_index"
          class="chunk-preview-card"
        >
          <div class="chunk-preview-head">
            <div>
              <strong>Chunk {{ chunk.chunk_index }}</strong>
              <el-tag size="small" effect="plain">{{ chunk.chunk_type }}</el-tag>
            </div>
            <span class="chunk-section">
              {{ chunk.heading_path || chunk.section || chunk.chapter || chunk.source_name || '-' }}
            </span>
          </div>
          <pre class="chunk-content">{{ chunk.content }}</pre>
          <el-collapse
            v-if="chunk.retrieval_text && chunk.retrieval_text !== chunk.content"
            class="chunk-retrieval-collapse"
          >
            <el-collapse-item title="查看实际检索文本" name="retrieval">
              <pre class="chunk-retrieval-text">{{ chunk.retrieval_text }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </el-dialog>

    <el-dialog
      v-model="retrievalDialogVisible"
      title="Retrieval Testing · 完整检索链"
      width="1060px"
      top="4vh"
    >
      <div class="retrieval-form">
        <el-input
          v-model="retrievalQuery"
          type="textarea"
          :rows="3"
          placeholder="输入 Query。测试会走正式的分类、Rewrite、Scope、路由、检索、HyDE、Sufficiency / Gap Retrieval，但不会生成最终回答。"
        />
        <div class="retrieval-options">
          <el-select
            v-model="retrievalCourseId"
            clearable
            filterable
            placeholder="全部课程"
            style="width: 260px"
          >
            <el-option
              v-for="course in courses"
              :key="course.id"
              :label="course.name"
              :value="course.id"
            />
          </el-select>
          <span class="runtime-hint">使用当前系统运行时检索参数</span>
          <el-switch
            v-model="retrievalWebEnabled"
            active-text="模拟 Web Fallback"
            inactive-text="不启用 Web"
          />
          <el-button
            type="primary"
            :loading="retrievalTesting"
            @click="runRetrievalTest"
          >
            开始测试
          </el-button>
        </div>
      </div>

      <template v-if="retrievalResult">
        <div class="retrieval-summary">
          <el-tag :type="retrievalStatusType(retrievalResult.status)">
            {{ retrievalStatusText(retrievalResult.status) }}
          </el-tag>
          <el-tag effect="plain">{{ retrievalResult.strategy }}</el-tag>
          <el-tag effect="plain">
            Final Top-1 {{ (retrievalResult.confidence * 100).toFixed(1) }}%
          </el-tag>
          <el-tag effect="plain">
            Final Evidence {{ retrievalResult.evidence_count }}
          </el-tag>
          <el-tag effect="plain">
            总耗时 {{ formatElapsed(retrievalResult.total_ms) }}
          </el-tag>
        </div>
        <div class="retrieval-runtime-config">
          阈值 {{ Number(retrievalResult.runtime_config.retrieval_confidence_threshold || 0).toFixed(2) }}
          · SINGLE {{ retrievalResult.runtime_config.recall_top_k_single }}
          · HyDE {{ retrievalResult.runtime_config.recall_top_k_hyde }}
          · BROAD {{ retrievalResult.runtime_config.recall_top_k_broad_per }}/Query
          · ITERATIVE {{ retrievalResult.runtime_config.recall_top_k_iterative }}/Query
          · Evidence Top {{ retrievalResult.runtime_config.rerank_evidence_top_k }}
          · Final Context Top {{ retrievalResult.runtime_config.final_context_top_k }}
          · Gap {{ retrievalResult.runtime_config.max_gap_queries }} × {{ retrievalResult.runtime_config.max_gap_rounds }}
        </div>

        <el-tabs v-model="retrievalTab">
          <el-tab-pane label="完整链路" name="chain">
            <el-timeline class="retrieval-timeline">
              <el-timeline-item
                v-for="(step, index) in retrievalResult.steps"
                :key="`${index}-${step.name}`"
                :timestamp="step.elapsed_ms > 0 ? formatElapsed(step.elapsed_ms) : '决策'"
                placement="top"
              >
                <div class="retrieval-step-card">
                  <div class="retrieval-step-head">
                    <strong>{{ step.label }}</strong>
                    <el-tag size="small" effect="plain">{{ step.name }}</el-tag>
                  </div>
                  <div class="retrieval-step-summary">{{ step.summary }}</div>
                  <el-collapse
                    v-if="hasStepDetails(step.details)"
                    class="retrieval-step-details"
                  >
                    <el-collapse-item title="查看具体操作" name="details">
                      <pre>{{ formatStepDetails(step.details) }}</pre>
                    </el-collapse-item>
                  </el-collapse>
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-tab-pane>

          <el-tab-pane
            :label="`Final Evidence（${retrievalResult.final_evidence.length}）`"
            name="evidence"
          >
            <div class="retrieval-result-list">
              <div
                v-for="item in retrievalResult.final_evidence"
                :key="`evidence-${item.rank}-${item.document_id}-${item.chunk_index}`"
                class="retrieval-result-card"
              >
                <div class="retrieval-result-head">
                  <strong>#{{ item.rank }} {{ item.source_name || '课程文档' }}</strong>
                  <el-tag size="small">{{ (item.score * 100).toFixed(1) }}%</el-tag>
                </div>
                <div class="retrieval-result-meta">
                  {{ item.relative_path || item.document_id }}
                  <span v-if="item.heading_path"> · {{ item.heading_path }}</span>
                  <span v-else-if="item.section"> · {{ item.section }}</span>
                  · Chunk {{ item.chunk_index }}
                </div>
                <div class="retrieval-result-content">{{ item.content }}</div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane
            :label="`检索调用（${retrievalResult.retrieval_calls.length}）`"
            name="calls"
          >
            <div class="retrieval-result-list">
              <div
                v-for="(call, index) in retrievalResult.retrieval_calls"
                :key="`call-${index}-${call.query}`"
                class="retrieval-result-card"
              >
                <div class="retrieval-result-head">
                  <strong>#{{ index + 1 }} {{ call.query }}</strong>
                  <el-tag size="small" effect="plain">
                    {{ formatElapsed(call.elapsed_ms) }}
                  </el-tag>
                </div>
                <div class="retrieval-result-meta">
                  Candidate {{ call.candidate_count }}
                  → Rerank {{ call.ranked_count }}
                  · Top-1 {{ (call.confidence * 100).toFixed(1) }}%
                  · Recall {{ call.recall_top_k }}
                  / Rerank {{ call.rerank_top_k }}
                </div>
                <code class="retrieval-filter">{{ call.filter_expr }}</code>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, Plus, Refresh } from '@element-plus/icons-vue'
import {
  knowledgeApi,
  type KnowledgeChunkPreview,
  type KnowledgeCourse,
  type KnowledgeDocument,
  type KnowledgeDocumentStatus,
  type RetrievalTestResponse,
} from '@/api/knowledge'

const courses = ref<KnowledgeCourse[]>([])
const documents = ref<KnowledgeDocument[]>([])
const selectedCourseId = ref('')
const coursesLoading = ref(false)
const documentsLoading = ref(false)
const uploading = ref(false)
const creating = ref(false)
const deletingCourse = ref(false)
const createDialogVisible = ref(false)
const chunkDialogVisible = ref(false)
const chunksLoading = ref(false)
const chunkDialogTitle = ref('Chunk Preview')
const chunkPreview = ref<KnowledgeChunkPreview[]>([])
const retrievalDialogVisible = ref(false)
const retrievalTesting = ref(false)
const retrievalQuery = ref('')
const retrievalCourseId = ref('')
const retrievalWebEnabled = ref(false)
const retrievalResult = ref<RetrievalTestResponse | null>(null)
const retrievalTab = ref('chain')
const fileInput = ref<HTMLInputElement>()
const folderInput = ref<HTMLInputElement>()
const courseForm = reactive({ name: '', description: '' })

let pollTimer: number | undefined

const selectedCourse = computed(
  () => courses.value.find(item => item.id === selectedCourseId.value) ?? null,
)
const hasProcessingDocuments = computed(
  () => documents.value.some(
    item => item.status === 'uploaded' || item.status === 'parsing',
  ),
)

function statusText(status: KnowledgeDocumentStatus) {
  return {
    uploaded: '等待处理',
    parsing: '解析中',
    completed: '已完成',
    failed: '失败',
  }[status]
}

function statusType(status: KnowledgeDocumentStatus) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'parsing') return 'warning'
  return 'info'
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value || 0)
}

function formatElapsed(ms: number) {
  if (ms < 1000) return `${ms.toFixed(0)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

function retrievalStatusText(status: string) {
  return {
    ready_for_rag: '证据充分',
    ready_for_partial_rag: '证据部分充分',
    would_direct_fallback: '低置信度兜底',
    would_web_fallback: '需要联网兜底',
    general_query: '通用问题',
  }[status] || status
}

function retrievalStatusType(status: string) {
  if (status === 'ready_for_rag') return 'success'
  if (status === 'ready_for_partial_rag') return 'warning'
  if (status === 'would_direct_fallback' || status === 'would_web_fallback') {
    return 'danger'
  }
  return 'info'
}

function hasStepDetails(details: Record<string, unknown>) {
  return Object.keys(details || {}).length > 0
}

function formatStepDetails(details: Record<string, unknown>) {
  const labels: Record<string, string> = {
    query_type: '问题类型',
    original_query: '原 Query',
    rewritten_query: 'Rewrite',
    metadata_scope: 'Scope',
    scope_source: 'Scope 来源',
    strategy: '检索结构',
    queries: 'Query 列表',
    plan: '迭代计划',
    confidence: 'Top-1 置信度',
    threshold: '置信度阈值',
    evidence_count: '证据数',
    high_confidence: '是否通过阈值',
    hyde_document: 'HyDE 假想文档',
    sufficient: '证据是否充分',
    missing_gaps: '证据缺口',
    search_hints: '补搜提示',
    gap_round: 'Gap 轮次',
    new_evidence_count: '新增证据',
    evidence_pool_count: '证据池大小',
    decision: '路由决策',
    max_gap_rounds: '最大 Gap 轮数',
  }

  const lines: string[] = []
  for (const [key, value] of Object.entries(details || {})) {
    const label = labels[key] || key
    if (key === 'retrieval_calls' && Array.isArray(value)) {
      value.forEach((raw, index) => {
        const call = raw as Record<string, unknown>
        const confidence = Number(call.confidence || 0)
        lines.push(
          `检索 ${index + 1}: ${String(call.query || '')}`,
          `  Candidate ${Number(call.candidate_count || 0)} → Rerank ${Number(call.ranked_count || 0)} · Top-1 ${(confidence * 100).toFixed(1)}% · ${formatElapsed(Number(call.elapsed_ms || 0))}`,
          `  Filter: ${String(call.filter_expr || '')}`,
        )
        return
      })
      continue
    }

    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      lines.push(`${label}: ${String(value)}`)
    } else {
      lines.push(`${label}: ${JSON.stringify(value, null, 2)}`)
    }
  }
  return lines.join('\n')
}

async function loadCourses(selectFirst = true) {
  coursesLoading.value = true
  try {
    const { data } = await knowledgeApi.listCourses()
    courses.value = data
    if (
      selectFirst &&
      !selectedCourseId.value &&
      courses.value.length
    ) {
      await selectCourse(courses.value[0].id)
    }
  } finally {
    coursesLoading.value = false
  }
}

async function loadDocuments(showLoading = true) {
  if (!selectedCourseId.value) return
  if (showLoading) documentsLoading.value = true
  try {
    const { data } = await knowledgeApi.listDocuments(selectedCourseId.value)
    documents.value = data
  } finally {
    if (showLoading) documentsLoading.value = false
  }
}

async function refreshSelectedCourse() {
  if (!selectedCourseId.value) return
  const id = selectedCourseId.value
  const [{ data: course }] = await Promise.all([
    knowledgeApi.getCourse(id),
    loadDocuments(),
  ])
  const index = courses.value.findIndex(item => item.id === id)
  if (index >= 0) courses.value[index] = course
}

async function selectCourse(courseId: string) {
  selectedCourseId.value = courseId
  await loadDocuments()
}

async function createCourse() {
  const name = courseForm.name.trim()
  if (!name) {
    ElMessage.warning('请输入课程名称')
    return
  }

  creating.value = true
  try {
    const { data } = await knowledgeApi.createCourse({
      name,
      description: courseForm.description.trim(),
    })
    courses.value.unshift(data)
    selectedCourseId.value = data.id
    documents.value = []
    createDialogVisible.value = false
    courseForm.name = ''
    courseForm.description = ''
    ElMessage.success('课程已创建')
  } finally {
    creating.value = false
  }
}

async function removeCourse() {
  const course = selectedCourse.value
  if (!course || deletingCourse.value) return

  await ElMessageBox.confirm(
    `删除“${course.name}”后，将同时删除该课程下的 ${course.document_count} 个文档、全部向量 Chunk 和上传的资源文件。此操作不可恢复。`,
    '删除课程及全部文档',
    {
      confirmButtonText: '确认全部删除',
      cancelButtonText: '取消',
      type: 'warning',
      distinguishCancelAndClose: true,
    },
  )

  deletingCourse.value = true
  try {
    await knowledgeApi.deleteCourse(course.id)

    const deletedIndex = courses.value.findIndex(item => item.id === course.id)
    if (deletedIndex >= 0) {
      courses.value.splice(deletedIndex, 1)
    }
    selectedCourseId.value = ''
    documents.value = []

    const nextCourse = courses.value[Math.min(
      Math.max(deletedIndex, 0),
      Math.max(courses.value.length - 1, 0),
    )]
    if (nextCourse) {
      await selectCourse(nextCourse.id)
    }

    ElMessage.success('课程及其全部文档已删除')
  } finally {
    deletingCourse.value = false
  }
}

function openFilePicker() {
  fileInput.value?.click()
}

function openFolderPicker() {
  folderInput.value?.click()
}

async function onPicked(event: Event, mode: 'files' | 'folder') {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files ?? [])
  input.value = ''
  if (!selectedCourseId.value || !selected.length) return

  uploading.value = true
  try {
    const { data } = await knowledgeApi.uploadDocuments(
      selectedCourseId.value,
      selected,
      mode,
    )
    const sitemapText = data.sitemap_used ? '，已使用 sitemap.xml' : ''
    ElMessage.success(
      `已接收 ${data.uploaded_files} 个文件，${data.documents_queued} 个文档进入解析队列，${data.asset_files} 个资源文件保留${sitemapText}`,
    )
    await refreshSelectedCourse()
  } finally {
    uploading.value = false
  }
}

async function reparse(document: KnowledgeDocument) {
  await knowledgeApi.reparseDocument(document.id)
  ElMessage.success('已加入重新解析队列')
  await loadDocuments()
}

async function removeDocument(document: KnowledgeDocument) {
  await ElMessageBox.confirm(
    `删除“${document.filename}”及其向量 Chunk？原网页包中的其他资源文件不会被删除。`,
    '删除文档',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )
  await knowledgeApi.deleteDocument(document.id)
  ElMessage.success('文档已删除')
  await refreshSelectedCourse()
}

async function previewChunks(document: KnowledgeDocument) {
  chunkDialogVisible.value = true
  chunkDialogTitle.value = `Chunk Preview · ${document.filename}`
  chunkPreview.value = []
  chunksLoading.value = true
  try {
    const { data } = await knowledgeApi.previewChunks(document.id)
    chunkPreview.value = data
  } finally {
    chunksLoading.value = false
  }
}

function openRetrievalTest() {
  retrievalDialogVisible.value = true
  retrievalCourseId.value = selectedCourseId.value
  retrievalResult.value = null
  retrievalTab.value = 'chain'
}

async function runRetrievalTest() {
  const query = retrievalQuery.value.trim()
  if (!query) {
    ElMessage.warning('请输入要测试的 Query')
    return
  }

  retrievalTesting.value = true
  try {
    const { data } = await knowledgeApi.retrievalTest({
      query,
      course_id: retrievalCourseId.value || null,
      enable_web_search: retrievalWebEnabled.value,
    })
    retrievalResult.value = data
    retrievalTab.value = 'chain'
  } finally {
    retrievalTesting.value = false
  }
}

onMounted(async () => {
  await loadCourses()
  pollTimer = window.setInterval(async () => {
    if (!selectedCourseId.value) return
    if (documents.value.some(item => item.status === 'uploaded' || item.status === 'parsing')) {
      await refreshSelectedCourse()
    }
  }, 3000)
})

onBeforeUnmount(() => {
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
})
</script>

<style scoped>
.knowledge-page {
  max-width: 1440px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 6px;
  font-size: 24px;
  color: var(--nm-text-primary);
}

.page-header p,
.detail-header p {
  margin: 0;
  color: var(--nm-text-secondary);
  font-size: 13px;
}

.knowledge-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 18px;
  min-height: 620px;
}

.course-panel,
.detail-panel {
  padding: 18px;
}

.panel-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--nm-text-primary);
  margin-bottom: 14px;
}

.panel-loading,
.course-empty {
  padding: 28px 10px;
  text-align: center;
  color: var(--nm-text-secondary);
  font-size: 13px;
}

.course-item {
  width: 100%;
  border: 0;
  border-radius: var(--nm-radius-md);
  background: transparent;
  text-align: left;
  padding: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  color: var(--nm-text-primary);
  transition: var(--nm-transition);
}

.course-item:hover {
  box-shadow: var(--nm-shadow-sm);
}

.course-item.active {
  box-shadow: var(--nm-shadow-inset);
  color: var(--nm-primary);
}

.course-name {
  font-size: 14px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course-meta {
  margin-top: 5px;
  font-size: 11.5px;
  color: var(--nm-text-secondary);
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.detail-header h2 {
  margin: 0 0 6px;
  font-size: 19px;
  color: var(--nm-text-primary);
}

.detail-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.folder-tip {
  margin: 16px 0;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}

.summary-card {
  padding: 14px 16px;
  border-radius: var(--nm-radius-md);
  box-shadow: var(--nm-shadow-inset);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.summary-card span {
  color: var(--nm-text-secondary);
  font-size: 12px;
}

.summary-card strong {
  font-size: 20px;
  color: var(--nm-text-primary);
}

.hidden-input {
  display: none;
}

.document-table {
  width: 100%;
}

.document-table :deep(td.el-table-fixed-column--right) {
  background-color: var(--nm-bg) !important;
}

.document-table :deep(th.el-table-fixed-column--right) {
  background-color: var(--nm-bg-soft) !important;
}

.document-table
  :deep(.el-table__body tr:hover > td.el-table-fixed-column--right) {
  background-color: var(--nm-bg-soft) !important;
}

.document-name {
  font-weight: 600;
  color: var(--nm-text-primary);
}

.document-path {
  margin-top: 3px;
  font-size: 11px;
  color: var(--nm-text-secondary);
  word-break: break-all;
}

.chunk-preview-list,
.retrieval-result-list {
  display: grid;
  gap: 10px;
  max-height: 65vh;
  overflow: auto;
}

.chunk-preview-card,
.retrieval-result-card {
  padding: 12px 14px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset);
}

.chunk-preview-head,
.retrieval-result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chunk-preview-head > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chunk-section,
.retrieval-result-meta {
  color: var(--nm-text-secondary);
  font-size: 11.5px;
}

.chunk-content {
  margin: 10px 0 0;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--nm-text-primary);
}

.chunk-retrieval-collapse {
  margin-top: 8px;
  border: none !important;
}

.chunk-retrieval-collapse :deep(.el-collapse-item__header) {
  height: 30px;
  border: none;
  background: transparent;
  color: var(--nm-primary);
  font-size: 11.5px;
}

.chunk-retrieval-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}

.chunk-retrieval-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 0;
}

.chunk-retrieval-text {
  margin: 0;
  max-height: 260px;
  overflow: auto;
  padding: 9px 10px;
  border-radius: 7px;
  background: rgba(59, 130, 246, 0.05);
  color: var(--nm-text-secondary);
  font-family: inherit;
  font-size: 11.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.retrieval-form {
  display: grid;
  gap: 12px;
  margin-bottom: 14px;
}

.retrieval-options {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--nm-text-secondary);
  font-size: 12px;
}

.runtime-hint {
  margin-left: 2px;
  padding: 5px 9px;
  border-radius: 7px;
  background: rgba(148, 163, 184, 0.09);
}

.retrieval-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.retrieval-runtime-config {
  margin-bottom: 12px;
  padding: 7px 9px;
  border-radius: 7px;
  background: rgba(148, 163, 184, 0.07);
  color: var(--nm-text-secondary);
  font-size: 11.5px;
  line-height: 1.55;
}

.retrieval-timeline {
  max-height: 62vh;
  overflow: auto;
  padding: 8px 6px 0 4px;
}

.retrieval-step-card {
  padding: 11px 13px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset);
}

.retrieval-step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.retrieval-step-summary {
  margin-top: 6px;
  color: var(--nm-text-secondary);
  font-size: 12.5px;
  line-height: 1.55;
}

.retrieval-step-details {
  margin-top: 6px;
  border: none !important;
}

.retrieval-step-details :deep(.el-collapse-item__header) {
  height: 30px;
  border: none;
  background: transparent;
  color: var(--nm-primary);
  font-size: 11.5px;
}

.retrieval-step-details :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}

.retrieval-step-details :deep(.el-collapse-item__content) {
  padding-bottom: 0;
}

.retrieval-step-details pre {
  margin: 0;
  max-height: 260px;
  overflow: auto;
  padding: 9px 10px;
  border-radius: 7px;
  background: rgba(148, 163, 184, 0.08);
  color: var(--nm-text-secondary);
  font-family: var(--nm-font-mono, monospace);
  font-size: 11.5px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.retrieval-filter {
  display: block;
  margin-top: 8px;
  overflow: auto;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(148, 163, 184, 0.1);
  color: var(--nm-text-secondary);
  font-size: 11px;
}

.retrieval-result-content {
  margin-top: 8px;
  max-height: 180px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 7px;
  background: rgba(148, 163, 184, 0.08);
  color: var(--nm-text-primary);
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.select-placeholder {
  min-height: 520px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--nm-text-secondary);
}

.select-placeholder h3 {
  margin: 12px 0 5px;
  color: var(--nm-text-primary);
}

.select-placeholder p {
  margin: 0;
  font-size: 13px;
}

@media (max-width: 980px) {
  .knowledge-layout {
    grid-template-columns: 1fr;
  }

  .detail-header {
    flex-direction: column;
  }
}
</style>
