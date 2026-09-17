import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import paper_digest as pd


class OpenAlexFilterTests(unittest.TestCase):
    def test_joins_issns_with_openalex_or(self):
        clause = pd.openalex_issn_clause(["2058-7546", "0306-2619"])
        self.assertEqual(
            clause,
            "locations.source.issn:2058-7546|0306-2619",
        )


class ReconstructAbstractTests(unittest.TestCase):
    def test_rebuilds_words_in_index_order(self):
        inverted = {
            "Climate": [0],
            "risk": [1],
            "planning": [2],
        }
        self.assertEqual(pd.reconstruct_abstract(inverted), "Climate risk planning")

    def test_empty_index_returns_empty_string(self):
        self.assertEqual(pd.reconstruct_abstract(None), "")
        self.assertEqual(pd.reconstruct_abstract({}), "")

    def test_strips_crossref_jats_tags(self):
        self.assertEqual(pd._strip_jats("<jats:p>Hello climate</jats:p>"), "Hello climate")


class FilenameTests(unittest.TestCase):
    def test_uses_chinese_title_and_strips_illegal_chars(self):
        name = pd.markdown_filename('考虑极端天气的电源/电网规划: 研究"A"')
        self.assertTrue(name.endswith(".md"))
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)
        self.assertNotIn('"', name)

    def test_falls_back_when_title_empty(self):
        self.assertEqual(pd.markdown_filename("   "), "untitled.md")


class RelevanceTests(unittest.TestCase):
    def test_keeps_weather_and_planning_paper(self):
        title = "Power system planning under extreme weather and climate risk"
        abstract = "We propose generation expansion planning using meteorological scenarios."
        self.assertTrue(pd.is_relevant(title, abstract))

    def test_rejects_unrelated_power_electronics_paper(self):
        title = "A new SiC MOSFET gate driver"
        abstract = "Switching loss is reduced by 12 percent."
        self.assertFalse(pd.is_relevant(title, abstract))


class MarkdownTests(unittest.TestCase):
    def test_renders_bilingual_abstract_note(self):
        text = pd.render_markdown(
            zh_title="极端天气下的电源规划",
            en_title="Generation expansion under extreme weather",
            authors="Alice; Bob",
            journal="Applied Energy",
            doi="10.1016/example",
            date="2026-09-16",
            zh_abstract="中文摘要。",
            en_abstract="English abstract.",
        )
        self.assertIn("# 极端天气下的电源规划", text)
        self.assertIn("Applied Energy", text)
        self.assertIn("## 中文摘要", text)
        self.assertIn("## Abstract", text)


class SeenStoreTests(unittest.TestCase):
    def test_skips_already_seen_doi(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seen.json"
            store = pd.SeenStore(path)
            self.assertFalse(store.has("10.1/abc"))
            store.add("10.1/abc")
            store.save()
            again = pd.SeenStore(path)
            self.assertTrue(again.has("10.1/abc"))


if __name__ == "__main__":
    unittest.main()
