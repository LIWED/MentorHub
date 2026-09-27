import client from './client'

export interface KnowledgeCourse {
  id: string
  name: string
  description: string
  document_count: number
  completed_count: number
  chunk_count: number
  created_at?: string | null
  updated_at?: string | null
}

export type KnowledgeDocumentStatus = 'uploaded' | 'parsing' | 'completed' | 'failed'

export interface KnowledgeDocument {
  id: string
  course_id: string
  filename: string
  relative_path: string
  file_type: string
  status: KnowledgeDocumentStatus
  parser?: string | null
  content_format?: string | null
  extracted_chars: number
  chunk_count: number
  image_count: number
  image_enriched_count: number
  image_failed_count: number
  error_msg?: string | null
  updated_at?: string | null
}

export interface KnowledgeUploadResult {
  uploaded_files: number
  documents_queued: number
  skipped_unchanged: number
  asset_files: number
  sitemap_used: boolean
}

export interface KnowledgeChunkPreview {
  id: string
  content: string
  chunk_index: number
  source_name: string
  chunk_type: string
  document_type: string
  relative_path: string
  chapter: string
  section: string
  heading_path: string
  retrieval_text: string
}

export interface RetrievalTestItem {
  rank: number
  content: string
  score: number
  source_name: string
  document_id: string
  relative_path: string
  chapter: string
  section: string
  heading_path: string
  chunk_index: number
  chunk_type: string
}

export interface RetrievalChainStep {
  name: string
  label: string
  elapsed_ms: number
  summary: string
  details: Record<string, unknown>
}

export interface RetrievalCallTrace {
  query: string
  elapsed_ms: number
  filter_expr: string
  candidate_count: number
  ranked_count: number
  confidence: number
  recall_top_k: number
  rerank_top_k: number
}

export interface RetrievalTestResponse {
  query: string
  status: string
  strategy: string
  rewritten_query: string
  metadata_scope: Record<string, string>
  scope_source: string
  confidence: number
  evidence_count: number
  total_ms: number
  steps: RetrievalChainStep[]
  final_evidence: RetrievalTestItem[]
  retrieval_calls: RetrievalCallTrace[]
  runtime_config: Record<string, number>
}

export const knowledgeApi = {
  listCourses: () => client.get<KnowledgeCourse[]>('/knowledge/courses'),
  listAvailableCourses: () =>
    client.get<KnowledgeCourse[]>('/knowledge/available-courses'),

  createCourse: (data: { name: string; description?: string }) =>
    client.post<KnowledgeCourse>('/knowledge/courses', data),

  getCourse: (courseId: string) =>
    client.get<KnowledgeCourse>(`/knowledge/courses/${courseId}`),

  deleteCourse: (courseId: string) =>
    client.delete(`/knowledge/courses/${courseId}`),

  listDocuments: (courseId: string) =>
    client.get<KnowledgeDocument[]>(`/knowledge/courses/${courseId}/documents`),

  previewChunks: (documentId: string, limit = 200) =>
    client.get<KnowledgeChunkPreview[]>(
      `/knowledge/documents/${documentId}/chunks`,
      { params: { limit } },
    ),

  retrievalTest: (data: {
    query: string
    course_id?: string | null
    document_id?: string | null
    enable_web_search?: boolean
  }) =>
    client.post<RetrievalTestResponse>('/knowledge/retrieval-test', data, {
      // 全链路可能包含 Query Rewrite / HyDE / Sufficiency / Gap Retrieval 的 LLM 调用。
      timeout: 0,
    }),

  uploadDocuments: (
    courseId: string,
    files: File[],
    mode: 'files' | 'folder',
  ) => {
    const form = new FormData()
    for (const file of files) {
      form.append('files', file, file.name)
      const relativePath =
        mode === 'folder' && file.webkitRelativePath
          ? file.webkitRelativePath
          : file.name
      form.append('relative_paths', relativePath)
    }
    form.append('upload_mode', mode)

    return client.post<KnowledgeUploadResult>(
      `/knowledge/courses/${courseId}/documents`,
      form,
      {
        // 文件夹上传可能包含大量静态资源，不能沿用全局 30s 超时。
        timeout: 0,
      },
    )
  },

  reparseDocument: (documentId: string) =>
    client.post<{ document_id: string; status: string }>(
      `/knowledge/documents/${documentId}/reparse`,
    ),

  deleteDocument: (documentId: string) =>
    client.delete(`/knowledge/documents/${documentId}`),
}
