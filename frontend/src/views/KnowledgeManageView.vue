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

            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
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
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, Plus, Refresh } from '@element-plus/icons-vue'
import {
  knowledgeApi,
  type KnowledgeCourse,
  type KnowledgeDocument,
  type KnowledgeDocumentStatus,
} from '@/api/knowledge'

const courses = ref<KnowledgeCourse[]>([])
const documents = ref<KnowledgeDocument[]>([])
const selectedCourseId = ref('')
const coursesLoading = ref(false)
const documentsLoading = ref(false)
const uploading = ref(false)
const creating = ref(false)
const createDialogVisible = ref(false)
const fileInput = ref<HTMLInputElement>()
const folderInput = ref<HTMLInputElement>()
const courseForm = reactive({ name: '', description: '' })

let pollTimer: number | undefined

const selectedCourse = computed(
  () => courses.value.find(item => item.id === selectedCourseId.value) ?? null,
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
