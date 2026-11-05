import asyncio
import json
import math
import unittest
from unittest.mock import patch

from aidp_agent_flow import services
from aidp_agent_flow.services import RecordedServices, ServiceError


def record(kind="mcp", name="lookup", arguments=None, result=None):
    return {"kind": kind, "name": name, "arguments": {} if arguments is None else arguments, "result": result}


class RecordedServicesTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_service_kind_replays_its_own_exact_contract(self):
        fixture = [record(kind, "same_name", {"id": 7}, {"source": kind}) for kind in ("mcp", "rag", "table")]
        adapter = RecordedServices(fixture)
        for kind in ("table", "mcp", "rag"):
            self.assertEqual(await adapter.call(kind, "same_name", {"id": 7}), {"source": kind})
        adapter.assert_consumed()
        self.assertEqual([call["record_index"] for call in adapter.calls], [2, 0, 1])

    async def test_empty_and_false_results_remain_successful_distinct_values(self):
        outcomes = [None, [], {}, False, 0, ""]
        adapter = RecordedServices([record(result=value) for value in outcomes])
        for expected in outcomes:
            actual = await adapter.call("mcp", "lookup", {})
            self.assertEqual(actual, expected)
            self.assertIs(type(actual), type(expected))
        adapter.assert_consumed()
        self.assertTrue(all(call["status"] == "ok" for call in adapter.calls))

    async def test_argument_mapping_order_is_ignored_but_json_types_are_exact(self):
        adapter = RecordedServices([record(arguments={"a": True, "b": [1, 2]}, result="bool"),
                                    record(arguments={"a": 1, "b": [1, 2]}, result="int")])
        self.assertEqual(await adapter.call("mcp", "lookup", {"b": [1, 2], "a": 1}), "int")
        with self.assertRaises(ServiceError):
            await adapter.call("mcp", "lookup", {"a": True, "b": [2, 1]})
        self.assertEqual(await adapter.call("mcp", "lookup", {"b": [1, 2], "a": True}), "bool")
        with self.assertRaisesRegex(ServiceError, "unexpected"):
            adapter.assert_consumed()

    async def test_one_record_cannot_be_consumed_twice(self):
        adapter = RecordedServices([record(result="frozen")])
        self.assertEqual(await adapter.call("mcp", "lookup", {}), "frozen")
        with self.assertRaisesRegex(ServiceError, "unconsumed recorded service"):
            await adapter.call("mcp", "lookup", {})
        with self.assertRaisesRegex(ServiceError, "unexpected"):
            adapter.assert_consumed()
        self.assertEqual([call["status"] for call in adapter.calls], ["ok", "unmatched"])

    async def test_single_loop_concurrent_calls_consume_distinct_records_in_order(self):
        adapter = RecordedServices([record(result=index) for index in range(25)])
        outcomes = await asyncio.gather(*(adapter.call("mcp", "lookup", {}) for _ in range(25)))
        self.assertEqual(outcomes, list(range(25)))
        adapter.assert_consumed()
        self.assertEqual(len({call["record_index"] for call in adapter.calls}), 25)

    async def test_concurrent_duplicate_consumption_has_one_success(self):
        adapter = RecordedServices([record(result="single")])
        outcomes = await asyncio.gather(adapter.call("mcp", "lookup", {}),
                                        adapter.call("mcp", "lookup", {}), return_exceptions=True)
        self.assertEqual(outcomes[0], "single")
        self.assertIsInstance(outcomes[1], ServiceError)
        with self.assertRaisesRegex(ServiceError, "unexpected"):
            adapter.assert_consumed()

    async def test_recorded_error_is_consumed_once_and_message_is_sanitized(self):
        fixture = {"kind": "table", "name": "approved_query", "arguments": {"id": 1},
                   "error": {"code": "query_failed", "message": "DO-NOT-PRINT credentials or SQL"}}
        adapter = RecordedServices([fixture])
        with self.assertRaisesRegex(ServiceError, "configured error") as caught:
            await adapter.call("table", "approved_query", {"id": 1})
        self.assertNotIn("DO-NOT-PRINT", str(caught.exception))
        self.assertNotIn("DO-NOT-PRINT", json.dumps(adapter.calls))
        adapter.assert_consumed()
        with self.assertRaisesRegex(ServiceError, "No unconsumed"):
            await adapter.call("table", "approved_query", {"id": 1})

    async def test_result_with_business_error_field_is_not_an_error_record(self):
        expected = {"error": "a domain field", "isError": True}
        adapter = RecordedServices([record(result=expected)])
        self.assertEqual(await adapter.call("mcp", "lookup", {}), expected)
        adapter.assert_consumed()

    async def test_unmatched_call_leaves_expected_result_unconsumed(self):
        adapter = RecordedServices([record(arguments={"expected": 1}, result=[])])
        with self.assertRaises(ServiceError):
            await adapter.call("rag", "other_name", {"secret": "DO-NOT-PRINT"})
        self.assertNotIn("DO-NOT-PRINT", json.dumps(adapter.calls))
        with self.assertRaisesRegex(ServiceError, "unconsumed"):
            adapter.assert_consumed()
        self.assertEqual(await adapter.call("mcp", "lookup", {"expected": 1}), [])
        with self.assertRaisesRegex(ServiceError, "unexpected"):
            adapter.assert_consumed()

    async def test_fixture_results_and_call_metadata_are_independent_snapshots(self):
        fixture = [record(arguments={"nested": {"id": 1}}, result={"rows": [{"value": "original"}]}),
                   record(arguments={"nested": {"id": 1}}, result={"rows": [{"value": "original"}]})]
        adapter = RecordedServices(fixture)
        fixture[0]["arguments"]["nested"]["id"] = 2
        fixture[0]["result"]["rows"][0]["value"] = "modified fixture"
        first = await adapter.call("mcp", "lookup", {"nested": {"id": 1}})
        first["rows"][0]["value"] = "modified result"
        metadata = adapter.calls
        metadata[0]["status"] = "modified metadata"
        second = await adapter.call("mcp", "lookup", {"nested": {"id": 1}})
        self.assertEqual(second, {"rows": [{"value": "original"}]})
        self.assertEqual(adapter.calls[0]["status"], "ok")
        adapter.assert_consumed()

    async def test_calls_omit_raw_arguments_and_results(self):
        adapter = RecordedServices([record("table", "catalog.schema.lookup", {"parameter": "DO-NOT-PRINT"},
                                           {"rows": [{"private_value": "DO-NOT-PRINT"}]})])
        await adapter.call("table", "catalog.schema.lookup", {"parameter": "DO-NOT-PRINT"})
        self.assertEqual(set(adapter.calls[0]), {"kind", "name", "status", "record_index"})
        self.assertNotIn("DO-NOT-PRINT", json.dumps(adapter.calls))

    async def test_opaque_query_strings_are_data_and_are_never_executed(self):
        query = "DROP TABLE example; arbitrary unexecuted fixture text"
        adapter = RecordedServices([record("table", "approved_query", {"query": query}, {"rows": []})])
        self.assertEqual(await adapter.call("table", "approved_query", {"query": query}), {"rows": []})
        adapter.assert_consumed()

    async def test_call_count_is_bounded_even_for_repeated_mismatches(self):
        adapter = RecordedServices([])
        with patch.object(services, "_MAX_CALLS", 2):
            for _ in range(2):
                with self.assertRaises(ServiceError):
                    await adapter.call("mcp", "lookup", {})
            with self.assertRaisesRegex(ServiceError, "call count"):
                await adapter.call("mcp", "lookup", {})
        self.assertEqual(len(adapter.calls), 2)

    async def test_invalid_call_arguments_do_not_consume_an_expected_result(self):
        adapter = RecordedServices([record(result=[])])
        for kind, name, arguments in (("sql", "lookup", {}), ("mcp", "bad name", {}),
                                      ("mcp", "lookup", []), ("mcp", "lookup", {"value": math.nan})):
            with self.subTest(kind=kind, name=name, arguments=arguments), self.assertRaises(ServiceError):
                await adapter.call(kind, name, arguments)
        self.assertEqual(await adapter.call("mcp", "lookup", {}), [])
        with self.assertRaisesRegex(ServiceError, "unexpected"):
            adapter.assert_consumed()


class RecordedServiceValidationTests(unittest.TestCase):
    def test_error_or_result_field_is_required_but_null_result_is_valid(self):
        base = {"kind": "mcp", "name": "lookup", "arguments": {}}
        for invalid in (base, {**base, "error": {"code": "failed"}, "result": None},
                        {**base, "result": None, "unexpected": True}, {**base, "error": {}},
                        {**base, "error": "DO-NOT-PRINT"},
                        {**base, "error": {"code": "DO NOT PRINT"}}):
            with self.subTest(invalid=invalid), self.assertRaises(ServiceError):
                RecordedServices([invalid])
        RecordedServices([{**base, "result": None}])

    def test_non_json_values_and_invalid_keys_fail_without_evaluating_objects(self):
        executed = []

        def forbidden():
            executed.append(True)

        for value in (forbidden, {1: "value"}, (1, 2), b"bytes", {1, 2}, math.inf, "\ud800"):
            with self.subTest(type=type(value)), self.assertRaises(ServiceError):
                RecordedServices([record(result=value)])
        self.assertEqual(executed, [])

    def test_record_count_record_size_and_total_size_are_bounded(self):
        with patch.object(services, "_MAX_RECORDS", 1):
            with self.assertRaises(ServiceError):
                RecordedServices([record(), record()])
        with patch.object(services, "_MAX_RECORD_BYTES", 200):
            with self.assertRaisesRegex(ServiceError, "size limit"):
                RecordedServices([record(result="DO-NOT-PRINT" * 50)])
        with patch.object(services, "_MAX_TOTAL_BYTES", 100):
            with self.assertRaisesRegex(ServiceError, "total fixture size"):
                RecordedServices([record(), record()])

    def test_nesting_cycle_and_node_count_are_bounded(self):
        nested = []
        nested.append(nested)
        with self.assertRaisesRegex(ServiceError, "nesting"):
            RecordedServices([record(result=nested)])
        with patch.object(services, "_MAX_NODES", 10):
            with self.assertRaisesRegex(ServiceError, "item limit"):
                RecordedServices([record(result=list(range(11)))])

    def test_empty_fixture_is_valid_and_already_consumed(self):
        adapter = RecordedServices([])
        adapter.assert_consumed()
        self.assertEqual(adapter.calls, [])

    def test_reusing_an_instance_on_another_event_loop_fails(self):
        adapter = RecordedServices([record(result=1), record(result=2)])
        self.assertEqual(asyncio.run(adapter.call("mcp", "lookup", {})), 1)
        with self.assertRaisesRegex(ServiceError, "between event loops"):
            asyncio.run(adapter.call("mcp", "lookup", {}))
        with self.assertRaises(ServiceError):
            adapter.assert_consumed()


if __name__ == "__main__":
    unittest.main()
