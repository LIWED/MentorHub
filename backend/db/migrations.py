# backend/db/migrations.py
#
# 启动时自动执行的 Schema 补丁（全部幂等，可重复运行）。
# 规则：
#   - 只写 ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS 等幂等 DDL
#   - 禁止写 DROP / TRUNCATE 等破坏性变更
#   - 每次 init_db.sql 新增字段，同步在 _MIGRATIONS 里追加一条

from sqlalchemy import text
from backend.dependencies import AsyncSessionLocal
from backend.core.logger import get_logger

logger = get_logger(__name__)

# ── 所有需要补丁的 DDL，按时间顺序追加。SQL 必须幂等（IF NOT EXISTS）──
_MIGRATIONS: list[tuple[str, str]] = [
    (
        "knowledge_courses.table",
        """
        CREATE TABLE IF NOT EXISTS knowledge_courses (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'tenant_default',
            name VARCHAR(128) NOT NULL,
            description TEXT,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        )
        """,
    ),
    (
        "knowledge_documents.table",
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id VARCHAR(64) NOT NULL DEFAULT 'tenant_default',
            course_id UUID NOT NULL REFERENCES knowledge_courses(id) ON DELETE CASCADE,
            filename VARCHAR(512) NOT NULL,
            relative_path VARCHAR(1024) NOT NULL,
            file_type VARCHAR(32) NOT NULL,
            storage_path VARCHAR(1024) NOT NULL,
            file_hash VARCHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'uploaded'
                CHECK (status IN ('uploaded', 'parsing', 'completed', 'failed')),
            parser VARCHAR(64),
            content_format VARCHAR(32),
            extracted_chars INT NOT NULL DEFAULT 0,
            chunk_count INT NOT NULL DEFAULT 0,
            image_count INT NOT NULL DEFAULT 0,
            image_enriched_count INT NOT NULL DEFAULT 0,
            image_failed_count INT NOT NULL DEFAULT 0,
            error_msg TEXT,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (course_id, relative_path)
        )
        """,
    ),
    (
        "idx_knowledge_courses_tenant",
        "CREATE INDEX IF NOT EXISTS idx_knowledge_courses_tenant "
        "ON knowledge_courses (tenant_id, created_at DESC)",
    ),
    (
        "idx_knowledge_documents_course",
        "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_course "
        "ON knowledge_documents (course_id, created_at DESC)",
    ),
    (
        "idx_knowledge_documents_status",
        "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_status "
        "ON knowledge_documents (tenant_id, status)",
    ),
    (
        "exam_submissions.weak_points",
        "ALTER TABLE exam_submissions ADD COLUMN IF NOT EXISTS weak_points JSONB",
    ),
    (
        "exam_reviews.knowledge_tag",
        "ALTER TABLE exam_reviews ADD COLUMN IF NOT EXISTS knowledge_tag VARCHAR(128)",
    ),
    (
        "exam_submissions.weak_points_summary",
        "ALTER TABLE exam_submissions ADD COLUMN IF NOT EXISTS weak_points_summary TEXT",
    ),
    (
        "idx_exam_submissions_student_created",
        "CREATE INDEX IF NOT EXISTS idx_exam_submissions_student_created "
        "ON exam_submissions (student_id, created_at DESC)",
    ),
    (
        "idx_resume_reviews_student_created",
        "CREATE INDEX IF NOT EXISTS idx_resume_reviews_student_created "
        "ON resume_reviews (student_id, created_at DESC)",
    ),
    (
        "interview_sessions.runtime_state",
        "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS runtime_state JSONB",
    ),
    (
        "idx_interview_sessions_student_created",
        "CREATE INDEX IF NOT EXISTS idx_interview_sessions_student_created "
        "ON interview_sessions (student_id, created_at DESC)",
    ),
]


async def run_migrations() -> None:
    """
    在应用启动时执行所有 Schema 补丁。
    单条失败只记录警告，不阻断启动流程。
    """
    async with AsyncSessionLocal() as session:
        for desc, sql in _MIGRATIONS:
            try:
                await session.execute(text(sql))
                await session.commit()
                logger.debug("db.migration_applied", column=desc)
            except Exception as e:
                await session.rollback()
                err = str(e)
                if "already exists" not in err:
                    logger.warning("db.migration_failed", column=desc, error=err)

    logger.info("db.migrations_done", count=len(_MIGRATIONS))
