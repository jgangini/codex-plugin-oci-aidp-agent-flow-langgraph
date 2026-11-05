"""Scoped native package/agent/deployment operations with durable write intent.

Legacy TEST selectors are deliberate. GA deployment routes are used only by
the explicitly requested publish operation. No operation invokes an agent.
"""

import hashlib
import itertools
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote, unquote, urlencode, urlsplit
from uuid import uuid4

from .packaging import inspect_package
from .project import FlowError, canonical_hash, load_project, private_json
from .progress import require_publication_acceptance
from .remote import WorkbenchClient, signer_for


_MAX_PAGES = 20
_MAX_ITEMS = 2000
_MAX_INTENTS = 1000
_MAX_FILE = 500_000_000
_MAX_JSON = 8 * 1024 * 1024
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,200}\Z")


def _key(value):
    if not isinstance(value, str) or not _KEY.fullmatch(value) or value in {".", ".."}:
        raise FlowError("Invalid native resource key")
    return value


def _remote(value):
    if (not isinstance(value, str) or len(value) > 1000 or not value.startswith("/Workspace/")
            or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")[1:])
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in value.split("/")[1:])):
        raise FlowError("native.remote_root must be a canonical absolute /Workspace/ path with safe path components")
    return value


def _unlinked(path):
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or getattr(ancestor, "is_junction", lambda: False)():
            raise FlowError("Native source and journals cannot use linked paths")


def _read_json(path):
    _unlinked(path)
    try:
        with path.open("rb") as stream:
            data = stream.read(_MAX_JSON + 1)
        value = json.loads(data) if len(data) <= _MAX_JSON else None
    except (OSError, ValueError):
        raise FlowError("Native journal cannot be read; reconcile it before writing") from None
    if not isinstance(value, dict):
        raise FlowError("Native journal is invalid; reconcile it before writing")
    return value


class NativeLifecycle:
    """One project, workspace, remote folder and CODE-agent binding.

    ``transport`` is an optional requests-compatible session for offline tests.
    All mutations default to a read-only plan; no method polls or retries.
    """

    def __init__(self, root, config, *, transport=None):
        _unlinked(Path(root).absolute())
        self.root, project = load_project(root)
        if config.get("agent") != project.get("agent"):
            raise FlowError("Use the selected project's authoritative agent configuration")
        self.client = WorkbenchClient(self.root, config)
        native = config.get("native", {})
        self.workspace = _key(native.get("workspace_key"))
        self.compute = _key(native.get("compute_key"))
        self.remote_root = _remote(native.get("remote_root"))
        self.name = native.get("display_name")
        if (not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 255
                or any(ord(c) < 32 for c in self.name)):
            raise FlowError("Select a nonsecret native.display_name of at most 255 characters")
        self.config = config
        self.base = self.client.base
        self.legacy_base = self.base.replace("/20260430/aiDataPlatforms/", "/20240831/dataLakes/", 1)
        self.ws = "/workspaces/" + self.workspace
        self.context = canonical_hash({"target": self.base, "workspace": self.workspace, "remote_root": self.remote_root})
        # Short path components keep journals usable under Windows worktrees;
        # the full hashes are retained and checked in the records themselves.
        self.journal = self.root / ".aidp-local/native" / self.context[:16]
        self.state_path = self.journal / "state.json"
        self.state = _read_json(self.state_path) if self.state_path.exists() else {}
        if self.state and self.state.get("target_context") != self.context:
            raise FlowError("Native journal target differs from the selected project context")
        configured = native.get("agent_key")
        self.agent_key = _key(configured) if configured else self.state.get("agent_key")
        if self.agent_key:
            _key(self.agent_key)
        if configured and self.state.get("agent_key") not in (None, configured):
            raise FlowError("Configured agent differs from this project's recorded native binding")
        self.transport = transport
        self._posting = False

    def close(self):
        if self.transport is not None:
            self.transport.close()

    def _session(self):
        if self.transport is None:
            try:
                import oci
                import requests
                self.transport = requests.Session()
                self.transport.auth = signer_for(oci.config.from_file(str(self.client.config_file), self.client.profile))
            except Exception:
                raise FlowError("Cannot load the selected native authentication context") from None
        return self.transport

    def _allowed(self, method, path, headers, legacy):
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.fragment or "\\" in path or ".." in parsed.path.split("/"):
            return False
        route = parsed.path
        if method == "GET":
            prefixes = [self.ws + "/agentFlowDeployments", self.ws + "/agentFlowSessions"] if legacy else [self.ws + "/agents", "/asyncOperations/"]
            if not legacy and route.startswith(self.ws + "/objects/"):
                remote = unquote(route.removeprefix(self.ws + "/objects/"))
                return remote == "/Workspace" or remote == self.remote_root or remote.startswith(self.remote_root + "/") or self.remote_root.startswith(remote + "/")
            return any(route == prefix or route.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)
        if method != "POST" or not self._posting or parsed.query:
            return False
        if legacy:
            return route in {self.ws + "/actions/redeployAgentFlow", self.ws + "/agentFlowSessions",
                             self.ws + "/agentFlows/" + str(self.agent_key) + "/deployments/actions/redeploy"}
        if route == self.ws + "/objects":
            remote = headers.get("path", "")
            if headers.get("type") == "FOLDER":
                return remote == self.remote_root or self.remote_root.startswith(remote + "/") or remote.startswith(self.remote_root + "/")
            return headers.get("type") == "FILE" and remote.startswith(self.remote_root + "/")
        return route in {self.ws + "/agents", self.ws + "/agents/" + str(self.agent_key) + "/deployments/actions/deploy",
                         self.ws + "/agents/" + str(self.agent_key) + "/deployments/actions/redeploy"}

    def _request(self, method, path, *, payload=None, data=None, headers=None, legacy=False, raw=False, absent=False):
        headers = dict(headers or {})
        if not self._allowed(method, path, headers, legacy):
            raise FlowError("Unsupported or unjournaled native lifecycle operation")
        if payload is not None:
            data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            response = self._session().request(method, (self.legacy_base if legacy else self.base) + path,
                data=data, headers=headers, timeout=(5, 75), allow_redirects=False)
            if absent and response.status_code == 404:
                return None, {}
            if not 200 <= response.status_code < 300:
                raise FlowError("Native lifecycle request failed; reconcile any submitted write before retrying")
            content = response.content
            if len(content) > (_MAX_FILE if raw else _MAX_JSON):
                raise FlowError("Native lifecycle response exceeds its bounded size")
            result = content if raw else json.loads(content) if content else {}
            safe_headers = {k.lower(): v for k, v in response.headers.items() if k.lower() in {
                "opc-next-page", "aidp-async-operation-key", "datalake-async-operation-key"}}
            return result, safe_headers
        except FlowError:
            raise
        except Exception:
            raise FlowError("Native transport failed; reconcile any submitted write before retrying") from None

    def _rows(self, path, *, legacy=False, query=None):
        query, items, page, seen = dict(query or {}), [], None, set()
        for _ in range(_MAX_PAGES):
            params = {**query, "limit": 100}
            if page is not None:
                params["page"] = page
            body, headers = self._request("GET", path + "?" + urlencode(params), legacy=legacy)
            batch = body.get("items") if isinstance(body, dict) else None
            if not isinstance(batch, list) or len(batch) > 100 or any(not isinstance(item, dict) for item in batch):
                raise FlowError("Native collection returned an unsupported shape")
            items.extend(batch)
            if len(items) > _MAX_ITEMS:
                raise FlowError("Native collection exceeds the bounded item count")
            page = headers.get("opc-next-page")
            if not page:
                return items
            if not isinstance(page, str) or len(page) > 1024 or page in seen:
                raise FlowError("Native collection returned invalid pagination state")
            seen.add(page)
        raise FlowError("Native listing is incomplete; no write is allowed")

    def _package(self):
        declared = self.config["agent"]
        for field in ("entry", "dependencies"):
            relative = PurePosixPath(declared[field])
            if relative.is_absolute() or ".." in relative.parts or "\\" in declared[field]:
                raise FlowError("Native source paths must stay within the declared agent folder")
            _unlinked(self.root / relative)
        package = inspect_package(self.root)
        folder = (self.root / declared["entry"]).parent
        for relative in package["files"]:
            source = folder / relative
            _unlinked(source)
            if not source.resolve().is_relative_to(folder.resolve()):
                raise FlowError("Native source escaped the declared agent folder")
        return package, folder

    def _object(self, remote, *, absent=True):
        return self._request("GET", self.ws + "/objects/" + quote(remote, safe=""),
                             headers={"Accept": "*/*"}, raw=True, absent=absent)[0]

    def _verify_package(self, package):
        for relative, expected in package["files"].items():
            saved = self._object(self.remote_root + "/" + relative)
            if saved is None or hashlib.sha256(saved).hexdigest() != expected:
                raise FlowError("Saved native package bytes differ; run source sync before deployment")

    def _save_state(self):
        self.state["target_context"] = self.context
        private_json(self.state_path, self.state, overwrite=self.state_path.exists())

    def _intents(self):
        paths = list(itertools.islice((self.journal / "intents").glob("*.json"), _MAX_INTENTS + 1))
        if len(paths) > _MAX_INTENTS:
            raise FlowError("Native journal exceeds its bounded intent count")
        records = [(path, _read_json(path)) for path in paths]
        if any(record.get("target_context") != self.context for _, record in records):
            raise FlowError("Native intent target differs from the selected project context")
        return records

    def _reconciled(self, path, record, *, resource_key=None):
        record.update(state="RECONCILED")
        if resource_key:
            record["resource_key"] = _key(resource_key)
        private_json(path, record, overwrite=True)

    def _write(self, kind, path, *, payload=None, data=None, headers=None, legacy=False, package=None, extra=None):
        self._guard()
        body = data if payload is None else json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        identity = {"kind": kind, "path": path, "legacy": legacy, "body_sha256": hashlib.sha256(body or b"").hexdigest(),
                    "headers": headers or {}, "package_sha256": package, "agent_key": self.agent_key,
                    "target_context": self.context}
        digest = canonical_hash(identity)
        ledger = self.journal / "intents" / (digest[:32] + ".json")
        if ledger.exists():
            raise FlowError("This native write was already recorded; reconcile its result instead of resubmitting")
        record = {**identity, **(extra or {}), "intent_sha256": digest, "retry_token": uuid4().hex, "state": "SUBMITTED"}
        private_json(ledger, record)
        self._posting = True
        try:
            result, returned = self._request("POST", path, payload=payload, data=data, legacy=legacy,
                                             headers={**(headers or {}), "opc-retry-token": record["retry_token"]})
        finally:
            self._posting = False
        record["state"] = "ACKNOWLEDGED"
        operation = returned.get("aidp-async-operation-key") or returned.get("datalake-async-operation-key")
        if operation:
            record["operation_key"] = _key(operation)
        if isinstance(result, dict) and result.get("key"):
            record["resource_key"] = _key(result["key"])
        private_json(ledger, record, overwrite=True)
        return result, ledger, record

    def _binding(self):
        declared = self.config["agent"]
        folder = PurePosixPath(declared["entry"]).parent
        return {"displayName": self.name, "type": "CODE", "pathInfo": self.remote_root,
                "entryFilePath": self.remote_root + "/" + PurePosixPath(declared["entry"]).name,
                "dependenciesFilePath": self.remote_root + "/" + PurePosixPath(declared["dependencies"]).relative_to(folder).as_posix(),
                "computeKey": self.compute}

    def _validate_agent(self, item, key):
        if not isinstance(item, dict) or item.get("key") != key or any(item.get(k) != v for k, v in self._binding().items()):
            raise FlowError("Native CODE-agent binding differs; foreign bindings will not be changed")

    def _agent(self):
        if not self.agent_key:
            raise FlowError("Select native.agent_key or create the agent with ensure-agent first")
        item, _ = self._request("GET", self.ws + "/agents/" + _key(self.agent_key))
        self._validate_agent(item, self.agent_key)
        return item

    def _ownership(self, agents):
        if self.agent_key:
            self._agent()
        for item in agents:
            path = item.get("pathInfo")
            if isinstance(path, str) and (path == self.remote_root or path.startswith(self.remote_root + "/") or self.remote_root.startswith(path.rstrip("/") + "/")):
                if item.get("key") != self.agent_key:
                    raise FlowError("The remote source path overlaps another agent; an explicit matching binding is required")
                self._agent()

    def _deployments(self, kind):
        if kind == "TEST":
            rows = self._rows(self.ws + "/agentFlowDeployments", legacy=True,
                              query={"agentFlowKey": self.agent_key, "deploymentType": "TEST"})
        else:
            rows = self._rows(self.ws + "/agents/" + self.agent_key + "/deployments")
        for item in rows:
            _key(item.get("key"))
            if item.get("lifecycleState") not in {"CREATING", "ACTIVE", "INACTIVE", "FAILED", "DELETED"}:
                raise FlowError("Deployment returned an unsupported lifecycle state")
            version = item.get("deploymentVersion")
            if version is not None and (type(version) not in {str, int} or len(str(version)) > 128):
                raise FlowError("Deployment returned an unsupported version")
            if kind == "TEST" and (item.get("deploymentType") != "TEST" or item.get("agentFlowKey") != self.agent_key):
                raise FlowError("Deployment list escaped the explicit TEST scope")
            if kind != "TEST" and item.get("deploymentType") not in (None, "PROD", "PRODUCTION"):
                raise FlowError("GA deployment list returned an unexpected deployment type")
            if item.get("agentKey", self.agent_key) != self.agent_key:
                raise FlowError("Deployment belongs to another agent")
            compute = item.get("agentFlowComputeKey") or item.get("agentComputeKey")
            if compute != self.compute:
                raise FlowError("Deployment compute differs from the approved agent binding")
        return rows

    @staticmethod
    def _snapshot(rows):
        fields = ("key", "lifecycleState", "deploymentType", "deploymentVersion", "agentComputeKey", "agentFlowComputeKey")
        return sorted(({key: row[key] for key in fields if key in row} for row in rows), key=lambda row: row["key"])

    def _reconcile(self):
        for path, record in self._intents():
            if record.get("state") in {"RECONCILED", "FAILED_RECONCILED"}:
                continue
            kind = record.get("kind")
            if kind in {"file", "folder"}:
                saved = self._object(record["remote_path"])
                if saved is not None and (kind == "folder" or hashlib.sha256(saved).hexdigest() == record["body_sha256"]):
                    self._reconciled(path, record)
            elif kind in {"test-init", "test-refresh", "publish"} and record.get("operation_key"):
                operation, _ = self._request("GET", "/asyncOperations/" + _key(record["operation_key"]))
                if (not isinstance(operation, dict) or operation.get("key") != record["operation_key"]
                        or operation.get("resourceType") != "AGENT" or operation.get("actionType") != "DEPLOY_AGENT"):
                    raise FlowError("Async operation readback does not match the recorded deployment operation")
                if record.get("operation_status") != operation.get("status"):
                    record["operation_status"] = operation.get("status")
                    private_json(path, record, overwrite=True)
                if operation.get("status") == "SUCCEEDED":
                    selected = "PROD" if kind == "publish" else "TEST"
                    rows = self._deployments(selected)
                    if not any(row.get("lifecycleState") == "ACTIVE" for row in rows):
                        continue
                    if self._snapshot(rows) == record["deployment_before"]:
                        continue
                    if selected == "TEST" and self._snapshot(self._deployments("PROD")) != record["prod_before"]:
                        raise FlowError("Production deployment changed during the TEST operation; reconcile before continuing")
                    self._reconciled(path, record)
                    self.state[selected.lower() + "_receipt"] = {"package_sha256": record["package_sha256"], "deployments": self._snapshot(rows)}
                    self._save_state()
                elif operation.get("status") in {"FAILED", "CANCELED"}:
                    selected = "PROD" if kind == "publish" else "TEST"
                    after = self._snapshot(self._deployments(selected))
                    prod_after = after if selected == "PROD" else self._snapshot(self._deployments("PROD"))
                    if selected == "TEST" and prod_after != record["prod_before"]:
                        raise FlowError("Production changed during a failed TEST operation; manual reconciliation is required")
                    record.update(state="FAILED_RECONCILED", deployment_after=after, prod_after=prod_after)
                    private_json(path, record, overwrite=True)
                elif operation.get("status") != "IN_PROGRESS":
                    raise FlowError("Async operation returned an unsupported state")
            elif kind == "session-test" and record.get("resource_key"):
                saved = self._session_info(record["resource_key"], self._deployments("TEST"))
                if saved["lifecycleState"] in (None, "ACTIVE"):
                    record.update(binding_verified=True, session_state=saved["lifecycleState"],
                                  session_state_reported=saved["lifecycleState"] is not None)
                    self._reconciled(path, record)
                    self.state["test_session_key"] = record["resource_key"]
                    self._save_state()

    def _guard(self):
        if any(record.get("state") not in {"RECONCILED", "FAILED_RECONCILED"} for _, record in self._intents()):
            raise FlowError("A prior native write is pending or uncertain; use status and reconcile before another write")

    def sync_package(self, apply=False):
        package, folder = self._package()
        changed = []
        for relative, digest in package["files"].items():
            saved = self._object(self.remote_root + "/" + relative)
            if saved is None or hashlib.sha256(saved).hexdigest() != digest:
                changed.append(relative)
        if not apply:
            return {"action": "sync-package", "applied": False, "files_to_write": changed,
                    "package_sha256": package["package_sha256"], "remote_extra_files_checked": False}
        self._reconcile()
        if changed:
            self._ownership(self._rows(self.ws + "/agents"))
            self._guard()
        writes = 0
        folders = {self.remote_root} if changed else set()
        for relative in package["files"] if changed else ():
            folders.update(self.remote_root + "/" + parent.as_posix() for parent in PurePosixPath(relative).parents if parent.as_posix() != ".")
        if changed:
            folders.update(parent.as_posix() for parent in PurePosixPath(self.remote_root).parents if parent.as_posix() not in {"/", "/Workspace"})
        for remote in sorted(folders, key=lambda value: (value.count("/"), value)):
            if self._object(remote) is None:
                _, ledger, record = self._write("folder", self.ws + "/objects", data=b"", headers={
                    "path": remote, "type": "FOLDER", "is-overwrite": "false", "Content-Type": "application/octet-stream"},
                    extra={"remote_path": remote})
                if self._object(remote, absent=False) is None:
                    raise FlowError("Created native folder cannot be read back")
                self._reconciled(ledger, record)
                writes += 1
        for relative in changed:
            source = folder / relative
            _unlinked(source)
            with source.open("rb") as stream:
                data = stream.read(_MAX_FILE + 1)
            if len(data) > _MAX_FILE or hashlib.sha256(data).hexdigest() != package["files"][relative]:
                raise FlowError("Local package changed during source sync")
            remote = self.remote_root + "/" + relative
            saved = self._object(remote)
            if saved == data:
                continue
            _, ledger, record = self._write("file", self.ws + "/objects", data=data, headers={
                "path": remote, "type": "FILE", "is-overwrite": str(saved is not None).lower(), "Content-Type": "application/octet-stream"},
                extra={"remote_path": remote})
            if self._object(remote, absent=False) != data:
                raise FlowError("Uploaded native file failed exact byte readback; reconcile before retrying")
            self._reconciled(ledger, record)
            writes += 1
        if self._package()[0]["package_sha256"] != package["package_sha256"]:
            raise FlowError("Local source changed during native sync")
        self._verify_package(package)
        self.state["package_sha256"] = package["package_sha256"]
        self._save_state()
        return {"action": "sync-package", "applied": bool(writes), "readback_verified": True,
                "file_count": package["file_count"], "package_sha256": package["package_sha256"], "remote_extra_files_checked": False}

    def ensure_agent(self, apply=False):
        package, _ = self._package()
        agents = self._rows(self.ws + "/agents")
        matches = [item for item in agents if item.get("displayName") == self.name]
        if len(matches) > 1:
            raise FlowError("Multiple native agents have the exact display name; select and reconcile by key")
        if matches:
            key = _key(matches[0].get("key"))
            creates = [(path, record) for path, record in self._intents() if record.get("kind") == "agent" and record.get("state") != "RECONCILED"]
            if self.agent_key != key and not (self.agent_key is None and creates):
                raise FlowError("Reusing an existing native agent requires its explicit native.agent_key")
            item, _ = self._request("GET", self.ws + "/agents/" + key)
            self._validate_agent(item, key)
            self.agent_key = key
            self._ownership(agents)
            if apply:
                for path, record in creates:
                    self._reconciled(path, record, resource_key=key)
                self.agent_key = key
                self.state["agent_key"] = key
                self._save_state()
            return {"action": "ensure-agent", "applied": False, "agent_key": key, "binding_verified": True}
        if self.agent_key:
            raise FlowError("The explicitly selected native agent is absent from the complete exact-name listing")
        self._ownership(agents)
        if not apply:
            return {"action": "ensure-agent", "applied": False, "would_create": True, "type": "CODE"}
        self._reconcile()
        self._guard()
        self._verify_package(package)
        payload = {**self._binding(), "description": "Project-owned agent managed through explicit lifecycle commands", "sessionConfig": {"variables": {}}}
        _, ledger, record = self._write("agent", self.ws + "/agents", payload=payload, package=package["package_sha256"])
        matches = [item for item in self._rows(self.ws + "/agents") if item.get("displayName") == self.name]
        if len(matches) != 1:
            raise FlowError("Agent creation requires unique readback reconciliation")
        key = _key(matches[0].get("key"))
        item, _ = self._request("GET", self.ws + "/agents/" + key)
        self._validate_agent(item, key)
        self._reconciled(ledger, record, resource_key=key)
        self.agent_key = key
        self.state["agent_key"] = key
        self._save_state()
        return {"action": "ensure-agent", "applied": True, "agent_key": key, "binding_verified": True}

    def status(self):
        self._agent()
        self._reconcile()
        return {"agent_key": self.agent_key, "test": self._snapshot(self._deployments("TEST")),
                "prod": self._snapshot(self._deployments("PROD")),
                "operations": [{key: record[key] for key in ("kind", "state", "operation_key", "operation_status") if key in record}
                               for _, record in self._intents()], "native_test_accepted": False}

    def _deploy(self, kind, apply):
        self._agent()
        package, _ = self._package()
        self._verify_package(package)
        if apply:
            self._reconcile()
            self._guard()
        tests, prod = self._deployments("TEST"), self._deployments("PROD")
        if kind == "test-init" and tests:
            raise FlowError("First TEST initialization requires no existing TEST deployments")
        if kind == "test-refresh" and not any(item.get("lifecycleState") == "ACTIVE" for item in tests):
            raise FlowError("TEST refresh requires an existing ACTIVE TEST deployment")
        if any(item.get("lifecycleState") == "CREATING" for item in tests + prod):
            raise FlowError("A deployment is still creating; inspect status before another mutation")
        selected = "PROD" if kind == "publish" else "TEST"
        if kind == "publish" and not any(item.get("lifecycleState") == "ACTIVE" for item in tests):
            raise FlowError("Production publication requires an existing ACTIVE TEST candidate")
        tested = self.state.get("test_receipt") == {"package_sha256": package["package_sha256"], "deployments": self._snapshot(tests)}
        if kind == "publish" and apply and not tested:
            raise FlowError("Current package has no reconciled ACTIVE TEST receipt; refresh and verify TEST before publication")
        if kind == "publish" and apply:
            require_publication_acceptance(self.root, self._snapshot(tests))
        receipt = self.state.get(selected.lower() + "_receipt", {})
        rows = prod if selected == "PROD" else tests
        if receipt == {"package_sha256": package["package_sha256"], "deployments": self._snapshot(rows)}:
            return {"action": kind, "applied": False, "up_to_date": True, "deployment_type": selected}
        if not apply:
            return {"action": kind, "applied": False, "deployment_type": selected,
                    "package_sha256": package["package_sha256"], "test_package_verified": tested}
        if kind == "publish":
            path = self.ws + "/agents/" + self.agent_key + "/deployments/actions/" + ("redeploy" if prod else "deploy")
            payload = {"agentKey": self.agent_key, "agentComputeKey": self.compute,
                       "description": "Explicit project publication"}
            if not prod:
                payload["displayName"] = self.name
        else:
            path = self.ws + ("/actions/redeployAgentFlow" if kind == "test-init" else "/agentFlows/" + self.agent_key + "/deployments/actions/redeploy")
            payload = {"agentFlowKey": self.agent_key, "agentFlowComputeKey": self.compute, "deploymentType": "TEST"}
        _, _, record = self._write(kind, path, payload=payload, legacy=kind != "publish", package=package["package_sha256"],
                                   extra={"prod_before": self._snapshot(prod), "deployment_before": self._snapshot(rows)})
        if kind != "publish" and self._snapshot(self._deployments("PROD")) != self._snapshot(prod):
            raise FlowError("Production deployment changed during TEST submission; reconcile the recorded operation")
        return {"action": kind, "applied": True, "submitted": True, "deployment_type": selected,
                "operation_key": record.get("operation_key"), "native_test_accepted": False}

    def test_init(self, apply=False):
        return self._deploy("test-init", apply)

    def test_refresh(self, apply=False):
        return self._deploy("test-refresh", apply)

    def publish(self, apply=False):
        return self._deploy("publish", apply)

    def _session_info(self, key, tests):
        saved, _ = self._request("GET", self.ws + "/agents/" + self.agent_key + "/sessions/" + _key(key))
        endpoints = {row.get("endpointUrl") or row.get("uri") for row in tests}
        if (not isinstance(saved, dict) or saved.get("key") != key or saved.get("agentKey") != self.agent_key
                or saved.get("agentComputeKey") != self.compute or not saved.get("endpointUrl")
                or saved["endpointUrl"] not in endpoints):
            raise FlowError("Saved session does not match the selected TEST agent, compute and endpoint")
        state = saved.get("lifecycleState")
        if ("lifecycleState" not in saved or type(state) not in {str, type(None)}
                or state not in {None, "CREATING", "ACTIVE", "INACTIVE", "FAILED", "DELETED"}):
            raise FlowError("TEST session returned an unsupported lifecycle state")
        return saved

    def create_test_session(self, apply=False):
        self._agent()
        tests = self._deployments("TEST")
        if not any(item.get("lifecycleState") == "ACTIVE" for item in tests):
            raise FlowError("A TEST session requires an ACTIVE TEST deployment")
        if self.state.get("test_session_key"):
            saved = self._session_info(self.state["test_session_key"], tests)
            state = saved["lifecycleState"]
            if state not in (None, "ACTIVE"):
                raise FlowError("The recorded TEST session is not ACTIVE; inspect it before creating another")
            return {"action": "create-test-session", "applied": False, "session_key": self.state["test_session_key"],
                    "deployment_type": "TEST", "binding_verified": True, "session_ready": None if state is None else True,
                    "session_state": state, "session_state_reported": state is not None}
        if not apply:
            return {"action": "create-test-session", "applied": False, "deployment_type": "TEST"}
        self._reconcile()
        self._guard()
        if self.state.get("test_session_key"):
            return self.create_test_session(apply=False)
        payload = {"agentFlowKey": self.agent_key, "agentFlowComputeKey": self.compute,
                   "displayName": self.name, "deploymentType": "TEST"}
        body, ledger, record = self._write("session-test", self.ws + "/agentFlowSessions", payload=payload, legacy=True)
        if not isinstance(body, dict) or not body.get("key"):
            raise FlowError("TEST session create has no readable key; reconcile before retrying")
        key = _key(body["key"])
        saved = self._session_info(key, tests)
        state = saved["lifecycleState"]
        if state not in (None, "ACTIVE"):
            return {"action": "create-test-session", "applied": True, "submitted": True,
                    "session_key": key, "deployment_type": "TEST", "session_ready": False}
        record.update(binding_verified=True, session_state=state, session_state_reported=state is not None)
        self._reconciled(ledger, record, resource_key=key)
        self.state["test_session_key"] = key
        self._save_state()
        return {"action": "create-test-session", "applied": True, "session_key": key, "deployment_type": "TEST",
                "binding_verified": True, "session_ready": None if state is None else True,
                "session_state": state, "session_state_reported": state is not None}
