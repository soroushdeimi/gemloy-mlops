import importlib.util
from pathlib import Path

import httpx
import pytest
import respx

from app.main import app

SPEC = importlib.util.spec_from_file_location(
    "verify_model",
    Path(__file__).resolve().parents[1] / "deploy/charts/llamacpp/files/verify_model.py",
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def test_existing_model_size_is_accepted(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUFsample")
    VALIDATOR.verify_model(model, 10)
    assert model.read_bytes() == b"GGUFsample"


def test_missing_model_fails_clearly(tmp_path):
    with pytest.raises(ValueError, match="Model file missing"):
        VALIDATOR.verify_model(tmp_path / "missing.gguf", 10)


def test_wrong_model_size_fails_clearly(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUFsample")
    with pytest.raises(ValueError, match="expected 11 bytes, found 10"):
        VALIDATOR.verify_model(model, 11)


@respx.mock
def test_llamacpp_context_overflow_is_422():
    from fastapi.testclient import TestClient

    route = respx.post("http://model:8000/v1/chat/completions").mock(
        return_value=httpx.Response(
            400,
            json={
                "error": {
                    "code": 400,
                    "message": "request (131073 tokens) exceeds the available context size "
                    "(131072 tokens), try increasing it",
                    "type": "exceed_context_size_error",
                }
            },
        )
    )
    with TestClient(app) as client:
        response = client.post("/summarize", json={"text": "token-heavy prompt"})
    assert response.status_code == 422
    assert response.json() == {"detail": "input too long for model context"}
    assert route.call_count == 1


def test_gitops_activates_only_existing_gguf_engine():
    import yaml

    root = Path(__file__).resolve().parents[1]
    models = []
    for path in (root / "gitops/apps").glob("*.yaml"):
        application = yaml.safe_load(path.read_text())
        for source in application["spec"]["sources"]:
            if source.get("path") in {"deploy/charts/llamacpp", "deploy/charts/vllm"}:
                models.append(source["path"])
            assert source.get("chart") != "gpu-operator"
    assert models == ["deploy/charts/llamacpp"]
