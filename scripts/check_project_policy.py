"""Check release metadata and the protected develop -> main promotion path."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_versions(root=ROOT):
    expected = (root / 'VERSION').read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?', expected):
        raise ValueError('VERSION must contain a supported semantic version')
    package = json.loads((root / 'dashboard-ui/package.json').read_text(encoding='utf-8'))
    lock = json.loads((root / 'dashboard-ui/package-lock.json').read_text(encoding='utf-8'))
    versions = [package['version'], lock['version'], lock['packages']['']['version']]
    for name, pattern in [('dashboard-ui/src/lib/version.ts', r"APP_VERSION\s*=\s*['\"]([^'\"]+)"), ('taskflow-seo/app/web/app.py', r'version\s*=\s*[\"\']([^\"\']+)')]:
        match = re.search(pattern, (root / name).read_text(encoding='utf-8'))
        if not match:
            raise ValueError(f'Version not found: {name}')
        versions.append(match.group(1))
    if any(version != expected for version in versions):
        raise ValueError(f'Version metadata disagrees with VERSION: {versions}')
    return expected


def check_pull_request(event, repository):
    pr = event.get('pull_request')
    if not pr or pr['base']['ref'] != 'main':
        return
    head = pr['head']
    if head['ref'] != 'develop' or not head.get('repo') or head['repo']['full_name'] != repository:
        raise ValueError('main accepts release pull requests only from this repository develop branch')


if __name__ == '__main__':
    print('Version:', check_versions())
    if os.environ.get('GITHUB_EVENT_NAME') == 'pull_request':
        check_pull_request(json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8')), os.environ['GITHUB_REPOSITORY'])
    print('Project policy OK')
