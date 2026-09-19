<template>
  <div class="resume-upload-page">
    <!-- 上传卡片 -->
    <div class="nm-card upload-card">
      <div class="card-header">
        <div class="header-icon-box">
          <img :src="iconResume" class="header-icon-img" alt="Resume" />
        </div>
        <div>
          <h3 class="card-title">上传简历进行多维诊断</h3>
          <p class="card-subtitle">基于大模型深度剖析格式规范、内容深度、技术关键词、项目匹配度等六大维度</p>
        </div>
      </div>

      <div class="upload-dropzone" :class="{ 'has-file': !!selectedFile }" @click="triggerFilePicker">
        <input
          ref="fileInputRef"
          type="file"
          accept=".pdf"
          style="display: none"
          @change="handleFileChange"
        />
        <div class="dropzone-icon">
          <el-icon v-if="!selectedFile"><UploadFilled /></el-icon>
          <el-icon v-else class="file-ready-icon"><DocumentChecked /></el-icon>
        </div>
        <div class="dropzone-text">
          <span v-if="!selectedFile" class="main-tip">点击选择或拖拽 PDF 简历至此处</span>
          <span v-else class="selected-file-name">{{ selectedFile.name }}</span>
          <span class="sub-tip">仅支持 PDF 格式文件，单文件最大 10MB</span>
        </div>
        <button
          v-if="selectedFile"
          type="button"
          class="clear-file-btn"
          title="移除文件"
          @click.stop="clearFile"
        >
          <el-icon><Close /></el-icon>
        </button>
      </div>

      <div class="upload-actions">
        <button
          type="button"
          class="nm-button-primary start-review-btn"
          :disabled="!selectedFile || loading"
          @click="handleUpload"
        >
          <span v-if="loading" class="btn-spinner" />
          <span v-else>开始 AI 诊断审查</span>
        </button>
      </div>
    </div>

    <!-- 历史记录 -->
    <div class="nm-card history-card">
      <div class="card-header">
        <div class="header-icon-box">
          <el-icon class="header-icon-el"><Clock /></el-icon>
        </div>
        <div style="flex: 1">
          <h3 class="card-title">历史简历审查档案</h3>
          <p class="card-subtitle">查看过往提交的简历综合得分与修改建议</p>
        </div>
        <button class="nm-icon-refresh-btn" title="刷新列表" @click="fetchHistory">
          <el-icon><Refresh /></el-icon>
        </button>
      </div>

      <div v-if="!history.length" class="empty-history">
        <el-empty description="暂无审查记录，立即上传简历进行初筛" />
      </div>

      <el-table v-else :data="history" size="default" class="history-table">
        <el-table-column prop="review_id" label="审查流水号" width="220">
          <template #default="{ row }">
            <span class="review-id-text">{{ row.review_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="审查时间" width="180">
          <template #default="{ row }">
            <span class="time-text">{{ row.created_at }}</span>
          </template>
        </el-table-column>
        <el-table-column label="综合评分" width="130">
          <template #default="{ row }">
            <span v-if="row.weighted_score !== undefined" class="score-pill">
              {{ row.weighted_score.toFixed(1) }} 分
            </span>
            <span v-else class="processing-pill">处理中...</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" align="center">
          <template #default="{ row }">
            <div class="table-ops">
              <button
                class="op-btn report"
                type="button"
                @click="router.push(`/resume/${row.review_id}`)"
              >
                查看报告
              </button>
              <button
                class="op-btn delete"
                type="button"
                @click="handleDelete(row.review_id)"
              >
                删除
              </button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled, DocumentChecked, Close, Refresh, Clock } from '@element-plus/icons-vue'
import iconResume from '@/assets/images/icon_resume.jpg'
import { resumeApi, type ReviewListItem } from '@/api/resume'

const router = useRouter()
const loading = ref(false)
const selectedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const history = ref<ReviewListItem[]>([])

function triggerFilePicker() {
  fileInputRef.value?.click()
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (file && file.size > 10 * 1024 * 1024) {
    ElMessage.error('简历文件超过 10MB 限制')
    input.value = ''
    return
  }
  selectedFile.value = file
}

function clearFile() {
  selectedFile.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function handleUpload() {
  if (!selectedFile.value) return
  loading.value = true
  try {
    const { data } = await resumeApi.upload(selectedFile.value)
    ElMessage.success('上传成功，AI 正在多维审查中...')
    router.push(`/resume/${data.review_id}`)
  } finally {
    loading.value = false
  }
}

async function handleDelete(reviewId: string) {
  try {
    await resumeApi.deleteReview(reviewId)
    history.value = history.value.filter(r => r.review_id !== reviewId)
    ElMessage.success('已删除记录')
  } catch {
    // handled by client
  }
}

async function fetchHistory() {
  try {
    const { data } = await resumeApi.listReviews()
    history.value = data.items
  } catch {
    // ignore
  }
}

onMounted(fetchHistory)
</script>

<style scoped>
.resume-upload-page {
  max-width: 920px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.upload-card, .history-card {
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

/* 拟物上传槽 */
.upload-dropzone {
  width: 100%;
  padding: 26px 20px;
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

.upload-actions {
  margin-top: 20px;
}

.start-review-btn {
  padding: 10px 24px;
  font-size: 14.5px;
  cursor: pointer;
}

.start-review-btn:disabled {
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

.review-id-text {
  font-family: Consolas, monospace;
  font-size: 12.5px;
  color: var(--nm-text-primary);
  font-weight: 500;
}

.time-text {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.score-pill {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--nm-primary);
  background: #eff6ff;
  padding: 2px 10px;
  border-radius: var(--nm-radius-full);
}

.processing-pill {
  font-size: 11px;
  color: var(--nm-text-light);
  background: rgba(255, 255, 255, 0.7);
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
}

.table-ops {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.op-btn {
  padding: 4px 10px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--nm-transition);
}

.op-btn.report {
  color: var(--nm-primary);
}

.op-btn.delete {
  color: var(--nm-danger);
}

.op-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--nm-shadow-hover);
}
</style>
