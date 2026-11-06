from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.models.base import ModelAdapter, ModelInfo

client = TestClient(main.app)


class Fake(ModelAdapter):
    def __init__(self, model_id, loaded=False):
        self.model_id, self.loaded, self.unloaded = model_id, loaded, 0

    def info(self):
        return ModelInfo(id=self.model_id, name=self.model_id, checkpoint=self.model_id, tasks=["caption"], modalities=["optical-rgb"], licence="x", loaded=self.loaded)

    def check_availability(self):
        return True, None

    def load(self):
        pass

    def unload(self):
        self.unloaded += 1
        self.loaded = False

    def caption(self, image_path, prompt=None, **kw):
        self.loaded = True
        return {"text": self.model_id, "model_id": self.model_id, "checkpoint": self.model_id, "revision": None, "device": "cpu", "dtype": None, "prompt": "p", "latency_ms": 1}


def setup(monkeypatch, tmp_path, *adapters):
    img = tmp_path / "c.png"
    Image.new("RGB", (64, 64)).save(img)
    monkeypatch.setattr(main, "safe_path", lambda p: img)
    table = {a.model_id: a for a in adapters}
    monkeypatch.setattr(main.registry, "get", lambda mid: table.get(mid))


def post(model_id):
    return client.post("/caption", json={"image_path": "x.png", "model_id": model_id})


def test_other_big_model_is_unloaded_first(monkeypatch, tmp_path):
    small, big = Fake("smolvlm-instruct", loaded=True), Fake("qwen2.5-vl")
    setup(monkeypatch, tmp_path, small, big)
    assert post("qwen2.5-vl").status_code == 200
    assert small.unloaded == 1 and big.loaded is True


def test_nothing_unloaded_when_the_other_is_not_loaded(monkeypatch, tmp_path):
    small, big = Fake("smolvlm-instruct"), Fake("qwen2.5-vl")
    setup(monkeypatch, tmp_path, small, big)
    post("qwen2.5-vl")
    assert small.unloaded == 0


def test_can_keep_both_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBIT_KEEP_MODELS_LOADED", "1")
    small, big = Fake("smolvlm-instruct", loaded=True), Fake("qwen2.5-vl")
    setup(monkeypatch, tmp_path, small, big)
    post("qwen2.5-vl")
    assert small.unloaded == 0
