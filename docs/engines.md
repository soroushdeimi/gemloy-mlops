# Select exactly one model engine

This is the only engine-switching procedure. The default active Application is `gitops/apps/model.yaml`: llama.cpp with the existing GGUF. `gitops/alternatives/vllm.yaml` is excluded from the root's nonrecursive `gitops/apps` source. Both use Service `model`, alias `gemma4-summary`, and port 8000; the app uses `http://model:8000`. Never install both charts into the same namespace. An exclusive GPU and the shared Service name make concurrent installation invalid.

To change engines in a future authorized environment:

1. Pause root and model auto-sync/self-heal. Stop app traffic and scale the current model Deployment to zero; wait for its pod to terminate and release the GPU. Preserve weight PVs/PVCs.
2. Replace the contents of `gitops/apps/model.yaml` with the desired Application. For vLLM use `gitops/alternatives/vllm.yaml`; for llama.cpp restore the repository's default model Application. Do not add an additional model child. Review the resource diff before allowing prune of the old engine's Deployment and ServiceMonitor.
3. Align app values in `gitops/values/summarizer.yaml`: llama.cpp uses `modelContextTokens: 131072` and `maxInputChars: 450000`; the retained vLLM alternative uses `modelContextTokens: 2048` and `maxInputChars: 5000`. The app endpoint and alias do not change. For manual Helm use the same app overrides.
4. vLLM cannot use the GGUF. It requires the separately pinned packed checkpoint/cache described in design-decisions.md. This test task authorizes no weight download; do not switch to an empty vLLM cache during this test. Its init downloader remains code for a separately authorized alternative deployment.
5. Sync/prune the model Application while app traffic stays stopped. Confirm only one model Deployment, one Service `model`, one active engine ServiceMonitor and one GPU allocation. Wait for health, check startup memory and run an authorized test completion before restoring app traffic and reconciliation.

Rollback uses the same stop-and-replace sequence and the retained cache of the desired engine. Argo does not provide transactional replacement across unrelated Applications. Never rely on two Deployments racing for the only GPU.

Infrastructure selection is separate from engine selection. The default WSL profile activates `gitops/apps/gpu-device-plugin.yaml`, with no GPU Operator. For a future native Ubuntu topology, replace that child with the retained `gitops/alternatives/gpu-operator.yaml`, remove the WSL monitoring overlay, and use gpu-node-join.md. Never run both device-plugin owners on the same node. The WSL tolerations on CPU infrastructure and app are test-profile exceptions to native GPU-node isolation.
