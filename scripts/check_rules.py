"""Validate all rendered alert rules without contacting a cluster."""

import pathlib
import subprocess
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
streams = [p.read_text() for p in (ROOT / "monitoring").glob("*.yaml")]
streams += [
    subprocess.check_output(
        ["helm", "template", name, str(ROOT / "deploy/charts" / name)], text=True
    )
    for name in ["summarizer", "vllm", "llamacpp"]
]
streams += [
    subprocess.check_output(["kustomize", "build", str(ROOT / "deploy/manifests/app")], text=True)
]
count = 0
with tempfile.TemporaryDirectory(dir=ROOT / ".tools") as tmp:
    for stream in streams:
        for obj in yaml.safe_load_all(stream):
            if obj and obj.get("kind") == "PrometheusRule":
                count += 1
                path = pathlib.Path(tmp) / f"rules-{count}.yaml"
                path.write_text(yaml.safe_dump(obj["spec"]))
                subprocess.run(["promtool", "check", "rules", str(path)], check=True)
assert count >= 4, "Expected platform, chart and plain app rules"
print(f"Validated {count} rule resources")
