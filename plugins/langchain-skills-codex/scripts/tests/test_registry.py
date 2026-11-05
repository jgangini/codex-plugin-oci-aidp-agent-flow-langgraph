import copy
import json
from pathlib import Path
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from aidp_agent_flow import registry
from aidp_agent_flow.project import FlowError, initialize, load_project


AGENT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
GATEWAY = "https://gateway.aidp.us-chicago-1.oci.oraclecloud.com"
CARD = GATEWAY + "/agentendpoint/" + AGENT + "/a2a/.well-known/agent-card.json"
PREFIX = "/20240831/dataLakes/platform-one/agent-registry/v1"


class FakeHTTP:
    def __init__(self):
        self.calls, self.agents, self.versions = [], [], {}
        self.inspect_auth, self.inspect_nested = None, False
        self.inspect_name = "Synthetic support"
        self.bad_card = self.timeout_register = self.bad_uri = self.readback_drift = False

    def close(self):
        pass

    def request(self, method, url, *, data, headers, timeout, allow_redirects):
        parsed = urlsplit(url)
        path = parsed.path.removeprefix(PREFIX)
        body = json.loads(data) if data is not None else None
        self.calls.append({"method": method, "path": path, "query": parse_qs(parsed.query),
                           "body": body, "headers": headers, "timeout": timeout, "redirects": allow_redirects})
        if method == "GET" and path == "/agents":
            query = parse_qs(parsed.query)
            limit, offset = int(query["limit"][0]), int(query["offset"][0])
            value = {"agents": self.agents[offset:offset + limit], "limit": limit, "offset": offset, "total": len(self.agents)}
        elif method == "POST" and path == "/agents/inspect-a2a":
            interface = {"kind": "a2a_aidp", "agent_card_url": CARD,
                         "agent_card": {"name": self.inspect_name, "version": "1.0.0",
                                        "url": GATEWAY + "/internal/agentendpoint/" + AGENT + "/a2a"}}
            if self.bad_card:
                interface["agent_card_url"] = CARD.replace(AGENT, OTHER)
            if self.inspect_nested:
                interface = {"status": "inspected", "interface_contract": interface}
            value = {"status": "inspected", "interface_contract": interface, "auth": self.inspect_auth}
        elif method == "POST" and path.endswith("/register"):
            if self.timeout_register:
                raise TimeoutError("DO-NOT-PRINT secret provider body")
            key = path.split("/")[2]
            version_path = PREFIX + "/agents/" + key + "/versions/" + body["version"]
            saved = {**copy.deepcopy(body), "agent_key": key, "status": "ACTIVE", "is_latest": True}
            saved["additional_metadata"].pop("cluster_key", None)
            if self.readback_drift:
                saved["additional_metadata"]["workspace_key"] = "foreign-workspace"
            self.versions[version_path.removeprefix(PREFIX)] = saved
            self.agents.append({"agent_key": key, "display_name": body["display_name"],
                                "active_version": body["version"], "latest_version": body["version"],
                                "auth_key": "DO-NOT-PRINT"})
            value = {"agent_key": key, "version": body["version"], "status": "ACTIVE", "is_latest": True,
                     "uri": version_path.replace("platform-one", "foreign-platform") if self.bad_uri else version_path}
        elif method == "GET" and path in self.versions:
            value = self.versions[path]
        else:
            raise AssertionError("Unexpected fake Registry request")
        return SimpleNamespace(status_code=200, content=json.dumps(value).encode())


class RegistryTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Synthetic Registry fixture", sync=False)
        _, self.config = load_project(self.root)
        self.config["native"] = {"endpoint": "https://aidp.us-chicago-1.oci.oraclecloud.com", "platform_id": "platform-one"}
        self.http = FakeHTTP()
        self.deployment = {"key": "production-one", "agentKey": AGENT, "agentComputeKey": "compute-one",
                           "deploymentType": "PROD", "deploymentVersion": "revision-one", "lifecycleState": "ACTIVE",
                           "endpointUrl": GATEWAY + "/agentendpoint/" + AGENT + "/chat"}
        self.native = SimpleNamespace(agent_key=AGENT, workspace="workspace-one", compute="compute-one",
                                      _agent=Mock(), _deployments=Mock(return_value=[self.deployment]))
        for patcher in (patch.object(registry, "load_project", return_value=(self.root, self.config)),
                        patch.object(registry, "NativeLifecycle", return_value=self.native)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = registry.Registry(self.root, self.config, transport=self.http)
        self.metadata = {"version": "1.0.0", "display_name": "Synthetic Support Acceptance", "description": "Synthetic only",
                         "tags": ["acceptance"], "labels": {}, "registry_metadata": {
                             "schema": "oasf.record@0.7.0", "record": {"authors": [], "domains": [], "skills": [], "locators": []}}}
        self.metadata_file = self.root / "registry-review.json"
        self.metadata_file.write_text(json.dumps(self.metadata), encoding="utf-8")

    def register(self):
        self.client.inspect()
        return self.client.register(self.metadata_file, apply=True)

    def test_inspect_uses_published_gateway_and_preserves_direct_interface(self):
        result = self.client.inspect()
        call = self.http.calls[-1]
        self.assertEqual(call["body"]["agent_card_url"], CARD)
        self.assertEqual(call["body"]["additional_metadata"], {"cluster_key": "compute-one", "compute_id": "compute-one"})
        artifact = json.loads(Path(result["artifact"]).read_text())
        self.assertEqual(set(artifact["interface_contract"]), {"kind", "agent_card_url", "agent_card"})
        self.assertFalse(call["redirects"])
        self.assertFalse(result["registered"])

    def test_relative_review_metadata_uses_selected_project(self):
        result = self.client.register("registry-review.json", apply=False)
        self.assertFalse(result["applied"])
        self.assertFalse(any(call["method"] == "POST" for call in self.http.calls))

    def test_wrong_card_extra_nesting_and_external_auth_are_rejected(self):
        for field, value in (("bad_card", True), ("inspect_nested", True), ("inspect_auth", {"token": "DO-NOT-PRINT"})):
            with self.subTest(field=field):
                setattr(self.http, field, value)
                with self.assertRaises(FlowError):
                    self.client.inspect()
                setattr(self.http, field, None if field == "inspect_auth" else False)

    def test_wrong_gateway_agent_or_no_active_publication_never_inspects(self):
        for endpoint in ("https://example.invalid/agentendpoint/" + AGENT + "/chat",
                         GATEWAY + "/agentendpoint/" + OTHER + "/chat", GATEWAY + "/agentendpoint/" + AGENT + "/chat?token=x"):
            self.deployment["endpointUrl"] = endpoint
            with self.assertRaises(FlowError):
                self.client.inspect()
        self.assertEqual(self.http.calls, [])
        self.native._deployments.return_value = []
        with self.assertRaises(FlowError):
            self.client.inspect()

    def test_dry_plan_does_not_post_or_pin_an_identity(self):
        result = self.client.register(self.metadata_file)
        self.assertFalse(result["applied"])
        self.assertFalse(any(call["method"] == "POST" for call in self.http.calls))
        self.assertFalse(self.client._paths(self.client._binding())[2].exists())

    def test_create_pins_key_direct_interface_and_signed_version_readback(self):
        result = self.register()
        self.assertTrue(result["readback_verified"])
        self.assertFalse(result["agent_hub_invocation_verified"])
        post = next(call for call in self.http.calls if call["path"].endswith("/register"))
        payload = post["body"]
        self.assertEqual(payload["auth_key"], "none")
        self.assertEqual(set(payload["interface_contract"]), {"kind", "agent_card_url", "agent_card"})
        self.assertEqual(payload["additional_metadata"], {"agent_flow_key": AGENT, "workspace_key": "workspace-one",
                                                         "compute_id": "compute-one"})
        self.assertEqual(set(next(iter(self.http.versions.values()))["additional_metadata"]),
                         {"agent_flow_key", "workspace_key", "compute_id"})
        self.assertNotEqual(result["registry_key"], AGENT)
        self.assertTrue(post["headers"]["opc-retry-token"])
        state_path = self.client._paths(self.client._binding())[2]
        state = json.loads(state_path.read_text())
        self.assertEqual(state["state"], "RECONCILED")
        self.assertEqual(state["registry_key"], result["registry_key"])
        count = len([call for call in self.http.calls if call["path"].endswith("/register")])
        self.assertFalse(self.client.register(self.metadata_file, apply=True)["applied"])
        self.assertEqual(count, len([call for call in self.http.calls if call["path"].endswith("/register")]))

    def test_unknown_write_blocks_retries_and_changed_version_uuid_escape(self):
        self.client.inspect()
        self.http.timeout_register = True
        with self.assertRaises(FlowError) as caught:
            self.client.register(self.metadata_file, apply=True)
        self.assertNotIn("DO-NOT-PRINT", str(caught.exception))
        state_path = self.client._paths(self.client._binding())[2]
        state = json.loads(state_path.read_text())
        self.assertEqual(state["state"], "SUBMITTED")
        for version in ("1.0.0", "2.0.0"):
            self.metadata["version"] = version
            self.metadata_file.write_text(json.dumps(self.metadata))
            fresh = registry.Registry(self.root, self.config, transport=self.http)
            with self.assertRaises(FlowError):
                fresh.register(self.metadata_file, apply=True)
        self.assertEqual(1, len([call for call in self.http.calls if call["path"].endswith("/register")]))
        self.assertEqual(state["registry_key"], json.loads(state_path.read_text())["registry_key"])

    def test_version_uri_namespace_guard_prevents_foreign_follow(self):
        self.http.bad_uri = True
        with self.assertRaisesRegex(FlowError, "URI escaped"):
            self.register()
        self.assertFalse(any("foreign-platform" in call["path"] for call in self.http.calls))
        with self.assertRaises(FlowError):
            self.client.status()

    def test_unknown_acknowledged_identity_keeps_original_intent_uncertain(self):
        self.client.inspect()
        request = self.client._request
        def changed_response(method, path, payload=None):
            result = request(method, path, payload)
            return {**result, "agent_key": OTHER} if path.endswith("/register") else result
        with patch.object(self.client, "_request", side_effect=changed_response), self.assertRaisesRegex(FlowError, "response is unknown"):
            self.client.register(self.metadata_file, apply=True)
        state = json.loads(self.client._paths(self.client._binding())[2].read_text())
        self.assertEqual(state["state"], "SUBMITTED")
        self.assertNotEqual(state["registry_key"], OTHER)
        with self.assertRaises(FlowError):
            self.client.register(self.metadata_file, apply=True)
        self.assertEqual(1, len([call for call in self.http.calls if call["path"].endswith("/register")]))

    def test_changed_inspection_artifact_prevents_registration(self):
        result = self.client.inspect()
        artifact = Path(result["artifact"])
        changed = json.loads(artifact.read_text())
        changed["interface_contract"]["agent_card"]["name"] = "Changed after inspection"
        artifact.write_text(json.dumps(changed))
        with self.assertRaisesRegex(FlowError, "inspection"):
            self.client.register(self.metadata_file, apply=True)
        self.assertFalse(any(call["path"].endswith("/register") for call in self.http.calls))

    def test_native_identity_or_version_drift_refuses_success_without_second_post(self):
        self.http.readback_drift = True
        with self.assertRaisesRegex(FlowError, "readback differs"):
            self.register()
        with self.assertRaises(FlowError):
            self.client.status()
        self.assertEqual(1, len([call for call in self.http.calls if call["path"].endswith("/register")]))
        self.http.agents[0]["latest_version"] = "2.0.0"
        with self.assertRaisesRegex(FlowError, "version differs"):
            self.client.status()

    def test_reviewed_metadata_drift_refuses_status_success(self):
        self.register()
        for body in self.http.versions.values():
            body["description"] = "Different from the reviewed description"
        with self.assertRaisesRegex(FlowError, "metadata differs"):
            self.client.status()

    def test_existing_name_without_owned_state_refuses_duplicate(self):
        self.http.agents = [{"agent_key": OTHER, "display_name": self.metadata["display_name"],
                             "active_version": "1.0.0", "latest_version": "1.0.0"}]
        with self.assertRaisesRegex(FlowError, "adoption"):
            self.client.register(self.metadata_file, apply=True)
        self.assertFalse(any(call["method"] == "POST" for call in self.http.calls))

    def test_adopt_uses_only_get_and_pins_after_native_readback(self):
        result = self.register()
        state_path = self.client._paths(self.client._binding())[2]
        state_path.unlink()
        self.http.calls.clear()
        adopted = self.client.adopt(result["registry_key"])
        self.assertTrue(adopted["readback_verified"])
        self.assertFalse(adopted["cloud_changed"])
        self.assertTrue(all(call["method"] == "GET" for call in self.http.calls))
        self.assertTrue(self.client.status()["registered"])
        with self.assertRaisesRegex(FlowError, "different Registry key"):
            self.client.adopt(OTHER)

    def test_adopt_rejects_foreign_native_identity_before_local_binding(self):
        result = self.register()
        state_path = self.client._paths(self.client._binding())[2]
        state_path.unlink()
        body = next(iter(self.http.versions.values()))
        expected = copy.deepcopy(body["additional_metadata"])
        for field in ("agent_flow_key", "workspace_key", "compute_id"):
            with self.subTest(field=field):
                body["additional_metadata"] = {**expected, field: OTHER}
                with self.assertRaisesRegex(FlowError, "identity or version"):
                    self.client.adopt(result["registry_key"])
                self.assertFalse(state_path.exists())

    def test_persisted_canonical_metadata_supports_adoption_without_cluster_alias(self):
        result = self.register()
        self.client._paths(self.client._binding())[2].unlink()
        persisted = next(iter(self.http.versions.values()))["additional_metadata"]
        self.assertNotIn("cluster_key", persisted)
        self.assertEqual(persisted, {"agent_flow_key": AGENT, "compute_id": "compute-one", "workspace_key": "workspace-one"})
        self.assertTrue(self.client.adopt(result["registry_key"])["readback_verified"])
        self.assertTrue(self.client.status()["registered"])

    def test_redeployment_requires_explicit_same_key_adoption_and_fresh_inspection(self):
        result = self.register()
        self.deployment.update(key="production-two", deploymentVersion="revision-two")
        with self.assertRaisesRegex(FlowError, "binding differs"):
            self.client.status()
        with self.assertRaisesRegex(FlowError, "fresh inspection"):
            self.client.adopt(result["registry_key"])
        self.client.inspect()
        self.http.calls.clear()
        self.assertTrue(self.client.adopt(result["registry_key"])["readback_verified"])
        self.assertTrue(all(call["method"] == "GET" for call in self.http.calls))
        self.assertTrue(self.client.status()["registered"])
        state = json.loads(self.client._paths(self.client._binding())[2].read_text())
        self.assertEqual(state["binding"]["deployment_key"], "production-two")
        self.assertEqual(state["binding"]["deployment_version"], "revision-two")

    def test_redeployment_cannot_adopt_changed_card_or_compute_identity(self):
        result = self.register()
        self.deployment.update(key="production-two", deploymentVersion="revision-two")
        self.http.inspect_name = "Changed published card"
        self.client.inspect()
        with self.assertRaisesRegex(FlowError, "card differs"):
            self.client.adopt(result["registry_key"])
        self.native.compute = "another-compute"
        self.client.inspect()
        with self.assertRaisesRegex(FlowError, "binding differs"):
            self.client.adopt(result["registry_key"])
        state = json.loads(self.client._paths(self.client._binding())[2].read_text())
        self.assertEqual(state["binding"]["compute_key"], "compute-one")
        self.assertEqual(state["binding"]["deployment_key"], "production-one")

    def test_collection_pages_metadata_allowlist_and_total_bounds(self):
        self.http.agents = [{"agent_key": str(uuid4()), "display_name": "Fixture " + str(index),
                             "active_version": "1.0.0", "latest_version": "1.0.0", "token": "DO-NOT-PRINT"}
                            for index in range(3)]
        result = self.client.list(limit=2)
        self.assertEqual(result["pageCount"], 2)
        self.assertEqual(len(result["agents"]), 3)
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))
        with patch.object(registry, "_MAX_PAGES", 1), self.assertRaisesRegex(FlowError, "page bound"):
            self.client.list(limit=2)
        with patch.object(registry, "_MAX_ITEMS", 1), self.assertRaisesRegex(FlowError, "bounded"):
            self.client.list()

    def test_repeated_collection_identity_refuses_registration(self):
        row = {"agent_key": OTHER, "display_name": "Duplicate", "active_version": "1.0.0", "latest_version": "1.0.0"}
        self.http.agents = [row, copy.deepcopy(row)]
        with self.assertRaisesRegex(FlowError, "repeated"):
            self.client.list(limit=1)

    def test_incomplete_offset_and_changed_total_fail_closed(self):
        row = {"agent_key": OTHER, "display_name": "Fixture", "active_version": "1.0.0", "latest_version": "1.0.0"}
        cases = ([{"agents": [], "limit": 1, "offset": 0, "total": 1}],
                 [{"agents": [], "limit": 1, "offset": 1, "total": 0}],
                 [{"agents": [row], "limit": 1, "offset": 0, "total": 2},
                  {"agents": [], "limit": 1, "offset": 1, "total": 3}])
        for bodies in cases:
            responses = [SimpleNamespace(status_code=200, content=json.dumps(body).encode()) for body in bodies]
            with self.subTest(bodies=bodies), patch.object(self.http, "request", side_effect=responses), self.assertRaises(FlowError):
                self.client.list(limit=1)

    def test_metadata_cannot_supply_auth_identity_or_nested_contract(self):
        for key, value in (("auth_key", "none"), ("additional_metadata", {}), ("interface_contract", {}), ("password", "secret")):
            self.metadata_file.write_text(json.dumps({**self.metadata, key: value}))
            with self.assertRaises(FlowError):
                self.client.register(self.metadata_file, apply=True)
        self.assertEqual(self.http.calls, [])

    def test_hub_link_returns_only_configured_verified_portal_after_active_status(self):
        active = {"registered": True, "status": "ACTIVE", "readback_verified": True,
                  "registry_key": OTHER, "version": "1.0.0"}
        for url in ("https://instanceagenthub.datalake.oci.oraclecloud.com/",
                    "https://instanceagenthub.datalake.oci.oraclecloud.com/static/ah/",
                    "https://instanceagenthub.datalake.oci.oraclecloud.com/static/ah/#?tenant=ocid1.tenancy.example&domain=Default"):
            with self.subTest(url=url):
                self.config["native"]["agent_hub_url"] = url
                with patch.object(self.client, "status", return_value=active) as status:
                    result = self.client.hub_link()
                status.assert_called_once_with()
                self.assertEqual(result["url"], url)
                self.assertEqual(result["link_type"], "agent_hub_portal")
                self.assertTrue(result["authentication_required"])
                self.assertFalse(result["client_invocation_verified"])
        self.assertEqual(self.http.calls, [])

    def test_hub_link_missing_configuration_does_not_invent_a_url(self):
        active = {"registered": True, "status": "ACTIVE", "readback_verified": True,
                  "registry_key": OTHER, "version": "1.0.0"}
        with patch.object(self.client, "status", return_value=active) as status:
            with self.assertRaisesRegex(FlowError, "Set native.agent_hub_url"):
                self.client.hub_link()
        status.assert_called_once_with()

    def test_hub_link_rejects_inactive_unverified_or_missing_registration_first(self):
        self.config["native"]["agent_hub_url"] = "https://instanceagenthub.datalake.oci.oraclecloud.com/"
        for registered in ({"registered": False},
                           {"registered": True, "status": "INACTIVE", "readback_verified": True},
                           {"registered": True, "status": "ACTIVE", "readback_verified": False}):
            with self.subTest(registered=registered), patch.object(self.client, "status", return_value=registered):
                with self.assertRaisesRegex(FlowError, "verified ACTIVE"):
                    self.client.hub_link()
        with patch.object(self.client, "status", side_effect=FlowError("Native registration readback failed")):
            with self.assertRaisesRegex(FlowError, "readback failed"):
                self.client.hub_link()
        self.assertEqual(self.http.calls, [])

    def test_hub_link_rejects_foreign_destinations_paths_queries_and_fragments(self):
        portal = "https://instanceagenthub.datalake.oci.oraclecloud.com"
        active = {"registered": True, "status": "ACTIVE", "readback_verified": True,
                  "registry_key": OTHER, "version": "1.0.0"}
        invalid = ("http://instanceagenthub.datalake.oci.oraclecloud.com/",
                   "https://instanceagenthub.datalake.oci.oraclecloud.com.evil.test/",
                   "https://agenthub.datalake.oci.oraclecloud.com/", "https://example.invalid/",
                   portal.replace("https://", "https://user:password@") + "/", portal + ":443/",
                   portal + "/another-app/", portal + "/?tenant=example", portal + "/?",
                   portal + "/#agent/" + AGENT, portal + "/#tenant=example&domain=Default",
                   portal + "/#?tenant=example&domain=Default&token=value", portal + "/#?tenant=example&tenant=other",
                   portal + "/#?tenant=&domain=Default", portal + "/#?tenant=example&domain=%GG",
                   portal + "/#?tenant=example&domain=%0A", portal + "/#?tenant=example&domain=Default%26other%3Dvalue")
        with patch.object(self.client, "status", return_value=active):
            for url in invalid:
                with self.subTest(url=url):
                    self.config["native"]["agent_hub_url"] = url
                    with self.assertRaises(FlowError):
                        self.client.hub_link()
        self.assertEqual(self.http.calls, [])


if __name__ == "__main__":
    unittest.main()
