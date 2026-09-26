# scripts/build_knowledge_base.py（阶段版：文档加载 + 分块，5.4 / 5.5 继续补全）

import re
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownTextSplitter,
)

# ── 模块级分块器单例 ──────────────────────────────────────────
_CHAR_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=100,
    separators=["\n\n", "\n", "。", "，", " ", ""],
)

_FENCED_CODE_RE = re.compile(
    r"(?ms)"
    r"(?:^\[代码\][ \t]*\n)?"
    r"^```(?P<language>[^\n`]*)\n"
    r"(?P<body>.*?)"
    r"^```[ \t]*(?=\n|$)"
)


_MD_HEADING_RE = re.compile(
    r"^(?P<marks>#{1,4})[ \t]+(?P<title>.+?)[ \t]*$"
)
_CODE_FENCE_LINE_RE = re.compile(r"^[ \t]*```")
_PYTHON_TOP_LEVEL_RE = re.compile(
    r"^(?:async[ \t]+def|def|class)[ \t]+[A-Za-z_]\w*"
)


# ── 文档加载（5.2 内容，此处合并为完整文件）────────────────────

def parse_document(file_path: str, document_id: str | None = None):
    """统一解析入口：Markdown/TXT 原生解析，富文档优先 MinerU。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")

    from backend.core.parsers import get_parser_registry

    parsed = get_parser_registry().parse(
        file_path,
        document_id=document_id,
    )
    total_chars = sum(len(doc.page_content) for doc in parsed.documents)
    print(
        f"  [{parsed.parser_name}] 解析完成："
        f"{len(parsed.documents)} 个 document / {total_chars} 字符 ← {path.name}"
    )
    if parsed.output_dir:
        print(f"  MinerU 输出：{parsed.output_dir}")
    return parsed


def load_document(file_path: str, document_id: str | None = None) -> list[Document]:
    """兼容旧调用：仅返回解析后的 LangChain Document 列表。"""
    return parse_document(file_path, document_id=document_id).documents


# ── PDF 分块 ──────────────────────────────────────────────────

def split_pdf_documents(pages: list[Document]) -> list[Document]:
    """PDF 文档分块：过滤空页 + RecursiveCharacterTextSplitter"""
    non_empty_pages = [p for p in pages if len(p.page_content.strip()) > 20]
    skipped = len(pages) - len(non_empty_pages)
    if skipped > 0:
        print(f"  过滤空页：{skipped} 页（图片/扫描件页）")

    chunks = _CHAR_SPLITTER.split_documents(non_empty_pages)

    for chunk in chunks:
        filename = Path(chunk.metadata.get("source", "未知文件")).stem
        page_num = chunk.metadata.get("page", 0) + 1
        chunk.metadata["source_name"] = f"{filename} 第{page_num}页"

    print(f"  [PDF] 分块完成：{len(non_empty_pages)} 页 → {len(chunks)} 个 chunk")
    return chunks


# ── Markdown 分块 ─────────────────────────────────────────────

def _split_markdown_headings_preserving_code(doc: Document) -> list[Document]:
    """按 H1-H4 拆分 Markdown，同时原样保留 fenced code 的缩进。"""
    sections: list[Document] = []
    hierarchy: dict[str, str] = {}
    current_metadata = dict(doc.metadata)
    buffer: list[str] = []
    in_code = False

    def flush() -> None:
        if not buffer:
            return
        content = "".join(buffer).strip()
        if content:
            sections.append(
                Document(
                    page_content=content,
                    metadata=dict(current_metadata),
                )
            )
        buffer.clear()

    for line in doc.page_content.splitlines(keepends=True):
        line_without_eol = line.rstrip("\r\n")

        if _CODE_FENCE_LINE_RE.match(line_without_eol):
            in_code = not in_code
            buffer.append(line)
            continue

        heading = _MD_HEADING_RE.match(line_without_eol) if not in_code else None
        if heading:
            flush()
            level = len(heading.group("marks"))
            hierarchy[f"H{level}"] = heading.group("title").strip()
            for deeper in range(level + 1, 5):
                hierarchy.pop(f"H{deeper}", None)
            current_metadata = {**doc.metadata, **hierarchy}
            buffer.append(line)
            continue

        buffer.append(line)

    flush()
    return sections


def _split_python_code_preserving_top_level(
    body: str,
    *,
    chunk_size: int,
    fallback_splitter: RecursiveCharacterTextSplitter,
) -> list[str]:
    """优先在 Python 顶层 def/class 边界切分；超长函数才继续内部切分。"""
    lines = body.splitlines(keepends=True)
    starts = [
        index
        for index, line in enumerate(lines)
        if _PYTHON_TOP_LEVEL_RE.match(line)
    ]
    if not starts:
        return fallback_splitter.split_text(body)

    segments: list[str] = []
    if starts[0] > 0:
        preamble = "".join(lines[:starts[0]]).strip("\n")
        if preamble:
            segments.append(preamble)

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        segment = "".join(lines[start:end]).strip("\n")
        if segment:
            segments.append(segment)

    parts: list[str] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        if current:
            parts.append(current)
            current = ""

    for segment in segments:
        if len(segment) > chunk_size:
            flush_current()
            parts.extend(fallback_splitter.split_text(segment))
            continue

        if not current:
            current = segment
            continue

        candidate = f"{current}\n\n{segment}"
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            flush_current()
            current = segment

    flush_current()
    return parts


def _split_markdown_section_code_aware(
    section: Document,
    *,
    text_chunk_size: int,
    text_chunk_overlap: int,
    code_chunk_size: int,
    code_chunk_overlap: int,
) -> list[Document]:
    """
    在单个 Markdown 标题区间内分离 prose / fenced code。

    普通文字继续使用较小窗口；代码块用更大的窗口，并尽量按空行/行边界切，
    避免原来的 MarkdownTextSplitter 在 512 字符处直接截断函数或代码示例。
    """
    text = section.page_content
    matches = list(_FENCED_CODE_RE.finditer(text))
    if not matches:
        splitter = MarkdownTextSplitter(
            chunk_size=text_chunk_size,
            chunk_overlap=text_chunk_overlap,
        )
        chunks = splitter.create_documents(
            [text],
            metadatas=[dict(section.metadata)],
        )
        for chunk in chunks:
            chunk.metadata["chunk_type"] = "text"
        return chunks

    text_splitter = MarkdownTextSplitter(
        chunk_size=text_chunk_size,
        chunk_overlap=text_chunk_overlap,
    )
    code_splitter = RecursiveCharacterTextSplitter(
        chunk_size=code_chunk_size,
        chunk_overlap=code_chunk_overlap,
        separators=[
            "\n\nclass ",
            "\n\nasync def ",
            "\n\ndef ",
            "\n\n",
            "\n",
            " ",
            "",
        ],
    )

    chunks: list[Document] = []

    def append_text_segment(segment: str) -> None:
        segment = segment.strip()
        if not segment:
            return
        docs = text_splitter.create_documents(
            [segment],
            metadatas=[dict(section.metadata)],
        )
        for doc in docs:
            doc.metadata["chunk_type"] = "text"
        chunks.extend(docs)

    cursor = 0
    for match in matches:
        append_text_segment(text[cursor:match.start()])

        language = match.group("language").strip()
        body = match.group("body").strip("\n")
        if len(body) <= code_chunk_size:
            code_parts = [body]
        elif language.lower() in {"python", "py"}:
            code_parts = _split_python_code_preserving_top_level(
                body,
                chunk_size=code_chunk_size,
                fallback_splitter=code_splitter,
            )
        else:
            code_parts = code_splitter.split_text(body)

        total_parts = len(code_parts)
        for part_index, part in enumerate(code_parts):
            fenced = f"```{language}\n{part.rstrip()}\n```"
            chunks.append(
                Document(
                    page_content=f"[代码]\n{fenced}",
                    metadata={
                        **section.metadata,
                        "chunk_type": "code",
                        "code_language": language or "text",
                        "code_split_strategy": (
                            "python_top_level"
                            if language.lower() in {"python", "py"}
                            else "generic"
                        ),
                        "code_part_index": part_index,
                        "code_part_total": total_parts,
                    },
                )
            )
        cursor = match.end()

    append_text_segment(text[cursor:])
    return chunks


def split_markdown_documents(
    docs: list[Document],
    chunk_size: int = 512,
    chunk_overlap: int = 100,
    code_chunk_size: int = 1200,
    code_chunk_overlap: int = 120,
) -> list[Document]:
    """Markdown 分块：先按标题，再对正文与 fenced code 使用不同窗口。"""

    header_chunks: list[Document] = []
    for doc in docs:
        sections = _split_markdown_headings_preserving_code(doc)
        header_chunks.extend(sections)

    final_chunks: list[Document] = []
    for section in header_chunks:
        final_chunks.extend(
            _split_markdown_section_code_aware(
                section,
                text_chunk_size=chunk_size,
                text_chunk_overlap=chunk_overlap,
                code_chunk_size=code_chunk_size,
                code_chunk_overlap=code_chunk_overlap,
            )
        )

    for chunk in final_chunks:
        source_path = chunk.metadata.get("source", "")
        base_source_name = chunk.metadata.get("source_name", "")
        filename = base_source_name or (
            Path(source_path).stem if source_path else "未知文件"
        )
        parts = [
            chunk.metadata.get("H1", ""),
            chunk.metadata.get("H2", ""),
            chunk.metadata.get("H3", ""),
            chunk.metadata.get("H4", ""),
        ]
        parts = [p for p in parts if p]
        chunk.metadata["source_name"] = (
            f"{filename} > {' > '.join(parts)}" if parts else filename
        )

    print(f"  [MD]  分块完成：{len(docs)} 个文件 → {len(final_chunks)} 个 chunk")
    return final_chunks


# ── 统一分块入口 ──────────────────────────────────────────────

def split_documents(docs: list[Document], file_path: str) -> list[Document]:
    """统一分块入口：按 Parser 输出格式选择分块策略，而不是只看源文件扩展名。"""
    ext = Path(file_path).suffix.lower()
    content_format = (
        docs[0].metadata.get("content_format", "")
        if docs else ""
    )
    parser_name = (
        docs[0].metadata.get("parser", "")
        if docs else ""
    )

    # MinerU 统一输出 Markdown，PDF/图片/Office 都走结构感知 Markdown 分块。
    if content_format == "markdown" or parser_name in {"mineru", "markdown"}:
        return split_markdown_documents(docs)
    if ext == ".pdf":
        return split_pdf_documents(docs)
    if ext == ".txt":
        return _CHAR_SPLITTER.split_documents(docs)
    else:
        raise ValueError(f"不支持的文件类型：{ext}")


import uuid
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 把项目根目录加入 Python 路径，使得 build_knowledge_base.py 能 import backend.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.documents import Document
from backend.core.knowledge_base import BGEMEmbedder, DocumentChunk, generate_chunk_id

BATCH_SIZE = 12   # BGE-M3 批量推理大小（12 = 速度与显存的经验平衡点）


def embed_chunks(
    chunks: list[Document],
    course_id: str,
    document_id: str,
    tenant_id: str = "tenant_default",
    version: str = "1.0",
) -> list[DocumentChunk]:
    """
    对 split_documents() 产出的 chunk 列表做 BGE-M3 嵌入，返回 DocumentChunk 列表。

    BGE-M3 推理为 CPU / GPU-bound，按 BATCH_SIZE 批量处理：
    - 减少模型推理次数（每次推理有固定启动开销）
    - 控制显存/内存峰值（整批一次性推理会爆显存）

    Args:
        chunks:      split_documents() 返回的 list[Document]
        course_id:   所属课程 UUID
        document_id: 文档的 UUID（用于 Milvus 幂等更新，删旧插新）
        tenant_id:   租户 ID，用于 Milvus 多租户过滤
        version:     课程版本号

    Returns:
        list[DocumentChunk]，每项包含 BGE-M3 Dense 向量；BM25 稀疏权重在写入前按当前全库语料重新计算
    """
    embedder = BGEMEmbedder.get_instance()   # 单例，首次调用加载模型
    all_doc_chunks: list[DocumentChunk] = []
    total = len(chunks)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = chunks[batch_start: batch_start + BATCH_SIZE]
        texts = [c.page_content for c in batch]
        # BGE-M3 只负责 Dense；BM25 sparse 在写入前按当前全库语料计算
        dense_vecs = embedder.encode(texts, batch_size=BATCH_SIZE)
        for i, (chunk, dense) in enumerate(zip(batch, dense_vecs)):
            global_index = batch_start + i    # 在整个文档中的顺序编号

            all_doc_chunks.append(DocumentChunk(
                id=generate_chunk_id(chunk.page_content, document_id, global_index),
                content=chunk.page_content,
                embedding=dense,
                sparse_embedding={},
                course_id=course_id,
                document_id=document_id,
                source_name=chunk.metadata.get("source_name", ""),
                chunk_type=chunk.metadata.get("chunk_type", "text"),
                chunk_index=global_index,
                version=version,
                tenant_id=tenant_id,
            ))

        done = min(batch_start + BATCH_SIZE, total)
        print(f"  嵌入进度：{done}/{total}")

    print(f"  嵌入完成：{len(all_doc_chunks)} 个 DocumentChunk")
    return all_doc_chunks

MAX_CONTEXT_CONCURRENCY = 5

CONTEXTUAL_CHUNK_PROMPT = """\
<document>
{document_text}
</document>

以下是需要在整个文档中定位的 chunk：
<chunk>
{chunk_content}
</chunk>

请用一句简洁的中文，描述这段内容在整个文档中的位置和作用，以便改善检索效果。
只输出这一句描述，不要加任何前缀或标签。"""

from backend.core.llm_factory import get_llm
import asyncio
async def generate_chunk_context(
    llm,
    document_text: str,
    chunk_content: str,
    semaphore: asyncio.Semaphore,
) -> str:
    """
    用 LLM 为单个 chunk 生成一句定位描述。

    失败时返回空字符串，调用方保留原始 chunk 文本（降级处理）。

    Args:
        llm:           DeepSeek LLM 实例（via get_llm）
        document_text: 整篇文档全文（截断至 8000 字）
        chunk_content: 当前 chunk 的原始文本
        semaphore:     并发限流（最多 MAX_CONTEXT_CONCURRENCY 个 LLM 请求同时进行）
    """
    async with semaphore:
        try:
            from langchain_core.messages import HumanMessage
            prompt = CONTEXTUAL_CHUNK_PROMPT.format(
                document_text=document_text,
                chunk_content=chunk_content,
            )
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            ctx = (
                resp.text
                if hasattr(resp, "text") and not callable(resp.text)
                else str(resp.content)
            ).strip()
            return ctx
        except Exception as e:
            print(f"   [warning] 上下文生成失败，保留原始 chunk：{e}")
            return ""

async def add_context(
    chunks: list[Document],
    docs: list[Document],
    concurrency: int = MAX_CONTEXT_CONCURRENCY,
) -> list[Document]:
    """
    Contextual RAG：并发为所有 chunk 生成上下文描述，拼接到 chunk 文本前方。

    拼接后格式：
        "<上下文描述一句话>\\n\\n<原始 chunk 文本>"

    拼接后再做嵌入（embed_chunks），向量同时编码"在哪里"和"说了什么"两层信息。

    Args:
        chunks:      split_documents() 输出的 list[Document]
        docs:        load_document() 输出的原始 list[Document]（用于构建全文参考）
        concurrency: 最大并发 LLM 请求数（默认 5，防止触发 API 限流）

    Returns:
        page_content 已被就地修改（拼接上下文）的 list[Document]
    """
    # 拼接全文供 LLM 参考（截断 8000 字，避免超出模型 context 长度）
    full_doc_text = "\n\n".join(d.page_content for d in docs)[:8000]
    # print(f'full_doc_text-->{full_doc_text}')

    llm       = get_llm("qa", temperature=0)
    semaphore = asyncio.Semaphore(concurrency)

    # 并发调用 LLM，为每个 chunk 生成上下文描述
    contexts = await asyncio.gather(*[
        generate_chunk_context(llm, full_doc_text, c.page_content, semaphore)
        for c in chunks
    ])
    enriched = 0
    for chunk, ctx in zip(chunks, contexts):
        if ctx:
            chunk.page_content = f"{ctx}\n\n{chunk.page_content}"
            enriched += 1

    print(f"  上下文增强完成：{enriched}/{len(chunks)} 个 chunk 已添加描述")
    return chunks

# ── Step 4：写入 Milvus ────────────────────────────────────────

from backend.core.knowledge_base import KnowledgeBaseClient
def write_to_milvus(doc_chunks: list[DocumentChunk]) -> None:
    """
    将 embed_chunks() 产出的 DocumentChunk 列表写入 Milvus。

    先按 document_id 删除同文档旧版本 chunk，再批量 upsert，
    保证文档更新时不残留旧数据。
    """
    if not doc_chunks:
        print("  ⚠️  无 chunk 可写入，跳过")
        return

    kb          = KnowledgeBaseClient()
    document_id = doc_chunks[0].document_id
    #
    # print(f"  🗑️  删除旧版本 chunk（document_id={document_id[:8]}…）")
    # kb.delete_document_chunks(document_id)

    written = kb.upsert_with_bm25_rebuild(doc_chunks)
    print(f"  ✅ 写入完成：{written} 个 chunk → knowledge_domain")


# ── 主流水线 ─────────────────────────────────────────────────

async def build_pipeline(
    file_path:   str,
    course_id:   str,
    document_id: str,
    tenant_id:   str = "tenant_default",
    version:     str = "1.0",
    use_context: bool = False,
) -> None:
    """
    知识库建库完整流水线（五步）：

      Step 1   Parser Registry 解析（富文档优先 MinerU）
      Step 2   智能分块（MinerU Markdown / 原生 Markdown / 文本）
      Step 2.5 Contextual RAG 上下文增强（LLM 并发，可跳过）
      Step 3   BGE-M3 Dense 嵌入 + 全库 BM25 稀疏权重重建
      Step 4   写入 Milvus（MilvusClient upsert）
    """
    print(f"\n{'='*55}")
    print(f" MentorHub 知识库构建")
    print(f" 文件      ：{file_path}")
    print(f" 课程      ：{course_id}")
    print(f" 文档 ID   ：{document_id}")
    print(f" 租户      ：{tenant_id}")
    print(f" Contextual RAG：{'启用' if use_context else '跳过（--no-context）'}")
    print(f"{'='*55}\n")

    # Step 1：读取
    print("📖 Step 1/4  读取文档…")
    parsed = parse_document(file_path, document_id=document_id)
    docs = parsed.documents

    # Step 2：分块
    print("\n✂️  Step 2/4  智能分块…")
    chunks = split_documents(docs, file_path)

    # Step 2.5：Contextual RAG（可选）
    if use_context and chunks:
        print(f"\n🧠 Step 2.5  Contextual RAG 上下文增强"
              f"（并发={MAX_CONTEXT_CONCURRENCY}）…")
        chunks = await add_context(chunks, docs)

    # Step 3：嵌入
    print("\n🔢 Step 3/4  BGE-M3 嵌入…")
    doc_chunks = embed_chunks(
        chunks,
        course_id=course_id,
        document_id=document_id,
        tenant_id=tenant_id,
        version=version,
    )

    # Step 4：写入
    print("\n💾 Step 4/4  写入 Milvus…")
    write_to_milvus(doc_chunks)

    print(f"\n🎉 完成！共处理 {len(doc_chunks)} 个 chunk")
    print(f"   document_id = {document_id}")
    print(f"   ⚠️  更新此文档时请保留此 document_id")


if __name__ == '__main__':
    import asyncio
    FILE_PATH = r"F:\mygit\EduAgent\samples\sample2.md"
    COURSE_ID = "3e76aeed-5e01-4aa7-be8d-2055d12b9ea7"  # 替换为实际课程 UUID
    DOCUMENT_ID = None  # None = 自动生成；更新同一文档时填入上次输出的 ID
    TENANT_ID = "tenant_default"
    VERSION = "1.0"
    USE_CONTEXT = False  # 默认关闭，避免为每个 chunk 调用 LLM 产生较高成本

    doc_id = DOCUMENT_ID or str(uuid.uuid4())

    asyncio.run(build_pipeline(
        file_path=FILE_PATH,
        course_id=COURSE_ID,
        document_id=doc_id,
        tenant_id=TENANT_ID,
        version=VERSION,
        use_context=USE_CONTEXT,
    ))
