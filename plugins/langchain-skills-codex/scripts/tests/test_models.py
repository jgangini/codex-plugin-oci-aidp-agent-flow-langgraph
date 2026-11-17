from datetime import datetime, timezone
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from aidp_agent_flow import models
from aidp_agent_flow.cli import main
from aidp_agent_flow.project import FlowError


def model(identifier="model-1", **fields):
    return SimpleNamespace(id=identifier, display_name="Candidate", vendor="Provider", version="1.0",
                           lifecycle_state="ACTIVE", capabilities=["CHAT"], **fields)


def response(items, page=None):
    return SimpleNamespace(data=SimpleNamespace(items=items),
                           headers={"OPC-NEXT-PAGE": page} if page is not None else {})


class ModelInventoryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("selected-project").resolve()
        self.project = {"oci": {"config_file": ".oci/config", "profile": "SELECTED"},
                        "model": {"region": "us-chicago-1", "compartment_id": "ocid1.compartment.test"}}
        self.config = {"region": "us-ashburn-1", "user": "private-user", "key_file": "private-path"}
        self.client = Mock()
        self.sdk = SimpleNamespace(
            config=SimpleNamespace(from_file=Mock(return_value=self.config)),
            retry=SimpleNamespace(NoneRetryStrategy=Mock(return_value=object())),
            generative_ai=SimpleNamespace(GenerativeAiClient=Mock(return_value=self.client)))
        self.signer = object()
        for patcher in (patch.dict("sys.modules", {"oci": self.sdk}),
                        patch.object(models, "load_project", return_value=(self.root, self.project)),
                        patch.object(models, "signer_for", return_value=self.signer)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_selected_region_profile_and_compartment_with_no_retries(self):
        self.client.list_models.side_effect = [response([model()], "next/+"), response([model("model-2")])]
        result = models.list_models(self.root, limit=7)
        self.sdk.config.from_file.assert_called_once_with(str(self.root / ".oci/config"), "SELECTED")
        args, kwargs = self.sdk.generative_ai.GenerativeAiClient.call_args
        self.assertEqual(args[0], {**self.config, "region": "us-chicago-1"})
        self.assertIs(kwargs["signer"], self.signer)
        retry = self.sdk.retry.NoneRetryStrategy.return_value
        self.assertIs(kwargs["retry_strategy"], retry)
        self.assertEqual(kwargs["timeout"], (5, 60))
        self.assertEqual(self.client.list_models.call_args_list[0].args, ("ocid1.compartment.test",))
        self.assertEqual(self.client.list_models.call_args_list[0].kwargs, {"limit": 7, "retry_strategy": retry})
        self.assertEqual(self.client.list_models.call_args_list[1].kwargs["page"], "next/+")
        self.assertTrue(result["complete"])
        self.assertEqual(result["pageCount"], 2)
        self.assertFalse(result["inference_checked"])
        self.assertFalse(result["model_selected"])
        self.assertFalse(result["configuration_changed"])
        self.client.base_client.session.close.assert_called_once()

    def test_allowlists_metadata_retirement_and_optional_deprecation(self):
        retirement = datetime(2027, 1, 2, tzinfo=timezone.utc)
        item = model(time_deprecated=retirement, model_deprecated=False, is_long_term_supported=True,
                     time_on_demand_retired=retirement, time_dedicated_retired=retirement,
                     freeform_tags={"token": "DO-NOT-PRINT"}, private_key="DO-NOT-PRINT")
        self.client.list_models.return_value = response([item])
        result = models.list_models(self.root)
        metadata = result["items"][0]
        self.assertEqual(metadata["displayName"], "Candidate")
        self.assertEqual(metadata["lifecycleState"], "ACTIVE")
        self.assertEqual(metadata["capabilities"], ["CHAT"])
        self.assertEqual(metadata["timeDeprecated"], retirement.isoformat())
        self.assertEqual(metadata["timeOnDemandRetired"], retirement.isoformat())
        self.assertEqual(metadata["timeDedicatedRetired"], retirement.isoformat())
        self.assertIs(metadata["modelDeprecated"], False)
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))
        self.assertNotIn("private-path", json.dumps(result))

    def test_missing_optional_metadata_is_not_invented_and_nonactive_is_visible(self):
        item = model()
        item.lifecycle_state = "DELETING"
        self.client.list_models.return_value = response([item])
        result = models.list_models(self.root)
        self.assertEqual(result["items"][0]["lifecycleState"], "DELETING")
        self.assertNotIn("modelDeprecated", result["items"][0])
        self.assertNotIn("timeDeprecated", result["items"][0])

    def test_empty_complete_inventory_is_not_a_model_recommendation(self):
        self.client.list_models.return_value = response([])
        self.assertEqual(models.list_models(self.root)["items"], [])

    def test_repeated_cursor_and_duplicate_identity_fail(self):
        for pages in ([response([model()], "again"), response([model("model-2")], "again")],
                      [response([model()], "next"), response([model()])]):
            with self.subTest(pages=pages):
                self.client.list_models.side_effect = pages
                with self.assertRaisesRegex(FlowError, "repeat"):
                    models.list_models(self.root)

    def test_page_bound_fails_instead_of_returning_truncated_success(self):
        self.client.list_models.side_effect = [response([model()], "page-2"), response([model("model-2")], "page-3")]
        with patch.object(models, "_MAX_PAGES", 2), self.assertRaisesRegex(FlowError, "incomplete"):
            models.list_models(self.root)
        self.assertEqual(self.client.list_models.call_count, 2)

    def test_item_bound_and_oversized_page_fail(self):
        for bound, limit in ((1, 100), (2000, 1)):
            with self.subTest(bound=bound, limit=limit):
                self.client.list_models.return_value = response([model(), model("model-2")])
                with patch.object(models, "_MAX_ITEMS", bound), self.assertRaises(FlowError):
                    models.list_models(self.root, limit=limit)

    def test_invalid_metadata_and_cursor_fail(self):
        for invalid in (response([SimpleNamespace(id="model", lifecycle_state=None)]),
                        response([model(capabilities_override=True)]), response([], 27), response([], False)):
            if invalid.data.items and getattr(invalid.data.items[0], "capabilities_override", False):
                invalid.data.items[0].capabilities = "CHAT"
            with self.subTest(invalid=invalid):
                self.client.list_models.return_value = invalid
                with self.assertRaises(FlowError):
                    models.list_models(self.root)

    def test_invalid_limits_and_missing_target_never_load_auth(self):
        for limit in (0, 1001, True, "10"):
            with self.subTest(limit=limit), self.assertRaises(FlowError):
                models.list_models(self.root, limit=limit)
        self.project["model"]["region"] = ""
        with self.assertRaisesRegex(FlowError, "region"):
            models.list_models(self.root)
        self.project["model"]["region"] = "us-chicago-1"
        self.project["model"]["compartment_id"] = ""
        with self.assertRaisesRegex(FlowError, "compartment"):
            models.list_models(self.root)
        self.sdk.config.from_file.assert_not_called()

    def test_provider_failure_does_not_expose_exception_or_retry(self):
        self.client.list_models.side_effect = RuntimeError("DO-NOT-PRINT provider credential body")
        with self.assertRaises(FlowError) as error:
            models.list_models(self.root)
        self.assertNotIn("DO-NOT-PRINT", str(error.exception))
        self.assertEqual(self.client.list_models.call_count, 1)
        self.client.base_client.session.close.assert_called_once()

    def test_cli_dispatch_needs_no_native_endpoint(self):
        self.client.list_models.return_value = response([])
        output = io.StringIO()
        with patch("aidp_agent_flow.cli.WorkbenchClient", side_effect=AssertionError("No native request")), redirect_stdout(output):
            status = main(["--project", str(self.root), "--json", "models", "list", "--limit", "7"])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(output.getvalue())["result"]["complete"])
        self.assertEqual(self.client.list_models.call_args.kwargs["limit"], 7)


if __name__ == "__main__":
    unittest.main()
