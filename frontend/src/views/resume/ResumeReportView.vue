<template>
  <div class="resume-report-page">
    <!-- 顶部导航 -->
    <div class="top-nav-bar">
      <button class="back-btn" @click="router.push('/resume')">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回上传档案</span>
      </button>
      <span class="page-title">简历多维诊断评估报告</span>
    </div>

    <!-- 加载骨架 -->
    <div v-if="loading && !review" class="nm-card skeleton-card">
      <el-skeleton :rows="10" animated />
    </div>

    <!-- 报告完整内容 -->
    <template v-else-if="review?.status === 'done' && review.dimension_scores">
      <!-- 综合得分 Hero 卡片 -->
      <div class="nm-card total-score-hero">
        <div class="hero-content">
          <div class="score-circle-wrapper">
            <div class="score-circle">
              <span class="score-big">{{ review.weighted_score?.toFixed(1) }}</span>
              <span class="score-unit">综合得分 (满分 100)</span>
            </div>
          </div>
          <div class="score-summary-text">
            <div class="summary-badge">AI 综合评定结论</div>
            <p class="overall-comment">{{ review.summary?.overall_comment }}</p>
            <div v-if="review.summary?.fit_assessment" class="fit-chip">
              <span class="fit-label">🎯 岗位匹配度评估：</span>
              <span class="fit-val">{{ review.summary.fit_assessment }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 六维度评分网格 -->
      <div class="section-title-row">
        <span class="section-title">六大核心维度评分与明细</span>
      </div>

      <el-row :gutter="18" style="margin-bottom: 24px">
        <el-col
          :xs="24"
          :sm="12"
          :md="8"
          v-for="dim in review.dimension_scores"
          :key="dim.key"
          style="margin-bottom: 18px"
        >
          <DimensionScoreCard
            :dimension="dim.dimension"
            :score="dim.score"
            :weight="dim.weight"
            :issues="dim.issues"
            :suggestions="dim.suggestions"
          />
        </el-col>
      </el-row>

      <!-- 问题清单列表 -->
      <div v-if="review.issues?.length" class="nm-card issues-card">
        <div class="card-header">
          <div class="header-icon-box">
            <span class="header-icon">⚠️</span>
          </div>
          <div>
            <h3 class="card-title">诊断问题清单（按优先级排序）</h3>
            <p class="card-subtitle">带原文定位与定制修改建议的高价值优化清单</p>
          </div>
        </div>

        <el-table :data="review.issues" size="default" class="issues-table">
          <el-table-column label="优先级" width="100">
            <template #default="{ row }">
              <span class="priority-pill" :class="row.priority">
                {{ priorityLabel(row.priority) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="dimension" label="所属维度" width="120">
            <template #default="{ row }">
              <span class="dim-tag">{{ row.dimension }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="问题描述" min-width="200" />
          <el-table-column prop="location" label="原文位置" width="160">
            <template #default="{ row }">
              <span class="location-pill">{{ row.location }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="suggestion" label="修改建议" min-width="240">
            <template #default="{ row }">
              <span class="suggestion-text">{{ row.suggestion }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 亮点与核心改进建议 -->
      <div v-if="review.summary" class="nm-card summary-card">
        <div class="card-header">
          <div class="header-icon-box">
            <el-icon class="header-icon-el"><Opportunity /></el-icon>
          </div>
          <div>
            <h3 class="card-title">整体优化战略与亮点提炼</h3>
            <p class="card-subtitle">AI 提炼的简历优势与必改攻坚要点</p>
          </div>
        </div>

        <el-row :gutter="24">
          <el-col :xs="24" :md="12">
            <div class="summary-box highlights">
              <div class="box-title">
                <span>🌟 简历既有亮点</span>
              </div>
              <ul class="summary-list">
                <li v-for="(h, i) in review.summary.highlights" :key="i">{{ h }}</li>
              </ul>
            </div>
          </el-col>
          <el-col :xs="24" :md="12">
            <div class="summary-box improvements">
              <div class="box-title">
                <span>🔧 核心必改攻坚项</span>
              </div>
              <ul class="summary-list">
                <li v-for="(c, i) in review.summary.core_improvements" :key="i">{{ c }}</li>
              </ul>
            </div>
          </el-col>
        </el-row>
      </div>
    </template>

    <!-- 处理中状态 -->
    <div v-else-if="review?.status === 'processing'" class="nm-card processing-card">
      <div class="processing-spinner-box">
        <img :src="iconResume" class="processing-spinner-img" alt="Processing" />
      </div>
      <h3 class="processing-title">AI 正在深度审查与交叉评估中...</h3>
      <p class="processing-sub">多模型六维度综合计算中，通常需要 30-60 秒，结果将自动呈现。</p>
      <div v-if="transientError" class="transient-warn">{{ transientError }}</div>
    </div>

    <!-- 失败状态 -->
    <div v-else-if="review?.status === 'failed'" class="nm-card failed-card">
      <div class="failed-icon">
        <el-icon><CircleCloseFilled /></el-icon>
      </div>
      <h3 class="failed-title">简历审查处理失败</h3>
      <p class="failed-sub">{{ review?.error_msg || '文件解析或大模型服务超时，请重新上传。' }}</p>
      <button class="nm-button-primary retry-btn" @click="router.push('/resume')">
        重新上传简历
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CircleCloseFilled, Opportunity } from '@element-plus/icons-vue'
import iconResume from '@/assets/images/icon_resume.jpg'
import { resumeApi, type ReviewDetail } from '@/api/resume'
import DimensionScoreCard from '@/components/resume/DimensionScoreCard.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const review = ref<ReviewDetail | null>(null)
const transientError = ref('')
let pollTimer: ReturnType<typeof setTimeout> | null = null
let mounted = false

function priorityLabel(p: string) {
  if (p === 'high') return '高优先'
  if (p === 'medium') return '中优先'
  return '低优先'
}

async function fetchReview() {
  if (!mounted) return
  try {
    const { data } = await resumeApi.getReview(route.params.reviewId as string)
    if (!mounted) return
    transientError.value = ''
    review.value = data
    if (data.status !== 'processing') stopPoll()
  } catch {
    if (mounted) transientError.value = '服务连接波动，正在自动重连中...'
  } finally {
    if (mounted) loading.value = false
  }
}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  mounted = true
  fetchReview()
  const schedulePoll = () => {
    if (!mounted) return
    pollTimer = setTimeout(async () => {
      await fetchReview()
      if (mounted && (!review.value || review.value.status === 'processing')) {
        schedulePoll()
      }
    }, 5_000)
  }
  schedulePoll()
})

onUnmounted(() => {
  mounted = false
  stopPoll()
})
</script>

<style scoped>
.resume-report-page {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
  animation: pop-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.top-nav-bar {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-sm);
  color: var(--nm-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--nm-transition);
}

.back-btn:hover {
  transform: translateX(-3px);
  color: var(--nm-primary);
  box-shadow: var(--nm-shadow-hover);
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

/* 综合得分 Hero 卡片 */
.total-score-hero {
  padding: 28px 36px;
}

.hero-content {
  display: flex;
  align-items: center;
  gap: 36px;
  flex-wrap: wrap;
}

.score-circle-wrapper {
  flex-shrink: 0;
}

.score-circle {
  width: 140px;
  height: 140px;
  border-radius: var(--nm-radius-full);
  background: var(--nm-bg);
  box-shadow: 8px 8px 20px rgba(166, 180, 200, 0.6), -8px -8px 20px rgba(255, 255, 255, 1);
  border: var(--nm-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.score-big {
  font-size: 46px;
  font-weight: 800;
  background: linear-gradient(135deg, #1e293b 0%, #3b82f6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1;
}

.score-unit {
  font-size: 11px;
  color: var(--nm-text-secondary);
  margin-top: 4px;
  font-weight: 500;
}

.score-summary-text {
  flex: 1;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-badge {
  font-size: 11px;
  color: var(--nm-primary);
  background: rgba(59, 130, 246, 0.1);
  padding: 3px 10px;
  border-radius: var(--nm-radius-full);
  display: inline-block;
  font-weight: 600;
  align-self: flex-start;
}

.overall-comment {
  margin: 0;
  font-size: 14.5px;
  color: var(--nm-text-regular);
  line-height: 1.65;
}

.fit-chip {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 13px;
  margin-top: 4px;
}

.fit-label {
  font-weight: 600;
  color: var(--nm-text-primary);
}

.fit-val {
  color: var(--nm-text-secondary);
}

/* 区域标题 */
.section-title-row {
  margin-top: 6px;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

/* 列表卡片共用 Header */
.issues-card, .summary-card {
  padding: 24px 28px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
}

.header-icon-box {
  width: 42px;
  height: 42px;
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
  font-size: 20px;
}

.header-icon-el {
  font-size: 22px;
  color: #d97706;
}

.card-title {
  margin: 0 0 4px;
  font-size: 16.5px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.card-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--nm-text-secondary);
}

.priority-pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
}

.priority-pill.high { background: #fee2e2; color: #dc2626; }
.priority-pill.medium { background: #fef3c7; color: #d97706; }
.priority-pill.low { background: #e0f2fe; color: #0284c7; }

.dim-tag {
  font-size: 12px;
  color: var(--nm-text-regular);
  font-weight: 500;
}

.location-pill {
  font-size: 11.5px;
  color: var(--nm-text-light);
  background: rgba(255, 255, 255, 0.6);
  padding: 2px 6px;
  border-radius: 4px;
  box-shadow: inset 1px 1px 2px rgba(166, 180, 200, 0.25);
}

.suggestion-text {
  font-size: 12.5px;
  color: var(--nm-text-regular);
  line-height: 1.5;
}

/* 亮点与攻坚卡片 */
.summary-box {
  padding: 16px 20px;
  border-radius: var(--nm-radius-lg);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-inset);
  border: 1px solid rgba(255, 255, 255, 0.4);
  height: 100%;
  box-sizing: border-box;
}

.summary-box.highlights {
  border-left: 4px solid var(--nm-success);
}

.summary-box.improvements {
  border-left: 4px solid var(--nm-warning);
}

.box-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--nm-text-primary);
  margin-bottom: 12px;
}

.summary-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--nm-text-regular);
}

/* 处理中 / 失败卡片 */
.processing-card, .failed-card {
  padding: 50px 24px;
  text-align: center;
}

.processing-spinner-box {
  width: 72px;
  height: 72px;
  border-radius: var(--nm-radius-xl);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
}

.processing-spinner-img {
  width: 42px;
  height: 42px;
  border-radius: 8px;
  object-fit: cover;
  animation: float-gentle 2.5s ease-in-out infinite;
}

.processing-title, .failed-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.processing-sub, .failed-sub {
  margin: 0;
  font-size: 13px;
  color: var(--nm-text-secondary);
}

.transient-warn {
  margin-top: 12px;
  font-size: 12.5px;
  color: var(--nm-warning);
}

.failed-icon {
  font-size: 40px;
  margin-bottom: 16px;
  color: var(--nm-danger);
  display: flex;
  align-items: center;
  justify-content: center;
}

.retry-btn {
  margin-top: 20px;
  padding: 8px 22px;
}

.skeleton-card {
  padding: 30px;
}
</style>
