"""Exact source-tree acceptance and explicit retirement of a development CODE agent."""
from pathlib import PurePosixPath
import hashlib
import re
from urllib.parse import quote

from .project import FlowError, canonical_hash


def inventory(lifecycle, root):
    files, folders, stack = set(), set(), [root]
    while stack:
        folder = stack.pop()
        if len(files) + len(folders) > 2000 or len(PurePosixPath(folder).parts) > 30:
            raise FlowError('Native layout inventory exceeds its bounded scope')
        for row in lifecycle._rows(lifecycle.ws + '/objects', query={'path': folder}):
            path, kind = row.get('path'), row.get('type')
            if (not isinstance(path, str) or str(PurePosixPath(path).parent) != folder
                    or kind not in {'FILE', 'FOLDER'} or '\\' in path
                    or any(part in {'.', '..'} for part in path.split('/'))):
                raise FlowError('Native layout inventory escaped the selected source root')
            relative = path.removeprefix(root + '/')
            if relative in files or path in folders:
                raise FlowError('Native layout inventory contains duplicate objects')
            if kind == 'FOLDER':
                folders.add(path)
                stack.append(path)
            else:
                files.add(relative)
    return files, folders


def inspect_layout(lifecycle, *, verify_bytes=True):
    package, _ = lifecycle._package()
    expected = set(package['files'])
    files, folders = inventory(lifecycle, lifecycle.remote_root)
    allowed_folders = {str(parent) for name in expected for parent in PurePosixPath(name).parents if str(parent) != '.'}
    unexpected = sorted(files - expected)
    unexpected_folders = sorted(path.removeprefix(lifecycle.remote_root + '/') for path in folders
                                if path.removeprefix(lifecycle.remote_root + '/') not in allowed_folders)
    missing, changed = sorted(expected - files), []
    for name in sorted(expected & files) if verify_bytes else []:
        raw = lifecycle._object(lifecycle.remote_root + '/' + name)
        if raw is None or hashlib.sha256(raw).hexdigest() != package['files'][name]:
            changed.append(name)
    binding = lifecycle.inspect_binding()
    metadata_aligned = binding['metadata_location'] == lifecycle.remote_root
    matched = not (unexpected or unexpected_folders or missing or changed) and binding['binding_verified'] and metadata_aligned
    return {'action': 'inspect-layout', 'read_only': True, 'passed': matched, 'layout_matches': matched,
            'source_root': lifecycle.remote_root, 'package_sha256': package['package_sha256'],
            'metadata_aligned': metadata_aligned, 'binding_verified': binding['binding_verified'],
            'missing_files': missing, 'changed_files': changed, 'unexpected_files': unexpected,
            'unexpected_folders': unexpected_folders, 'native_test_accepted': False}


def require_layout(lifecycle, *, verify_bytes=True):
    report = inspect_layout(lifecycle, verify_bytes=verify_bytes)
    if not report['layout_matches']:
        raise FlowError('Native source tree or metadata differs from the local package; inspect-layout before deployment')
    return report


def prune_tree(lifecycle, tree, expected_hashes, *, apply=False):
    """Retire one inventoried obsolete subtree, backing up bytes locally first."""
    from .native_lifecycle import _remote, _unlinked
    _remote(tree)
    if not tree.startswith(lifecycle.remote_root + '/'):
        raise FlowError('Pruning is restricted to a child of the selected source root')
    package, _ = lifecycle._package()
    if any((lifecycle.remote_root + '/' + name) == tree or (lifecycle.remote_root + '/' + name).startswith(tree + '/') for name in package['files']):
        raise FlowError('Pruning cannot remove any current package file')
    if (not isinstance(expected_hashes, dict) or not 0 <= len(expected_hashes) <= 500
            or any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', name)
                   or any(p in {'.', '..'} for p in name.split('/'))
                   or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                   for name, digest in expected_hashes.items())):
        raise FlowError('Pruning requires a bounded, canonical owned-file hash inventory')
    lifecycle._ownership(lifecycle._rows(lifecycle.ws + '/agents'))
    if lifecycle._deployments('PROD'):
        raise FlowError('Pruning an agent with a production deployment requires a separate release operation')
    digest = canonical_hash(expected_hashes)
    intents = {(row.get('remote_path'), row.get('kind')): (path, row) for path, row in lifecycle._intents()
               if row.get('kind') in {'prune-file', 'prune-folder'} and row.get('package_sha256') == digest}
    if apply:
        for (remote, kind), (path, row) in intents.items():
            if row['state'] != 'RECONCILED' and lifecycle._object(remote) is None:
                lifecycle._reconciled(path, row)
    if lifecycle._object(tree) is None:
        if (tree, 'prune-folder') not in intents:
            raise FlowError('The obsolete root disappeared without a recorded pruning intent')
        return {'action': 'prune-tree', 'applied': apply, 'tree_absent': True, 'native_test_accepted': False}
    files, folders = inventory(lifecycle, tree)
    if files - set(expected_hashes) or any((tree + '/' + name, 'prune-file') not in intents for name in set(expected_hashes) - files):
        raise FlowError('Obsolete subtree inventory changed; no unowned file will be removed')
    backup = lifecycle.journal / 'pruned' / canonical_hash({'tree': tree, 'inventory': expected_hashes})[:24]
    _unlinked(backup)
    for name in sorted(files):
        raw = lifecycle._object(tree + '/' + name)
        if raw is None or hashlib.sha256(raw).hexdigest() != expected_hashes[name]:
            raise FlowError('Obsolete file changed; preserve it before pruning')
        if apply:
            saved = backup / name
            _unlinked(saved)
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and saved.read_bytes() != raw:
                raise FlowError('Local pruning backup differs; preserve both states')
            if not saved.exists():
                with saved.open('xb') as stream:
                    stream.write(raw)
    if not apply:
        return {'action': 'prune-tree', 'applied': False, 'files_to_remove': len(files),
                'inventory_sha256': digest, 'native_test_accepted': False}
    for remote, kind in [(tree + '/' + name, 'prune-file') for name in sorted(files)] + [
            (folder, 'prune-folder') for folder in sorted(folders | {tree}, key=lambda p: (-len(PurePosixPath(p).parts), p))]:
        if kind == 'prune-folder' and lifecycle._rows(lifecycle.ws + '/objects', query={'path': remote}):
            raise FlowError('Only an empty obsolete folder may be removed')
        lifecycle._guard()
        if kind == 'prune-file':
            raw = lifecycle._object(remote)
            if raw is None or hashlib.sha256(raw).hexdigest() != expected_hashes[remote.removeprefix(tree + '/')]:
                raise FlowError('Obsolete file changed immediately before delete')
        _, ledger, row = lifecycle._write(kind, lifecycle.ws + '/objects/' + quote(remote, safe=''), method='DELETE',
                                         package=digest, extra={'remote_path': remote})
        if lifecycle._object(remote) is not None:
            raise FlowError('Pruning was submitted; wait for absence before any further write')
        lifecycle._reconciled(ledger, row)
    return {'action': 'prune-tree', 'applied': True, 'tree_absent': True, 'files_removed': len(files),
            'inventory_sha256': digest, 'native_test_accepted': False}


def retire_agent(lifecycle, *, apply=False, expected_binding=None):
    """Delete only the explicitly bound development agent; compute is never deleted."""
    if not lifecycle.agent_key:
        raise FlowError('Retirement requires the exact existing agent key')
    pending = [(path, row) for path, row in lifecycle._intents()
               if row.get('kind') == 'retire-agent' and row.get('agent_key') == lifecycle.agent_key]
    if len(pending) > 1:
        raise FlowError('Multiple retirement intents require reconciliation')
    item, headers = lifecycle._request('GET', lifecycle.ws + '/agents/' + lifecycle.agent_key, absent=True)
    if item is None:
        if not pending:
            raise FlowError('The selected agent is absent without a recorded retirement intent')
        if apply:
            path, row = pending[0]
            lifecycle.state.pop('test_receipt', None)
            lifecycle.state.pop('agent_key', None)
            lifecycle.state['retired_agent_key'] = lifecycle.agent_key
            lifecycle._save_state()
            lifecycle._reconciled(path, row, resource_key=lifecycle.agent_key)
        return {'action': 'retire-agent', 'applied': apply, 'agent_absent': True,
                'retired_agent_key': lifecycle.agent_key, 'compute_preserved': True, 'native_test_accepted': False}
    lifecycle._validate_agent(item, lifecycle.agent_key)
    tests, prod = lifecycle._deployments('TEST'), lifecycle._deployments('PROD')
    if prod or any(row['lifecycleState'] == 'CREATING' for row in tests):
        raise FlowError('Retirement is development-only and requires no production deployment or creating TEST')
    binding = {key: item.get(key) for key in (*lifecycle._binding(), 'key', 'recordVersion')}
    digest = canonical_hash({'binding': binding, 'test': lifecycle._snapshot(tests)})
    result = {'action': 'retire-agent', 'applied': False, 'agent_key': lifecycle.agent_key,
              'binding_sha256': digest, 'compute_preserved': True, 'will_interrupt_test': bool(tests),
              'native_test_accepted': False}
    if not apply:
        return result
    if expected_binding != digest:
        raise FlowError('Retirement requires the current read-only binding hash')
    if pending:
        raise FlowError('Retirement was already submitted; reconcile its absence before any retry')
    lifecycle._rebind_guard()
    lifecycle._guard()
    fresh, _ = lifecycle._source_agent()
    if any(fresh.get(key) != value for key, value in binding.items()):
        raise FlowError('Agent changed before retirement; no delete was sent')
    _, ledger, row = lifecycle._write('retire-agent', lifecycle.ws + '/agents/' + lifecycle.agent_key,
                                     method='DELETE', headers={'if-match': headers['etag']} if headers.get('etag') else {})
    observed, _ = lifecycle._request('GET', lifecycle.ws + '/agents/' + lifecycle.agent_key, absent=True)
    if observed is not None:
        raise FlowError('Retirement is recorded but absence is not yet verified; do not resubmit')
    lifecycle.state.pop('test_receipt', None)
    lifecycle.state.pop('agent_key', None)
    lifecycle.state['retired_agent_key'] = lifecycle.agent_key
    lifecycle._save_state()
    lifecycle._reconciled(ledger, row, resource_key=lifecycle.agent_key)
    return {**result, 'applied': True, 'agent_absent': True}
