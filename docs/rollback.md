# Rollback

## GitOps default: revert desired state

Revert the image-bump commit (or the offending chart/config commit) in the repository and allow Argo to reconcile. Example operator workflow:

```sh
git revert BAD_COMMIT
# Review and publish the revert using the repository's approved process.
argocd app sync summarizer
argocd app wait summarizer --health
```

These commands were not executed during implementation. Validate the intended image SHA and probes after rollback. A Git revert is durable because it changes desired state. For a model revision rollback, sync the desired revision; its separate cached directory is reused if complete. Preserve the PVC and ensure space for both revisions. If a cache is corrupt, stop serving before deleting only that revision directory and marker.

## Argo history rollback

For urgent recovery, disable automated sync and self-heal on the affected child and temporarily suspend parent reconciliation of that child's policy. Parent-owned Applications otherwise restore automation. Use:

```sh
argocd app history summarizer
argocd app rollback summarizer HISTORY_ID
argocd app wait summarizer --health
```

Choose a known healthy history entry; Argo cannot perform history rollback while automated sync remains enabled. Follow with a Git revert or desired-state correction before restoring parent/child automation. Argo renders Helm charts but does not maintain native Helm release history for them.

## Native Helm releases

For installations made with Helm rather than Argo:

```sh
helm history summarizer -n platform
helm rollback summarizer REVISION -n platform --wait
helm history vllm -n platform
helm rollback vllm REVISION -n platform --wait --timeout 35m
```

The timeout follows the proposed startup budget in reproduce.md. Recreate means model rollback has downtime. Preserve weights and review cache revision compatibility separately. Helm rollback does not reverse CRD schema upgrades or restore local disks. For plain manifests, apply the earlier reviewed kustomize revision and wait for rollout. Do not mix native Helm rollback with Argo-managed resources.
