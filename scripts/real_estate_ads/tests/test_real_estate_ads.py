"""Lightweight no-network compliance + rendering smoke tests."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reels", ROOT / "render.py")
reels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reels)
MANIFEST = json.loads((ROOT / "examples" / "azizi-florence.json").read_text())


class ReelsTests(unittest.TestCase):
    def test_30_and_15_duration(self):
        self.assertEqual(sum(s['seconds'] for s in reels.validate(MANIFEST, 30, False, '', False, False)), 30)
        self.assertEqual(sum(s['seconds'] for s in reels.validate(MANIFEST, 15, False, '', False, False)), 15)

    def test_public_blocked_without_clearance(self):
        for p, r, c in [('', False, False), ('REF-1', True, False), ('REF-1', False, True)]:
            with self.assertRaises(ValueError):
                reels.validate(MANIFEST, 30, True, p, r, c)

    def test_public_allowed_after_clearance_assertions(self):
        self.assertEqual(len(reels.validate(MANIFEST, 30, True, 'REF-1', True, True)), 6)

    def test_banned_claims_blocked(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad['scenes'][0]['headline'] = 'Villas from AED 2.09M, guaranteed return'
        with self.assertRaisesRegex(ValueError, 'Prohibited'):
            reels.validate(bad, 30, False, '', False, False)

    def test_dubai_location_rejected(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad['location'] = 'Business Bay, Dubai'
        with self.assertRaisesRegex(ValueError, 'Sharjah'):
            reels.validate(bad, 30, False, '', False, False)

    def test_path_traversal_rejected(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad['scenes'][0]['asset'] = '../../secret.png'
        with self.assertRaisesRegex(ValueError, 'simple filename'):
            reels.validate(bad, 30, False, '', False, False)

    def test_missing_source_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                reels.render(ROOT / 'examples' / 'azizi-florence.json', Path(d), Path(d)/'out.mp4', 15, False, '', False, False, None, 0.5)

    def test_card_generation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'card.png'
            reels.card(MANIFEST['scenes'][0], path, False, '', 30)
            with Image.open(path) as im:
                self.assertEqual(im.size, (1080, 1920))


if __name__ == '__main__':
    unittest.main()