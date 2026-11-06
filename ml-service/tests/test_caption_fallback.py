import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.errors import ModelError, ModelUnavailable
from app.models.base import ModelAdapter, ModelInfo

client = TestClient(main.app)


class Fake(ModelAdapter):
    def __init__(self, model_id, text=None, error=None, available=True):
        self.model_id, self.text, self.error, self.available = model_id, text, error, available
        self.calls, self.unloaded = 0, False

    def info(self):
        return ModelInfo(id=self.model_id, name=self.model_id, checkpoint=self.model_id, tasks=["caption"], modalities=["optical-rgb"], licence="x")

    def check_availability(self):
        return (True, None) if self.available else (False, "not installed")

    def load(self):
        pass

    def unload(self):
        self.unloaded = True

    def caption(self, image_path, prompt=None, **kw):
        self.calls += 1
        if self.error:
            raise self.error
        return {"text": self.text, "model_id": self.model_id, "checkpoint": self.model_id, "revision": None, "device": "cpu", "dtype": None, "prompt": prompt or "p", "latency_ms": 1}


@pytest.fixture
def setup(monkeypatch, tmp_path):
    img = tmp_path / "c.png"
    Image.new("RGB", (64, 64)).save(img)
    monkeypatch.setattr(main, "safe_path", lambda p: img)
    monkeypatch.setenv("ORBIT_CAPTION_FALLBACK", "1")

    def install(*adapters):
        table = {a.model_id: a for a in adapters}
        monkeypatch.setattr(main.registry, "get", lambda mid: table.get(mid))

    return install


def post(model_id):
    return client.post("/caption", json={"image_path": "x.png", "model_id": model_id})


def test_falls_back_when_the_big_model_errors(setup):
    big = Fake("qwen2.5-vl", error=ModelError("out of memory"))
    small = Fake("smolvlm-instruct", text="Some fields.")
    setup(big, small)
    r = post("qwen2.5-vl")
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "Some fields." and body["model_id"] == "smolvlm-instruct"
    assert body["fallback_from"] == "qwen2.5-vl" and "out of memory" in body["fallback_reason"]
    assert big.unloaded is True


def test_falls_back_when_the_big_model_is_unavailable(setup):
    setup(Fake("qwen2.5-vl", available=False), Fake("smolvlm-instruct", text="Some fields."))
    r = post("qwen2.5-vl")
    assert r.status_code == 200 and r.json()["fallback_from"] == "qwen2.5-vl"


def test_no_loop_when_the_small_model_itself_fails(setup):
    small = Fake("smolvlm-instruct", error=ModelError("broken"))
    setup(small)
    r = post("smolvlm-instruct")
    assert r.status_code == 500 and small.calls == 1


def test_reports_original_error_when_fallback_also_fails(setup):
    setup(Fake("qwen2.5-vl", error=ModelError("out of memory")), Fake("smolvlm-instruct", error=ModelError("also broken")))
    r = post("qwen2.5-vl")
    assert r.status_code == 500 and "out of memory" in r.json()["error"]["message"]


def test_unknown_model_is_not_masked(setup):
    setup(Fake("smolvlm-instruct", text="x"))
    assert post("nope").status_code == 404


def test_can_be_switched_off(setup, monkeypatch):
    monkeypatch.setenv("ORBIT_CAPTION_FALLBACK", "0")
    setup(Fake("qwen2.5-vl", error=ModelError("out of memory")), Fake("smolvlm-instruct", text="x"))
    assert post("qwen2.5-vl").status_code == 500
