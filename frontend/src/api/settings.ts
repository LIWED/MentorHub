import client from './client'

export interface QARetrievalSettings {
  recall_top_k_single: number
  recall_top_k_hyde: number
  recall_top_k_broad_per: number
  recall_top_k_iterative: number
  rerank_evidence_top_k: number
  final_context_top_k: number
  retrieval_confidence_threshold: number
  max_gap_queries: number
  max_gap_rounds: number
}

export interface APISettingsView {
  llm_base_url: string
  llm_model: string
  web_search_provider: 'auto' | 'tavily' | 'duckduckgo'
  deepseek_api_key_configured: boolean
  tavily_api_key_configured: boolean
}

export interface SystemSettingsView {
  qa: QARetrievalSettings
  api: APISettingsView
}

export interface SystemSettingsPatch {
  qa?: Partial<QARetrievalSettings>
  api?: {
    llm_base_url?: string
    llm_model?: string
    web_search_provider?: 'auto' | 'tavily' | 'duckduckgo'
    deepseek_api_key?: string
    tavily_api_key?: string
  }
}

export const settingsApi = {
  get: () => client.get<SystemSettingsView>('/settings'),

  update: (data: SystemSettingsPatch) =>
    client.patch<SystemSettingsView>('/settings', data),

  reset: () =>
    client.delete<SystemSettingsView>('/settings'),
}
