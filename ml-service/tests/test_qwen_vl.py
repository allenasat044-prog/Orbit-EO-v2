import types

import numpy as np
import pytest
from PIL import Image

from app.errors import ModelUnavailable, UnsupportedTask
from app.models import qwen_vl
from app.models.qwen_vl import DEFAULT_PROMPT, MODEL_ID, QwenVLAdapter, approx_memory_gb, display_name


class FakeInputs(dict):
    def to(self, device):
        self.device = device
        return self


class FakeProcessor:
    def apply_chat_template(self, messages, add_generation_prompt):
        self.messages = messages
        return "<chat>"

    def __call__(self, text, images, return_tensors):
        self.call = (text, images)
        return FakeInputs(input_ids=np.zeros((1, 7), dtype=int))

    def batch_decode(self, ids, skip_special_tokens):
        return ["  Dense city blocks beside a river.  "]


class FakeModel:
    config = types.SimpleNamespace(_commit_hash="abc123")

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return np.arange(12).reshape(1, 12)


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "chip.png"
    Image.new("RGB", (128, 128), (60, 60, 60)).save(p)
    return str(p)


def make():
    proc, model = FakeProcessor(), FakeModel()
    return QwenVLAdapter(loader=lambda: (proc, model, "cpu", "float32")), proc, model


def test_caption_uses_default_prompt_and_returns_metadata(png):
    a, proc, model = make()
    r = a.caption(png)
    assert r["text"] == "Dense city blocks beside a river."
    assert r["model_id"] == MODEL_ID and r["device"] == "cpu" and r["prompt"] == DEFAULT_PROMPT
    assert proc.call[0] == ["<chat>"] and len(proc.call[1]) == 1
    assert model.kwargs["do_sample"] is False and model.kwargs["max_new_tokens"] == 220
    assert proc.messages[0]["content"][1]["text"] == DEFAULT_PROMPT


def test_rejects_tiny_images(tmp_path):
    p = tmp_path / "tiny.png"
    Image.new("RGB", (10, 10)).save(p)
    with pytest.raises(UnsupportedTask):
        make()[0].caption(str(p))


def test_loader_failure_becomes_model_unavailable(png):
    def boom():
        raise RuntimeError("out of memory")

    with pytest.raises(ModelUnavailable) as e:
        QwenVLAdapter(loader=boom).caption(png)
    assert "out of memory" in str(e.value)


def test_checkpoint_can_be_switched_by_env(monkeypatch):
    monkeypatch.setenv("QWEN_VL_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
    info = QwenVLAdapter(loader=lambda: None).info()
    assert info.checkpoint == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert info.name == "Qwen2.5-VL-Instruct (7B)"
    assert info.resources["approx_memory_gb"] == 16.5


def test_helpers():
    assert approx_memory_gb("Qwen/Qwen2.5-VL-3B-Instruct") == 8.0
    assert display_name("Qwen/Qwen2.5-VL-3B-Instruct") == "Qwen2.5-VL-Instruct (3B)"
    assert qwen_vl._transformers_too_old("4.46.1") is True
    assert qwen_vl._transformers_too_old("4.50.0") is False
