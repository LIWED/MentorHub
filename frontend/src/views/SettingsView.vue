<template>
  <div class="settings-page" v-loading="loading">
    <div class="page-header">
      <div>
        <div class="eyebrow">SYSTEM CONFIG</div>
        <h1>系统设置</h1>
        <p>调整 QA 检索链和外部 API。保存后对后续请求立即生效，无需重启服务。</p>
      </div>
      <div class="header-actions">
        <el-button @click="loadSettings">重新加载</el-button>
        <el-button type="danger" plain @click="resetSettings">恢复默认</el-button>
        <el-button type="primary" :loading="saving" @click="saveSettings">保存设置</el-button>
      </div>
    </div>

    <el-alert
      title="这是全局管理员设置，会影响所有后续 QA 请求。API Key 不会从后端明文回传。"
      type="info"
      :closable="false"
      show-icon
      class="settings-alert"
    />

    <div class="settings-grid">
      <section class="settings-card">
        <div class="card-heading">
          <div>
            <h2>检索与重排</h2>
            <p>控制不同检索策略的候选池、证据窗口和最终上下文数量。</p>
          </div>
          <el-tag effect="plain">RAG</el-tag>
        </div>

        <div class="field-grid">
          <SettingNumber
            v-model="form.qa.recall_top_k_single"
            label="Single 召回数量"
            tip="普通单路 Hybrid Retrieval 的候选数量"
            :min="1"
            :max="200"
          />
          <SettingNumber
            v-model="form.qa.recall_top_k_hyde"
            label="HyDE 召回数量"
            tip="低置信度触发 HyDE 后的候选数量"
            :min="1"
            :max="200"
          />
          <SettingNumber
            v-model="form.qa.recall_top_k_broad_per"
            label="Broad 每 Query 召回"
            tip="Multi Query 中每个子 Query 的候选数量"
            :min="1"
            :max="100"
          />
          <SettingNumber
            v-model="form.qa.recall_top_k_iterative"
            label="Iterative 每 Query 召回"
            tip="迭代检索中每个展开 Query 的候选数量"
            :min="1"
            :max="100"
          />
          <SettingNumber
            v-model="form.qa.rerank_evidence_top_k"
            label="重排证据数量"
            tip="Reranker 后保留给 Sufficiency 判断的证据窗口"
            :min="1"
            :max="50"
          />
          <SettingNumber
            v-model="form.qa.final_context_top_k"
            label="最终上下文数量"
            tip="真正交给回答模型的 Top-K Context"
            :min="1"
            :max="20"
          />
        </div>

        <div class="threshold-block">
          <div class="field-label-row">
            <div>
              <div class="field-label">Reranker 置信度阈值</div>
              <div class="field-tip">低于该阈值进入 HyDE / Web 等低置信度分支</div>
            </div>
            <el-input-number
              v-model="form.qa.retrieval_confidence_threshold"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              controls-position="right"
              class="threshold-number"
            />
          </div>
          <el-slider
            v-model="form.qa.retrieval_confidence_threshold"
            :min="0"
            :max="1"
            :step="0.05"
            :show-tooltip="true"
          />
        </div>
      </section>

      <section class="settings-card">
        <div class="card-heading">
          <div>
            <h2>Sufficiency 循环</h2>
            <p>控制证据不足时的 Gap Rewrite 与补充检索规模。</p>
          </div>
          <el-tag type="success" effect="plain">Agentic RAG</el-tag>
        </div>

        <div class="field-grid field-grid--compact">
          <SettingNumber
            v-model="form.qa.max_gap_queries"
            label="每轮 Gap Query 数"
            tip="每轮最多针对缺失证据生成多少个补充 Query"
            :min="1"
            :max="10"
          />
          <SettingNumber
            v-model="form.qa.max_gap_rounds"
            label="最大循环次数"
            tip="Sufficiency → Gap Retrieval 最多循环多少轮；0 表示不补搜"
            :min="0"
            :max="10"
          />
        </div>

        <div class="pipeline-preview">
          <span>Retrieve</span>
          <b>→</b>
          <span>Rerank</span>
          <b>→</b>
          <span>Sufficiency</span>
          <b>→</b>
          <span>Gap Retrieval × {{ form.qa.max_gap_rounds }}</span>
        </div>
      </section>

      <section class="settings-card settings-card--wide">
        <div class="card-heading">
          <div>
            <h2>LLM API</h2>
            <p>OpenAI 兼容接口配置。修改后会清空现有 LLM 实例缓存并使用新配置。</p>
          </div>
          <el-tag :type="apiStatus.deepseek_api_key_configured ? 'success' : 'warning'" effect="plain">
            {{ apiStatus.deepseek_api_key_configured ? 'API Key 已配置' : 'API Key 未配置' }}
          </el-tag>
        </div>

        <div class="api-grid">
          <div class="form-field">
            <label>Base URL</label>
            <el-input v-model="form.api.llm_base_url" placeholder="https://api.deepseek.com/v1" />
          </div>
          <div class="form-field">
            <label>Model</label>
            <el-input v-model="form.api.llm_model" placeholder="模型名称" />
          </div>
          <div class="form-field form-field--wide">
            <label>LLM API Key</label>
            <el-input
              v-model="secretInputs.deepseek"
              type="password"
              show-password
              autocomplete="new-password"
              :placeholder="apiStatus.deepseek_api_key_configured ? '已配置；留空表示保持不变' : '输入 API Key'"
              :disabled="clearSecrets.deepseek"
            />
            <el-checkbox v-model="clearSecrets.deepseek">保存时清空现有 LLM API Key</el-checkbox>
          </div>
        </div>
      </section>

      <section class="settings-card settings-card--wide">
        <div class="card-heading">
          <div>
            <h2>Web Search API</h2>
            <p>选择联网搜索后端。Auto 会优先 Tavily，失败或无 Key 时回退 DuckDuckGo。</p>
          </div>
          <el-tag :type="apiStatus.tavily_api_key_configured ? 'success' : 'info'" effect="plain">
            Tavily {{ apiStatus.tavily_api_key_configured ? '已配置' : '未配置' }}
          </el-tag>
        </div>

        <div class="api-grid">
          <div class="form-field">
            <label>搜索提供方</label>
            <el-select v-model="form.api.web_search_provider" style="width: 100%">
              <el-option label="Auto（Tavily 优先，DDG 回退）" value="auto" />
              <el-option label="Tavily 优先" value="tavily" />
              <el-option label="DuckDuckGo" value="duckduckgo" />
            </el-select>
          </div>
          <div class="form-field form-field--wide">
            <label>Tavily API Key</label>
            <el-input
              v-model="secretInputs.tavily"
              type="password"
              show-password
              autocomplete="new-password"
              :placeholder="apiStatus.tavily_api_key_configured ? '已配置；留空表示保持不变' : '可选；未配置时使用 DuckDuckGo'"
              :disabled="clearSecrets.tavily"
            />
            <el-checkbox v-model="clearSecrets.tavily">保存时清空现有 Tavily API Key</el-checkbox>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import SettingNumber from '@/components/settings/SettingNumber.vue'
import {
  settingsApi,
  type APISettingsView,
  type QARetrievalSettings,
  type SystemSettingsPatch,
} from '@/api/settings'

const loading = ref(false)
const saving = ref(false)

const defaultQa: QARetrievalSettings = {
  recall_top_k_single: 20,
  recall_top_k_hyde: 20,
  recall_top_k_broad_per: 10,
  recall_top_k_iterative: 12,
  rerank_evidence_top_k: 6,
  final_context_top_k: 3,
  retrieval_confidence_threshold: 0.75,
  max_gap_queries: 2,
  max_gap_rounds: 2,
}

const form = reactive({
  qa: { ...defaultQa },
  api: {
    llm_base_url: '',
    llm_model: '',
    web_search_provider: 'auto' as 'auto' | 'tavily' | 'duckduckgo',
  },
})

const apiStatus = reactive<APISettingsView>({
  llm_base_url: '',
  llm_model: '',
  web_search_provider: 'auto',
  deepseek_api_key_configured: false,
  tavily_api_key_configured: false,
})

const secretInputs = reactive({
  deepseek: '',
  tavily: '',
})

const clearSecrets = reactive({
  deepseek: false,
  tavily: false,
})

function applyResponse(data: { qa: QARetrievalSettings; api: APISettingsView }) {
  Object.assign(form.qa, data.qa)
  form.api.llm_base_url = data.api.llm_base_url
  form.api.llm_model = data.api.llm_model
  form.api.web_search_provider = data.api.web_search_provider
  Object.assign(apiStatus, data.api)
  secretInputs.deepseek = ''
  secretInputs.tavily = ''
  clearSecrets.deepseek = false
  clearSecrets.tavily = false
}

async function loadSettings() {
  loading.value = true
  try {
    const { data } = await settingsApi.get()
    applyResponse(data)
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  try {
    const apiPatch: NonNullable<SystemSettingsPatch['api']> = {
      llm_base_url: form.api.llm_base_url.trim(),
      llm_model: form.api.llm_model.trim(),
      web_search_provider: form.api.web_search_provider,
    }

    if (clearSecrets.deepseek) apiPatch.deepseek_api_key = ''
    else if (secretInputs.deepseek.trim()) apiPatch.deepseek_api_key = secretInputs.deepseek.trim()

    if (clearSecrets.tavily) apiPatch.tavily_api_key = ''
    else if (secretInputs.tavily.trim()) apiPatch.tavily_api_key = secretInputs.tavily.trim()

    const { data } = await settingsApi.update({
      qa: { ...form.qa },
      api: apiPatch,
    })
    applyResponse(data)
    ElMessage.success('系统设置已保存并立即生效')
  } finally {
    saving.value = false
  }
}

async function resetSettings() {
  await ElMessageBox.confirm(
    '将删除运行时覆盖设置，恢复 .env.local 与项目默认参数。确定继续吗？',
    '恢复默认设置',
    {
      confirmButtonText: '恢复默认',
      cancelButtonText: '取消',
      type: 'warning',
    },
  )

  loading.value = true
  try {
    const { data } = await settingsApi.reset()
    applyResponse(data)
    ElMessage.success('已恢复默认设置')
  } finally {
    loading.value = false
  }
}

void loadSettings()
</script>

<style scoped>
.settings-page {
  height: 100%;
  overflow-y: auto;
  padding: 28px 32px 48px;
  box-sizing: border-box;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}

.eyebrow {
  color: var(--nm-primary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1.3px;
  margin-bottom: 7px;
}

h1 {
  margin: 0;
  font-size: 28px;
  color: var(--nm-text-primary);
}

.page-header p,
.card-heading p {
  margin: 7px 0 0;
  color: var(--nm-text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.header-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.settings-alert {
  margin-bottom: 20px;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(300px, 0.8fr);
  gap: 18px;
}

.settings-card {
  border: var(--nm-border);
  border-radius: var(--nm-radius-lg);
  background: var(--nm-bg);
  box-shadow: var(--nm-shadow-sm);
  padding: 22px;
}

.settings-card--wide {
  grid-column: 1 / -1;
}

.card-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 22px;
}

.card-heading h2 {
  margin: 0;
  color: var(--nm-text-primary);
  font-size: 18px;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.field-grid--compact {
  grid-template-columns: 1fr 1fr;
}

.threshold-block {
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
}

.field-label-row {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
  margin-bottom: 10px;
}

.field-label {
  font-size: 13px;
  font-weight: 650;
  color: var(--nm-text-primary);
}

.field-tip {
  margin-top: 4px;
  font-size: 11px;
  color: var(--nm-text-light);
  line-height: 1.5;
}

.threshold-number {
  width: 130px;
}

.pipeline-preview {
  margin-top: 22px;
  padding: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  align-items: center;
  border-radius: var(--nm-radius-md);
  box-shadow: var(--nm-shadow-inset);
  color: var(--nm-text-secondary);
  font-size: 12px;
}

.pipeline-preview span {
  padding: 5px 9px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.55);
}

.pipeline-preview b {
  color: var(--nm-primary);
}

.api-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-field {
  min-width: 0;
}

.form-field--wide {
  grid-column: 1 / -1;
}

.form-field label {
  display: block;
  font-size: 13px;
  font-weight: 650;
  color: var(--nm-text-primary);
  margin-bottom: 8px;
}

.form-field :deep(.el-checkbox) {
  margin-top: 8px;
}

@media (max-width: 980px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }

  .settings-card--wide {
    grid-column: auto;
  }

  .page-header {
    flex-direction: column;
  }

  .field-grid,
  .field-grid--compact,
  .api-grid {
    grid-template-columns: 1fr;
  }

  .form-field--wide {
    grid-column: auto;
  }
}
</style>
