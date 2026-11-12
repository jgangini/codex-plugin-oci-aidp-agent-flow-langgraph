import hashlib
from pathlib import Path
import unittest
from urllib.parse import unquote, urlsplit

import test_native_lifecycle as support
from aidp_agent_flow.native_layout import prune_tree
from aidp_agent_flow.project import FlowError
from unittest.mock import patch


class NativeLayoutTests(unittest.TestCase):
    setUp = support.NativeLifecycleTests.setUp
    tearDown = support.NativeLifecycleTests.tearDown
    instance = support.NativeLifecycleTests.instance
    seed_package = support.NativeLifecycleTests.seed_package
    bound_instance = support.NativeLifecycleTests.bound_instance
    posts = support.NativeLifecycleTests.posts

    def transport(self, *, lost_delete=False):
        original = self.http.request
        def request(method, url, **kwargs):
            parsed = urlsplit(url)
            if method == 'DELETE':
                if '/objects/' in parsed.path:
                    self.http.objects.pop(unquote(parsed.path.split('/objects/', 1)[1]), None)
                else:
                    self.http.agents.clear()
                    self.http.tests.clear()
                self.http.calls.append({'method': method, 'url': url})
                if lost_delete:
                    raise TimeoutError('Lost reply after accepted delete')
                return support.FakeResponse(status=204)
            if method == 'GET' and '/agents/' in parsed.path and parsed.path.endswith('/agent-one') and not self.http.agents:
                return support.FakeResponse(status=404)
            return original(method, url, **kwargs)
        self.http.request = request

    def test_current_exact_package_is_accepted(self):
        selected = self.bound_instance()
        self.assertTrue(selected.inspect_layout()['layout_matches'])
        self.assertEqual(self.posts(), [])

    def test_old_tree_blocks_TEST_and_production_before_write(self):
        selected = self.bound_instance()
        self.http.objects[selected.remote_root + '/old/agent.py'] = b'old'
        report = selected.inspect_layout()
        self.assertEqual(report['unexpected_files'], ['old/agent.py'])
        self.assertEqual(report['unexpected_folders'], ['old'])
        for method in (selected.test_init, selected.publish):
            with self.assertRaisesRegex(FlowError, 'source tree'):
                method(apply=True)
        self.assertEqual(self.posts(), [])

    def test_separate_old_metadata_fails_even_with_correct_code(self):
        selected = self.bound_instance()
        selected.metadata_root = selected.remote_root + '/old'
        self.http.agents[0]['pathInfo'] = selected.metadata_root
        self.assertFalse(selected.inspect_layout()['metadata_aligned'])
        with self.assertRaises(FlowError):
            selected.test_init(apply=True)

    def test_foreign_listing_path_rejected(self):
        selected = self.bound_instance()
        original = selected._rows
        selected._rows = lambda path, **kwargs: ([{'path': '/Workspace/other/file.py', 'type': 'FILE'}]
            if path.endswith('/objects') else original(path, **kwargs))
        with self.assertRaises(FlowError):
            selected.inspect_layout()

    def test_retirement_plan_is_read_only_and_hash_required(self):
        selected = self.bound_instance()
        self.transport()
        selected.retire_agent()
        with self.assertRaises(FlowError):
            selected.retire_agent(apply=True, expected_binding='wrong')
        self.assertFalse(any(call['method'] == 'DELETE' for call in self.http.calls))

    def test_retirement_preserves_compute_and_reconciles_lost_reply(self):
        selected = self.bound_instance()
        self.transport(lost_delete=True)
        plan = selected.retire_agent()
        with self.assertRaises(FlowError):
            selected.retire_agent(apply=True, expected_binding=plan['binding_sha256'])
        result = selected.retire_agent(apply=True)
        self.assertTrue(result['agent_absent'])
        self.assertEqual(selected.compute, 'compute-one')
        self.assertEqual(sum(c['method'] == 'DELETE' for c in self.http.calls), 1)
        self.assertNotIn('agent_key', selected.state)

    def test_retirement_rejects_production_or_creating_TEST(self):
        for kind in ('prod', 'creating'):
            selected = self.bound_instance()
            if kind == 'prod':
                self.http.prod = [self.http.deployment('PROD')]
            else:
                self.http.prod = []
                self.http.tests = [{**self.http.deployment(), 'lifecycleState': 'CREATING'}]
            with self.subTest(kind=kind), self.assertRaises(FlowError):
                selected.retire_agent()

    def test_create_agent_state_failure_recovers_without_second_create(self):
        selected = self.instance()
        self.seed_package()
        with patch.object(selected, '_save_state', side_effect=OSError('Lost local state write')):
            with self.assertRaises(OSError):
                selected.ensure_agent(apply=True)
        fresh = self.instance()
        result = fresh.ensure_agent(apply=True)
        self.assertEqual(result['agent_key'], 'agent-one')
        creates = [call for call in self.posts() if call['route'] == '/workspaces/workspace-one/agents']
        self.assertEqual(len(creates), 1)

    def obsolete(self, selected):
        tree = selected.remote_root + '/old'
        self.http.objects[tree] = b''
        self.http.objects[tree + '/legacy.py'] = b'old'
        return tree, {'legacy.py': hashlib.sha256(b'old').hexdigest()}

    def test_prune_preserves_local_backup_and_removes_exact_old_tree(self):
        selected = self.bound_instance()
        self.transport()
        tree, hashes = self.obsolete(selected)
        self.assertEqual(prune_tree(selected, tree, hashes)['files_to_remove'], 1)
        result = prune_tree(selected, tree, hashes, apply=True)
        self.assertTrue(result['tree_absent'])
        self.assertTrue(selected.inspect_layout()['layout_matches'])
        backups = list((selected.journal / 'pruned').rglob('legacy.py'))
        self.assertEqual([p.read_bytes() for p in backups], [b'old'])

    def test_prune_unknown_file_or_drift_blocks_without_delete(self):
        selected = self.bound_instance()
        self.transport()
        tree, hashes = self.obsolete(selected)
        self.http.objects[tree + '/unknown.py'] = b'foreign'
        with self.assertRaises(FlowError):
            prune_tree(selected, tree, hashes, apply=True)
        self.http.objects.pop(tree + '/unknown.py')
        self.http.objects[tree + '/legacy.py'] = b'drift'
        with self.assertRaises(FlowError):
            prune_tree(selected, tree, hashes, apply=True)
        self.assertFalse(any(call['method'] == 'DELETE' for call in self.http.calls))

    def test_prune_empty_obsolete_folders_after_delete_cascade(self):
        selected = self.bound_instance()
        self.transport()
        tree = selected.remote_root + '/old'
        self.http.objects.update({tree: b'', tree + '/empty': b''})
        self.assertTrue(prune_tree(selected, tree, {}, apply=True)['tree_absent'])
        self.assertTrue(selected.inspect_layout()['layout_matches'])

    def test_empty_inventory_cannot_delete_unknown_files(self):
        selected = self.bound_instance()
        self.transport()
        tree, _ = self.obsolete(selected)
        with self.assertRaises(FlowError):
            prune_tree(selected, tree, {}, apply=True)
        self.assertFalse(any(call['method'] == 'DELETE' for call in self.http.calls))

    def test_prune_cannot_remove_current_code_or_escape_root(self):
        selected = self.bound_instance()
        for tree in (selected.remote_root, '/Workspace/other', selected.remote_root + '/core'):
            with self.subTest(tree=tree), self.assertRaises(FlowError):
                prune_tree(selected, tree, {'legacy.py': 'a' * 64}, apply=True)


if __name__ == '__main__':
    unittest.main()
