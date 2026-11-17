import hashlib
import io
import json
import os
import types
import unittest
from unittest.mock import Mock, patch

from aidp_agent_flow import credential_store as store


def summary(name="AgentApiKey", kind="SERVICE_ACCOUNT", key="credential-1", state="ACTIVE"):
    return {"key": key, "displayName": name, "credentialType": kind, "lifeCycleState": state}


def detail(item, **fields):
    return {"key": item["key"], "displayName": item["displayName"], "type": item["credentialType"],
            "lifecycleState": item["lifeCycleState"],
            "credentialDetails": {"credentialType": item["credentialType"], **fields}}


IDENTITY = {"userId": "ocid1.user.test", "fingerprint": ":".join(["12"] * 16),
            "tenancy": "ocid1.tenancy.test", "region": "us-ashburn-1", "isReadOnly": False}
RUNTIME_IDENTITY = {"tenancy": IDENTITY["tenancy"], "user": IDENTITY["userId"],
                    "fingerprint": IDENTITY["fingerprint"], "region": IDENTITY["region"]}


def token_detail(item, key="token", value="synthetic"):
    return detail(item, secretTokenPair=[{"secretKey": key, "secretValue": value}])


def runtime_detail(item, identity=None):
    pairs = [{"secretKey": key, "secretValue": value} for key, value in (identity or RUNTIME_IDENTITY).items()]
    return detail(item, secretTokenPair=pairs + [{"secretKey": "private_key", "secretValue": "DO-NOT-PRINT"}])


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.operations = []
        self.completed = []
        self.deferred = []

    def request(self, method, path, body=None, headers=None):
        self.calls.append((method, path, body, headers))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def prepare_operation(self, operation_key, public_identity):
        self.operations.append((operation_key, public_identity))
        return "stable-operation-token"

    def complete_operation(self, operation_key, public_identity, credential_key):
        self.completed.append((operation_key, public_identity, credential_key))

    def defer_operation(self, operation_key, public_identity, credential_key):
        self.deferred.append((operation_key, public_identity, credential_key))


class CredentialStoreTests(unittest.TestCase):
    def test_paginates_exact_name_and_allowlists_outputs(self):
        first = {**summary(), "privateKey": "DO-NOT-PRINT", "credentialDetails": {"token": "DO-NOT-PRINT"}}
        second = summary(key="credential-2")
        client = FakeClient([({"items": [first]}, {"OPC-NEXT-PAGE": "a+b/?"}), ({"items": [second]}, {})])
        result = store.list_credentials(client, "AgentApiKey")
        self.assertTrue(result["complete"])
        self.assertEqual(result["pageCount"], 2)
        self.assertEqual(result["items"], [summary(), second])
        self.assertIn("displayName=AgentApiKey", client.calls[0][1])
        self.assertIn("page=a%2Bb%2F%3F", client.calls[1][1])
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))

    def test_duplicate_names_across_pages_prevent_create(self):
        client = FakeClient([({"items": [summary()]}, {"opc-next-page": "next"}),
                             ({"items": [summary(key="other")]}, {})])
        with self.assertRaisesRegex(store.CredentialStoreError, "Multiple"):
            store.ensure_service_account(client, "AgentApiKey", "unread-config", apply=True)
        self.assertEqual([c[0] for c in client.calls], ["GET", "GET"])

    def test_type_collision_and_nonactive_fail_closed(self):
        for item in [summary(kind="SECRET_TOKEN"), summary(state="CREATING"), summary(state="DELETING")]:
            with self.subTest(item=item):
                client = FakeClient([({"items": [item]}, {})])
                with self.assertRaises(store.CredentialStoreError):
                    store.ensure_service_account(client, "AgentApiKey", "unread-config", apply=True)
                self.assertFalse(client.operations)

    def test_dry_run_never_loads_config_key_or_token(self):
        client = FakeClient([({"items": []}, {})])
        with patch.object(store, "_service_account_config", side_effect=AssertionError("read config")):
            result = store.ensure_service_account(client, "AgentApiKey", "unread-config")
        self.assertEqual(result["action"], "create")
        client = FakeClient([({"items": []}, {})])
        with patch.object(store.os, "environ", Mock(get=Mock(side_effect=AssertionError("read token")))):
            result = store.ensure_secret_token(client, "AgentToken", "EXAMPLE_TEST_TOKEN")
        self.assertEqual(result["action"], "create")
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(client.operations)

    def test_existing_service_account_dry_run_requires_later_validation(self):
        client = FakeClient([({"items": [summary()]}, {})])
        result = store.ensure_service_account(client, "AgentApiKey", "unread-config")
        self.assertEqual(result["action"], "validate-existing")
        self.assertIn("validationPending", result)

    def test_reuses_existing_service_account_only_after_public_identity_check(self):
        client = FakeClient([({"items": [summary()]}, {}), (detail(summary(), **IDENTITY, privateKey="HIDDEN"), {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)), patch.object(store, "_private_key", side_effect=AssertionError("read key")):
            result = store.ensure_service_account(client, "AgentApiKey", "selected-config", apply=True)
        self.assertEqual(result["action"], "reused")
        self.assertFalse(result["secretValueVerified"])
        self.assertNotIn("HIDDEN", json.dumps(result))
        self.assertFalse(client.operations)

    def test_service_account_mismatched_identity_or_changed_metadata_refuses_reuse(self):
        for changed in [detail(summary(), **{**IDENTITY, "userId": "different"}),
                        detail(summary(key="different"), **IDENTITY),
                        detail(summary(state="UPDATING"), **IDENTITY)]:
            with self.subTest(changed=changed):
                client = FakeClient([({"items": [summary()]}, {}), (changed, {})])
                with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)):
                    with self.assertRaises(store.CredentialStoreError):
                        store.ensure_service_account(client, "AgentApiKey", "selected-config", apply=True)

    def test_token_existing_dry_run_does_not_get_secret_details(self):
        item = summary(name="AgentToken", kind="SECRET_TOKEN")
        client = FakeClient([({"items": [item]}, {})])
        result = store.ensure_secret_token(client, "AgentToken", "MISSING_TOKEN")
        self.assertEqual(result["action"], "validate-existing")
        self.assertIn("validationPending", result)
        self.assertEqual(len(client.calls), 1)

    def test_token_apply_creates_from_environment_with_readback_and_no_output_secret(self):
        item = summary(name="AgentToken", kind="SECRET_TOKEN")
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": [item]}, {}),
                             (token_detail(item, value="DO-NOT-PRINT"), {})])
        with patch.dict(os.environ, {"EXAMPLE_TEST_TOKEN": "DO-NOT-PRINT"}):
            result = store.ensure_secret_token(client, "AgentToken", "EXAMPLE_TEST_TOKEN", apply=True)
        self.assertEqual(result["action"], "created")
        post = client.calls[1]
        self.assertEqual(post[0], "POST")
        self.assertEqual(post[2]["credentialDetails"], {"credentialType": "SECRET_TOKEN", "secretTokenPair": [{"secretKey": "token", "secretValue": "DO-NOT-PRINT"}]})
        self.assertEqual(post[3], {"opc-retry-token": "stable-operation-token"})
        self.assertEqual(client.completed[0][2], item["key"])
        self.assertNotIn("DO-NOT-PRINT", json.dumps([result, client.operations, client.completed]))

    def test_service_account_creation_uses_current_envelope_and_verifies_readback(self):
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": [summary()]}, {}),
                             (detail(summary(), **IDENTITY), {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)), patch.object(store, "_private_key", return_value="SYNTHETIC-PEM"):
            result = store.ensure_service_account(client, "AgentApiKey", "selected-config", apply=True)
        body = client.calls[1][2]
        self.assertEqual(body["type"], "SERVICE_ACCOUNT")
        self.assertEqual(body["credentialDetails"]["userId"], IDENTITY["userId"])
        self.assertEqual(body["credentialDetails"]["privateKey"], "SYNTHETIC-PEM")
        self.assertEqual(result["credential"], summary())
        self.assertNotIn("SYNTHETIC-PEM", json.dumps([result, client.operations, client.completed]))

    def test_create_readback_mismatch_does_not_complete_operation(self):
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": [summary()]}, {}),
                             (detail(summary(), **{**IDENTITY, "region": "different"}), {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)), patch.object(store, "_private_key", return_value="SYNTHETIC-PEM"):
            with self.assertRaises(store.CredentialStoreError):
                store.ensure_service_account(client, "AgentApiKey", "selected-config", apply=True)
        self.assertFalse(client.completed)

    def test_uncertain_post_is_not_retried_or_exposed(self):
        client = FakeClient([({"items": []}, {}), RuntimeError("request body DO-NOT-PRINT")])
        with patch.dict(os.environ, {"EXAMPLE_TEST_TOKEN": "DO-NOT-PRINT"}):
            with self.assertRaises(store.CredentialStoreError) as caught:
                store.ensure_secret_token(client, "AgentToken", "EXAMPLE_TEST_TOKEN", apply=True)
        self.assertNotIn("DO-NOT-PRINT", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual([c[0] for c in client.calls], ["GET", "POST"])
        self.assertFalse(client.completed)

    def test_missing_protected_ledger_refuses_post(self):
        client = FakeClient([({"items": []}, {})])
        client.prepare_operation = Mock(side_effect=RuntimeError("sensitive context"))
        with patch.dict(os.environ, {"EXAMPLE_TEST_TOKEN": "synthetic"}):
            with self.assertRaisesRegex(store.CredentialStoreError, "protected create operation"):
                store.ensure_secret_token(client, "AgentToken", "EXAMPLE_TEST_TOKEN", apply=True)
        self.assertEqual(len(client.calls), 1)

    def test_no_active_resource_readback_leaves_operation_uncertain(self):
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": []}, {})])
        with patch.dict(os.environ, {"EXAMPLE_TEST_TOKEN": "synthetic"}):
            with self.assertRaisesRegex(store.CredentialStoreError, "uncertain"):
                store.ensure_secret_token(client, "AgentToken", "EXAMPLE_TEST_TOKEN", apply=True)
        self.assertFalse(client.completed)

    def test_empty_token_fails_before_post(self):
        client = FakeClient([({"items": []}, {})])
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(store.CredentialStoreError, "nonempty token"):
                store.ensure_secret_token(client, "AgentToken", "MISSING_TOKEN", apply=True)
        self.assertEqual(len(client.calls), 1)

    def test_repeated_or_exhausted_pagination_refuses_ensure(self):
        client = FakeClient([({"items": []}, {"opc-next-page": "same"}), ({"items": []}, {"opc-next-page": "same"})])
        with self.assertRaisesRegex(store.CredentialStoreError, "pagination"):
            store.list_credentials(client)
        client = FakeClient([({"items": []}, {"opc-next-page": "first"}), ({"items": []}, {"opc-next-page": "second"})])
        with patch.object(store, "_MAX_PAGES", 2):
            with self.assertRaisesRegex(store.CredentialStoreError, "incomplete"):
                store.ensure_secret_token(client, "AgentToken", "MISSING_TOKEN", apply=True)
        self.assertEqual(len(client.calls), 2)

    def test_malformed_state_or_page_size_is_rejected(self):
        for limit in (0, 1001, True, "100"):
            with self.subTest(limit=limit), self.assertRaises(store.CredentialStoreError):
                store.list_credentials(FakeClient([]), limit=limit)
        client = FakeClient([({"items": [{**summary(), "lifeCycleState": None}]}, {})])
        with self.assertRaises(store.CredentialStoreError):
            store.list_credentials(client)
        client = FakeClient([({"items": [{**summary(), "credentialType": {"unexpected": "DO-NOT-PRINT"}}]}, {})])
        with self.assertRaises(store.CredentialStoreError) as caught:
            store.list_credentials(client)
        self.assertNotIn("DO-NOT-PRINT", str(caught.exception))

    def test_filtered_listing_counts_scanned_records_for_bound(self):
        client = FakeClient([({"items": [summary(name="Unrelated")]}, {"opc-next-page": "next"}),
                             ({"items": [summary(name="Unrelated")]}, {})])
        with patch.object(store, "_MAX_ITEMS", 1):
            with self.assertRaisesRegex(store.CredentialStoreError, "item count"):
                store.list_credentials(client, name="AgentApiKey")

    def test_bad_retry_token_or_ledger_completion_failure_remains_safe(self):
        item = summary(name="AgentToken", kind="SECRET_TOKEN")
        client = FakeClient([({"items": []}, {})])
        client.prepare_operation = Mock(return_value="invalid token DO-NOT-PRINT")
        with patch.dict(os.environ, {"EXAMPLE_TEST_TOKEN": "synthetic"}):
            with self.assertRaisesRegex(store.CredentialStoreError, "stable retry token") as caught:
                store.ensure_secret_token(client, "AgentToken", "EXAMPLE_TEST_TOKEN", apply=True)
        self.assertNotIn("DO-NOT-PRINT", str(caught.exception))
        self.assertEqual(len(client.calls), 1)
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": [item]}, {}), (token_detail(item), {})])
        client.complete_operation = Mock(side_effect=RuntimeError("DO-NOT-PRINT"))
        with patch.dict(os.environ, {"EXAMPLE_TEST_TOKEN": "synthetic"}):
            with self.assertRaisesRegex(store.CredentialStoreError, "reconcile before retrying") as caught:
                store.ensure_secret_token(client, "AgentToken", "EXAMPLE_TEST_TOKEN", apply=True)
        self.assertNotIn("DO-NOT-PRINT", str(caught.exception))

    def test_token_apply_reuses_only_verified_single_pair_key(self):
        item = summary(name="AgentToken", kind="SECRET_TOKEN")
        client = FakeClient([({"items": [item]}, {}), (token_detail(item), {})])
        result = store.ensure_secret_token(client, "AgentToken", "MISSING_TOKEN", apply=True)
        self.assertEqual(result["action"], "reused")
        self.assertFalse(result["secretValueVerified"])
        for response in (detail(item), token_detail(item, key="different"),
                         detail(item, secretTokenPair=[{"secretKey": "token"}, {"secretKey": "token"}])):
            with self.subTest(response=response):
                client = FakeClient([({"items": [item]}, {}), (response, {})])
                with self.assertRaisesRegex(store.CredentialStoreError, "key layout"):
                    store.ensure_secret_token(client, "AgentToken", "MISSING_TOKEN", apply=True)

    def test_runtime_plan_never_opens_config_or_gets_secret_details(self):
        item = summary(name="AidpRuntime", kind="SECRET_TOKEN")
        client = FakeClient([({"items": [item]}, {})])
        with patch.object(store, "_service_account_config", side_effect=AssertionError("read config")):
            result = store.ensure_runtime_credential(client, "AidpRuntime", "unread-config")
        self.assertEqual(result["action"], "validate-existing")
        self.assertEqual(result["layout"], "aidputils-runtime")
        self.assertEqual(len(client.calls), 1)

    def test_runtime_reuses_shared_entry_only_after_public_identity_check(self):
        item = summary(name="AidpRuntime", kind="SECRET_TOKEN")
        client = FakeClient([({"items": [item]}, {}), (runtime_detail(item), {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)), patch.object(store, "_private_key", side_effect=AssertionError("read key")):
            result = store.ensure_runtime_credential(client, "AidpRuntime", "selected-config", apply=True)
        self.assertEqual(result["action"], "reused")
        self.assertFalse(client.operations)
        self.assertEqual([call[0] for call in client.calls], ["GET", "GET"])
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))

    def test_runtime_unknown_mismatched_or_duplicate_layout_refuses_shared_entry(self):
        item = summary(name="AidpRuntime", kind="SECRET_TOKEN")
        valid = runtime_detail(item)
        duplicate = detail(item, secretTokenPair=valid["credentialDetails"]["secretTokenPair"][:-1] + [{"secretKey": "user", "secretValue": "duplicate"}])
        for response in (detail(item), token_detail(item), duplicate,
                         runtime_detail(item, {**RUNTIME_IDENTITY, "user": "***"}),
                         runtime_detail(item, {**RUNTIME_IDENTITY, "region": "different"})):
            with self.subTest(response=response):
                client = FakeClient([({"items": [item]}, {}), (response, {})])
                with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)):
                    with self.assertRaises(store.CredentialStoreError):
                        store.ensure_runtime_credential(client, "AidpRuntime", "selected-config", apply=True)
                self.assertFalse(client.operations)
                self.assertEqual([call[0] for call in client.calls], ["GET", "GET"])

    def test_runtime_creation_preserves_native_five_pair_layout_and_redacts_outputs(self):
        item = summary(name="AgentRuntime", kind="SECRET_TOKEN")
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": [item]}, {}), (runtime_detail(item), {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)), patch.object(store, "_private_key", return_value="SYNTHETIC-PEM"):
            result = store.ensure_runtime_credential(client, "AgentRuntime", "selected-config", apply=True)
        body = client.calls[1][2]
        self.assertEqual(body["type"], "SECRET_TOKEN")
        pairs = {pair["secretKey"]: pair["secretValue"] for pair in body["credentialDetails"]["secretTokenPair"]}
        self.assertEqual(set(pairs), {"tenancy", "user", "fingerprint", "region", "private_key"})
        self.assertEqual(pairs["user"], IDENTITY["userId"])
        self.assertEqual(pairs["private_key"], "SYNTHETIC-PEM")
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["layout"], "aidputils-runtime")
        self.assertNotIn("SYNTHETIC-PEM", json.dumps([result, client.operations, client.completed]))
        self.assertEqual(len(client.completed), 1)

    def test_runtime_create_hidden_identity_readback_remains_uncertain(self):
        item = summary(name="AgentRuntime", kind="SECRET_TOKEN")
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": [item]}, {}),
                             (runtime_detail(item, {**RUNTIME_IDENTITY, "tenancy": "***"}), {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)), patch.object(store, "_private_key", return_value="SYNTHETIC-PEM"):
            with self.assertRaisesRegex(store.CredentialStoreError, "public identity"):
                store.ensure_runtime_credential(client, "AgentRuntime", "selected-config", apply=True)
        self.assertFalse(client.completed)

    def test_runtime_create_omitted_values_records_created_pending_native_proof(self):
        item = summary(name="AgentRuntime", kind="SECRET_TOKEN")
        hidden = detail(item, secretTokenPair=[{"secretKey": key} for key in [*RUNTIME_IDENTITY, "private_key"]])
        client = FakeClient([({"items": []}, {}), ({}, {}), ({"items": [item]}, {}), (hidden, {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)), patch.object(store, "_private_key", return_value="SYNTHETIC-PEM"):
            result = store.ensure_runtime_credential(client, "AgentRuntime", "selected-config", apply=True)
        self.assertEqual(result["action"], "created-pending-native-verification")
        self.assertTrue(result["applied"])
        self.assertTrue(result["nativeVerificationRequired"])
        self.assertFalse(result["publicIdentityVerified"])
        self.assertFalse(client.completed)
        self.assertEqual(len(client.deferred), 1)
        self.assertEqual(sum(call[0] == "POST" for call in client.calls), 1)
        reused = FakeClient([({"items": [item]}, {}), (hidden, {})])
        with patch.object(store, "_service_account_config", return_value=({}, IDENTITY)):
            with self.assertRaises(store.CredentialStoreError):
                store.ensure_runtime_credential(reused, "AgentRuntime", "selected-config", apply=True)
        self.assertFalse(any(call[0] == "POST" for call in reused.calls))

    def test_sdk_uses_selected_profile_and_rejects_session_token(self):
        config = {"user": IDENTITY["userId"], "fingerprint": IDENTITY["fingerprint"],
                  "tenancy": IDENTITY["tenancy"], "region": IDENTITY["region"], "key_file": "unused-key"}
        sdk = types.SimpleNamespace(config=types.SimpleNamespace(from_file=Mock(return_value=config), validate_config=Mock()))
        with patch.dict("sys.modules", {"oci": sdk}):
            actual, identity = store._service_account_config("selected-config", "SELECTED")
            self.assertEqual(actual, config)
            self.assertEqual(identity, IDENTITY)
            sdk.config.from_file.assert_called_once_with(file_location="selected-config", profile_name="SELECTED")
            config["security_token_file"] = "session-token-path"
            with self.assertRaisesRegex(store.CredentialStoreError, "session-token"):
                store._service_account_config("selected-config", "SELECTED")

    def test_private_key_fingerprint_matches_before_in_memory_serialization(self):
        public_der = b"synthetic-public-der"
        digest = hashlib.md5(public_der, usedforsecurity=False).hexdigest()
        identity = {**IDENTITY, "fingerprint": ":".join(digest[i:i + 2] for i in range(0, 32, 2))}
        key = Mock()
        key.public_key.return_value.public_bytes.return_value = public_der
        key.private_bytes.return_value = b"SYNTHETIC-DECRYPTED-PEM"
        sdk = types.SimpleNamespace(signer=types.SimpleNamespace(load_private_key=Mock(return_value=key)))
        serialization = types.SimpleNamespace(Encoding=types.SimpleNamespace(DER="DER", PEM="PEM"),
            PublicFormat=types.SimpleNamespace(SubjectPublicKeyInfo="SPKI"),
            PrivateFormat=types.SimpleNamespace(PKCS8="PKCS8"), NoEncryption=lambda: None)
        primitives = types.ModuleType("cryptography.hazmat.primitives")
        primitives.serialization = serialization
        config = {"key_file": "synthetic-key.pem", "pass_phrase": "synthetic-passphrase"}
        with patch.dict("sys.modules", {"oci": sdk, "cryptography.hazmat.primitives": primitives}), patch.object(store.Path, "open", side_effect=lambda *args: io.BytesIO(b"SYNTHETIC-INPUT-PEM")):
            self.assertEqual(store._private_key(config, identity), "SYNTHETIC-DECRYPTED-PEM")
            key.private_bytes.reset_mock()
            with self.assertRaisesRegex(store.CredentialStoreError, "fingerprint"):
                store._private_key(config, IDENTITY)
            key.private_bytes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
