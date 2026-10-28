"""Offline smoke tests of the v1.4.1 viewport and focus correction."""
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
HTML=(ROOT/'index.html').read_text(encoding='utf-8')
JS=(ROOT/'assets/app.js').read_text(encoding='utf-8')
CSS=(ROOT/'assets/app.css').read_text(encoding='utf-8')

class TestNavigation(unittest.TestCase):
 def test_ai_panel_has_id(self): self.assertIn('id="ai-investigation-panel"',HTML)
 def test_ai_panel_keyboard_focusable(self): self.assertIn('tabindex="-1" role="region"',HTML)
 def test_scroll_on_successful_preview_or_meta_only(self): self.assertIn("if (mode==='preview' || mode==='meta') navigateToAdvisory()",JS)
 def test_not_scroll_on_page_load(self): self.assertIn("const response=await request('/api/investigate','POST',payload);render(response);",JS)
 def test_waits_for_dom_render(self): self.assertIn('window.requestAnimationFrame(() => {',JS)
 def test_skips_hidden_advisory(self): self.assertIn("get('advisory-view').hidden",JS)
 def test_focus_without_scroll(self): self.assertIn('panel.focus({preventScroll:true})',JS)
 def test_reduced_motion_support(self): self.assertIn("prefers-reduced-motion: reduce",JS)
 def test_scrolled_element_is_panel(self): self.assertIn('panel.scrollIntoView(',JS)
 def test_css_scroll_offset(self): self.assertIn('scroll-margin-top:24px',CSS)
 def test_backend_server_unmodified(self):
  base=ROOT.parent/'VoiceID_Sentinel_Workbench_v1_4'/'workbench_v1_4.py'
  if base.exists(): self.assertEqual((ROOT/'workbench_v1_4.py').read_bytes(),base.read_bytes())

if __name__=='__main__': unittest.main(verbosity=2)
