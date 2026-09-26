import hashlib
import math
import os
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from pymilvus import AnnSearchRequest, MilvusClient, WeightedRanker

from backend.config import get_settings
from backend.core.logger import configure_logging, get_logger

backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
configure_logging()
logger = get_logger(__name__)

COLLECTION_NAME = "knowledge_domain"


class BGEMEmbedder:
    """BGE-M3 本地 Dense Embedding 单例。BM25 词法检索不再依赖 BGE lexical weights。"""

    _instance: Optional["BGEMEmbedder"] = None
    _instance_lock = threading.Lock()

    def __init__(self, model_path: str):
        import importlib.util as _ilu
        from transformers.utils import import_utils as _tf_iu

        if not hasattr(_tf_iu, "is_torch_fx_available"):
            _tf_iu.is_torch_fx_available = lambda: _ilu.find_spec("torch.fx") is not None

        from transformers.models.xlm_roberta import modeling_xlm_roberta as _xlm

        _OriginalXLMRoberta = _xlm.XLMRobertaModel

        class _PatchedXLMRobertaModel(_OriginalXLMRoberta):
            def __init__(self, config, **kwargs):
                kwargs.pop("dtype", None)
                super().__init__(config, **kwargs)

        # FlagEmbedding 1.4.x 与当前 transformers 组合需要兼容 dtype 参数，
        # 但这个 monkey patch 只能在 BGE-M3 构造期间临时生效。
        # Reranker 同样基于 XLM-R；如果长期保留全局替换，或与其并发加载，
        # 会污染另一个模型的初始化路径。
        try:
            _xlm.XLMRobertaModel = _PatchedXLMRobertaModel
            from FlagEmbedding import BGEM3FlagModel

            logger.info("bge_m3.loading", model_path=model_path)
            self._model = BGEM3FlagModel(model_name_or_path=model_path, use_fp16=False)
        finally:
            _xlm.XLMRobertaModel = _OriginalXLMRoberta

        self._encode_lock = threading.Lock()
        logger.info("bge_m3.loaded", use_fp16=False)

    @classmethod
    def get_instance(cls) -> "BGEMEmbedder":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    model_path = os.path.join(backend_path, get_settings().bge_m3_model_path)
                    cls._instance = cls(model_path)
        return cls._instance

    def encode(self, texts: list[str], batch_size: int = 12) -> list[list[float]]:
        # BGEM3FlagModel 被多个检索线程共享，串行化 encode 保证线程安全。
        with self._encode_lock:
            output = self._model.encode(
                texts,
                batch_size=batch_size,
                max_length=8192,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
        return output["dense_vecs"].tolist()

    def encode_query(self, text: str) -> list[float]:
        return self.encode([text], batch_size=1)[0]


class BM25SparseEncoder:
    """
    将 BM25 分数分解为 Milvus 可检索的 sparse vector。

    文档侧保存：idf(term) * BM25 TF saturation
    Query 侧保存：query term frequency
    两者做 Inner Product 即得到 BM25 风格词法相关性分数。

    中文使用 jieba 分词；token id 使用稳定哈希，因此查询时无需额外词表文件。
    """

    K1 = 1.5
    B = 0.75
    _VALID_TOKEN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_+#.\-]")

    @classmethod
    def tokenize(cls, text: str) -> list[str]:
        import jieba

        tokens = []
        for raw in jieba.lcut((text or "").lower(), cut_all=False):
            token = raw.strip()
            if token and cls._VALID_TOKEN.search(token):
                tokens.append(token)
        return tokens

    @staticmethod
    def _token_id(token: str) -> int:
        # Milvus sparse vector 使用整数维度；32-bit 稳定哈希足够当前课程知识库规模。
        value = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:4], "big")
        return value or 1

    @classmethod
    def encode_documents(cls, texts: list[str]) -> list[dict[int, float]]:
        tokenized = [cls.tokenize(text) for text in texts]
        n_docs = len(tokenized)
        if n_docs == 0:
            return []

        lengths = [len(tokens) for tokens in tokenized]
        avgdl = sum(lengths) / n_docs if n_docs else 1.0
        avgdl = max(avgdl, 1.0)

        df = Counter()
        for tokens in tokenized:
            df.update(set(tokens))

        idf = {
            token: math.log(1.0 + (n_docs - freq + 0.5) / (freq + 0.5))
            for token, freq in df.items()
        }

        vectors: list[dict[int, float]] = []
        for tokens, dl in zip(tokenized, lengths):
            tf = Counter(tokens)
            vector: dict[int, float] = {}
            norm = cls.K1 * (1.0 - cls.B + cls.B * dl / avgdl)
            for token, freq in tf.items():
                tf_weight = (freq * (cls.K1 + 1.0)) / (freq + norm)
                vector[cls._token_id(token)] = float(idf[token] * tf_weight)

            # Milvus 2.4 sparse field 不接受完全空的向量。
            if not vector:
                vector[cls._token_id("__empty__")] = 1e-9
            vectors.append(vector)
        return vectors

    @classmethod
    def encode_query(cls, text: str) -> dict[int, float]:
        tf = Counter(cls.tokenize(text))
        vector = {cls._token_id(token): float(freq) for token, freq in tf.items()}
        if not vector:
            vector[cls._token_id("__empty__")] = 1e-9
        return vector


@dataclass
class DocumentChunk:
    id: str
    content: str
    embedding: list[float]
    sparse_embedding: dict[int, float]
    course_id: str
    document_id: str
    source_name: str
    chunk_type: str
    chunk_index: int
    version: str
    tenant_id: str = "tenant_default"
    document_type: str = ""
    relative_path: str = ""
    chapter: str = ""
    section: str = ""
    updated_at: int = field(default_factory=lambda: int(time.time()))


def generate_chunk_id(content: str, document_id: str, chunk_index: int) -> str:
    raw = f"{document_id}_{chunk_index}_{content[:50]}"
    return hashlib.md5(raw.encode()).hexdigest()


class KnowledgeBaseClient:
    """Milvus 2.4 知识库客户端：BGE-M3 Dense + BM25 Sparse Hybrid Retrieval。"""

    _client: Optional[MilvusClient] = None
    _loaded: bool = False
    ANN_EF = 64
    VECTOR_TOP_K = 10

    def __init__(self):
        if KnowledgeBaseClient._client is None:
            settings = get_settings()
            uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
            KnowledgeBaseClient._client = MilvusClient(uri=uri)
            logger.info("milvus.connected", uri=uri)

        if not KnowledgeBaseClient._loaded:
            try:
                KnowledgeBaseClient._client.load_collection(COLLECTION_NAME)
            except Exception:
                pass
            KnowledgeBaseClient._loaded = True

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0
        data = [
            {
                "id": c.id,
                "embedding": c.embedding,
                "sparse_embedding": c.sparse_embedding,
                "content": c.content[:4096],
                "chunk_index": c.chunk_index,
                "document_id": c.document_id,
                "course_id": c.course_id,
                "tenant_id": c.tenant_id,
                "source_name": c.source_name,
                "chunk_type": c.chunk_type,
                "version": c.version,
                "document_type": c.document_type,
                "relative_path": c.relative_path,
                "chapter": c.chapter,
                "section": c.section,
                "updated_at": c.updated_at,
            }
            for c in chunks
        ]
        self._client.upsert(collection_name=COLLECTION_NAME, data=data)
        logger.info("knowledge_base.chunks_upserted", count=len(chunks))
        return len(chunks)

    def list_chunks(
        self,
        exclude_document_id: Optional[str] = None,
        exclude_course_id: Optional[str] = None,
    ) -> list[DocumentChunk]:
        """读取当前语料，用于新增文档时重新计算全库 BM25 IDF。"""
        filter_parts: list[str] = []
        if exclude_document_id:
            safe_id = exclude_document_id.replace('"', '\\"')
            filter_parts.append(f'document_id != "{safe_id}"')
        if exclude_course_id:
            safe_course = exclude_course_id.replace('"', '\\"')
            filter_parts.append(f'course_id != "{safe_course}"')
        filter_expr = " and ".join(filter_parts)

        rows = self._client.query(
            collection_name=COLLECTION_NAME,
            filter=filter_expr,
            output_fields=[
                "id", "embedding", "sparse_embedding", "content", "chunk_index",
                "document_id", "course_id", "tenant_id", "source_name",
                "chunk_type", "version", "document_type", "relative_path",
                "chapter", "section", "updated_at",
            ],
            limit=16384,
        )
        return [
            DocumentChunk(
                id=row["id"],
                content=row.get("content", ""),
                embedding=row.get("embedding", []),
                sparse_embedding=row.get("sparse_embedding", {}) or {},
                course_id=row.get("course_id", ""),
                document_id=row.get("document_id", ""),
                source_name=row.get("source_name", ""),
                chunk_type=row.get("chunk_type", "text"),
                chunk_index=row.get("chunk_index", 0),
                version=row.get("version", "1.0"),
                tenant_id=row.get("tenant_id", "tenant_default"),
                document_type=row.get("document_type", "") or "",
                relative_path=row.get("relative_path", "") or "",
                chapter=row.get("chapter", "") or "",
                section=row.get("section", "") or "",
                updated_at=row.get("updated_at", int(time.time())),
            )
            for row in rows
        ]

    def upsert_with_bm25_rebuild(self, new_chunks: list[DocumentChunk]) -> int:
        """
        新增/更新文档时，基于“已有语料 + 新文档”重新计算 BM25 IDF，
        然后统一 upsert，保证不同批次导入的 BM25 权重处于同一统计空间。
        """
        if not new_chunks:
            return 0

        document_id = new_chunks[0].document_id
        existing = self.list_chunks(exclude_document_id=document_id)
        corpus = existing + new_chunks
        sparse_vectors = BM25SparseEncoder.encode_documents([c.content for c in corpus])
        for chunk, sparse in zip(corpus, sparse_vectors):
            chunk.sparse_embedding = sparse

        # 更新同一 document_id 时，新旧 chunk 数量和内容都可能变化。
        # 先删旧文档，避免旧 chunk id 未被新 upsert 覆盖而残留在集合中。
        self.delete_document_chunks(document_id)
        self.upsert_chunks(corpus)
        logger.info(
            "knowledge_base.bm25_rebuilt",
            corpus_chunks=len(corpus),
            new_chunks=len(new_chunks),
        )
        return len(new_chunks)

    def delete_document_chunks(self, document_id: str) -> None:
        safe_id = document_id.replace('"', '\\"')
        self._client.delete(
            collection_name=COLLECTION_NAME,
            filter=f'document_id == "{safe_id}"',
        )
        logger.info("knowledge_base.document_deleted", document_id=document_id)

    def delete_document_and_rebuild(self, document_id: str) -> None:
        """删除一个文档，并为剩余语料重新计算 BM25 IDF。"""
        remaining = self.list_chunks(exclude_document_id=document_id)
        self.delete_document_chunks(document_id)
        if not remaining:
            return

        sparse_vectors = BM25SparseEncoder.encode_documents(
            [chunk.content for chunk in remaining]
        )
        for chunk, sparse in zip(remaining, sparse_vectors):
            chunk.sparse_embedding = sparse
        self.upsert_chunks(remaining)
        logger.info(
            "knowledge_base.bm25_rebuilt_after_delete",
            remaining_chunks=len(remaining),
        )

    def delete_course_chunks(self, course_id: str, tenant_id: str) -> None:
        """删除指定租户课程的全部 Chunk。"""
        safe_course = course_id.replace('"', '\\"')
        safe_tenant = tenant_id.replace('"', '\\"')
        self._client.delete(
            collection_name=COLLECTION_NAME,
            filter=(
                f'course_id == "{safe_course}" '
                f'and tenant_id == "{safe_tenant}"'
            ),
        )
        logger.info(
            "knowledge_base.course_deleted",
            course_id=course_id,
            tenant_id=tenant_id,
        )

    def delete_course_and_rebuild(self, course_id: str, tenant_id: str) -> None:
        """
        删除一个课程的全部 Chunk，并只对剩余语料重建一次 BM25。

        相比逐文档调用 delete_document_and_rebuild，可避免一个课程 N 个文档
        触发 N 次全库重建。
        """
        remaining = self.list_chunks(exclude_course_id=course_id)
        self.delete_course_chunks(course_id, tenant_id)
        if not remaining:
            return

        sparse_vectors = BM25SparseEncoder.encode_documents(
            [chunk.content for chunk in remaining]
        )
        for chunk, sparse in zip(remaining, sparse_vectors):
            chunk.sparse_embedding = sparse
        self.upsert_chunks(remaining)
        logger.info(
            "knowledge_base.bm25_rebuilt_after_course_delete",
            course_id=course_id,
            remaining_chunks=len(remaining),
        )

    @staticmethod
    def generate_chunk_id(content: str, document_id: str, chunk_index: int) -> str:
        return generate_chunk_id(content, document_id, chunk_index)

    def _hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int,
        filters: Optional[str] = None,
    ) -> list[dict]:
        """BGE-M3 Dense + BM25 Sparse 两路召回，再以 0.7 / 0.3 权重融合。"""
        try:
            dense_req = AnnSearchRequest(
                data=[query_embedding],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"ef": self.ANN_EF}},
                limit=top_k,
                expr=filters,
            )

            bm25_req = AnnSearchRequest(
                data=[BM25SparseEncoder.encode_query(query_text)],
                anns_field="sparse_embedding",
                param={"metric_type": "IP"},
                limit=top_k,
                expr=filters,
            )

            results = self._client.hybrid_search(
                collection_name=COLLECTION_NAME,
                reqs=[dense_req, bm25_req],
                ranker=WeightedRanker(0.7, 0.3),
                limit=top_k,
                output_fields=[
                    "content", "source_name", "chunk_type",
                    "course_id", "document_id", "chunk_index",
                    "document_type", "relative_path", "chapter", "section",
                ],
            )

            candidates = []
            for hit in results[0]:
                entity = hit.get("entity", {})
                candidates.append(
                    {
                        "content": entity.get("content") or "",
                        "score": hit.get("distance") or 0.0,
                        "metadata": {
                            "source_name": entity.get("source_name") or "",
                            "chunk_type": entity.get("chunk_type") or "text",
                            "course_id": entity.get("course_id") or "",
                            "document_id": entity.get("document_id") or "",
                            "chunk_index": entity.get("chunk_index") or 0,
                            "document_type": entity.get("document_type") or "",
                            "relative_path": entity.get("relative_path") or "",
                            "chapter": entity.get("chapter") or "",
                            "section": entity.get("section") or "",
                        },
                    }
                )

            logger.info(
                "knowledge_base.hybrid_search_done",
                candidates=len(candidates),
                dense_weight=0.7,
                bm25_weight=0.3,
            )
            return candidates
        except Exception as exc:
            logger.error("knowledge_base.hybrid_search_failed", error=str(exc))
            return []

    @staticmethod
    def _build_filter(
        tenant_id: str,
        course_id: Optional[str] = None,
        *,
        metadata_scope: Optional[dict] = None,
    ) -> str:
        """
        构造 Milvus metadata filter。

        tenant_id 永远是硬边界；metadata_scope 可继续收窄 course/document/chapter
        等范围。调用方传入的 course_id 保留兼容，scope 中同名字段优先。
        """
        scope = dict(metadata_scope or {})
        safe_tenant = tenant_id.replace('"', '\\"')
        expr = f'tenant_id == "{safe_tenant}"'

        resolved_course = scope.get("course_id") or course_id
        if resolved_course:
            safe_course = str(resolved_course).replace('"', '\\"')
            expr += f' and course_id == "{safe_course}"'

        for field_name in (
            "document_id",
            "document_type",
            "chapter",
            "section",
            "chunk_type",
        ):
            value = scope.get(field_name)
            if value in (None, ""):
                continue
            safe_value = str(value).replace('"', '\\"')
            expr += f' and {field_name} == "{safe_value}"'
        return expr


if __name__ == "__main__":
    query = "商品聚合多模态大模型项目主要讲的是什么内容"
    embedder = BGEMEmbedder.get_instance()
    kb = KnowledgeBaseClient()
    results = kb._hybrid_search(
        query_text=query,
        query_embedding=embedder.encode_query(query),
        top_k=5,
    )
    print(results[:1])
