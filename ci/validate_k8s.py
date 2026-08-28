from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
K8S_DIR = ROOT / "infra" / "kubernetes"
SENSITIVE_ENV_MARKERS = (
    "SECRET",
    "PASSWORD",
    "DATABASE_URL",
    "REDIS_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
)
REQUIRED_DEPLOYMENTS = {
    "freelancing-api",
    "freelancing-socket",
    "freelancing-worker",
    "celery-beat",
    "celery-payments",
    "celery-reconciliation",
    "celery-notifications",
    "celery-search",
    "celery-files",
}
EXPECTED_QUEUES = {
    "freelancing-worker": "default",
    "celery-payments": "payments",
    "celery-reconciliation": "reconciliation",
    "celery-notifications": "notifications",
    "celery-search": "search_index",
    "celery-files": "files",
}


def _documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted(K8S_DIR.glob("*.yaml")):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if document is not None:
                if not isinstance(document, dict):
                    raise ValueError(f"{path} contains a non-mapping document")
                documents.append(document)
    if not documents:
        raise ValueError("no Kubernetes manifests found")
    return documents


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_deployment(document: dict[str, Any]) -> str:
    metadata = document.get("metadata", {})
    name = str(metadata.get("name", "<unknown>"))
    spec = document["spec"]["template"]["spec"]
    _require(
        spec.get("automountServiceAccountToken") is False,
        f"{name}: disable SA token mount",
    )
    _require(bool(spec.get("serviceAccountName")), f"{name}: serviceAccountName required")
    pod_security = spec.get("securityContext", {})
    _require(pod_security.get("runAsNonRoot") is True, f"{name}: runAsNonRoot required")
    _require(
        pod_security.get("seccompProfile", {}).get("type") == "RuntimeDefault",
        f"{name}: RuntimeDefault seccomp required",
    )
    containers = spec.get("containers", [])
    _require(bool(containers), f"{name}: containers required")
    for container in containers:
        cname = container.get("name", "<unknown>")
        security = container.get("securityContext", {})
        _require(
            security.get("allowPrivilegeEscalation") is False,
            f"{name}/{cname}: privilege escalation must be disabled",
        )
        _require(
            security.get("readOnlyRootFilesystem") is True,
            f"{name}/{cname}: root filesystem must be read-only",
        )
        _require(
            security.get("capabilities", {}).get("drop") == ["ALL"],
            f"{name}/{cname}: all Linux capabilities must be dropped",
        )
        resources = container.get("resources", {})
        _require(resources.get("requests"), f"{name}/{cname}: resource requests required")
        _require(resources.get("limits"), f"{name}/{cname}: resource limits required")
        for env in container.get("env", []):
            env_name = str(env.get("name", ""))
            if any(marker in env_name for marker in SENSITIVE_ENV_MARKERS):
                source = env.get("valueFrom", {}).get("secretKeyRef")
                _require(bool(source), f"{name}/{cname}: {env_name} must use secretKeyRef")
    if name in {"freelancing-api", "freelancing-socket"}:
        container = containers[0]
        for probe in ("livenessProbe", "readinessProbe", "startupProbe"):
            _require(probe in container, f"{name}: {probe} required")
    command = [str(item) for item in containers[0].get("command", [])]
    expected_queue = EXPECTED_QUEUES.get(name)
    if expected_queue is not None:
        _require(
            f"--queues={expected_queue}" in command,
            f"{name}: must consume only {expected_queue!r}",
        )
    if name == "celery-beat":
        _require("beat" in command, "celery-beat: must run the Celery beat scheduler")
        _require("worker" not in command, "celery-beat: must not consume worker queues")
        _require(
            "--schedule=/tmp/celerybeat-schedule" in command,
            "celery-beat: schedule database must use the writable /tmp mount",
        )
        _require(
            "--pidfile=/tmp/celerybeat.pid" in command,
            "celery-beat: pid file must use the writable /tmp mount",
        )
    return name


def main() -> None:
    documents = _documents()
    namespace_restricted = False
    service_accounts = 0
    network_policies = 0
    deployments: set[str] = set()
    for document in documents:
        kind = document.get("kind")
        if kind == "Namespace":
            labels = document.get("metadata", {}).get("labels", {})
            namespace_restricted = labels.get("pod-security.kubernetes.io/enforce") == "restricted"
        elif kind == "ServiceAccount":
            service_accounts += 1
            _require(
                document.get("automountServiceAccountToken") is False,
                "ServiceAccount token automount must be disabled",
            )
        elif kind == "Deployment":
            deployments.add(_validate_deployment(document))
        elif kind == "NetworkPolicy":
            network_policies += 1
            policy_types = set(document.get("spec", {}).get("policyTypes", []))
            _require(
                {"Ingress", "Egress"}.issubset(policy_types),
                "NetworkPolicy must declare both Ingress and Egress",
            )
    _require(namespace_restricted, "restricted Pod Security namespace label required")
    _require(service_accounts >= 3, "separate API, socket, and worker ServiceAccounts required")
    missing = sorted(REQUIRED_DEPLOYMENTS - deployments)
    _require(not missing, f"required workload deployments missing: {missing}")
    _require(network_policies >= 1, "at least one NetworkPolicy required")
    print(f"validated {len(documents)} Kubernetes resources")


if __name__ == "__main__":
    main()
