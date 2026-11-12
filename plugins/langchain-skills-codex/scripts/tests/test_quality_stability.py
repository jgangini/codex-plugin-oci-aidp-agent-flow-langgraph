from copy import deepcopy
import unittest

from aidp_agent_flow.quality_stability import reference_stability


def case(identifier):
    return {'id': identifier, 'input': {'packet': {'question': 'Same question',
        'evidence': [{'id': 'doc', 'text': 'Same evidence'}],
        'reference_facts': [{'id': 'main'}, {'id': 'secondary'}],
        'context': {'generation_identity': {'config_sha256': 'a' * 64, 'package_sha256': 'b' * 64,
            'engine_sha256': 'c' * 64, 'environment_sha256': 'd' * 64,
            'model_settings': {'model_id': 'same-model'}, 'mode': 'local_fixture_model'}}}}}


def result(identifier, covered, *, valid=True, accepted=True):
    return {'case_id': identifier, 'execution_ok': valid, 'semantic_pass': accepted,
            'assessment': {'assessment': {'reference_facts': [
                {'id': key, 'covered': key in covered} for key in ('main', 'secondary')]}}}


class QualityStabilityTests(unittest.TestCase):
    def test_equivalent_reference_facts_are_compared_without_word_similarity(self):
        report = reference_stability([case('one'), case('two')],
                                     [result('one', {'main', 'secondary'}), result('two', {'main'})])
        group = report['groups'][0]
        self.assertEqual(group['common_facts'], ['main'])
        self.assertEqual(group['pairs'][0]['jaccard_similarity'], 0.5)
        self.assertIsNone(report['acceptance_threshold'])

    def test_distinct_evidence_or_generation_is_not_mixed_into_one_score(self):
        first, second, third = case('one'), case('two'), case('three')
        second['input']['packet']['evidence'][0]['text'] = 'Different evidence'
        third['input']['packet']['context']['generation_identity']['package_sha256'] = 'e' * 64
        report = reference_stability([first, second, third], [result(key, {'main'}) for key in ('one', 'two', 'three')])
        self.assertEqual(len(report['groups']), 3)
        self.assertTrue(all(not group['pairs'] for group in report['groups']))

    def test_missing_or_invalid_generation_identity_is_explicitly_unavailable(self):
        first, second = case('one'), case('two')
        first['input']['packet']['context'] = {}
        second['input']['packet']['context']['generation_identity']['mode'] = []
        report = reference_stability([first, second], [result('one', {'main'}), result('two', {'main'})])
        self.assertEqual(report['groups'], [])
        self.assertEqual(report['unavailable_generation_identity'], ['one', 'two'])

    def test_empty_answers_do_not_receive_perfect_factual_stability(self):
        report = reference_stability([case('one'), case('two')], [result('one', set()), result('two', set())])
        self.assertIsNone(report['groups'][0]['pairs'][0]['jaccard_similarity'])

    def test_failed_judge_is_kept_as_an_excluded_trial(self):
        report = reference_stability([case('one'), case('two')],
                                     [result('one', {'main'}), result('two', set(), valid=False)])
        group = report['groups'][0]
        self.assertEqual(group['selected_cases'], ['one', 'two'])
        self.assertEqual(group['excluded_cases'], ['two'])
        self.assertFalse(group['all_semantic_pass'])
        self.assertEqual(group['pairs'], [])
