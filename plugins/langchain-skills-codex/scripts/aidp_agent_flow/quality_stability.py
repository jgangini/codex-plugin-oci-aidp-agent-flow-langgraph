"""Descriptive reference-fact stability for comparable frozen generations."""
from itertools import combinations
import re

from .project import canonical_hash


def _generation(packet):
    identity = packet.get('context', {}).get('generation_identity')
    hashes = ('config_sha256', 'package_sha256', 'engine_sha256', 'environment_sha256')
    if (not isinstance(identity, dict) or set(identity) != {*hashes, 'model_settings', 'mode'}
            or any(not isinstance(identity[key], str) or not re.fullmatch('[0-9a-f]{64}', identity[key]) for key in hashes)
            or not isinstance(identity['model_settings'], dict)
            or not isinstance(identity['mode'], str) or identity['mode'] not in {'local_real_oci_model', 'local_fixture_model'}):
        return None
    return identity


def reference_stability(cases, results):
    by_id = {row['case_id']: row for row in results}
    groups, unavailable = {}, []
    for case in cases:
        packet = case['input']['packet']
        identity = _generation(packet)
        if identity is None:
            unavailable.append(case['id'])
            continue
        frozen = canonical_hash({key: packet[key] for key in ('question', 'evidence', 'reference_facts')} | {'generation': identity})
        groups.setdefault(frozen, []).append(case['id'])
    comparisons = []
    for frozen, identifiers in groups.items():
        covered, excluded = {}, []
        for identifier in identifiers:
            row = by_id.get(identifier, {})
            if row.get('execution_ok') is not True:
                excluded.append(identifier)
                continue
            facts = row['assessment']['assessment']['reference_facts']
            covered[identifier] = {item['id'] for item in facts if item['covered']}
        pairs = []
        for left, right in combinations(covered, 2):
            union = covered[left] | covered[right]
            pairs.append({'left': left, 'right': right, 'shared_facts': len(covered[left] & covered[right]),
                          'union_facts': len(union), 'jaccard_similarity': len(covered[left] & covered[right]) / len(union) if union else None})
        sets = list(covered.values())
        comparisons.append({'frozen_comparison_sha256': frozen, 'selected_cases': identifiers,
                            'assessed_cases': list(covered), 'excluded_cases': excluded,
                            'covered_facts_by_case': {key: sorted(value) for key, value in covered.items()},
                            'common_facts': sorted(set.intersection(*sets)) if sets else [],
                            'union_facts': sorted(set.union(*sets)) if sets else [], 'pairs': pairs,
                            'all_semantic_pass': not excluded and all(by_id[key]['semantic_pass'] for key in identifiers)})
    return {'groups': comparisons, 'unavailable_generation_identity': unavailable,
            'acceptance_threshold': None,
            'limitations': ['Reference-fact coverage is not exhaustive factual correctness or word similarity',
                            'Identical mistakes can be stable; apply per-answer grounding and scope checks separately',
                            'Empty covered sets have no informative factual-comparison value; similarity is null']}
