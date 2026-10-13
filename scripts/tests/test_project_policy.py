import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

module_path = Path(__file__).resolve().parents[1] / 'check_project_policy.py'
spec = importlib.util.spec_from_file_location('project_policy', module_path)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

class ProjectPolicyTests(unittest.TestCase):
    def test_actual_release_versions_agree(self):
        self.assertEqual(policy.check_versions(), (policy.ROOT / 'VERSION').read_text(encoding='utf-8').strip())

    def test_main_accepts_local_develop(self):
        policy.check_pull_request({'pull_request': {'base': {'ref': 'main'}, 'head': {'ref': 'develop', 'repo': {'full_name': 'owner/repo'}}}}, 'owner/repo')

    def test_main_rejects_feature_and_fork_develop(self):
        for ref, repo in [('codex/example', 'owner/repo'), ('develop', 'attacker/fork')]:
            with self.subTest(ref=ref, repo=repo), self.assertRaises(ValueError):
                policy.check_pull_request({'pull_request': {'base': {'ref': 'main'}, 'head': {'ref': ref, 'repo': {'full_name': repo}}}}, 'owner/repo')

    def test_feature_pr_to_develop_and_push_are_allowed(self):
        policy.check_pull_request({}, 'owner/repo')
        policy.check_pull_request({'pull_request': {'base': {'ref': 'develop'}, 'head': {'ref': 'feature/example'}}}, 'owner/repo')

    def test_version_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'VERSION').write_text('1.0.0-alpha.1')
            (root / 'dashboard-ui/src/lib').mkdir(parents=True)
            (root / 'taskflow-seo/app/web').mkdir(parents=True)
            (root / 'dashboard-ui/package.json').write_text(json.dumps({'version': '1.0.0-alpha.2'}))
            (root / 'dashboard-ui/package-lock.json').write_text(json.dumps({'version': '1.0.0-alpha.1', 'packages': {'': {'version': '1.0.0-alpha.1'}}}))
            (root / 'dashboard-ui/src/lib/version.ts').write_text("export const APP_VERSION = '1.0.0-alpha.1';")
            (root / 'taskflow-seo/app/web/app.py').write_text('version="1.0.0-alpha.1"')
            with self.assertRaises(ValueError):
                policy.check_versions(root)

if __name__ == '__main__':
    unittest.main()
