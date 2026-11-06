from __future__ import annotations

import contextlib
import importlib.util
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.errors import ModelError, ModelUnavailable, UnsupportedTask
from app.models.base import ModelAdapter, ModelInfo
from app.models.smolvlm import dtype_kwarg, pick_device, pick_dtype

MODEL_ID = "qwen2.5-vl"
DEFAULT_CHECKPOINT = "Qwen/Qwen2.5-VL-3B-Instruct"
MIN_SIDE_PX = 32
MIN_PIXELS = 448 * 448
MAX_PIXELS = 768 * 768
MIN_TRANSFORMERS = (4, 49)

DEFAULT_PROMPT = (
    "This is a Sentinel-2 true-colour satellite image at about 10 metres per pixel, with north at the top. "
    "Describe what is visible in 3 or 4 sentences: land cover, vegetation, water, roads, how dense and how regular "
    "the built-up areas are, and any clear patterns such as field boundaries, river courses or street grids. "
    "Focus on the centre of the image. Do not name places, count small objects or guess dates. "
    "If something is unclear at this resolution, say so instead of guessing."
)


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                found = line.split("=", 1)[1].strip().strip('"').strip("'")
                if found:
                    return found
    return None


def checkpoint() -> str:
    return _env_value("QWEN_VL_MODEL") or DEFAULT_CHECKPOINT


def approx_memory_gb(ckpt: str) -> float:
    low = ckpt.lower()
    for tag, gb in (("72b", 150.0), ("32b", 66.0), ("7b", 16.5), ("3b", 8.0)):
        if tag in low:
            return gb
    return 8.0


def display_name(ckpt: str) -> str:
    for part in ckpt.split("-"):
        if part.upper().endswith("B") and part[:-1].replace(".", "").isdigit():
            return f"Qwen2.5-VL-Instruct ({part.upper()})"
    return f"Qwen2.5-VL ({ckpt})"


def _transformers_too_old(version: str) -> bool:
    parts = version.split(".")
    try:
        return (int(parts[0]), int(parts[1])) < MIN_TRANSFORMERS
    except (ValueError, IndexError):
        return False


class QwenVLAdapter(ModelAdapter):
    def __init__(self, loader: Callable[[], tuple] | None = None, max_new_tokens: int = 220) -> None:
        self._custom_loader = loader
        self._loader = loader or self._default_loader
        self._max_new_tokens = max_new_tokens
        self._lock = threading.RLock()
        self._bundle: tuple | None = None

    def info(self) -> ModelInfo:
        ckpt = checkpoint()
        device = self._bundle[2] if self._bundle else None
        return ModelInfo(
            id=MODEL_ID,
            name=display_name(ckpt),
            checkpoint=ckpt,
            tasks=["caption", "vqa"],
            modalities=["optical-rgb"],
            licence="See the model card on Hugging Face for this checkpoint.",
            loaded=self._bundle is not None,
            resources={
                "approx_memory_gb": approx_memory_gb(ckpt),
                "device": device,
                "note": "Much larger general-purpose vision-language model than SmolVLM; not trained specifically on remote-sensing imagery. Runs locally.",
            },
        )

    def check_availability(self) -> tuple[bool, str | None]:
        if self._custom_loader is not None:
            return True, None
        missing = [m for m in ("torch", "transformers", "PIL") if importlib.util.find_spec(m) is None]
        if missing:
            return False, f"Missing Python packages: {', '.join(missing)}. Run: pip install -r requirements-ml.txt"
        import transformers

        if _transformers_too_old(transformers.__version__):
            return False, f"Qwen2.5-VL needs transformers 4.49 or newer (found {transformers.__version__}). Run: pip install -U transformers"
        return True, None

    def _default_loader(self) -> tuple:
        import torch
        import transformers
        from transformers import AutoProcessor

        ckpt = checkpoint()
        device = pick_device(torch)
        dtype = pick_dtype(torch, device)
        model_cls = getattr(transformers, "Qwen2_5_VLForConditionalGeneration", None)
        if model_cls is None:
            raise ModelUnavailable("This version of transformers has no Qwen2.5-VL support. Run: pip install -U transformers")
        processor = AutoProcessor.from_pretrained(ckpt, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS, use_fast=False)
        model = model_cls.from_pretrained(ckpt, **{dtype_kwarg(transformers.__version__): dtype}).to(device)
        model.eval()
        return processor, model, device, str(dtype).replace("torch.", "")

    def load(self) -> None:
        with self._lock:
            if self._bundle is not None:
                return
            ok, reason = self.check_availability()
            if not ok:
                raise ModelUnavailable(reason)
            try:
                self._bundle = self._loader()
            except Exception as err:
                raise ModelUnavailable(f"Could not load {checkpoint()}: {err}") from err

    def unload(self) -> None:
        with self._lock:
            self._bundle = None

    def validate_input(self, image_path: str) -> None:
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(image_path) as im:
                if min(im.size) < MIN_SIDE_PX:
                    raise UnsupportedTask(f"Image is too small ({im.size[0]}x{im.size[1]} px); at least {MIN_SIDE_PX} px per side is needed.")
        except (UnidentifiedImageError, OSError) as err:
            raise UnsupportedTask(f"Not a readable image: {err}") from err

    def caption(self, image_path: str, prompt: str | None = None, **kwargs: Any) -> dict[str, Any]:
        from PIL import Image

        self.validate_input(image_path)
        self.load()
        processor, model, device, dtype = self._bundle  # type: ignore[misc]
        text = prompt or DEFAULT_PROMPT
        with Image.open(image_path) as im:
            image = im.convert("RGB")

        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": text}]}]
        chat = processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = processor(text=[chat], images=[image], return_tensors="pt").to(device)

        try:
            import torch

            mode = torch.inference_mode()
        except ImportError:
            mode = contextlib.nullcontext()

        with self._lock:
            started = time.perf_counter()
            try:
                with mode:
                    ids = model.generate(**inputs, max_new_tokens=self._max_new_tokens, do_sample=False)
            except Exception as err:
                raise ModelError(f"Generation failed: {err}") from err
            latency_ms = int((time.perf_counter() - started) * 1000)

        new_tokens = ids[:, inputs["input_ids"].shape[1]:]
        out = processor.batch_decode(new_tokens, skip_special_tokens=True)[0].strip()
        if not out:
            raise ModelError("The model produced no text.")
        return {
            "text": out,
            "model_id": MODEL_ID,
            "checkpoint": checkpoint(),
            "revision": getattr(getattr(model, "config", None), "_commit_hash", None),
            "device": device,
            "dtype": dtype,
            "prompt": text,
            "latency_ms": latency_ms,
        }
