"""Static consistency: every element ID referenced from app.js must exist in index.html,
and no file may reference the author's old absolute paths (/home/claude, /mnt/user-data)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM = os.path.join(ROOT, 'simulator')
APP_JS = open(os.path.join(SIM, 'static', 'app.js'), encoding='utf-8').read()
INDEX = open(os.path.join(SIM, 'static', 'index.html'), encoding='utf-8').read()


def _js_ids():
    ids = set()
    ids.update(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", APP_JS))
    ids.update(re.findall(r"\$\(\"#([A-Za-z0-9_-]+)\"\)", APP_JS))
    ids.update(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", APP_JS))
    ids.update(re.findall(r"el\('([A-Za-z0-9_-]+)'\)", APP_JS))
    ids.update(re.findall(r"querySelector\('#([A-Za-z0-9_-]+)'\)", APP_JS))
    return ids


def test_all_referenced_ids_exist_in_html():
    html_ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', INDEX))
    missing = sorted(i for i in _js_ids() if i not in html_ids)
    assert not missing, f'app.js references IDs absent from index.html: {missing}'


def test_no_legacy_absolute_paths_anywhere():
    offenders = []
    for dirpath, _, files in os.walk(SIM):
        for fn in files:
            path = os.path.join(dirpath, fn)
            with open(path, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            for legacy in ('/home/claude', '/mnt/user-data'):
                if legacy in content:
                    offenders.append(f'{path}: contains {legacy}')
    assert not offenders, '\n'.join(offenders)


def test_layer_and_param_keys_unique():
    layer_keys = re.findall(r"\{ k: '([a-z_]+)', label:", APP_JS)
    assert len(layer_keys) == len(set(layer_keys)), 'duplicate layer keys'


def test_html_has_script_and_stylesheet():
    assert '<script src="/app.js"></script>' in INDEX
    assert '<link rel="stylesheet" href="/style.css">' in INDEX
