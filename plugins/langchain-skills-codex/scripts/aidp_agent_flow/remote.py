"""Signed data-plane reads and explicitly journaled credential creation."""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4

from .project import FlowError, canonical_hash, private_json, redact


def signer_for(config):
    import oci
    if config.get("security_token_file"):
        token = Path(config["security_token_file"]).expanduser().read_text(encoding="utf-8")
        key = oci.signer.load_private_key_from_file(config["key_file"], config.get("pass_phrase"))
        return oci.auth.signers.SecurityTokenSigner(token, key)
    return oci.signer.Signer.from_config(config)


class WorkbenchClient:
    def __init__(self, root, config):
        native = config.get("native", {})
        endpoint = native.get("endpoint", "").rstrip("/")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                or not parsed.hostname.endswith(".oci.oraclecloud.com")
                or not (parsed.hostname.endswith(".datalake.oci.oraclecloud.com")
                        or parsed.hostname.startswith(("datalake.", "aidp.")))):
            raise FlowError("Select an HTTPS Oracle data-plane endpoint without a path or credentials")
        platform = native.get("platform_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,500}", platform):
            raise FlowError("Select the target AIDP platform")
        self.base = endpoint + "/20260430/aiDataPlatforms/" + platform
        self.root, self.pending = Path(root), None
        auth = config.get("oci", {})
        path = Path(auth.get("config_file", ".oci/config")).expanduser()
        self.config_file = path if path.is_absolute() else self.root / path
        self.profile = auth.get("profile", "DEFAULT")
        self.session = None

    def prepare_operation(self, operation_key, public_identity):
        identity = canonical_hash({"target": self.base, "key": operation_key})
        path = self.root / ".aidp-local/operations" / (identity + ".json")
        if path.exists():
            raise FlowError("Prior credential creation needs reconciliation; no new request was submitted")
        record = {"identity": public_identity, "target_hash": canonical_hash(self.base),
                  "operation_key": operation_key, "retry_token": uuid4().hex, "state": "PREPARED"}
        private_json(path, record)
        self.pending = (path, record)
        return record["retry_token"]

    def complete_operation(self, operation_key, public_identity, credential_key):
        identity = canonical_hash({"target": self.base, "key": operation_key})
        path = self.root / ".aidp-local/operations" / (identity + ".json")
        if not path.exists():
            raise FlowError("Credential operation journal is missing; reconcile the created resource")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("identity") != public_identity:
            raise FlowError("Credential operation identity changed; reconciliation is required")
        record.update(state="RECONCILED", credential_key=credential_key)
        private_json(path, record, overwrite=True)
        self.pending = None

    def defer_operation(self, operation_key, public_identity, credential_key):
        identity = canonical_hash({"target": self.base, "key": operation_key})
        path = self.root / ".aidp-local/operations" / (identity + ".json")
        if not path.exists():
            raise FlowError("Credential operation journal is missing; reconcile the created resource")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("identity") != public_identity:
            raise FlowError("Credential operation identity changed; reconciliation is required")
        record.update(state="CREATED_PENDING_NATIVE_VERIFICATION", credential_key=credential_key)
        private_json(path, record, overwrite=True)
        self.pending = None

    def request(self, method, path, body=None, headers=None):
        parsed = urlsplit(path)
        if (method not in {"GET", "POST"} or not path.startswith("/") or path.startswith("//")
                or parsed.scheme or parsed.netloc or parsed.fragment or ".." in parsed.path.split("/") or "\\" in parsed.path):
            raise FlowError("Unsupported Workbench operation")
        if method == "POST" and (path != "/credentials" or not self.pending):
            raise FlowError("Only explicit journaled credential creation is implemented")
        if self.session is None:
            import oci
            import requests
            config = oci.config.from_file(str(self.config_file), self.profile)
            self.session = requests.Session()
            self.session.auth = signer_for(config)
        if method == "POST":
            ledger_path, record = self.pending
            record["state"] = "SUBMITTED"
            private_json(ledger_path, record, overwrite=True)
        try:
            response = self.session.request(method, self.base + path, json=body, headers=headers,
                                            timeout=(5, 60), allow_redirects=False)
            if not 200 <= response.status_code < 300:
                raise FlowError("Workbench request failed with HTTP " + str(response.status_code))
            result = response.json() if response.content else {}
            safe_headers = {key.lower(): value for key, value in response.headers.items()
                            if key.lower() in {"opc-next-page", "etag", "aidp-async-operation-key"}}
            return result, safe_headers
        except FlowError:
            raise
        except Exception:
            raise FlowError("Workbench transport failed; reconcile a submitted write before retrying") from None


def segment(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", value or ""):
        raise FlowError("Invalid native resource key")
    return value


def native_read(client, native, resource, *, session=None, trace=None):
    root = "/workspaces/" + segment(native.get("workspace_key")) + "/agents"
    if resource != "agents":
        root += "/" + segment(native.get("agent_key"))
    if resource == "deployments":
        root += "/deployments"
    elif resource == "session":
        root += "/sessions/" + segment(session)
        if trace:
            root += "/traces/" + segment(trace)
    data, headers = client.request("GET", root)
    fields = {"key", "displayName", "type", "lifecycleState", "deploymentType", "deploymentVersion"}
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return {"items": [{key: item[key] for key in fields if key in item} for item in data["items"]],
                "next_page": headers.get("opc-next-page"), "native_acceptance": False}
    result = {"metadata": {key: data[key] for key in fields if key in data}, "native_acceptance": False}
    if resource == "session":
        artifact = client.root / ".aidp-local/native" / (uuid4().hex + ".json")
        private_json(artifact, redact(data))
        result["artifact"] = str(artifact)
    return result
