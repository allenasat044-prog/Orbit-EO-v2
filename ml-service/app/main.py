from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import ModelError, ModelUnavailable, UnsupportedTask
from app.models.defaults import DEFAULT_CAPTION_MODEL, DEFAULT_MATCH_MODEL, register_defaults
from app.models.registry import registry
from app.change import ChangeError, analyze_change
from app.raster import RasterError, extract_chip, extract_label_chip, raster_support, safe_path

VERSION = "0.1.0"

app = FastAPI(title="Orbit ML Service", version=VERSION)
register_defaults(registry)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail)}})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Invalid request", "details": exc.errors()}})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "orbit-ml",
        "version": VERSION,
        "python": platform.python_version(),
        "torch_installed": importlib.util.find_spec("torch") is not None,
        "models_registered": len(registry),
        "raster": raster_support(),
    }


@app.get("/models")
def list_models():
    return {"items": registry.list()}


@app.get("/models/{model_id}")
def get_model(model_id: str):
    adapter = registry.get(model_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")
    return next(m for m in registry.list() if m["id"] == model_id)


class ChipRequest(BaseModel):
    path: str
    out_path: str
    display_out_path: str | None = None
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    size_px: int = Field(default=512, ge=64, le=2048)


@app.exception_handler(RasterError)
async def raster_error(_: Request, exc: RasterError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


@app.post("/raster/chip")
def raster_chip(req: ChipRequest):
    display = safe_path(req.display_out_path) if req.display_out_path else None
    return extract_chip(safe_path(req.path), safe_path(req.out_path), req.lon, req.lat, req.size_px, display)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(ModelUnavailable)
async def model_unavailable(_: Request, exc: ModelUnavailable):
    return _err(503, "model_unavailable", str(exc))


@app.exception_handler(UnsupportedTask)
async def unsupported_task(_: Request, exc: UnsupportedTask):
    return _err(422, "unsupported_input", str(exc))


@app.exception_handler(ModelError)
async def model_error(_: Request, exc: ModelError):
    return _err(500, "model_error", str(exc))


def _resolve(model_id: str, task: str):
    adapter = registry.get(model_id)
    if adapter is None:
        return None, _err(404, "unknown_model", f"Unknown model: {model_id}")
    if task not in adapter.info().tasks:
        return None, _err(422, "unsupported_task", f"{model_id} does not support {task}.")
    ok, reason = adapter.check_availability()
    if not ok:
        return None, _err(503, "model_unavailable", reason or "Model is not available.")
    return adapter, None


class CaptionRequest(BaseModel):
    image_path: str
    model_id: str | None = None
    prompt: str | None = Field(default=None, max_length=1000)


FALLBACK_CAPTION_MODEL = "smolvlm-instruct"


def _free_memory() -> None:
    import gc

    gc.collect()
    try:
        import torch

        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            torch.mps.empty_cache()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


HEAVY_CAPTION_MODELS = ("smolvlm-instruct", "qwen2.5-vl")


def _make_room(requested: str) -> None:
    """Keep only one big caption model in memory at a time, so a 16 GB Mac does not run out."""
    if os.environ.get("ORBIT_KEEP_MODELS_LOADED", "0").strip().lower() in ("1", "true", "on", "yes"):
        return
    if requested not in HEAVY_CAPTION_MODELS:
        return
    freed = False
    for model_id in HEAVY_CAPTION_MODELS:
        if model_id == requested:
            continue
        other = registry.get(model_id)
        if other is not None and other.info().loaded:
            other.unload()
            freed = True
    if freed:
        _free_memory()


def _fallback_enabled() -> bool:
    return os.environ.get("ORBIT_CAPTION_FALLBACK", "1").strip().lower() not in ("0", "false", "off", "no")


@app.post("/caption")
def caption(req: CaptionRequest):
    requested = req.model_id or DEFAULT_CAPTION_MODEL
    adapter, error = _resolve(requested, "caption")
    can_fall_back = _fallback_enabled() and requested != FALLBACK_CAPTION_MODEL
    if error is not None and (error.status_code != 503 or not can_fall_back):
        return error
    path = safe_path(req.image_path)
    if not path.exists():
        return _err(404, "image_not_found", "Image file does not exist.")

    if error is None:
        _make_room(requested)
        try:
            return adapter.caption(str(path), prompt=req.prompt)
        except (ModelUnavailable, ModelError) as err:
            if not can_fall_back:
                raise
            failure = str(err)
            adapter.unload()
            _free_memory()
    else:
        failure = json.loads(error.body)["error"]["message"]

    fallback, fallback_error = _resolve(FALLBACK_CAPTION_MODEL, "caption")
    if fallback_error is not None:
        return error if error is not None else _err(500, "model_error", failure)
    _make_room(FALLBACK_CAPTION_MODEL)
    print(f"[orbit] {requested} could not caption this image ({failure}). Using {FALLBACK_CAPTION_MODEL} instead.", file=sys.stderr)
    try:
        result = fallback.caption(str(path), prompt=req.prompt)
    except (ModelUnavailable, ModelError):
        return error if error is not None else _err(500, "model_error", failure)
    result["fallback_from"] = requested
    result["fallback_reason"] = failure
    return result


class ClassifyRequest(BaseModel):
    image_path: str
    model_id: str = DEFAULT_MATCH_MODEL
    labels: list[str] | None = Field(default=None, min_length=2, max_length=50)
    top_k: int = Field(default=5, ge=1, le=20)


@app.post("/classify")
def classify(req: ClassifyRequest):
    adapter, error = _resolve(req.model_id, "classify")
    if error:
        return error
    if req.labels and any(not (1 <= len(x.strip()) <= 80) for x in req.labels):
        return _err(422, "invalid_labels", "Each label must be 1 to 80 characters.")
    path = safe_path(req.image_path)
    if not path.exists():
        return _err(404, "image_not_found", "Image file does not exist.")
    return adapter.classify(str(path), labels=[x.strip() for x in req.labels] if req.labels else None, top_k=req.top_k)


class ScoreRequest(BaseModel):
    image_path: str
    texts: list[str] = Field(min_length=1, max_length=20)
    model_id: str = DEFAULT_MATCH_MODEL


@app.post("/score")
def score(req: ScoreRequest):
    adapter, error = _resolve(req.model_id, "score")
    if error:
        return error
    if any(not (1 <= len(x.strip()) <= 1000) for x in req.texts):
        return _err(422, "invalid_texts", "Each text must be 1 to 1000 characters.")
    path = safe_path(req.image_path)
    if not path.exists():
        return _err(404, "image_not_found", "Image file does not exist.")
    return adapter.score(str(path), [x.strip() for x in req.texts])


class LabelChipRequest(BaseModel):
    path: str
    out_path: str
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    size_px: int = Field(default=512, ge=64, le=2048)
    pixel_m: float = Field(default=10.0, gt=0, le=1000)


@app.post("/raster/label-chip")
def raster_label_chip(req: LabelChipRequest):
    return extract_label_chip(safe_path(req.path), safe_path(req.out_path), req.lon, req.lat, req.size_px, req.pixel_m)


class ChangeRequest(BaseModel):
    before_path: str
    after_path: str
    overlay_out_path: str
    before_scl_path: str | None = None
    after_scl_path: str | None = None
    pixel_m: float = Field(default=10.0, gt=0, le=1000)


@app.exception_handler(ChangeError)
async def change_error(_: Request, exc: ChangeError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


@app.post("/change/analyze")
def change_analyze(req: ChangeRequest):
    if (req.before_scl_path is None) != (req.after_scl_path is None):
        return _err(422, "invalid_request", "Give both class maps or neither.")
    return analyze_change(
        safe_path(req.before_path), safe_path(req.after_path), safe_path(req.overlay_out_path),
        safe_path(req.before_scl_path) if req.before_scl_path else None,
        safe_path(req.after_scl_path) if req.after_scl_path else None,
        req.pixel_m,
    )
