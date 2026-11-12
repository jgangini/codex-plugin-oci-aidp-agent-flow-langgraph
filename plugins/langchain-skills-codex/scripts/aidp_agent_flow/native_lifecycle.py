"""Scoped native package/agent/deployment operations with durable write intent.

Legacy TEST selectors are deliberate. GA deployment routes are used only by
the explicitly requested publish operation. No operation invokes an agent.
"""

import hashlib
import itertools
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from uuid import uuid4

from .packaging import inspect_package
from .project import FlowError, canonical_hash, contained, load_project, private_json
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
        self.metadata_root = _remote(native.get("metadata_root", self.remote_root))
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
        if self.metadata_root != self.remote_root and not self.agent_key:
            raise FlowError("Separate metadata_root requires the exact existing agent identity")
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
            if not legacy and route == self.ws + "/objects":
                query = parse_qs(parsed.query)
                roots = query.get("path", [])
                return (set(query) <= {"path", "limit", "page"} and len(roots) == 1
                        and (roots[0] == self.remote_root or roots[0].startswith(self.remote_root + "/")))
            prefixes = [self.ws + "/agentFlowDeployments", self.ws + "/agentFlowSessions"] if legacy else [self.ws + "/agents", "/asyncOperations/"]
            if not legacy and route.startswith(self.ws + "/objects/"):
                remote = unquote(route.removeprefix(self.ws + "/objects/"))
                return remote == "/Workspace" or remote == self.remote_root or remote.startswith(self.remote_root + "/") or self.remote_root.startswith(remote + "/")
            return any(route == prefix or route.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)
        if method == "DELETE":
            if not self._posting or legacy or parsed.query:
                return False
            if route.startswith(self.ws + "/objects/"):
                remote = unquote(route.removeprefix(self.ws + "/objects/"))
                return remote.startswith(self.remote_root + "/")
            return route == self.ws + "/agents/" + str(self.agent_key)
        if method == "PUT":
            return (self._posting and not legacy and not parsed.query
                    and route == self.ws + "/agents/" + str(self.agent_key))
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
                "opc-next-page", "etag", "aidp-async-operation-key", "datalake-async-operation-key"}}
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

    def _write(self, kind, path, *, payload=None, data=None, headers=None, legacy=False, package=None, extra=None, method="POST", identity_scope=None, renew_reconciled=False):
        self._guard()
        body = data if payload is None else json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        identity = {"kind": kind, "path": path, "legacy": legacy, "body_sha256": hashlib.sha256(body or b"").hexdigest(),
                    "headers": headers or {}, "package_sha256": package, "agent_key": self.agent_key,
                    "target_context": self.context}
        if method != "POST":
            identity["method"] = method
        if identity_scope is not None:
            identity["identity_scope"] = identity_scope
        base = dict(identity)
        digest = canonical_hash(identity)
        ledger = self.journal / "intents" / (digest[:32] + ".json")
        for generation in range(1, _MAX_INTENTS + 1):
            if not ledger.exists():
                break
            previous = _read_json(ledger)
            if (not renew_reconciled or previous.get("state") != "RECONCILED"
                    or previous.get("intent_sha256") != digest or previous.get("target_context") != self.context):
                raise FlowError("This native write was already recorded; reconcile its result instead of resubmitting")
            identity = {**base, "write_generation": generation}
            digest = canonical_hash(identity)
            ledger = self.journal / "intents" / (digest[:32] + ".json")
        else:
            raise FlowError("Native write generation exceeded its bounded history")
        record = {**identity, **(extra or {}), "intent_sha256": digest, "retry_token": uuid4().hex, "state": "SUBMITTED"}
        private_json(ledger, record)
        self._posting = True
        try:
            result, returned = self._request(method, path, payload=payload, data=data, legacy=legacy, raw=kind == "file",
                                             headers={**(headers or {}), **({"opc-retry-token": record["retry_token"]} if method == "POST" else {})})
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
        return {"displayName": self.name, "type": "CODE", "pathInfo": self.metadata_root,
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

    def _source_agent(self):
        if not self.agent_key:
            raise FlowError("Rebinding requires the exact existing native.agent_key")
        item, headers = self._request("GET", self.ws + "/agents/" + _key(self.agent_key))
        expected = self._binding()
        fixed = ("displayName", "type", "pathInfo", "computeKey")
        if (not isinstance(item, dict) or item.get("key") != self.agent_key
                or any(item.get(field) != expected[field] for field in fixed)):
            raise FlowError("Rebinding cannot change agent identity, type, metadata location or compute")
        for field in ("entryFilePath", "dependenciesFilePath"):
            _remote(item.get(field))
        return item, headers

    def _rebind_guard(self):
        paths = list(itertools.islice((self.root / ".aidp-local/native").glob("*/intents/*.json"), _MAX_INTENTS + 1))
        if len(paths) > _MAX_INTENTS:
            raise FlowError("Native intent audit exceeds its bounded count")
        for path in paths:
            if path.parent.parent == self.journal:
                continue
            record = _read_json(path)
            if (record.get("agent_key") == self.agent_key
                    and record.get("state") not in {"RECONCILED", "FAILED_RECONCILED"}):
                raise FlowError("Another native context has a pending write for this agent; reconcile it first")

    def _rebind_deployments(self):
        tests, prod = self._deployments("TEST"), self._deployments("PROD")
        if any(row.get("lifecycleState") == "CREATING" for row in tests + prod):
            raise FlowError("A deployment is creating; rebinding must wait")
        if any(row.get("lifecycleState") == "ACTIVE" for row in prod):
            raise FlowError("Rebinding an agent with ACTIVE production is outside this development operation")
        return tests, prod

    def _finish_rebind(self, ledger, record):
        self.state.pop("test_receipt", None)
        self.state["agent_key"] = self.agent_key
        self.state["rebind_receipt"] = {key: record[key] for key in
            ("binding_before", "binding_after", "package_sha256", "prod_before")}
        self._save_state()
        self._reconciled(ledger, record, resource_key=self.agent_key)

    def _ownership(self, agents, *, for_rebind=False):
        validate = self._source_agent if for_rebind else self._agent
        if self.agent_key:
            validate()
        for item in agents:
            paths = [item.get("pathInfo")]
            paths.extend(str(PurePosixPath(item[field]).parent) for field in
                         ("entryFilePath", "dependenciesFilePath") if isinstance(item.get(field), str))
            for path in paths:
                if isinstance(path, str) and (path == self.remote_root or path.startswith(self.remote_root + "/") or self.remote_root.startswith(path.rstrip("/") + "/")):
                    if item.get("key") != self.agent_key:
                        raise FlowError("The remote source path overlaps another agent; an explicit matching binding is required")
                    validate()

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
                    self.state[selected.lower() + "_receipt"] = {"package_sha256": record["package_sha256"], "deployments": self._snapshot(rows)}
                    self._save_state()
                    self._reconciled(path, record)
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
            elif kind == "rebind":
                if record.get("binding_after") != self._binding():
                    raise FlowError("Recorded rebinding differs from the selected configuration")
                item, _ = self._source_agent()
                if all(item.get(key) == value for key, value in record["binding_after"].items()):
                    package, _ = self._package()
                    if package["package_sha256"] != record["package_sha256"]:
                        raise FlowError("Rebinding package changed; preserve and reconcile its original candidate")
                    self._verify_package(package)
                    if self._snapshot(self._deployments("PROD")) != record["prod_before"]:
                        raise FlowError("Production changed during rebinding; reconcile before continuing")
                    self._finish_rebind(path, record)
                elif any(item.get(key) != value for key, value in record["binding_before"].items()):
                    raise FlowError("Rebinding outcome differs from both recorded bindings")
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

    def _sync_conditions(self, definition, package):
        if definition is None:
            return None
        value = _read_json(contained(self.root, definition))
        files = value.get("files")
        if (set(value) != {"version", "package_sha256", "files"} or value.get("version") != 1
                or value.get("package_sha256") != package["package_sha256"]
                or not isinstance(files, dict) or set(files) != set(package["files"])
                or any(not isinstance(values, list) or not 1 <= len(values) <= 2
                    or any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in values)
                    or package["files"][name] not in values for name, values in files.items())):
            raise FlowError("Sync preconditions must pin the exact package and every existing file")
        return files

    @staticmethod
    def _check_sync_condition(relative, saved, conditions):
        if conditions is not None and (saved is None or hashlib.sha256(saved).hexdigest() not in conditions[relative]):
            raise FlowError("Managed source drift was preserved; sync preconditions no longer match")

    def sync_package(self, apply=False, for_rebind=False, expected_inventory=None):
        package, folder = self._package()
        conditions = self._sync_conditions(expected_inventory, package)
        source_roots = []
        if for_rebind:
            current, _ = self._source_agent()
            self._rebind_deployments()
            self._rebind_guard()
            source_roots = [str(PurePosixPath(current[field]).parent)
                            for field in ("entryFilePath", "dependenciesFilePath")]
            if self.remote_root in source_roots:
                raise FlowError("Rebinding staging requires a separate code location; use normal sync for an unchanged root")
        changed = []
        for relative, digest in package["files"].items():
            remote = self.remote_root + "/" + relative
            if any(remote == source_root or remote.startswith(source_root + "/") for source_root in source_roots):
                raise FlowError("Rebinding staging cannot overwrite the prior source tree")
            saved = self._object(remote)
            self._check_sync_condition(relative, saved, conditions)
            if for_rebind and saved is not None and hashlib.sha256(saved).hexdigest() != digest:
                raise FlowError("Rebinding staging requires absent or identical target files; preserve conflicting bytes")
            if saved is None or hashlib.sha256(saved).hexdigest() != digest:
                changed.append(relative)
        if not apply:
            return {"action": "sync-package", "applied": False, "files_to_write": changed,
                    "package_sha256": package["package_sha256"], "remote_extra_files_checked": False}
        self._reconcile()
        if changed:
            self._ownership(self._rows(self.ws + "/agents"), for_rebind=for_rebind)
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
            self._check_sync_condition(relative, saved, conditions)
            if saved == data:
                continue
            if for_rebind and saved is not None:
                raise FlowError("A rebinding target changed during staging; no conflicting file was overwritten")
            _, ledger, record = self._write("file", self.ws + "/objects", data=data, headers={
                "path": remote, "type": "FILE", "is-overwrite": str(saved is not None).lower(), "Content-Type": "application/octet-stream"},
                extra={"remote_path": remote}, renew_reconciled=True,
                identity_scope={"preconditions_sha256": canonical_hash(conditions)} if conditions is not None else None)
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
                "preconditions_checked": conditions is not None,
                "file_count": package["file_count"], "package_sha256": package["package_sha256"], "remote_extra_files_checked": False}

    def rebind(self, apply=False, expected_binding=None, allow_no_etag=False):
        package, _ = self._package()
        current, headers = self._source_agent()
        before = {key: current[key] for key in self._binding()}
        after = self._binding()
        tests, prod = self._rebind_deployments()
        self._rebind_guard()
        binding_hash = canonical_hash({"context": self.context, "agent_key": self.agent_key,
            "before": before, "after": after, "package_sha256": package["package_sha256"],
            "test": self._snapshot(tests), "prod": self._snapshot(prod),
            "record_version": current.get("version")})
        result = {"action": "rebind", "applied": False, "agent_key": self.agent_key,
                  "binding_before": before, "binding_after": after, "binding_sha256": binding_hash,
                  "metadata_moved": False, "old_source_deleted": False, "native_test_accepted": False,
                  "concurrency_control": "etag" if headers.get("etag") else "explicit_readback_without_cas"}
        if not apply:
            return {**result, "up_to_date": before == after, "etag_present": bool(headers.get("etag")),
                    "package_sha256": package["package_sha256"], "test_refresh_required": before != after}
        self._reconcile()
        self._guard()
        if before == after:
            return {**result, "up_to_date": True, "test_refresh_required": True}
        if expected_binding != binding_hash:
            raise FlowError("Rebinding requires the current binding_sha256 from its read-only plan")
        etag = headers.get("etag")
        if etag is not None and (not isinstance(etag, str) or not etag or len(etag) > 1000 or any(ord(c) < 32 for c in etag)):
            raise FlowError("Rebinding requires a valid observed agent ETag")
        if etag is None and not allow_no_etag:
            raise FlowError("Agent ETag is absent; explicitly select --allow-no-etag for verified readback without atomic concurrency control")
        self._ownership(self._rows(self.ws + "/agents"), for_rebind=True)
        self._verify_package(package)
        if etag is None:
            latest, latest_headers = self._source_agent()
            if ({key: latest[key] for key in before} != before or latest.get("version") != current.get("version")):
                raise FlowError("Agent changed before rebinding; obtain a new plan")
            observed = latest_headers.get("etag")
            if observed is not None:
                if not isinstance(observed, str) or not observed or len(observed) > 1000 or any(ord(c) < 32 for c in observed):
                    raise FlowError("Rebinding requires a valid observed agent ETag")
                etag = observed
            latest_tests, latest_prod = self._rebind_deployments()
            if self._snapshot(latest_tests) != self._snapshot(tests) or self._snapshot(latest_prod) != self._snapshot(prod):
                raise FlowError("Deployments changed before rebinding; obtain a new plan")
            self._rebind_guard()
        result["concurrency_control"] = "etag" if etag else "explicit_readback_without_cas"
        payload = {key: after[key] for key in ("entryFilePath", "dependenciesFilePath")}
        _, ledger, record = self._write("rebind", self.ws + "/agents/" + self.agent_key,
            method="PUT", payload=payload, headers={"if-match": etag} if etag else {}, package=package["package_sha256"],
            extra={"binding_before": before, "binding_after": after, "prod_before": self._snapshot(prod),
                   "concurrency_control": result["concurrency_control"], "record_version_before": current.get("version")})
        observed, _ = self._source_agent()
        self._validate_agent(observed, self.agent_key)
        self._verify_package(package)
        if self._snapshot(self._deployments("PROD")) != self._snapshot(prod):
            raise FlowError("Production changed during rebinding; preserve its receipt and reconcile")
        self._finish_rebind(ledger, record)
        return {**result, "applied": True, "binding_verified": True, "test_refresh_required": True}

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
                self.agent_key = key
                self.state["agent_key"] = key
                self._save_state()
                for path, record in creates:
                    self._reconciled(path, record, resource_key=key)
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
        self.agent_key = key
        self.state["agent_key"] = key
        self._save_state()
        self._reconciled(ledger, record, resource_key=key)
        return {"action": "ensure-agent", "applied": True, "agent_key": key, "binding_verified": True}

    def inspect_binding(self):
        """Observe a configured identity without repairing or reconciling it.

        Unlike status, this diagnostic permits path drift so an existing
        installation can be understood before a separately journaled migration.
        """
        if not self.agent_key:
            raise FlowError("Binding inspection requires an explicit or recorded native.agent_key")
        item, _ = self._request("GET", self.ws + "/agents/" + _key(self.agent_key))
        if (not isinstance(item, dict) or item.get("key") != self.agent_key
                or item.get("type") != "CODE" or item.get("computeKey") != self.compute):
            raise FlowError("Binding inspection returned another agent, type or compute")
        expected = self._binding()
        actual = {key: item.get(key) for key in expected}
        for key in ("pathInfo", "entryFilePath", "dependenciesFilePath"):
            _remote(actual[key])
        if not isinstance(actual["displayName"], str) or len(actual["displayName"]) > 255:
            raise FlowError("Binding inspection returned an invalid agent name")
        differences = {key: {"actual": actual[key], "expected": value}
                       for key, value in expected.items() if actual[key] != value}
        return {"action": "inspect-binding", "read_only": True, "migration_applied": False,
                "agent_key": self.agent_key, "binding_verified": not differences,
                "actual": actual, "expected": expected, "differences": differences,
                "metadata_location": actual["pathInfo"],
                "code_root": str(PurePosixPath(actual["entryFilePath"]).parent),
                "metadata_object_verified": False,
                "relocation_required": "pathInfo" in differences,
                "entry_update_required": any(key in differences for key in
                                             ("entryFilePath", "dependenciesFilePath")),
                "migration_blockers": ["metadata_object_not_verified"] if "pathInfo" in differences else [],
                "test": self._snapshot(self._deployments("TEST")),
                "prod": self._snapshot(self._deployments("PROD")),
                "native_test_accepted": False}

    def inspect_layout(self):
        from .native_layout import inspect_layout
        return inspect_layout(self)

    def retire_agent(self, apply=False, expected_binding=None):
        from .native_layout import retire_agent
        return retire_agent(self, apply=apply, expected_binding=expected_binding)

    def prune_tree(self, definition, apply=False):
        from .native_layout import prune_tree
        from .progress import _path, _read
        value = _read(_path(self.root, definition))
        if not isinstance(value, dict) or set(value) != {"tree", "hashes"}:
            raise FlowError("Pruning definition needs only tree and hashes")
        return prune_tree(self, value["tree"], value["hashes"], apply=apply)

    def status(self):
        self._agent()
        self._reconcile()
        return {"agent_key": self.agent_key, "test": self._snapshot(self._deployments("TEST")),
                "prod": self._snapshot(self._deployments("PROD")),
                "operations": [{key: record[key] for key in ("kind", "state", "operation_key", "operation_status") if key in record}
                               for _, record in self._intents()], "native_test_accepted": False}

    def _deploy(self, kind, apply, recover_failed=False):
        from .native_layout import require_layout
        self._agent()
        package, _ = self._package()
        self._verify_package(package)
        require_layout(self, verify_bytes=False)
        if apply:
            self._reconcile()
            self._guard()
        tests, prod = self._deployments("TEST"), self._deployments("PROD")
        if kind == "test-init" and tests:
            raise FlowError("First TEST initialization requires no existing TEST deployments")
        recovery = (recover_failed and kind == "test-refresh" and bool(tests)
                    and all(item.get("lifecycleState") == "FAILED" for item in tests))
        if kind == "test-refresh" and not any(item.get("lifecycleState") == "ACTIVE" for item in tests) and not recovery:
            raise FlowError("TEST refresh requires an existing ACTIVE TEST deployment or explicit recovery of a known failed TEST")
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
            return {"action": kind, "applied": False, "up_to_date": True, "deployment_type": selected,
                    "package_sha256": package["package_sha256"]}
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
                                   extra={"prod_before": self._snapshot(prod), "deployment_before": self._snapshot(rows)},
                                   identity_scope={"deployment_before": self._snapshot(rows)})
        if kind != "publish" and self._snapshot(self._deployments("PROD")) != self._snapshot(prod):
            raise FlowError("Production deployment changed during TEST submission; reconcile the recorded operation")
        return {"action": kind, "applied": True, "submitted": True, "deployment_type": selected,
                "operation_key": record.get("operation_key"), "native_test_accepted": False}

    def test_init(self, apply=False):
        return self._deploy("test-init", apply)

    def test_refresh(self, apply=False, recover_failed=False):
        return self._deploy("test-refresh", apply, recover_failed=recover_failed)

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
