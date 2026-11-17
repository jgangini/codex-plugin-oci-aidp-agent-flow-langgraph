import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory

from aidp_agent_flow.model import FixtureModel
from aidp_agent_flow.project import FlowError, initialize
from aidp_agent_flow.quality import _at, _calibration, validate_quality_case
from aidp_agent_flow.quality_grader import grade_response
from aidp_agent_flow.worker import experiment


def packet():
    return {"question": "What does the captured discussion say about the store?",
            "answer": "Account A reports a parking incident [a]. The capture does not establish a national trend.",
            "evidence": [{"id": "a", "text": "Account A: a car reversed into the store parking exit."}],
            "criteria": [{"id": "grounded", "instruction": "Claims are entailed by cited sources and attributed; no population inference."}],
            "reference_facts": [{"id": "incident", "text": "A reports a parking incident", "evidence_ids": ["a"], "required": True}]}


def assessment():
    return {"criteria": [{"id": "grounded", "verdict": "pass", "reason": "The report is attributed and capture limits are explicit."}],
            "claims": [{"quote": "Account A reports a parking incident", "material": True, "verdict": "supported",
                        "evidence": [{"id": "a", "quote": "a car reversed into the store parking exit"}]}],
            "reference_facts": [{"id": "incident", "covered": True, "answer_quote": "Account A reports a parking incident"}]}


class QualityTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        self.temporary = TemporaryDirectory(dir=base)
        self.root = Path(self.temporary.name) / "project"
        initialize(self.root, "Quality tests", sync=False)
        self.data = packet()
        self.source = self.root / "tests/reviewed.json"
        self.source.write_text(json.dumps({"packet": self.data}), encoding="utf-8")
        self.case = {"id": "quality-positive", "input": {"packet": self.data, "source": {
            "kind": "curated", "bindings": {key: {"file": "tests/reviewed.json",
                "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(), "path": ["packet", key]} for key in self.data}}},
            "assertions": [{"path": "assessment.semantic_pass", "equals": True}, {"path": "assessment.criteria.grounded", "equals": "pass"}],
            "require_model_call": True, "expected_nodes": ["assess"], "model_responses": [json.dumps(assessment())]}

    def tearDown(self):
        self.temporary.cleanup()

    def grade(self, value):
        return grade_response(self.data, json.dumps(value))

    def test_supported_paraphrase_has_separate_metrics_and_no_percentage_gate(self):
        result = self.grade(assessment())
        self.assertTrue(result["semantic_pass"])
        self.assertEqual(result["metrics"]["supported_claim_fraction"], 1)
        self.assertNotIn("threshold", result)

    def test_material_error_blocks_even_if_criteria_pass(self):
        value = assessment()
        value["claims"][0].update(verdict="unsupported", evidence=[])
        result = self.grade(value)
        self.assertFalse(result["semantic_pass"])
        self.assertEqual(result["metrics"]["material_errors"], 1)

    def test_unknown_criterion_cannot_pass(self):
        value = assessment()
        value["criteria"][0]["verdict"] = "unknown"
        self.assertFalse(self.grade(value)["semantic_pass"])

    def test_missing_criterion_or_fact_is_invalid(self):
        for key in ("criteria", "reference_facts"):
            value = assessment()
            value[key] = []
            with self.subTest(key=key), self.assertRaises(FlowError):
                self.grade(value)

    def test_invented_answer_excerpt_is_invalid(self):
        value = assessment()
        value["claims"][0]["quote"] = "All shoppers nationwide agree"
        with self.assertRaises(FlowError):
            self.grade(value)

    def test_unknown_evidence_or_fabricated_excerpt_is_invalid(self):
        for source in ({"id": "unknown", "quote": "car"}, {"id": "a", "quote": "no one was injured"}):
            value = assessment()
            value["claims"][0]["evidence"] = [source]
            with self.subTest(source=source), self.assertRaises(FlowError):
                self.grade(value)

    def test_supported_claim_without_evidence_is_invalid(self):
        value = assessment()
        value["claims"][0]["evidence"] = []
        with self.assertRaises(FlowError):
            self.grade(value)

    def test_missing_required_topic_is_quality_failure_not_transport_failure(self):
        value = assessment()
        value["reference_facts"][0].update(covered=False, answer_quote="")
        result = self.grade(value)
        self.assertFalse(result["semantic_pass"])
        self.assertEqual(result["missing_required_facts"], ["incident"])

    def test_tampered_packet_or_file_rejected_before_model(self):
        for mutate in ("packet", "file"):
            case = deepcopy(self.case)
            if mutate == "packet":
                case["input"]["packet"]["answer"] = "Different answer"
            else:
                self.source.write_text("{}", encoding="utf-8")
            with self.subTest(mutate=mutate), patch("aidp_agent_flow.worker.OCIModel") as model:
                with self.assertRaises(FlowError):
                    asyncio.run(experiment({"project": str(self.root), "case": case,
                                            "real": True, "max_steps": 5, "quality_mode": "calibrate"}))
                model.assert_not_called()

    def test_external_path_and_invalid_json_path_rejected(self):
        self.case["input"]["source"]["bindings"]["answer"]["file"] = "../outside.json"
        with self.assertRaises(FlowError):
            validate_quality_case(self.root, self.case, "calibrate")
        for segments in ([True], [-1], ["missing"]):
            with self.subTest(segments=segments), self.assertRaises(FlowError):
                _at(["safe"], segments)

    def test_no_application_factory_tools_or_expected_labels_in_model_input(self):
        (self.root / "agent/core/graph.py").write_text("raise RuntimeError('Application factory must not load')", encoding="utf-8")
        observed = []

        class CapturingModel(FixtureModel):
            async def complete(self, system, question):
                observed.append(json.loads(question))
                return await super().complete(system, question)

        with patch("aidp_agent_flow.worker.FixtureModel", CapturingModel):
            result = asyncio.run(experiment({"project": str(self.root), "case": self.case,
                                            "real": False, "max_steps": 5, "quality_mode": "calibrate"}))
        self.assertTrue(result["passed"], result)
        self.assertEqual(observed, [self.data])
        self.assertEqual(result["service_calls"], [])
        self.assertEqual(result["model_calls"], 1)
        self.assertFalse(result["native_test_accepted"])

    def test_semantic_rejection_retained_without_failed_business_output(self):
        value = assessment()
        value["claims"][0].update(verdict="unsupported", evidence=[])
        self.case["model_responses"] = [json.dumps(value)]
        result = asyncio.run(experiment({"project": str(self.root), "case": self.case,
                                        "real": False, "max_steps": 5, "quality_mode": "calibrate"}))
        self.assertFalse(result["passed"])
        self.assertNotIn("output", result)
        self.assertFalse(result["quality_assessment"]["semantic_pass"])

    def test_curated_answer_cannot_be_agent_acceptance(self):
        with self.assertRaises(FlowError):
            validate_quality_case(self.root, self.case, "assess")

    def test_labels_cannot_redefine_rejected_assessment_as_pass(self):
        self.case["assertions"][0]["equals"] = False
        with self.assertRaises(FlowError):
            validate_quality_case(self.root, self.case, "assess")

    def test_forged_or_stale_calibration_marker_not_sufficient(self):
        path = self.root / "tests/calibration.json"
        path.write_text(json.dumps({"kind": "quality_calibration", "calibration_ready": True,
                                    "calibration_signature": "old"}), encoding="utf-8")
        with self.assertRaises(FlowError):
            _calibration(self.root, "tests/calibration.json", "current")

    def test_malformed_json_and_boolean_claim_flags_fail_closed(self):
        with self.assertRaises(FlowError):
            grade_response(self.data, "not JSON")
        value = assessment()
        value["claims"][0]["material"] = 1
        with self.assertRaises(FlowError):
            self.grade(value)

    def controlled_run(self, cases, *, stop_at_completion=False):
        import sys
        from aidp_agent_flow.campaign import initialize_campaign, finish_attempt
        from aidp_agent_flow.quality import run_quality
        if not (self.root / 'test-campaign.json').exists():
            initialize_campaign(self.root, 'tests/campaign-policy.json')
        path = self.root / 'tests/quality-cases.json'
        path.write_text(json.dumps(cases), encoding='utf-8')
        completed = 0
        def finish(*args, **kwargs):
            nonlocal completed
            completed += 1
            if stop_at_completion and completed == len(cases):
                raise OSError('Simulated final ledger write failure')
            return finish_attempt(*args, **kwargs)
        with patch('aidp_agent_flow.evaluation.python_path', return_value=Path(sys.executable)), \
             patch('aidp_agent_flow.identity.python_path', return_value=Path(sys.executable)), \
             patch('aidp_agent_flow.evaluation.finish_attempt', side_effect=finish):
            return run_quality(self.root, 'tests/quality-cases.json', mode='calibrate',
                               selected=[case['id'] for case in cases], hypothesis='Fixture protocol discrimination')

    def controlled_negative(self):
        case = deepcopy(self.case)
        case['id'] = 'quality-negative'
        value = assessment()
        value['criteria'][0]['verdict'] = 'fail'
        value['claims'][0].update(verdict='unsupported', evidence=[])
        case['model_responses'] = [json.dumps(value)]
        case['assertions'] = [{'path': 'assessment.semantic_pass', 'equals': False},
                              {'path': 'assessment.criteria.grounded', 'equals': 'fail'}]
        return case

    def test_controlled_calibration_keeps_negative_outcomes_and_no_agent_progress_credit(self):
        result = self.controlled_run([self.case, self.controlled_negative()])
        self.assertTrue(result['calibration_ready'], result)
        self.assertEqual(result['false_accepts'], 0)
        self.assertEqual(result['false_rejects'], 0)
        self.assertIn('/quality-runs/', result['run_receipt']['path'])
        self.assertEqual([row['semantic_pass'] for row in result['cases']], [True, False])
        self.assertFalse(result['native_test_accepted'])

    def test_final_campaign_completion_error_blocks_calibration_and_remains_visible(self):
        result = self.controlled_run([self.case, self.controlled_negative()], stop_at_completion=True)
        self.assertFalse(result['passed'])
        self.assertFalse(result['calibration_ready'])
        self.assertTrue(result['campaign_stopped'])
        self.assertTrue(all(row['execution_ok'] for row in result['cases']))

    def test_positive_only_calibration_cannot_be_enabled_by_editing_ready_marker(self):
        import sys
        result = self.controlled_run([self.case])
        self.assertFalse(result['calibration_ready'])
        path = Path(result['artifact'])
        saved = json.loads(path.read_bytes())
        saved['calibration_ready'] = True
        path.write_text(json.dumps(saved), encoding='utf-8')
        with patch('aidp_agent_flow.identity.python_path', return_value=Path(sys.executable)), self.assertRaises(FlowError):
            _calibration(self.root, path.relative_to(self.root).as_posix(), result['calibration_signature'])

    def test_quality_receipt_cannot_masquerade_as_an_original_agent_execution(self):
        result = self.controlled_run([self.case, self.controlled_negative()])
        receipt = self.root / result['run_receipt']['path']
        binding = {'file': result['run_receipt']['path'], 'sha256': hashlib.sha256(receipt.read_bytes()).hexdigest()}
        case = deepcopy(self.case)
        case['input']['source']['kind'] = 'agent_receipt'
        case['input']['source']['bindings']['answer'] = {**binding, 'path': ['results', 0, 'output', 'packet', 'answer']}
        case['input']['source']['bindings']['question'] = {**binding, 'path': ['experiments', 0, 'case', 'input', 'packet', 'question']}
        with self.assertRaisesRegex(FlowError, 'closed, identified source run'):
            validate_quality_case(self.root, case, 'assess')

    def test_calibration_requires_every_criterion_label_outside_model_input(self):
        self.case['assertions'] = self.case['assertions'][:1]
        with self.assertRaises(FlowError):
            validate_quality_case(self.root, self.case, 'calibrate')

    def test_changed_case_snapshot_fails_before_admission_or_worker(self):
        from aidp_agent_flow.evaluation import run_cases
        path = self.root / 'tests/snapshot.json'
        path.write_text(json.dumps([self.case]), encoding='utf-8')
        with patch('aidp_agent_flow.evaluation.reserve_attempt') as reserve, \
             patch('aidp_agent_flow.evaluation.subprocess.run') as worker, self.assertRaises(FlowError):
            run_cases(self.root, path, quality_mode='calibrate', case_snapshot_sha256='0' * 64)
        reserve.assert_not_called()
        worker.assert_not_called()

    def test_composite_context_is_bound_without_expected_labels(self):
        from aidp_agent_flow.quality import _bound
        binding = {'file': 'tests/reviewed.json', 'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
                   'path': ['packet', 'question']}
        self.assertEqual(_bound(self.root, {'parts': {'observed_question': binding}}),
                         {'observed_question': self.data['question']})

    def test_binding_rejects_hash_from_a_different_read_version(self):
        from contextlib import contextmanager
        from aidp_agent_flow.quality import _bound
        replacement = json.dumps({'packet': {'answer': 'Replacement'}}).encode()
        binding = {'file': 'tests/reviewed.json', 'sha256': hashlib.sha256(replacement).hexdigest(),
                   'path': ['packet', 'answer']}
        original_open = Path.open
        replaced = False
        @contextmanager
        def swapping_open(path, mode='r', *args, **kwargs):
            nonlocal replaced
            with original_open(path, mode, *args, **kwargs) as stream:
                yield stream
            if path == self.source and mode == 'rb' and not replaced:
                replaced = True
                with original_open(path, 'wb') as stream:
                    stream.write(replacement)
        with patch.object(Path, 'open', swapping_open), self.assertRaises(FlowError):
            _bound(self.root, binding)
        self.assertTrue(replaced)

    def test_source_metadata_supports_date_claims_without_inventing_source_text(self):
        self.data['evidence'][0]['published_at'] = '2026-11-06T19:26:07+00:00'
        self.data['answer'] += ' The source was published on 2026-11-06.'
        value = assessment()
        value['claims'].append({'quote': 'The source was published on 2026-11-06', 'material': True,
                                'verdict': 'supported', 'evidence': [{'id': 'a', 'quote': '2026-11-06', 'field': 'published_at'}]})
        self.assertTrue(self.grade(value)['semantic_pass'])

    def test_observed_authorship_and_content_fields_keep_literal_provenance(self):
        from aidp_agent_flow.quality_grader import ASSESSMENT_SCHEMA, validate_packet
        metadata = {"author_name": "Channel A", "author_url": "https://example.org/@a",
                    "source_title": "Store prices", "source_description": "A" * 3000,
                    "content_basis": "title_description"}
        self.data["evidence"][0].update(metadata)
        fields = ASSESSMENT_SCHEMA["properties"]["claims"]["items"]["properties"]["evidence"]["items"]["properties"]["field"]["enum"]
        for field, quote in metadata.items():
            with self.subTest(field=field):
                value = assessment()
                value["claims"][0]["evidence"] = [{"id": "a", "field": field, "quote": quote}]
                self.assertIn(field, fields)
                self.assertTrue(self.grade(value)["semantic_pass"])
        # Structural validation authenticates literal provenance, not entailment.
        for source in ({"id": "a", "field": "author_name", "quote": "Channel B"},
                       {"id": "a", "field": "source_title", "quote": "Channel A"},
                       {"id": "a", "field": "official_owner", "quote": "Channel A"}):
            with self.subTest(source=source), self.assertRaises(FlowError):
                value = assessment()
                value["claims"][0]["evidence"] = [source]
                self.grade(value)
        self.data["evidence"].append({"id": "b", "text": "Other source", "author_name": "Channel B"})
        value = assessment()
        value["claims"][0]["evidence"] = [{"id": "b", "field": "author_name", "quote": "Channel A"}]
        with self.assertRaises(FlowError):
            self.grade(value)
        for key, invalid in (("source_description", "A" * 12001), ("author_name", None),
                             ("official_owner", "Channel A")):
            with self.subTest(key=key), self.assertRaises(FlowError):
                changed = deepcopy(self.data)
                changed["evidence"][0][key] = invalid
                validate_packet(changed)

    def test_no_factual_claims_is_not_reported_as_perfect_factual_precision(self):
        self.data['answer'] = 'Which store do you mean?'
        self.data['reference_facts'] = []
        value = assessment()
        value['claims'], value['reference_facts'] = [], []
        result = self.grade(value)
        self.assertTrue(result['semantic_pass'])
        self.assertEqual(result['metrics']['claims'], 0)
        self.assertIsNone(result['metrics']['supported_claim_fraction'])

    def test_derived_output_question_is_not_the_original_user_input(self):
        result = self.controlled_run([self.case, self.controlled_negative()])
        receipt = self.root / result['run_receipt']['path']
        binding = {'file': result['run_receipt']['path'], 'sha256': hashlib.sha256(receipt.read_bytes()).hexdigest()}
        case = deepcopy(self.case)
        case['input']['source']['kind'] = 'agent_receipt'
        for field in ('answer', 'question'):
            case['input']['source']['bindings'][field] = {**binding, 'path': ['results', 0, 'output', 'packet', field]}
        with self.assertRaisesRegex(FlowError, 'original input'):
            validate_quality_case(self.root, case, 'assess')

    def test_generation_identity_is_verified_against_original_receipt(self):
        identity = {key: str(index) * 64 for index, key in enumerate(
            ("config_sha256", "package_sha256", "engine_sha256", "environment_sha256"), 1)}
        identity.update(mode="local_fixture_model", model_settings={"model_id": "fixture"})
        run = {"results": [{"case_id": "source", "passed": True, "experiment_sha256": "a" * 64,
                           **{key: value for key, value in identity.items() if key != "model_settings"},
                           "output": {"answer": self.data["answer"]}}],
               "experiments": [{"experiment_sha256": "a" * 64, "max_steps": 5,
                                "timeout_seconds": 30, "requested_model_settings": identity["model_settings"],
                                "case": {"input": {"question": self.data["question"]}}}]}
        original = self.root / "tests/original.json"
        original.write_text(json.dumps(run), encoding="utf-8")
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        for changed in (None, *identity):
            with self.subTest(changed=changed):
                case = deepcopy(self.case)
                declared = deepcopy(identity)
                if changed:
                    declared[changed] = ({"model_id": "other"} if changed == "model_settings" else
                                         "local_real_oci_model" if changed == "mode" else "f" * 64)
                case["input"]["packet"]["context"] = {"generation_identity": declared}
                self.source.write_text(json.dumps({"packet": case["input"]["packet"]}), encoding="utf-8")
                bindings = case["input"]["source"]["bindings"]
                for key in case["input"]["packet"]:
                    bindings[key] = {"file": "tests/reviewed.json",
                                     "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                                     "path": ["packet", key]}
                bindings["answer"] = {"file": "tests/original.json", "sha256": digest,
                                      "path": ["results", 0, "output", "answer"]}
                bindings["question"] = {"file": "tests/original.json", "sha256": digest,
                                        "path": ["experiments", 0, "case", "input", "question"]}
                case["input"]["source"]["kind"] = "agent_receipt"
                if changed:
                    with self.assertRaisesRegex(FlowError, "Generation identity"):
                        validate_quality_case(self.root, case, "assess")
                else:
                    validate_quality_case(self.root, case, "assess")

    def test_invalid_judge_output_is_saved_privately_with_safe_contract_reason(self):
        value = assessment()
        value['claims'][0]['quote'] = 'Invented phrase absent from the original answer'
        self.case['model_responses'] = [json.dumps(value)]
        result = self.controlled_run([self.case])
        row = result['cases'][0]
        self.assertFalse(result['calibration_ready'])
        self.assertEqual(row['failure_code'], 'quality_contract')
        self.assertEqual(row['quality_validation_code'], 'answer_excerpt')
        reference = row['quality_debug_artifact']
        saved = self.root / reference['path']
        self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), reference['sha256'])
        self.assertEqual(json.loads(saved.read_bytes())['judge_final_output'], self.case['model_responses'][0])
        public_receipt = json.loads((self.root / result['run_receipt']['path']).read_bytes())
        self.assertNotIn('output', public_receipt['results'][0])
        self.assertNotIn('Invented phrase', json.dumps(result))

    def test_wrapped_network_timeout_is_classified_without_provider_message(self):
        from requests.exceptions import ReadTimeout
        from oci.exceptions import RequestException
        from aidp_agent_flow.diagnostics import network_failure_cause, ProviderInvocationError, failure_details
        error = RequestException(ReadTimeout('sensitive-provider-address-and-body'))
        cause = network_failure_cause(error)
        self.assertEqual(cause, 'read_timeout')
        result = failure_details(ProviderInvocationError(cause=cause), 'execution', real=True)
        self.assertEqual(result['provider_cause'], 'read_timeout')
        self.assertNotIn('sensitive-provider', json.dumps(result))

    def test_unverified_provider_error_is_not_invented_as_timeout(self):
        from aidp_agent_flow.diagnostics import network_failure_cause
        self.assertEqual(network_failure_cause(RuntimeError('unknown service problem')), 'unverified')

    def test_diagnostic_fields_cannot_echo_arbitrary_user_data(self):
        from aidp_agent_flow.diagnostics import QualityContractError, ProviderInvocationError, failure_details
        error = QualityContractError('private-value')
        error.debug_artifact = {'path': 'private-value', 'sha256': 'not-a-hash'}
        result = failure_details(error, 'execution')
        self.assertEqual(result['quality_validation_code'], 'validation_shape')
        self.assertIsNone(result['quality_debug_artifact'])
        self.assertNotIn('private-value', json.dumps(result))
        self.assertEqual(failure_details(ProviderInvocationError(cause='private-value'), 'execution')['provider_cause'], 'unverified')

    def test_machine_json_is_portable_when_windows_console_encoding_is_legacy(self):
        import io
        from contextlib import redirect_stdout
        from aidp_agent_flow.cli import main
        output = io.StringIO()
        with patch('aidp_agent_flow.cli.execute', return_value={'passed': True, 'message': 'calibración y publicación'}), redirect_stdout(output):
            self.assertEqual(main(['--json', 'capabilities']), 0)
        self.assertTrue(output.getvalue().isascii())
        self.assertEqual(json.loads(output.getvalue())['result']['message'], 'calibración y publicación')


if __name__ == "__main__":
    unittest.main()
