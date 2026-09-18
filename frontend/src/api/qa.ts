import client from './client'

export interface ChatRequest {
  session_id: string
  course_id?: string | null
  message: string
}

export interface ChatResponse {
  session_id: string
  answer: string
  answer_mode: 'rag' | 'web_augmented' | 'llm_direct' | 'general'
  confidence: number
  sources: string[]
  fallback_used: boolean
}

export interface HistoryMessage {
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sources: string[]
  answer_mode?: string | null
  confidence?: number | null
}

export interface HistoryResponse {
  session_id: string
  messages: HistoryMessage[]
  summary: string | null
  total_turns: number
}

export interface SessionListItem {
  session_id: string
  title: string
  total_turns: number
  updated_at: string
}

export interface SessionListResponse {
  items: SessionListItem[]
  total: number
}

export const qaApi = {
  chat: (data: ChatRequest) =>
    client.post<ChatResponse>('/qa/chat', data),

  listSessions: () =>
    client.get<SessionListResponse>('/qa/sessions'),

  getHistory: (sessionId: string) =>
    client.get<HistoryResponse>(`/qa/sessions/${sessionId}/history`),

  deleteSession: (sessionId: string) =>
    client.delete(`/qa/sessions/${sessionId}`),
}
