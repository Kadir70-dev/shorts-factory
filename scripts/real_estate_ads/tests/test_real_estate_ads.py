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


def approved(manifest, kind="developer_render", disclosure=False):
    """Copy of the manifest with every slot filled and cleared (test-only fixture state)."""
    m = json.loads(json.dumps(manifest))
    for slot_id, slot in m["image_slots"].items():
        slot.update(file=f"{slot_id}.jpg", kind=kind, status="APPROVED",
                    approved=True, rights_cleared=True, ai_disclosure=disclosure)
    return m


class ReelsTests(unittest.TestCase):
    def test_30_and_15_duration(self):
        self.assertEqual(sum(s['seconds'] for s in reels.validate(MANIFEST, 30, False, '', False, False)), 30)
        self.assertEqual(sum(s['seconds'] for s in reels.validate(MANIFEST, 15, False, '', False, False)), 15)

    def test_public_blocked_without_clearance(self):
        for p, r, c in [('', False, False), ('REF-1', True, False), ('REF-1', False, True)]:
            with self.assertRaises(ValueError):
                reels.validate(MANIFEST, 30, True, p, r, c)

    def test_public_allowed_after_clearance_assertions(self):
        self.assertEqual(len(reels.validate(approved(MANIFEST), 30, True, 'REF-1', True, True)), 6)

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
        bad['image_slots']['azizi_villa_exterior'].update(file='../../secret.png', kind='developer_render')
        with self.assertRaisesRegex(ValueError, 'simple filename'):
            reels.validate(bad, 30, False, '', False, False)

    def test_public_blocked_when_approved_files_missing_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = Path(d) / 'm.json'
            manifest.write_text(json.dumps(approved(MANIFEST)))
            with self.assertRaisesRegex(FileNotFoundError, 'Public export blocked'):
                reels.render(manifest, Path(d), Path(d)/'out.mp4', 15, True, 'REF-1', True, True, None, 0.5)

    # --- missing-image / PENDING_ASSET handling ---

    def test_example_slots_are_all_blank_and_pending(self):
        for slot_id, slot in MANIFEST['image_slots'].items():
            self.assertIsNone(slot['file'], slot_id)
            self.assertEqual(slot['status'], 'PENDING_ASSET', slot_id)
            self.assertFalse(slot['approved'] or slot['rights_cleared'], slot_id)

    def test_pending_slot_resolves_to_none(self):
        with tempfile.TemporaryDirectory() as d:
            slot = MANIFEST['image_slots']['azizi_aerial']
            self.assertIsNone(reels.resolve_slot(slot, Path(d)))
            self.assertIsNone(reels.resolve_slot(slot, None))
            listed_but_absent = dict(slot, file='azizi_aerial.jpg', kind='developer_render', status='PROVIDED')
            self.assertIsNone(reels.resolve_slot(listed_but_absent, Path(d)))
            Image.new('RGB', (8, 8)).save(Path(d) / 'azizi_aerial.jpg')
            self.assertEqual(reels.resolve_slot(listed_but_absent, Path(d)), Path(d) / 'azizi_aerial.jpg')

    def test_draft_validates_with_every_slot_pending(self):
        self.assertEqual(len(reels.validate(MANIFEST, 15, False, '', False, False)), 3)

    def test_public_blocked_while_slots_pending_even_with_clearance_flags(self):
        with self.assertRaisesRegex(ValueError, 'PENDING_ASSET'):
            reels.validate(MANIFEST, 30, True, 'REF-1', True, True)

    def test_public_blocked_for_unapproved_or_uncleared_image(self):
        for field in ('approved', 'rights_cleared'):
            m = approved(MANIFEST)
            m['image_slots']['azizi_aerial'][field] = False
            with self.assertRaisesRegex(ValueError, 'azizi_aerial'):
                reels.validate(m, 15, True, 'REF-1', True, True)

    def test_ai_image_requires_disclosure_for_public(self):
        with self.assertRaisesRegex(ValueError, 'ai_disclosure'):
            reels.validate(approved(MANIFEST, 'ai_generated'), 15, True, 'REF-1', True, True)
        self.assertEqual(len(reels.validate(approved(MANIFEST, 'ai_generated', True), 15, True, 'REF-1', True, True)), 3)

    def test_ai_disclosure_never_claims_real_property(self):
        text = reels.DISCLOSURE['ai_generated']
        self.assertIn('AI-generated', text)
        self.assertIn('Not a photo of Azizi Florence', text)

    def test_slot_without_file_must_stay_pending(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad['image_slots']['azizi_aerial']['status'] = 'APPROVED'
        with self.assertRaisesRegex(ValueError, 'PENDING_ASSET'):
            reels.validate(bad, 15, False, '', False, False)

    def test_unknown_slot_and_kind_rejected(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad['scenes'][0]['slot'] = 'nope'
        with self.assertRaisesRegex(ValueError, 'unknown image slot'):
            reels.validate(bad, 30, False, '', False, False)
        bad = json.loads(json.dumps(MANIFEST))
        bad['image_slots']['azizi_aerial'].update(file='a.jpg', kind='stock_photo', status='PROVIDED')
        with self.assertRaisesRegex(ValueError, 'kind'):
            reels.validate(bad, 30, False, '', False, False)

    def test_placeholder_is_neutral_blank_frame(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'p.png'
            reels.placeholder('azizi_aerial', 'Aerial', path)
            with Image.open(path) as im:
                self.assertEqual(im.size, (1080, 1920))
                r, g, b = im.convert('RGB').getpixel((540, 1500))
                self.assertLess(max(r, g, b) - min(r, g, b), 16)  # grey, not a picture

    def test_card_generation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'card.png'
            reels.card(MANIFEST['scenes'][0], path, False, '', 30)
            with Image.open(path) as im:
                self.assertEqual(im.size, (1080, 1920))


if __name__ == '__main__':
    unittest.main()