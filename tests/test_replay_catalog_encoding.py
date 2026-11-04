"""Replay controls retain real translated text and their formatting fields."""
import ast
from pathlib import Path
import re
import runpy
import string
import unittest


ROOT = Path(__file__).resolve().parents[1]
LANGS = ('de', 'es', 'fr', 'ja', 'ko', 'pt_br')
CLIP_TIP = ('Ctrl+F10 or hold SELECT + R3 for 1 second to save an MP4 in Videos/T5DR Online. '
            'Includes game sound only. Disabled while power saving is on. Windows only.')


def replay_keys():
    tree = ast.parse((ROOT / 'launcher/replays_ui.py').read_text(encoding='utf-8'))
    return {node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ('t', 'N_') and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)}


def fields(text):
    return sorted(field for _, field, _, _ in string.Formatter().parse(text) if field is not None)


class ReplayCatalogEncoding(unittest.TestCase):
    def catalogs(self):
        for lang in LANGS:
            yield lang, runpy.run_path(str(ROOT / f'lobby/t5lobby/i18n_{lang}.py'))['MESSAGES']

    def test_replay_and_clip_text_has_no_lossy_character_placeholders(self):
        for lang, catalog in self.catalogs():
            for key in replay_keys() | {CLIP_TIP}:
                with self.subTest(language=lang, text=key):
                    translated = catalog[key]
                    self.assertNotIn('\ufffd', translated)
                    if '?' not in key:
                        self.assertNotIn('?', translated)

    def test_repaired_controls_preserve_all_format_fields(self):
        for lang, catalog in self.catalogs():
            for key in replay_keys() | {CLIP_TIP}:
                with self.subTest(language=lang, text=key):
                    self.assertEqual(fields(catalog[key]), fields(key))

    def test_japanese_and_korean_controls_keep_their_written_languages(self):
        controls = ('Back 10 s', 'Forward 10 s', 'Frame step', 'Take P{side}',
                    'Verified playback', 'Unverified: player control', CLIP_TIP)
        for lang, catalog in self.catalogs():
            if lang not in ('ja', 'ko'):
                continue
            script = r'[\u3040-\u30ff\u4e00-\u9fff]' if lang == 'ja' else r'[\uac00-\ud7a3]'
            for key in controls:
                with self.subTest(language=lang, text=key):
                    self.assertRegex(catalog[key], re.compile(script))


if __name__ == '__main__':
    unittest.main()
