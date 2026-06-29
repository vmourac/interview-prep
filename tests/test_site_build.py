from __future__ import annotations

import html as html_lib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "site" / "build.py"
SPEC = importlib.util.spec_from_file_location("interview_prep_build", BUILD_PATH)
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = build
SPEC.loader.exec_module(build)


class DiscoveryOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.exercises = build.discover_exercises()

    def topic_files(self, topic_slug: str) -> list[str]:
        return [
            Path(item.source_path).name
            for item in self.exercises
            if item.topic_slug == topic_slug
        ]

    def test_dsa_topics_follow_numeric_curriculum(self) -> None:
        topic_numbers = []
        for item in self.exercises:
            if item.kind == "DSA" and item.topic_number not in topic_numbers:
                topic_numbers.append(item.topic_number)
        self.assertEqual(topic_numbers, list(range(1, 18)))

    def test_readme_order_wins_over_filename_order(self) -> None:
        expected = {
            "01-estrutura-da-entrevista-dsa": [
                "two-sum.html", "valid-palindrome.html", "binary-search.html"
            ],
            "03-listas": [
                "reverse-linked-list.html", "merge-two-sorted-lists.html",
                "linked-list-cycle.html"
            ],
            "10-graphs-introducao": [
                "number-of-connected-components-in-an-undirected-graph.html",
                "find-if-path-exists-in-graph.html", "clone-graph.html"
            ],
            "15-graphs-mst-union-find": [
                "graph-valid-tree.html", "redundant-connection.html",
                "min-cost-to-connect-all-points.html"
            ],
            "17-brute-force": [
                "subsets.html", "combination-sum.html", "n-queens.html"
            ],
        }
        for topic, filenames in expected.items():
            with self.subTest(topic=topic):
                self.assertEqual(self.topic_files(topic), filenames)

    def test_concepts_precede_topic_exercises(self) -> None:
        self.assertEqual(
            self.topic_files("16-recursion-and-sorting"),
            [
                "01-conceitos.html", "permutations.html", "sort-an-array.html",
                "merge-k-sorted-lists.html"
            ],
        )


class OrderingFixtureTests(unittest.TestCase):
    def create_topic(self, root: Path, name: str, *filenames: str) -> Path:
        topic_dir = root / name
        html_dir = topic_dir / "html"
        html_dir.mkdir(parents=True)
        for filename in filenames:
            (html_dir / filename).write_text("<title>Fixture</title>", encoding="utf-8")
        return topic_dir

    def test_missing_readme_falls_back_to_filename_order(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            topic_dir = self.create_topic(
                Path(temporary_directory), "01-topic", "zeta.html", "alpha.html"
            )

            ordered = build.ordered_topic_htmls(topic_dir)

            self.assertEqual(
                [path.name for path in ordered], ["alpha.html", "zeta.html"]
            )

    def test_invalid_utf8_readme_falls_back_without_crashing(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            topic_dir = self.create_topic(
                Path(temporary_directory), "01-topic", "zeta.html", "alpha.html"
            )
            (topic_dir / "README.md").write_bytes(b"\xff")

            ordered = build.ordered_topic_htmls(topic_dir)

            self.assertEqual(
                [path.name for path in ordered], ["alpha.html", "zeta.html"]
            )

    def test_duplicate_readme_links_preserve_first_occurrence(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            topic_dir = self.create_topic(
                Path(temporary_directory), "01-topic", "alpha.html", "beta.html"
            )
            (topic_dir / "README.md").write_text(
                "\n".join(
                    [
                        "[Beta](./html/beta.html)",
                        "[Alpha](./html/alpha.html)",
                        "[Beta again](./html/beta.html)",
                    ]
                ),
                encoding="utf-8",
            )

            order = build.readme_html_order(topic_dir)

            self.assertEqual(order, {"beta.html": 1, "alpha.html": 2})

    def test_duplicate_numeric_prefixes_sort_by_number_then_name(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name in ("01-zeta", "02-beta", "01-alpha"):
                (root / name).mkdir()

            ordered = build.numbered_topic_dirs(root)

            self.assertEqual(
                [path.name for path in ordered],
                ["01-alpha", "01-zeta", "02-beta"],
            )


class GroupedRenderingTests(unittest.TestCase):
    SECTION_RE = re.compile(
        r'<section class="topic-group" data-track="([^"]+)"\s+'
        r'data-topic="(\d{2})" aria-labelledby="([^"]+)">'
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.exercises = build.discover_exercises()
        cls.html = build.render_index(cls.exercises)
        cls.sections = cls.SECTION_RE.findall(cls.html)

    def test_topic_sections_follow_the_complete_curriculum_order(self) -> None:
        expected = [
            ("DSA", f"{number:02d}") for number in range(1, 18)
        ] + [
            ("System Design", f"{number:02d}") for number in range(1, 6)
        ]

        self.assertEqual(
            [(track, topic) for track, topic, _ in self.sections],
            expected,
        )

    def test_category_and_composite_position_are_visible(self) -> None:
        self.assertRegex(
            self.html,
            r">[^<]*Algoritmos e Estruturas de Dados \(DSA\)[^<]*<",
        )
        self.assertIn("Tópico 03 de 17", self.html)
        self.assertIn('class="item-position">03.1</span>', self.html)

    def test_every_section_is_labelled_by_its_topic_heading(self) -> None:
        self.assertEqual(len(self.sections), 22)
        for track, topic, heading_id in self.sections:
            with self.subTest(track=track, topic=topic):
                self.assertIn(
                    f'<h2 id="{heading_id}">',
                    self.html,
                )

    def test_renders_seventeen_dsa_and_five_system_design_sections(self) -> None:
        tracks = [track for track, _, _ in self.sections]
        self.assertEqual(tracks.count("DSA"), 17)
        self.assertEqual(tracks.count("System Design"), 5)

    def test_generated_css_does_not_force_a_320px_body_width(self) -> None:
        self.assertNotIn("min-width: 320px", self.html)

    def test_result_count_is_the_only_live_announcement_region(self) -> None:
        self.assertIn(
            '<span id="result-count" role="status" aria-live="polite" '
            'aria-atomic="true">58 materiais visíveis</span>',
            self.html,
        )
        self.assertEqual(self.html.count('aria-live="polite"'), 1)
        self.assertIn('<div class="topic-sections" id="cards">', self.html)

    def test_filtering_reports_visible_cards_and_hides_empty_topic_groups(self) -> None:
        self.assertIn(
            'const groups = Array.from(document.querySelectorAll(".topic-group"));',
            self.html,
        )
        self.assertIn(
            'group.hidden = !group.querySelector(".card:not([hidden])");',
            self.html,
        )
        self.assertIn(
            'const materialLabel = visible === 1 ? "material visível" : '
            '"materiais visíveis";',
            self.html,
        )

    def test_filtering_behavior_in_headless_chrome(self) -> None:
        chrome = (
            shutil.which("google-chrome")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
        )
        if chrome is None:
            self.skipTest("Google Chrome or Chromium is not installed")

        probe = r"""
    (() => {
      const cards = () => Array.from(document.querySelectorAll(".card"));
      const groups = () => Array.from(document.querySelectorAll(".topic-group"));
      const visibleCards = () => cards().filter((card) => !card.hidden);
      const visibleGroups = () => groups().filter((group) => !group.hidden);
      const groupKey = (group) => `${group.dataset.track}:${group.dataset.topic}`;
      const cardKey = (card) => card.querySelector("a").getAttribute("href");
      const search = document.getElementById("search");
      const resultCount = document.getElementById("result-count");
      const originalGroupOrder = groups().map(groupKey);
      const originalCardOrder = cards().map(cardKey);
      const results = {};

      function setSearch(value) {
        search.value = value;
        search.dispatchEvent(new Event("input", { bubbles: true }));
      }

      function clickFilter(value) {
        document.querySelector(`[data-filter="${value}"]`).click();
      }

      function trackCounts() {
        const shown = visibleGroups();
        return {
          dsaGroups: shown.filter((group) => group.dataset.track === "DSA").length,
          systemDesignGroups: shown.filter(
            (group) => group.dataset.track === "System Design"
          ).length,
        };
      }

      results.initial = {
        visibleCards: visibleCards().length,
        visibleGroups: visibleGroups().length,
        label: resultCount.textContent,
      };

      setSearch("n-queens");
      results.nQueens = {
        visibleCards: visibleCards().length,
        visibleGroups: visibleGroups().map(groupKey),
        label: resultCount.textContent,
      };

      setSearch("");
      clickFilter("System Design");
      results.systemDesign = {
        visibleCards: visibleCards().length,
        ...trackCounts(),
        label: resultCount.textContent,
      };

      setSearch("chat");
      results.combined = {
        visibleCards: visibleCards().length,
        visibleGroups: visibleGroups().map(groupKey),
        label: resultCount.textContent,
      };

      setSearch("exercicio");
      clickFilter("DSA");
      results.accentlessDsa = {
        visibleCards: visibleCards().length,
        ...trackCounts(),
        label: resultCount.textContent,
      };

      setSearch("");
      clickFilter("all");
      results.restored = {
        visibleCards: visibleCards().length,
        visibleGroups: visibleGroups().length,
        exactGroupOrder:
          JSON.stringify(groups().map(groupKey)) === JSON.stringify(originalGroupOrder),
        exactCardOrder:
          JSON.stringify(cards().map(cardKey)) === JSON.stringify(originalCardOrder),
        label: resultCount.textContent,
      };

      const output = document.createElement("pre");
      output.id = "probe-results";
      output.textContent = JSON.stringify(results);
      document.body.append(output);
    })();
"""
        expected = {
            "initial": {
                "visibleCards": 58,
                "visibleGroups": 22,
                "label": "58 materiais visíveis",
            },
            "nQueens": {
                "visibleCards": 1,
                "visibleGroups": ["DSA:17"],
                "label": "1 material visível",
            },
            "systemDesign": {
                "visibleCards": 5,
                "dsaGroups": 0,
                "systemDesignGroups": 5,
                "label": "5 materiais visíveis",
            },
            "combined": {
                "visibleCards": 1,
                "visibleGroups": ["System Design:03"],
                "label": "1 material visível",
            },
            "accentlessDsa": {
                "visibleCards": 51,
                "dsaGroups": 17,
                "systemDesignGroups": 0,
                "label": "51 materiais visíveis",
            },
            "restored": {
                "visibleCards": 58,
                "visibleGroups": 22,
                "exactGroupOrder": True,
                "exactCardOrder": True,
                "label": "58 materiais visíveis",
            },
        }

        with TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            portal_path = temporary_path / "index.html"
            portal_path.write_text(
                self.html.replace("</body>", f"<script>{probe}</script>\n</body>"),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-background-networking",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-sandbox",
                    f"--user-data-dir={temporary_path / 'chrome-profile'}",
                    "--virtual-time-budget=1000",
                    "--dump-dom",
                    portal_path.as_uri(),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

        match = re.search(
            r'<pre id="probe-results">(.*?)</pre>', completed.stdout, flags=re.S
        )
        self.assertIsNotNone(match, completed.stderr)
        assert match is not None
        results = json.loads(html_lib.unescape(match.group(1)))
        self.maxDiff = None
        self.assertEqual(results, expected)


if __name__ == "__main__":
    unittest.main()
