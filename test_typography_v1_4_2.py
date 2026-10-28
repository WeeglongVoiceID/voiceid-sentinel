"""Offline checks for the VoiceID Sentinel v1.4.2 accessibility/readability update.
No network, no live API, no production connection. Python standard library only.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
CSS = (ROOT / 'assets' / 'app.css').read_text(encoding='utf-8')
JS = (ROOT / 'assets' / 'app.js').read_text(encoding='utf-8')
HTML = (ROOT / 'index.html').read_text(encoding='utf-8')


class TestWorkbenchTypography142(unittest.TestCase):
    def test_01_release_label_is_updated(self):
        self.assertIn('v1.6</strong>', HTML)

    def test_02_default_font_is_larger(self):
        self.assertIn('font-size:calc(16px * var(--type-multiplier))', CSS)

    def test_03_numbers_are_large(self):
        self.assertIn('font-size:calc(49px * var(--type-multiplier))', CSS)

    def test_04_numbers_are_heavy(self):
        self.assertIn('font-weight:900', CSS)
        self.assertIn('font-variant-numeric:tabular-nums', CSS)

    def test_05_priority_text_is_bigger(self):
        self.assertIn('.priority {font-size:calc(13px * var(--type-multiplier))', CSS)

    def test_06_event_labels_are_bigger(self):
        self.assertIn('.timeline-head strong {font-size:calc(16px * var(--type-multiplier))', CSS)

    def test_07_ai_narrative_is_bigger(self):
        self.assertIn('.ai-record p {font-size:calc(14px * var(--type-multiplier))', CSS)

    def test_08_accessible_text_control_exists(self):
        self.assertIn('id="type-size-btn"', HTML)
        self.assertIn('aria-pressed="false"', HTML)
        self.assertIn('type="button"', HTML)

    def test_09_control_toggles_css_class(self):
        self.assertIn("document.body.classList.toggle('type-extra-large')", JS)

    def test_10_control_updates_pressed_state(self):
        self.assertIn("control.setAttribute('aria-pressed', String(enabled))", JS)

    def test_11_extra_large_font_multiplier_exists(self):
        self.assertIn('body.type-extra-large { --type-multiplier: 1.16; }', CSS)

    def test_12_mobile_layout_and_print_styling(self):
        self.assertIn('@media(max-width:700px)', CSS)
        self.assertIn('.header-inner{gap:8px;flex-wrap:wrap;', CSS)
        self.assertIn('.type-size-btn{display:none!important;}', CSS)

    def test_13_navigation_fix_is_preserved(self):
        self.assertIn('panel.scrollIntoView(', JS)
        self.assertIn('scroll-margin-top:24px', CSS)

    def test_14_key_security_and_mode_copy_present(self):
        self.assertIn('Human review required', HTML)
        self.assertIn('Run LIVE Meta AI', HTML)
        self.assertIn('ILLUSTRATIVE · NOT META', JS)

    def test_15_engine_is_present_and_unchanged_in_location(self):
        self.assertTrue((ROOT / 'engine_v1_2' / 'sentinel_v1_2.py').is_file())
        self.assertTrue((ROOT / 'workbench_v1_4.py').is_file())


if __name__ == '__main__':
    unittest.main(verbosity=2)
