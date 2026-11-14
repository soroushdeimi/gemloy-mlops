SHELL := /bin/bash
BIN := $(CURDIR)/.tools/bin
VENV := $(CURDIR)/.tools/venv/bin
.PHONY: tools test lint-k8s lint-rules lint-dashboards

tools:
	/bin/bash scripts/install-tools.sh

test:
	"$(VENV)/ruff" check app tests scripts/check_rules.py loadtest deploy/charts/llamacpp/files/verify_model.py
	"$(VENV)/pytest" -q

lint-k8s:
	"$(BIN)/helm" lint deploy/charts/summarizer
	"$(BIN)/helm" lint deploy/charts/llamacpp
	"$(BIN)/helm" lint deploy/charts/vllm
	set -o pipefail; "$(BIN)/helm" template summarizer deploy/charts/summarizer | "$(BIN)/kubeconform" -strict -ignore-missing-schemas -summary
	set -o pipefail; "$(BIN)/helm" template llamacpp deploy/charts/llamacpp | "$(BIN)/kubeconform" -strict -ignore-missing-schemas -summary
	set -o pipefail; "$(BIN)/helm" template vllm deploy/charts/vllm | "$(BIN)/kubeconform" -strict -ignore-missing-schemas -summary
	set -o pipefail; "$(BIN)/helm" template summarizer deploy/charts/summarizer --set hpa.enabled=true --set serviceMonitor.enabled=false --set prometheusRule.enabled=false --set dashboard.enabled=false | "$(BIN)/kubeconform" -strict -ignore-missing-schemas -summary
	set -o pipefail; "$(BIN)/kustomize" build deploy/manifests/app | "$(BIN)/kubeconform" -strict -ignore-missing-schemas -summary
	set -o pipefail; "$(BIN)/kustomize" build monitoring | "$(BIN)/kubeconform" -strict -ignore-missing-schemas -summary
	"$(BIN)/kubeconform" -strict -ignore-missing-schemas -summary deploy/manifests/gpu/verify.yaml gitops/root.yaml gitops/apps/*.yaml gitops/alternatives/*.yaml

lint-rules:
	PATH="$(BIN):$(VENV):$$PATH" "$(VENV)/python" scripts/check_rules.py

lint-dashboards:
	@set -e; for file in $$(find monitoring deploy/charts -name '*.json'); do "$(VENV)/python" -m json.tool $$file /dev/null; echo "Valid JSON: $$file"; done
