# scripts/init_milvus.py
# 执行：python scripts/init_milvus.py
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymilvus import DataType, MilvusClient

from backend.config import get_settings

MILVUS_URI = f"http://{get_settings().milvus_host}:{get_settings().milvus_port}"
VECTOR_DIM = 1024
COLLECTION_NAME = "knowledge_domain"


def build_schema(client: MilvusClient):
    """构建 BGE-M3 Dense + BM25 Sparse 双路检索 Schema。"""
    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=VECTOR_DIM)
    # BM25 权重由应用侧计算，写入 Milvus sparse field。
    schema.add_field("sparse_embedding", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("content", DataType.VARCHAR, max_length=4096)
    schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
    schema.add_field("chunk_index", DataType.INT64)
    schema.add_field("document_id", DataType.VARCHAR, max_length=64)
    schema.add_field("course_id", DataType.VARCHAR, max_length=64)
    schema.add_field("source_name", DataType.VARCHAR, max_length=256)
    schema.add_field("chunk_type", DataType.VARCHAR, max_length=32)
    schema.add_field("version", DataType.VARCHAR, max_length=32)
    schema.add_field("updated_at", DataType.INT64)
    return schema


def build_index_params(client: MilvusClient):
    ip = client.prepare_index_params()
    ip.add_index(
        field_name="embedding",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 256},
    )
    # BM25 文档向量通过 Inner Product 得到 BM25 词法相关性。
    ip.add_index(
        field_name="sparse_embedding",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="IP",
        params={"drop_ratio_build": 0.0},
    )
    ip.add_index(field_name="tenant_id", index_type="INVERTED")
    ip.add_index(field_name="course_id", index_type="INVERTED")
    return ip


def main():
    print(f"连接 Milvus：{MILVUS_URI}")
    client = MilvusClient(uri=MILVUS_URI)

    if client.has_collection(COLLECTION_NAME):
        print(f"删除旧集合 '{COLLECTION_NAME}'...")
        client.drop_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=build_schema(client),
        index_params=build_index_params(client),
    )
    print(f"集合 '{COLLECTION_NAME}' 创建完成（BGE-M3 Dense + BM25 Sparse）")
    print("当前集合：", client.list_collections())
    print("集合已重建，原有知识库数据已清空。")


if __name__ == "__main__":
    main()
