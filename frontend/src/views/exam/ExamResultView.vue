<template>
  <div class="exam-result-page">
    <!-- 顶部返回导航 -->
    <div class="top-nav-bar">
      <button class="back-btn" @click="router.push('/exam')">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回试卷列表</span>
      </button>
      <span class="page-title">试卷批改详情报告</span>
    </div>

    <!-- 加载中骨架 -->
    <div v-if="loading && !review" class="nm-card loading-card">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 结果展示 -->
    <template v-else-if="review">
      <!-- 状态横幅 -->
      <div class="status-banner" :class="review.status">
        <div class="banner-icon-box">
          <span v-if="review.status === 'published'">✅</span>
          <span v-else-if="review.status === 'pending_review'">⏳</span>
          <span v-else>🔄</span>
        </div>
        <div class="banner-text">
          <div class="banner-title">{{ statusTitle }}</div>
          <div class="banner-sub">{{ statusSubtitle }}</div>
        </div>
      </div>

      <!-- 处理中但暂未生成分数的等待卡片 -->
      <div v-if="!review.pre_review_summary" class="nm-card processing-card">
        <div class="processing-spinner">
          <img :src="iconAiHero" class="processing-spinner-img" alt="Processing" />
        </div>
        <h4 class="processing-title">AI 正在深度阅卷与生成反馈...</h4>
        <p class="processing-sub">系统正在进行代码沙箱测试与语义多维打分，约需 10-30 秒，结果将自动刷新呈现。</p>
      </div>

      <!-- 完整批改结果 -->
      <template v-else>
        <!-- 总分与薄弱点汇总卡片 -->
        <el-row :gutter="20" style="margin-bottom: 24px">
          <el-col :xs="24" :md="8">
            <div class="nm-card score-hero-card">
              <div class="score-badge">{{ review.status === 'published' ? '最终成绩' : 'AI 预评分' }}</div>
              <div class="score-display">
                <span class="score-num">{{ review.pre_review_summary.total_score }}</span>
                <span class="score-divider">/</span>
                <span class="score-full">{{ review.pre_review_summary.full_score }}</span>
              </div>
              <div class="score-percentage">
                得分率：{{ Math.round((review.pre_review_summary.total_score / (review.pre_review_summary.full_score || 1)) * 100) }}%
              </div>
            </div>
          </el-col>

          <el-col :xs="24" :md="16">
            <div class="nm-card weak-points-card">
              <div class="card-title-row">
                <span class="card-icon">🎯</span>
                <span class="card-title">知识薄弱点分析</span>
              </div>
              <div v-if="review.weak_points?.length" class="weak-tags-container">
                <span
                  v-for="wp in review.weak_points"
                  :key="wp.tag"
                  class="weak-chip"
                >
                  <span class="weak-tag-name">{{ wp.tag }}</span>
                  <span class="weak-tag-count">错 {{ wp.wrong_count }} 题</span>
                </span>
              </div>
              <div v-else class="no-weak-points">
                🎉 太棒了！本次测评未发现明显薄弱知识点，各项掌握良好。
              </div>

              <div v-if="review.weak_points_summary" class="weak-summary-box">
                <p class="summary-text">{{ review.weak_points_summary }}</p>
              </div>
            </div>
          </el-col>
        </el-row>

        <!-- 逐题批改详情 -->
        <div class="nm-card questions-card">
          <div class="card-title-row questions-header">
            <span class="card-icon">📑</span>
            <span class="card-title">逐题批改明细（共 {{ review.pre_review_summary.by_question?.length || 0 }} 题）</span>
          </div>

          <el-collapse class="nm-collapse" v-model="expandedQuestions">
            <el-collapse-item
              v-for="q in review.pre_review_summary.by_question"
              :key="q.question_id"
              :name="q.question_id"
            >
              <template #title>
                <div class="q-title-bar">
                  <div class="q-title-left">
                    <span class="q-no">第 {{ q.question_no }} 题</span>
                    <span class="q-type-badge">{{ q.question_type }}</span>
                  </div>
                  <div class="q-title-right">
                    <span
                      class="q-score-badge"
                      :class="{ 'full-score': (q.final_score ?? q.score) === q.full_score }"
                    >
                      {{ q.final_score ?? q.score }} / {{ q.full_score }} 分
                    </span>
                    <span v-if="q.needs_review" class="needs-review-pill">待教师确认</span>
                  </div>
                </div>
              </template>

              <div class="q-detail-content">
                <!-- 题目内容 -->
                <div v-if="q.content" class="detail-row">
                  <div class="detail-label">题目内容</div>
                  <div class="detail-val question-content">{{ q.content }}</div>
                </div>

                <!-- 学员作答 -->
                <div class="detail-row">
                  <div class="detail-label">学员作答</div>
                  <div class="detail-val answer-val student">{{ q.student_answer || '（未作答）' }}</div>
                </div>

                <!-- 参考答案 -->
                <div v-if="q.correct_answer" class="detail-row">
                  <div class="detail-label">参考答案</div>
                  <div class="detail-val answer-val correct">{{ q.correct_answer }}</div>
                </div>

                <!-- AI 反馈 -->
                <div class="detail-row">
                  <div class="detail-label">AI 智能反馈</div>
                  <div class="detail-val feedback-val">{{ q.ai_feedback }}</div>
                </div>

                <!-- 教师批注 -->
                <div v-if="q.teacher_comment" class="detail-row teacher-comment-row">
                  <div class="detail-label">教师批注</div>
                  <div class="detail-val teacher-comment-val">{{ q.teacher_comment }}</div>
                </div>

                <!-- 测试用例通过情况（代码题） -->
                <div v-if="q.question_type === 'code' && q.test_cases_total" class="detail-row">
                  <div class="detail-label">沙箱测试</div>
                  <div class="detail-val">
                    <span v-if="q.sandbox_skipped" class="test-skip">Judge0 沙箱跳过</span>
                    <span v-else class="test-pass">通过 {{ q.test_cases_passed }} / {{ q.test_cases_total }} 测试用例</span>
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </template>
    </template>

    <div v-else class="nm-card empty-card">
      <el-empty description="未找到对应试卷的批改记录" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import iconAiHero from '@/assets/images/icon_ai_hero.svg'
import { examApi, type ReviewDetail } from '@/api/exam'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const review = ref<ReviewDetail | null>(null)
const expandedQuestions = ref<string[]>([])
let pollTimer: ReturnType<typeof setTimeout> | null = null

const statusTitle = computed(() => {
  if (!review.value) return ''
  if (review.value.status === 'published') return '教师已确认发布'
  if (review.value.status === 'pending_review') return 'AI 预批改完成，等待教师最终核准'
  return 'AI 正在全力批改中'
})

const statusSubtitle = computed(() => {
  if (!review.value) return ''
  if (review.value.status === 'published') return '本份试卷已完成所有批改环节，成绩已计入学习档案。'
  if (review.value.status === 'pending_review') return 'AI 批改结论已呈送教师，稍后教师确认后将更新为最终成绩。'
  return '系统正在执行自然语言语义理解与代码用例测试，完成后将自动刷新页面。'
})

async function fetchReview() {
  try {
    const { data } = await examApi.getSubmissionReview(route.params.submissionId as string)
    review.value = data

    // 默认展开所有题目
    if (data.pre_review_summary?.by_question && expandedQuestions.value.length === 0) {
      expandedQuestions.value = data.pre_review_summary.by_question.map(q => q.question_id)
    }

    if (data.status === 'published' || data.pre_review_summary) {
      stopPoll()
    }
  } catch {
    stopPoll()
  } finally {
    loading.value = false
  }
}

function stopPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  fetchReview()
  const schedulePoll = () => {
    pollTimer = setTimeout(async () => {
      await fetchReview()
      if (review.value?.status !== 'published' && !review.value?.pre_review_summary) {
        schedulePoll()
      }
    }, 8_000)
  }
  schedulePoll()
})

onUnmounted(stopPoll)
</script>

<style scoped>
.exam-result-page {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
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

/* 状态横幅 */
.status-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: var(--nm-radius-lg);
  background: var(--nm-bg);
  border: var(--nm-border);
  box-shadow: var(--nm-shadow-flat);
}

.banner-icon-box {
  width: 44px;
  height: 44px;
  border-radius: var(--nm-radius-md);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.banner-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--nm-text-primary);
  margin-bottom: 2px;
}

.banner-sub {
  font-size: 12.5px;
  color: var(--nm-text-secondary);
}

/* 处理中等待卡片 */
.processing-card {
  padding: 40px 20px;
  text-align: center;
}

.processing-spinner {
  width: 64px;
  height: 64px;
  border-radius: var(--nm-radius-lg);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-flat);
  border: var(--nm-border);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.processing-spinner-img {
  width: 38px;
  height: 38px;
  object-fit: contain;
  animation: float-gentle 2.5s ease-in-out infinite;
}

.processing-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.processing-sub {
  margin: 0;
  font-size: 13px;
  color: var(--nm-text-secondary);
}

/* 得分卡片 */
.score-hero-card {
  padding: 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  box-sizing: border-box;
}

.score-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--nm-text-secondary);
  background: rgba(255, 255, 255, 0.7);
  padding: 2px 10px;
  border-radius: var(--nm-radius-full);
  box-shadow: inset 1px 1px 2px rgba(166, 180, 200, 0.3);
  margin-bottom: 12px;
}

.score-display {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 4px;
  margin-bottom: 8px;
}

.score-num {
  font-size: 48px;
  font-weight: 800;
  background: linear-gradient(135deg, #1e293b 0%, #3b82f6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1;
}

.score-divider {
  font-size: 24px;
  color: var(--nm-text-light);
}

.score-full {
  font-size: 22px;
  color: var(--nm-text-secondary);
  font-weight: 600;
}

.score-percentage {
  font-size: 13px;
  color: var(--nm-primary);
  font-weight: 600;
}

/* 薄弱点卡片 */
.weak-points-card {
  padding: 22px 24px;
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.card-icon {
  font-size: 18px;
}

.card-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.weak-tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.weak-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #fee2e2;
  border-radius: var(--nm-radius-full);
  border: 1px solid #fecaca;
  box-shadow: 2px 2px 5px rgba(239, 68, 68, 0.15);
}

.weak-tag-name {
  font-size: 12px;
  font-weight: 600;
  color: #dc2626;
}

.weak-tag-count {
  font-size: 11px;
  color: #991b1b;
  background: rgba(255, 255, 255, 0.7);
  padding: 1px 5px;
  border-radius: 4px;
}

.no-weak-points {
  font-size: 13px;
  color: var(--nm-success);
  padding: 10px 0;
}

.weak-summary-box {
  margin-top: auto;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: var(--nm-radius-md);
  box-shadow: inset 1px 1px 3px rgba(166, 180, 200, 0.25);
}

.summary-text {
  margin: 0;
  font-size: 12.5px;
  color: var(--nm-text-secondary);
  line-height: 1.6;
}

/* 逐题详情卡片 */
.questions-card {
  padding: 22px 24px;
}

.questions-header {
  border-bottom: 1px solid rgba(203, 213, 225, 0.4);
  padding-bottom: 14px;
  margin-bottom: 8px;
}

.nm-collapse {
  border: none !important;
}

.nm-collapse :deep(.el-collapse-item__header) {
  background: var(--nm-bg) !important;
  border-radius: var(--nm-radius-md);
  margin-bottom: 8px;
  padding: 0 16px;
  box-shadow: var(--nm-shadow-sm);
  border: var(--nm-border);
  height: 48px;
  transition: var(--nm-transition);
}

.nm-collapse :deep(.el-collapse-item__header:hover) {
  box-shadow: var(--nm-shadow-hover);
  transform: translateY(-1px);
}

.nm-collapse :deep(.el-collapse-item__wrap) {
  background: transparent !important;
  border: none !important;
}

.nm-collapse :deep(.el-collapse-item__content) {
  padding: 10px 16px 18px;
}

.q-title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 12px;
}

.q-title-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.q-no {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--nm-text-primary);
}

.q-type-badge {
  font-size: 11px;
  color: var(--nm-text-secondary);
  background: rgba(255, 255, 255, 0.7);
  padding: 2px 7px;
  border-radius: 4px;
}

.q-title-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.q-score-badge {
  font-size: 13px;
  font-weight: 700;
  color: var(--nm-primary);
}

.q-score-badge.full-score {
  color: var(--nm-success);
}

.needs-review-pill {
  font-size: 10.5px;
  color: #d97706;
  background: #fef3c7;
  padding: 2px 7px;
  border-radius: var(--nm-radius-full);
  font-weight: 600;
}

.q-detail-content {
  background: var(--nm-bg);
  border-radius: var(--nm-radius-md);
  box-shadow: var(--nm-shadow-inset);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--nm-text-light);
}

.detail-val {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--nm-text-primary);
}

.question-content {
  font-weight: 500;
}

.answer-val {
  padding: 8px 12px;
  border-radius: var(--nm-radius-sm);
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.8);
}

.answer-val.student {
  color: #1e293b;
}

.answer-val.correct {
  color: #059669;
  background: #ecfdf5;
  border-color: #a7f3d0;
}

.feedback-val {
  color: #475569;
}

.teacher-comment-row {
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: var(--nm-radius-sm);
  border-left: 3px solid #f59e0b;
}

.teacher-comment-val {
  color: #b45309;
  font-weight: 500;
}

.test-pass {
  color: var(--nm-success);
  font-weight: 600;
  font-size: 12.5px;
}

.test-skip {
  color: var(--nm-text-light);
  font-size: 12.5px;
}

.loading-card, .empty-card {
  padding: 40px;
}
</style>
