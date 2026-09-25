from __future__ import annotations

import sys
import types

import pytest


def test_bge_embedder_restores_xlm_roberta_patch(monkeypatch):
    from backend.core.knowledge_base import BGEMEmbedder
    from transformers.models.xlm_roberta import modeling_xlm_roberta as xlm

    original = xlm.XLMRobertaModel
    observed = {}

    class FakeBGEM3FlagModel:
        def __init__(self, *args, **kwargs):
            observed["patched_during_load"] = xlm.XLMRobertaModel is not original

    fake_flagembedding = types.ModuleType("FlagEmbedding")
    fake_flagembedding.BGEM3FlagModel = FakeBGEM3FlagModel
    monkeypatch.setitem(sys.modules, "FlagEmbedding", fake_flagembedding)

    BGEMEmbedder("fake-model-path")

    assert observed["patched_during_load"] is True
    assert xlm.XLMRobertaModel is original


def test_bge_embedder_restores_xlm_roberta_patch_on_error(monkeypatch):
    from backend.core.knowledge_base import BGEMEmbedder
    from transformers.models.xlm_roberta import modeling_xlm_roberta as xlm

    original = xlm.XLMRobertaModel

    class FailingBGEM3FlagModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("synthetic load failure")

    fake_flagembedding = types.ModuleType("FlagEmbedding")
    fake_flagembedding.BGEM3FlagModel = FailingBGEM3FlagModel
    monkeypatch.setitem(sys.modules, "FlagEmbedding", fake_flagembedding)

    with pytest.raises(RuntimeError, match="synthetic load failure"):
        BGEMEmbedder("fake-model-path")

    assert xlm.XLMRobertaModel is original


def test_reranker_disables_meta_loading_and_moves_model_eagerly(monkeypatch):
    import backend.core.reranker as reranker_module

    captured = {}

    class FakeParameter:
        is_meta = False

    class FakeModel:
        def named_parameters(self):
            return [("encoder.weight", FakeParameter())]

        def to(self, device):
            captured["moved_to"] = str(device)
            return self

    class FakeCrossEncoder:
        def __init__(self, model_id, device, max_length, automodel_args):
            captured["model_id"] = model_id
            captured["device"] = device
            captured["max_length"] = max_length
            captured["automodel_args"] = automodel_args
            self.model = FakeModel()

    monkeypatch.setattr(reranker_module, "CrossEncoder", FakeCrossEncoder)
    monkeypatch.setattr(reranker_module.torch.cuda, "is_available", lambda: False)

    instance = reranker_module.BGEReranker()

    assert instance is not None
    assert captured["device"] == "cpu"
    assert captured["max_length"] == 512
    assert captured["automodel_args"] == {"low_cpu_mem_usage": False}
    assert captured["moved_to"] == "cpu"


def test_reranker_rejects_unmaterialized_meta_parameters(monkeypatch):
    import backend.core.reranker as reranker_module

    class MetaParameter:
        is_meta = True

    class FakeModel:
        def named_parameters(self):
            return [("encoder.weight", MetaParameter())]

        def to(self, device):
            raise AssertionError("device move must not happen while meta parameters remain")

    class FakeCrossEncoder:
        def __init__(self, *args, **kwargs):
            self.model = FakeModel()

    monkeypatch.setattr(reranker_module, "CrossEncoder", FakeCrossEncoder)
    monkeypatch.setattr(reranker_module.torch.cuda, "is_available", lambda: False)

    with pytest.raises(RuntimeError, match="unmaterialized meta parameters"):
        reranker_module.BGEReranker()
