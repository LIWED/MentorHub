<template>
  <div class="exam-submit-page">
    <!-- 提交卡片 -->
    <div class="nm-card submit-card">
      <div class="card-header">
        <div class="header-icon-box">
          <img :src="iconExam" class="header-icon-img" alt="Exam" />
        </div>
        <div>
          <h3 class="card-title">提交试卷批改</h3>
          <p class="card-subtitle">上传 .docx 答卷文件，AI 将全自动预批改并定位薄弱知识点</p>
        </div>
      </div>

      <el-form :model="form" label-position="top" class="exam-form">
        <el-form-item label="试卷 ID">
          <el-input
            v-model="form.examId"
            placeholder="请输入试卷 ID（例如 EXAM-2024-001，由教师或课程提供）"
            size="large"
          />
        </el-form-item>

        <el-form-item label="答题文件 (.docx)">
          <div
            class="upload-dropzone"
            :class="{ 'has-file': !!form.file }"
            @click="triggerUpload"
          >
            <input
              ref="fileInputRef"
              type="file"
              accept=".docx"
              style="display: none"
              @change="onFileSelected"
            />
            <div class="dropzone-icon">
              <el-icon v-if="!form.file"><UploadFilled /></el-icon>
              <el-icon v-else class="file-ready-icon"><DocumentChecked /></el-icon>
            </div>
            <div class="dropzone-text">
              <span v-if="!form.file" class="main-tip">点击选择或拖拽 .docx 答卷文件至此处</span>
              <span v-else class="selected-file-name">{{ form.file.name }}</span>
              <span class="sub-tip">支持 Word .docx 格式，最大 20MB</span>
            </div>
            <button
              v-if="form.file"
              type="button"
              class="clear-file-btn"
              title="清除重新选择"
              @click.stop="clearFile"
            >
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </el-form-item>

        <div class="form-actions">
          <button
            type="button"
            class="nm-button-primary submit-btn"
            :disabled="!form.examId.trim() || !form.file || loading"
            @click="handleSubmit"
          >
            <span v-if="loading" class="btn-spinner" />
            <span v-else>立即提交 AI 批改</span>
          </button>
        </div>
      </el-form>
    </div>

    <!-- 历史提交记录 -->
    <div class="nm-card history-card">
      <div class="card-header">
        <div class="header-icon-box">
          <el-icon class="header-icon-el"><Tickets /></el-icon>
        </div>
        <div style="flex: 1">
          <h3 class="card-title">历史提交记录</h3>
          <p class="card-subtitle">查看历史试卷的 AI 批改分析与教师确认结果</p>
        </div>
        <button class="nm-icon-refresh-btn" title="刷新列表" @click="fetchSubmissions">
          <el-icon><Refresh /></el-icon>
        </button>
      </div>

      <div v-if="!recentSubmissions.length" class="empty-history">
        <el-empty description="暂无提交记录，提交上方试卷开始学习" />
      </div>

      <el-table v-else :data="recentSubmissions" size="default" class="history-table">
        <el-table-column prop="exam_title" label="试卷名称" min-width="160">
          <template #default="{ row }">
            <span class="exam-title-text">{{ row.exam_title || row.exam_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="submitted_at" label="提交时间" width="180">
          <template #default="{ row }">
            <span class="time-text">{{ row.submitted_at }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="160">
          <template #default="{ row }">
            <span class="status-pill" :class="row.status">
              {{ statusLabel(row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <button
              class="table-action-btn"
              type="button"
              @click="router.push(`/exam/${row.submission_id}`)"
            >
              <span>查看结果</span>
            </button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled, DocumentChecked, Close, Refresh, Tickets } from '@element-plus/icons-vue'
import iconExam from '@/assets/images/icon_exam.jpg'
import { examApi, type MySubmissionItem } from '@/api/exam'

const router = useRouter()
const loading = ref(false)
const fileInputRef = ref<HTMLInputElement>()
const form = reactive({ examId: '', file: null as File | null })
const recentSubmissions = ref<MySubmissionItem[]>([])

function triggerUpload() {
  fileInputRef.value?.click()
}

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (f) {
    if (f.size > 20 * 1024 * 1024) {
      ElMessage.error('文件超出 20MB 大小限制')
      input.value = ''
      return
    }
    form.file = f
  }
}

function clearFile() {
  form.file = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function statusLabel(status: string) {
  if (status === 'published') return '已发布'
  if (status === 'pending_review') return '待教师确认'
  if (status === 'ai_processing') return 'AI 批改中'
  if (status === 'submitted') return '需重新提交'
  return status
}

async function fetchSubmissions() {
  try {
    const { data } = await examApi.listMySubmissions()
    recentSubmissions.value = data.items
  } catch {
    // ignore
  }
}

async function handleSubmit() {
  if (!form.examId.trim() || !form.file) return
  loading.value = true
  try {
    await examApi.submit(form.examId, form.file)
    ElMessage.success('提交成功，AI 正在批改中...')
    form.examId = ''
    clearFile()
    await fetchSubmissions()
  } catch {
    // error handled by client
  } finally {
    loading.value = false
  }
}

onMounted(fetchSubmissions)
</script>

<style scoped>
.exam-submit-page {
  max-width: 920px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.submit-card, .history-card {
  padding: 24px 28px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
}

.header-icon-box {
  width: 44px;
  height: 44px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-icon {
  font-size: 22px;
}

.header-icon-img {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  object-fit: cover;
}

.header-icon-el {
  font-size: 20px;
  color: var(--nm-primary);
}

.card-title {
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.card-subtitle {
  margin: 0;
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.exam-form :deep(.el-form-item__label) {
  font-weight: 600;
  color: var(--nm-text-primary);
  margin-bottom: 6px;
}

/* 拟物上传拖拽区 */
.upload-dropzone {
  width: 100%;
  padding: 24px 20px;
  box-sizing: border-box;
  background: var(--nm-bg);
  border-radius: var(--nm-radius-lg);
  box-shadow: var(--nm-shadow-inset);
  border: 2px dashed rgba(166, 180, 200, 0.6);
  display: flex;
  align-items: center;
  gap: 16px;
  cursor: pointer;
  transition: var(--nm-transition);
  position: relative;
}

.upload-dropzone:hover {
  border-color: var(--nm-primary);
  box-shadow: inset 4px 4px 8px rgba(166, 180, 200, 0.6), inset -4px -4px 8px rgba(255, 255, 255, 0.95);
}

.upload-dropzone.has-file {
  border-style: solid;
  border-color: rgba(59, 130, 246, 0.5);
  background: rgba(59, 130, 246, 0.03);
}

.dropzone-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: var(--nm-primary);
  flex-shrink: 0;
}

.file-ready-icon {
  color: var(--nm-success);
}

.dropzone-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow: hidden;
}

.main-tip {
  font-size: 14px;
  font-weight: 600;
  color: var(--nm-text-primary);
}

.selected-file-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--nm-primary);
  word-break: break-all;
}

.sub-tip {
  font-size: 12px;
  color: var(--nm-text-light);
}

.clear-file-btn {
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  border-radius: var(--nm-radius-full);
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--nm-text-light);
  cursor: pointer;
  transition: var(--nm-transition);
}

.clear-file-btn:hover {
  color: var(--nm-danger);
  box-shadow: var(--nm-shadow-hover);
  transform: rotate(90deg);
}

.form-actions {
  margin-top: 20px;
}

.submit-btn {
  padding: 10px 24px;
  font-size: 14.5px;
  cursor: pointer;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none !important;
}

.btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}

@keyframes spin { to { transform: rotate(360deg); } }

.nm-icon-refresh-btn {
  width: 34px;
  height: 34px;
  border-radius: var(--nm-radius-sm);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: var(--nm-transition);
}

.nm-icon-refresh-btn:hover {
  transform: rotate(180deg);
  color: var(--nm-primary);
  box-shadow: var(--nm-shadow-hover);
}

.exam-title-text {
  font-weight: 600;
  color: var(--nm-text-primary);
}

.time-text {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.status-pill {
  font-size: 11.5px;
  padding: 3px 10px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
  display: inline-block;
}

.status-pill.published { background: #dcfce7; color: #059669; }
.status-pill.pending_review { background: #fef3c7; color: #d97706; }
.status-pill.ai_processing { background: #e0f2fe; color: #0284c7; }
.status-pill.submitted { background: #fee2e2; color: #dc2626; }

.table-action-btn {
  padding: 4px 12px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--nm-transition);
}

.table-action-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--nm-shadow-hover);
}
</style>
