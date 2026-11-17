"""Register an explicitly selected, published AIDP agent with protected intent.

The Registry is a legacy service surface, separate from GA deployment metadata.
Only native AIDP cards with platform-managed authentication are supported here.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID, uuid4

from .native_lifecycle import NativeLifecycle, _read_json, _unlinked
from .project import FlowError, canonical_hash, load_project, private_json, redact
from .remote import WorkbenchClient, signer_for


_MAX_JSON = 1024 * 1024
_MAX_PAGES = 20
_MAX_ITEMS = 2000
_METADATA = {"version", "display_name", "description", "tags", "labels", "registry_metadata", "blueprint"}


def _uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise FlowError("Use a canonical Registry or native agent UUID") from None
    return value


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise FlowError("Registry version must be a short canonical version string")
    return value


def _nonsecret(value):
    if isinstance(value, dict):
        if any(str(key).lower().replace("_", "") in {
                "token", "password", "privatekey", "secretvalue", "authorization", "cookie",
                "passphrase", "keycontent", "accesstoken", "securitytoken"} for key in value):
            raise FlowError("Registry metadata and cards cannot contain credential values")
        for item in value.values():
            _nonsecret(item)
    elif isinstance(value, list):
        for item in value:
            _nonsecret(item)
    elif isinstance(value, str) and (redact(value) != value or re.search(
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|(?i:bearer)\s+\S+", value)):
        raise FlowError("Registry metadata and cards cannot contain credential values")


def _review(path):
    metadata = _read_json(Path(path))
    if not _METADATA - {"blueprint"} <= set(metadata) <= _METADATA:
        raise FlowError("Review only version, display_name, description, tags, labels, registry_metadata and optional blueprint")
    _version(metadata["version"])
    for key, maximum in (("display_name", 255), ("description", 4096)):
        value = metadata[key]
        if (not isinstance(value, str) or not value.strip() or len(value) > maximum
                or any(ord(character) < 32 for character in value)):
            raise FlowError("Registry display name and description must be bounded nonsecret text")
    if (not isinstance(metadata["tags"], list) or len(metadata["tags"]) > 50
            or any(not isinstance(tag, str) or len(tag) > 255 for tag in metadata["tags"])):
        raise FlowError("Registry tags must be a bounded string list")
    if (not isinstance(metadata["labels"], dict) or len(metadata["labels"]) > 50
            or any(not isinstance(key, str) or len(key) > 128 or not isinstance(value, str) or len(value) > 1024
                   for key, value in metadata["labels"].items())):
        raise FlowError("Registry labels must be a bounded string mapping")
    registry_metadata = metadata["registry_metadata"]
    if (not isinstance(registry_metadata, dict) or registry_metadata.get("schema") != "oasf.record@0.7.0"
            or not isinstance(registry_metadata.get("record"), dict) or metadata.get("blueprint", {}) != {}):
        raise FlowError("Use reviewed oasf.record@0.7.0 metadata and an empty blueprint")
    metadata["blueprint"] = {}
    _nonsecret(metadata)
    return metadata


class Registry:
    def __init__(self, root, config, *, transport=None):
        _unlinked(Path(root).absolute())
        self.root, project = load_project(root)
        if config != project:
            raise FlowError("Use the selected project's authoritative Registry configuration")
        self.config = config
        self.client = WorkbenchClient(self.root, config)
        self.legacy_base = self.client.base.replace("/20260430/aiDataPlatforms/", "/20240831/dataLakes/", 1)
        self.base = self.legacy_base + "/agent-registry/v1"
        self.prefix = urlsplit(self.base).path
        self.transport, self.native = transport, None
        self._posting = None
        self._version_route = None

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
                raise FlowError("Cannot load the selected Registry authentication context") from None
        return self.transport

    def _request(self, method, path, payload=None):
        parsed = urlsplit(path)
        if (parsed.scheme or parsed.netloc or parsed.fragment or "\\" in path
                or any(part in {".", ".."} for part in parsed.path.split("/"))):
            raise FlowError("Registry request escaped its selected namespace")
        allowed = method == "GET" and (parsed.path == "/agents" or path == self._version_route)
        allowed = allowed or method == "POST" and not parsed.query and (
            path == "/agents/inspect-a2a" or self._posting == (path, canonical_hash(payload)))
        if not allowed:
            raise FlowError("Unsupported or unjournaled Registry operation")
        try:
            response = self._session().request(method, self.base + path,
                data=json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None,
                headers={"Content-Type": "application/json", **({"opc-retry-token": self._retry_token} if self._posting else {})},
                timeout=(5, 60), allow_redirects=False)
            if response.status_code != 200:
                raise FlowError("Registry request failed; reconcile any submitted registration before retrying")
            if len(response.content) > _MAX_JSON:
                raise FlowError("Registry response exceeded its bounded size")
            body = json.loads(response.content)
            if not isinstance(body, dict):
                raise FlowError("Registry returned an unsupported response shape")
            return body
        except FlowError:
            raise
        except Exception:
            raise FlowError("Registry transport failed; reconcile any submitted registration before retrying") from None

    def _rows(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise FlowError("Registry page size must be an integer from 1 to 1000")
        rows, identities, total, offset = [], set(), None, 0
        for page in range(1, _MAX_PAGES + 1):
            body = self._request("GET", "/agents?" + urlencode({"limit": limit, "offset": offset}))
            batch, reported_total = body.get("agents"), body.get("total")
            if (not isinstance(batch, list) or type(body.get("offset")) is not int or body["offset"] != offset
                    or type(body.get("limit")) is not int or not 1 <= body["limit"] <= limit
                    or len(batch) > body["limit"] or type(reported_total) is not int
                    or not 0 <= reported_total <= _MAX_ITEMS or total not in (None, reported_total)
                    or offset + len(batch) > reported_total):
                raise FlowError("Registry listing changed or exceeded its bounded contract")
            total = reported_total
            for row in batch:
                if not isinstance(row, dict):
                    raise FlowError("Registry returned an invalid collection record")
                if not isinstance(row.get("display_name"), str) or not row["display_name"] or len(row["display_name"]) > 255:
                    raise FlowError("Registry returned an unreadable collection name")
                self._summary(row)
                key = _uuid(row.get("agent_key"))
                if key in identities:
                    raise FlowError("Registry listing repeated an identity")
                identities.add(key)
                rows.append(row)
            offset += len(batch)
            if offset == total:
                return rows, page
            if not batch:
                raise FlowError("Registry listing is incomplete; no registration is allowed")
        raise FlowError("Registry listing exceeded its page bound; no registration is allowed")

    @staticmethod
    def _summary(row):
        fields = {"agent_key", "display_name", "active_version", "latest_version", "status"}
        result = {key: row[key] for key in fields if key in row}
        for value in result.values():
            if value is not None and (not isinstance(value, str) or len(value) > 4096):
                raise FlowError("Registry returned invalid summary metadata")
        return redact(result)

    def list(self, limit=100):
        rows, pages = self._rows(limit)
        return {"agents": [self._summary(row) for row in rows], "complete": True, "pageCount": pages,
                "agent_hub_invocation_verified": False}

    def _binding(self, *, allow_unpublished=False):
        if self.native is None:
            self.native = NativeLifecycle(self.root, self.config, transport=self._session())
        self.native._agent()
        deployments = [row for row in self.native._deployments("PROD") if row.get("lifecycleState") == "ACTIVE"]
        if not deployments and allow_unpublished:
            return None
        if len(deployments) != 1:
            raise FlowError("Registry inspection requires exactly one ACTIVE production deployment")
        deployment = deployments[0]
        key = _uuid(self.native.agent_key)
        endpoint = deployment.get("endpointUrl") or deployment.get("uri")
        if not isinstance(endpoint, str):
            raise FlowError("Published agent has no readable endpoint")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment
                or not re.fullmatch(r"gateway\.aidp\.[a-z]+(?:-[a-z]+)+-\d+\.oci\.oraclecloud\.com", parsed.hostname or "")
                or parsed.path not in {"/agentendpoint/" + key + "/chat", "/agentendpoint/" + key + "/a2a"}):
            raise FlowError("Published endpoint does not match the selected native agent's HTTPS gateway")
        origin = "https://" + parsed.hostname
        return {"target": self.base, "workspace_key": self.native.workspace, "agent_flow_key": key,
                "compute_key": self.native.compute, "deployment_key": deployment["key"],
                "deployment_version": deployment.get("deploymentVersion"), "gateway": origin,
                "agent_card_url": origin + "/agentendpoint/" + key + "/a2a/.well-known/agent-card.json"}

    def _paths(self, binding):
        context = canonical_hash({key: binding[key] for key in ("target", "workspace_key", "agent_flow_key")})
        journal = self.root / ".aidp-local/registry" / context[:16]
        _unlinked(journal)
        return context, journal, journal / "state.json"

    def _state(self, binding, *, allow_redeployment=False):
        context, _, path = self._paths(binding)
        state = _read_json(path) if path.exists() else None
        if state is not None:
            previous = state.get("binding")
            if state.get("target_context") != context or not isinstance(previous, dict):
                raise FlowError("Registry journal binding differs; reconcile the original target before changing it")
            stable_previous = {key: value for key, value in previous.items() if key not in {"deployment_key", "deployment_version"}}
            stable_current = {key: value for key, value in binding.items() if key not in {"deployment_key", "deployment_version"}}
            if previous != binding and (not allow_redeployment or stable_previous != stable_current):
                raise FlowError("Registry journal binding differs; reconcile the original target before changing it")
        return state

    @staticmethod
    def _additional(binding):
        return {"agent_flow_key": binding["agent_flow_key"], "workspace_key": binding["workspace_key"],
                "compute_id": binding["compute_key"]}

    @staticmethod
    def _interface(interface, binding):
        if (not isinstance(interface, dict) or set(interface) != {"kind", "agent_card_url", "agent_card"}
                or interface.get("kind") != "a2a_aidp" or interface.get("agent_card_url") != binding["agent_card_url"]
                or not isinstance(interface.get("agent_card"), dict)):
            raise FlowError("Registry inspection has an invalid or nested interface contract")
        card = interface["agent_card"]
        root = "/agentendpoint/" + binding["agent_flow_key"] + "/a2a"
        if card.get("url") not in {binding["gateway"] + root, binding["gateway"] + "/internal" + root}:
            raise FlowError("Normalized agent card belongs to a different native endpoint")
        _nonsecret(interface)
        return copy.deepcopy(interface)

    def inspect_card(self):
        """Observe the public card without granting normalized Registry inspection."""
        binding = self._binding()
        response = None
        try:
            response = self._session().request("GET", binding["agent_card_url"],
                headers={"Accept": "application/json"}, timeout=(5, 30),
                allow_redirects=False, stream=True)
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if response.status_code != 200 or content_type != "application/json":
                raise FlowError("Published card GET failed; Registry inspection remains unverified")
            raw = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if len(raw) + len(chunk) > _MAX_JSON:
                    raise FlowError("Published card exceeded its bounded size")
                raw.extend(chunk)
            card = json.loads(raw)
            interface = self._interface({"kind": "a2a_aidp",
                "agent_card_url": binding["agent_card_url"], "agent_card": card}, binding)
            if self._binding() != binding:
                raise FlowError("Publication changed while observing its card")
            artifact = {"binding": binding, "public_interface_contract": interface,
                        "source": "authenticated_public_card_get",
                        "normalized_inspection_verified": False}
            _, journal, _ = self._paths(binding)
            path = journal / ("public-card-" + canonical_hash(artifact)[:16] + ".json")
            if path.exists():
                if _read_json(path) != artifact:
                    raise FlowError("Immutable public card artifact differs")
            else:
                private_json(path, artifact)
            return {"status": "observed", "artifact": str(path),
                    "published_card_available": True, "registry_ready": False,
                    "normalized_inspection_verified": False,
                    "agent_hub_invocation_verified": False}
        except FlowError:
            raise
        except Exception:
            raise FlowError("Published card observation failed; Registry inspection remains unverified") from None
        finally:
            if response is not None:
                response.close()

    def inspect(self):
        binding = self._binding()
        result = self._request("POST", "/agents/inspect-a2a", {
            "kind": "a2a_aidp", "agent_card_url": binding["agent_card_url"],
            "additional_metadata": {"cluster_key": binding["compute_key"], "compute_id": binding["compute_key"]}})
        if result.get("status") != "inspected" or "auth" not in result or result["auth"] is not None:
            raise FlowError("Only an inspected native AIDP card with platform-managed authentication is supported")
        artifact = {"binding": binding, "interface_contract": self._interface(result.get("interface_contract"), binding)}
        digest = canonical_hash(artifact)
        _, journal, _ = self._paths(binding)
        name = "inspection-" + digest[:16] + ".json"
        path = journal / name
        if path.exists():
            if _read_json(path) != artifact:
                raise FlowError("Immutable Registry inspection artifact differs")
        else:
            private_json(path, artifact)
        private_json(journal / "inspection.json", {"artifact": name, "sha256": digest}, overwrite=True)
        return {"status": "inspected", "kind": "a2a_aidp", "agent_card_url": binding["agent_card_url"],
                "artifact": str(path), "registered": False}

    def _inspection(self, binding):
        _, journal, _ = self._paths(binding)
        pointer = _read_json(journal / "inspection.json")
        name = pointer.get("artifact")
        if not isinstance(name, str) or not re.fullmatch(r"inspection-[a-f0-9]{16}\.json", name):
            raise FlowError("Registry inspection reference is invalid")
        artifact = _read_json(journal / name)
        if artifact.get("binding") != binding or canonical_hash(artifact) != pointer.get("sha256"):
            raise FlowError("Published binding changed since inspection; inspect the current publication")
        return self._interface(artifact.get("interface_contract"), binding)

    def _version_path(self, key, version, uri=None):
        path = "/agents/" + _uuid(key) + "/versions/" + _version(version)
        if uri is not None and uri != self.prefix + path:
            raise FlowError("Registry version URI escaped the exact registered identity and version")
        self._version_route = path
        return path

    def _record(self, binding, state):
        key, version = _uuid(state.get("registry_key")), _version(state.get("version"))
        matches = [row for row in self._rows()[0] if row["agent_key"] == key]
        if (len(matches) != 1 or matches[0].get("active_version") != version
                or matches[0].get("latest_version") != version):
            raise FlowError("Registry active/latest version differs or is not uniquely readable")
        body = self._request("GET", self._version_path(key, version, state.get("version_uri")))
        if (body.get("agent_key") != key or body.get("version") != version or body.get("status") != "ACTIVE"
                or body.get("is_latest") is not True or body.get("auth_key") != "none"
                or body.get("additional_metadata") != self._additional(binding)):
            raise FlowError("Registry version readback differs from the selected native identity or version")
        interface = self._interface(body.get("interface_contract"), binding)
        if canonical_hash(interface) != state.get("interface_sha256"):
            raise FlowError("Registry normalized interface differs from its pinned inspection")
        if state.get("display_name") != body.get("display_name"):
            raise FlowError("Registry registered name differs from the pinned review")
        metadata = {field: body[field] for field in _METADATA if field in body}
        metadata.setdefault("blueprint", {})
        if canonical_hash(metadata) != state.get("metadata_sha256"):
            raise FlowError("Registry version metadata differs from the pinned review")
        return body

    def status(self):
        binding = self._binding()
        state = self._state(binding)
        if state is None:
            return {"registered": False, "requires_explicit_registration_or_adoption": True}
        if state.get("state") not in {"ACKNOWLEDGED", "RECONCILED"} or not state.get("version_uri"):
            raise FlowError("Registration remains uncertain; explicitly adopt the pinned Registry key after readback")
        self._record(binding, state)
        if state["state"] != "RECONCILED":
            state["state"] = "RECONCILED"
            private_json(self._paths(binding)[2], state, overwrite=True)
        return {"registered": True, "registry_key": state["registry_key"], "version": state["version"],
                "status": "ACTIVE", "readback_verified": True, "agent_hub_invocation_verified": False}

    def readiness(self):
        binding = self._binding(allow_unpublished=True)
        if binding is None:
            return {"passed": False, "registry_ready": False, "blockers": ["published_endpoint_missing"],
                    "agent_hub_invocation_verified": False}
        registered = self.status()
        ready = (registered.get("registered") is True and registered.get("status") == "ACTIVE"
                 and registered.get("readback_verified") is True)
        return {"passed": ready, "registry_ready": ready,
                "blockers": [] if ready else ["registration_or_adoption_required"],
                "agent_hub_invocation_verified": False}

    def hub_link(self):
        registered = self.status()
        if (registered.get("registered") is not True or registered.get("status") != "ACTIVE"
                or registered.get("readback_verified") is not True):
            raise FlowError("Agent Hub link requires a verified ACTIVE registration; register or explicitly adopt it first")
        return {**self.portal_link(), "registry_key": registered["registry_key"],
                "version": registered["version"], "registry_ready": True}

    def portal_link(self):
        url = self.config.get("native", {}).get("agent_hub_url")
        if not isinstance(url, str) or not url:
            raise FlowError("Set native.agent_hub_url to the verified Agent Hub portal URL; it cannot be inferred from the platform or gateway")
        try:
            parsed = urlsplit(url)
            valid = (len(url) <= 2048 and not any(ord(character) < 33 for character in url)
                     and parsed.scheme == "https" and not parsed.username and not parsed.password
                     and not parsed.port and not parsed.query and "?" not in url.split("#", 1)[0]
                     and re.fullmatch(r"[a-z0-9][a-z0-9-]*agenthub\.datalake\.oci\.oraclecloud\.com", parsed.hostname or "")
                     and parsed.path in {"/", "/static/ah/"})
            if parsed.fragment:
                if not parsed.fragment.startswith("?") or re.search(r"%(?![A-Fa-f0-9]{2})", parsed.fragment):
                    raise ValueError()
                parameters = parse_qsl(parsed.fragment[1:], keep_blank_values=True, strict_parsing=True,
                                       errors="strict", max_num_fields=2)
                valid = valid and len(parameters) == 2 and {key for key, _ in parameters} == {"tenant", "domain"}
                valid = valid and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,499}", value) for _, value in parameters)
            if not valid:
                raise ValueError()
        except (ValueError, UnicodeError):
            raise FlowError("native.agent_hub_url must be the verified HTTPS Oracle Agent Hub portal, with only optional tenant/domain fragment parameters") from None
        return {"url": url, "link_type": "agent_hub_portal", "registry_ready": False,
                "authentication_required": True, "client_invocation_verified": False}

    def register(self, metadata_file, apply=False):
        metadata_path = Path(metadata_file).expanduser()
        if not metadata_path.is_absolute():
            metadata_path = self.root / metadata_path
        metadata, binding = _review(metadata_path), self._binding()
        state = self._state(binding)
        if state is not None:
            if state.get("metadata_sha256") != canonical_hash(metadata):
                raise FlowError("Registry intent already exists for different metadata; no new UUID or version was submitted")
            return {**self.status(), "action": "register", "applied": False}
        if any(row.get("display_name") == metadata["display_name"] for row in self._rows()[0]):
            raise FlowError("An existing Registry name requires explicit key adoption; no duplicate registration was submitted")
        if not apply:
            return {"action": "register", "applied": False, "version": metadata["version"],
                    "inspection_required": True, "configuration_changed": False}
        interface = self._inspection(binding)
        key, token = str(uuid4()), uuid4().hex
        payload = {**metadata, "auth_key": "none", "interface_contract": interface,
                   "additional_metadata": self._additional(binding)}
        context, _, state_path = self._paths(binding)
        state = {"target_context": context, "binding": binding, "registry_key": key, "version": metadata["version"],
                 "display_name": metadata["display_name"], "metadata_sha256": canonical_hash(metadata),
                 "interface_sha256": canonical_hash(interface), "payload_sha256": canonical_hash(payload),
                 "retry_token": token, "state": "PREPARED"}
        private_json(state_path, state)
        state["state"] = "SUBMITTED"
        private_json(state_path, state, overwrite=True)
        path = "/agents/" + key + "/register"
        self._posting, self._retry_token = (path, canonical_hash(payload)), token
        try:
            result = self._request("POST", path, payload)
        finally:
            self._posting = None
        if (result.get("agent_key") != key or result.get("version") != metadata["version"]
                or result.get("status") != "ACTIVE" or result.get("is_latest") is not True):
            raise FlowError("Registration response is unknown; reconcile the pinned Registry key before retrying")
        self._version_path(key, metadata["version"], result.get("uri", ""))
        state.update(state="ACKNOWLEDGED", version_uri=result["uri"])
        private_json(state_path, state, overwrite=True)
        return {**self.status(), "action": "register", "applied": True}

    def adopt(self, registry_key):
        key, binding = _uuid(registry_key), self._binding()
        state = self._state(binding, allow_redeployment=True)
        if state is not None and state.get("registry_key") != key:
            raise FlowError("A different Registry key is already pinned; no adoption was performed")
        current_interface = None
        if state is not None and state["binding"] != binding:
            try:
                current_interface = self._inspection(binding)
            except FlowError:
                raise FlowError("A fresh inspection of the current publication is required before re-adopting its Registry binding") from None
        matches = [row for row in self._rows()[0] if row["agent_key"] == key]
        if len(matches) != 1:
            raise FlowError("The explicit Registry key is not uniquely readable")
        version = _version(matches[0].get("active_version"))
        if matches[0].get("latest_version") != version or state is not None and state.get("version") != version:
            raise FlowError("Registry active/latest version differs from the requested or pinned version")
        path = self._version_path(key, version)
        body = self._request("GET", path)
        interface = self._interface(body.get("interface_contract"), binding)
        if current_interface is not None and current_interface != interface:
            raise FlowError("Current published card differs from the registered interface; re-adoption is refused")
        metadata = {field: body[field] for field in _METADATA if field in body}
        metadata.setdefault("blueprint", {})
        candidate = {"target_context": self._paths(binding)[0], "binding": binding, "registry_key": key,
                     "version": version, "display_name": body.get("display_name"),
                     "interface_sha256": canonical_hash(interface), "metadata_sha256": canonical_hash(metadata),
                     "version_uri": self.prefix + path, "state": "RECONCILED"}
        if state is not None and any(candidate[field] != state.get(field) for field in (
                "interface_sha256", "metadata_sha256", "display_name")):
            raise FlowError("Registry readback differs from the original pinned intent; adoption is refused")
        if (body.get("agent_key") != key or body.get("version") != version or body.get("status") != "ACTIVE"
                or body.get("is_latest") is not True or body.get("auth_key") != "none"
                or body.get("additional_metadata") != self._additional(binding)):
            raise FlowError("Registry adoption readback differs from the selected native identity or version")
        path = self._paths(binding)[2]
        private_json(path, candidate, overwrite=state is not None)
        return {"action": "adopt", "registry_key": key, "version": version, "registered": True,
                "readback_verified": True, "cloud_changed": False, "agent_hub_invocation_verified": False}
