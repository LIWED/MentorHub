<template>
  <div class="interview-setup-page">
    <!-- 面试配置卡片 -->
    <div class="nm-card setup-card">
      <div class="card-header">
        <div class="header-icon-box">
          <img :src="iconInterview" class="header-icon-img" alt="Interview" />
        </div>
        <div>
          <h3 class="card-title">开启 AI 模拟面试</h3>
          <p class="card-subtitle">模拟真实互联网大厂面试流程，支持技术原理深挖与针对简历项目的多轮双轨考察</p>
        </div>
      </div>

      <el-form :model="form" label-position="top" class="setup-form">
        <el-form-item label="目标应聘岗位">
          <el-input
            v-model="form.targetPosition"
            placeholder="例如：Java 后端开发工程师 / 前端开发工程师"
            size="large"
          />
          <!-- 快捷岗位选择胶囊 -->
          <div class="role-quick-chips">
            <span class="quick-title"><el-icon class="tip-icon"><Opportunity /></el-icon> 热门岗位：</span>
            <span
              v-for="role in hotRoles"
              :key="role"
              class="role-chip"
              @click="form.targetPosition = role"
            >
              {{ role }}
            </span>
          </div>
        </el-form-item>

        <el-form-item label="关联已诊断简历（可选）">
          <el-select
            v-model="form.resumeReviewId"
            placeholder="选择已完成诊断的简历（AI 将结合简历项目背景精准提问）"
            clearable
            size="large"
            style="width: 100%"
          >
            <el-option
              v-for="r in resumeHistory"
              :key="r.review_id"
              :label="`档案 ${r.review_id.slice(0, 8)}... (${r.created_at}) · 得分: ${r.weighted_score?.toFixed(1) ?? '--'}`"
              :value="r.review_id"
            />
          </el-select>
        </el-form-item>

        <div class="form-actions">
          <button
            type="button"
            class="nm-button-primary start-btn"
            :disabled="!form.targetPosition.trim() || loading"
            @click="startInterview"
          >
            <span v-if="loading" class="btn-spinner" />
            <span v-else>立即开启模拟面试</span>
          </button>
        </div>
      </el-form>
    </div>

    <!-- 历史面试记录 -->
    <div class="nm-card history-card">
      <div class="card-header">
        <div class="header-icon-box">
          <el-icon class="header-icon-el"><Tickets /></el-icon>
        </div>
        <div style="flex: 1">
          <h3 class="card-title">历史模拟面试记录</h3>
          <p class="card-subtitle">复盘历史面试问答表现与多维度评定建议</p>
        </div>
        <button class="nm-icon-refresh-btn" title="刷新列表" @click="fetchHistory">
          <el-icon><Refresh /></el-icon>
        </button>
      </div>

      <div v-if="!history.length" class="empty-history">
        <el-empty description="暂无面试记录，选择上方岗位立即开启" />
      </div>

      <el-table v-else :data="history" size="default" class="history-table">
        <el-table-column prop="target_position" label="目标岗位" min-width="180">
          <template #default="{ row }">
            <span class="role-text">{{ row.target_position }}</span>
          </template>
        </el-table-column>
        <el-table-column label="综合评分" width="120">
          <template #default="{ row }">
            <span v-if="row.overall_score" class="score-pill">
              {{ row.overall_score }} 分
            </span>
            <span v-else class="ongoing-pill">进行中</span>
          </template>
        </el-table-column>
        <el-table-column label="面试状态" width="120">
          <template #default="{ row }">
            <span class="status-pill" :class="row.status">
              {{ row.status === 'finished' ? '已完成' : '进行中' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            <span class="time-text">{{ row.created_at }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center">
          <template #default="{ row }">
            <button
              class="table-action-btn"
              type="button"
              @click="router.push(`/interview/${row.session_id}`)"
            >
              {{ row.status === 'finished' ? '查看报告' : '继续面试' }}
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
import { Refresh, Tickets, Opportunity } from '@element-plus/icons-vue'
import iconInterview from '@/assets/images/icon_interview.svg'
import { interviewApi, type SessionListItem } from '@/api/interview'
import { resumeApi, type ReviewListItem } from '@/api/resume'

const router = useRouter()
const loading = ref(false)
const form = reactive({ targetPosition: '', resumeReviewId: '' })
const history = ref<SessionListItem[]>([])
const resumeHistory = ref<ReviewListItem[]>([])

const hotRoles = [
  'Java 后端开发工程师',
  '前端开发工程师',
  '全栈开发工程师',
  'Go 高并发工程师',
  '算法 / 机器学习工程师',
]

async function startInterview() {
  if (!form.targetPosition.trim()) return
  loading.value = true
  try {
    const { data } = await interviewApi.startSession({
      target_position: form.targetPosition,
      resume_review_id: form.resumeReviewId || null,
    })
    router.push({ path: `/interview/${data.session_id}`, state: { openingMessage: data.message } })
  } finally {
    loading.value = false
  }
}

async function fetchHistory() {
  try {
    const { data } = await interviewApi.listSessions()
    history.value = data.items
  } catch {
    // ignore
  }
}

onMounted(async () => {
  fetchHistory()
  try {
    const { data } = await resumeApi.listReviews()
    resumeHistory.value = data.items.filter(r => r.status === 'done')
  } catch {
    // ignore
  }
})
</script>

<style scoped>
.interview-setup-page {
  max-width: 920px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.setup-card, .history-card {
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
  object-fit: contain;
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

.setup-form :deep(.el-form-item__label) {
  font-weight: 600;
  color: var(--nm-text-primary);
  margin-bottom: 6px;
}

.role-quick-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.quick-title {
  font-size: 12px;
  color: var(--nm-text-light);
}

.role-chip {
  font-size: 11.5px;
  color: var(--nm-primary);
  background: var(--nm-bg);
  padding: 3px 9px;
  border-radius: var(--nm-radius-full);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  cursor: pointer;
  transition: var(--nm-transition);
}

.role-chip:hover {
  transform: translateY(-1px);
  box-shadow: var(--nm-shadow-hover);
  color: var(--nm-primary-hover);
}

.form-actions {
  margin-top: 20px;
}

.start-btn {
  padding: 10px 24px;
  font-size: 14.5px;
  cursor: pointer;
}

.start-btn:disabled {
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

.role-text {
  font-weight: 600;
  color: var(--nm-text-primary);
}

.time-text {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

.score-pill {
  font-size: 12px;
  font-weight: 700;
  color: var(--nm-primary);
  background: #eff6ff;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
}

.ongoing-pill {
  font-size: 11px;
  color: #d97706;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
  font-weight: 500;
}

.status-pill {
  font-size: 11.5px;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
}

.status-pill.finished { background: #dcfce7; color: #059669; }
.status-pill.in_progress, .status-pill.active { background: #fef3c7; color: #d97706; }

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
