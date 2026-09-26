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

export const knowledgeApi = {
  listCourses: () => client.get<KnowledgeCourse[]>('/knowledge/courses'),

  createCourse: (data: { name: string; description?: string }) =>
    client.post<KnowledgeCourse>('/knowledge/courses', data),

  getCourse: (courseId: string) =>
    client.get<KnowledgeCourse>(`/knowledge/courses/${courseId}`),

  listDocuments: (courseId: string) =>
    client.get<KnowledgeDocument[]>(`/knowledge/courses/${courseId}/documents`),

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
