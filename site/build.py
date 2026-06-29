#!/usr/bin/env python3
"""Build the public Interview Prep static site.

The source repository contains authenticated/raw extraction material that must
not be published. This builder intentionally copies only the study artifacts
under interview-prep/ and skips project/process folders.
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "interview-prep"
PUBLIC = ROOT / "public"
CONTENT = PUBLIC / "content"


PRIVATE_MARKERS = tuple(f"{name}/" for name in ("raw", "wiki", "outputs"))


@dataclass(frozen=True)
class Exercise:
    title: str
    category: str
    group: str
    kind: str
    href: str
    source_path: str
    topic_number: int
    topic_slug: str
    item_number: int
    item_label: str
    material_type: str


TOPIC_RE = re.compile(r"^(?P<number>\d{2})-(?P<theme>.+)$")


def humanize_slug(value: str) -> str:
    value = re.sub(r"^\d+[-_ ]*", "", value)
    words = value.replace("_", "-").replace("ç", "c").split("-")
    small = {"da", "de", "do", "das", "dos", "and", "of", "e"}
    return " ".join(word if word in small else word.capitalize() for word in words if word)


def topic_metadata(topic_slug: str) -> tuple[int, str]:
    match = TOPIC_RE.fullmatch(topic_slug)
    if not match:
        raise ValueError(f"invalid numbered topic directory: {topic_slug}")
    return int(match.group("number")), humanize_slug(match.group("theme"))


def readme_html_order(topic_dir: Path) -> dict[str, int]:
    readme = topic_dir / "README.md"
    if not readme.exists():
        return {}
    try:
        readme_text = readme.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}
    filenames = re.findall(
        r"\]\(\./html/([^\s)#?]+\.html)\)",
        readme_text,
        flags=re.IGNORECASE,
    )
    order: dict[str, int] = {}
    for index, filename in enumerate(filenames, start=1):
        order.setdefault(filename, index)
    return order


def ordered_topic_htmls(topic_dir: Path) -> list[Path]:
    paths = list((topic_dir / "html").glob("*.html"))
    readme_order = readme_html_order(topic_dir)
    return sorted(
        paths,
        key=lambda path: (
            0 if path.name == "01-conceitos.html" else 1,
            readme_order.get(path.name, 10_000),
            path.name,
        ),
    )


def numbered_topic_dirs(root: Path) -> list[Path]:
    topics = [path for path in root.glob("[0-9][0-9]-*") if path.is_dir()]
    return sorted(topics, key=lambda path: (topic_metadata(path.name)[0], path.name))


def title_from_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")[:120_000]
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    if not match:
        match = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.I | re.S)
    if not match:
        return humanize_slug(path.stem)
    title = re.sub(r"<[^>]+>", " ", match.group(1))
    title = html.unescape(re.sub(r"\s+", " ", title)).strip()
    title = title.replace(" - Interview Prep", "")
    title = title.replace("Cockpit de entrevista — ", "")
    return title


def sanitize_markdown(text: str) -> str:
    """Remove links/references to local private extraction material."""
    lines = []
    for line in text.splitlines():
        if any(marker in line for marker in PRIVATE_MARKERS):
            continue
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def copy_file(source: Path, destination: Path, sanitize: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if sanitize:
        destination.write_text(sanitize_markdown(source.read_text(encoding="utf-8")), encoding="utf-8")
    else:
        shutil.copy2(source, destination)


def copy_content() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True)
    CONTENT.mkdir(parents=True)

    for path in sorted(SOURCE.glob("[0-9][0-9]-*/html/*.html")):
        copy_file(path, CONTENT / path.relative_to(SOURCE))

    system_design = SOURCE / "system-design"
    for path in sorted(system_design.glob("*.md")):
        copy_file(path, CONTENT / path.relative_to(SOURCE), sanitize=True)
    for topic in sorted(system_design.glob("[0-9][0-9]-*")):
        if not topic.is_dir():
            continue
        for filename in ("README.md", "deep-dives.md", "index.html"):
            path = topic / filename
            if path.exists():
                copy_file(path, CONTENT / path.relative_to(SOURCE), sanitize=path.suffix == ".md")


def discover_exercises() -> list[Exercise]:
    exercises: list[Exercise] = []

    for topic_dir in numbered_topic_dirs(SOURCE):
        topic_number, topic_title = topic_metadata(topic_dir.name)
        for item_number, path in enumerate(ordered_topic_htmls(topic_dir), start=1):
            rel = path.relative_to(SOURCE)
            exercises.append(
                Exercise(
                    title=title_from_html(path),
                    category="Algoritmos e Estruturas de Dados (DSA)",
                    group=topic_title,
                    kind="DSA",
                    href=f"content/{rel.as_posix()}",
                    source_path=rel.as_posix(),
                    topic_number=topic_number,
                    topic_slug=topic_dir.name,
                    item_number=item_number,
                    item_label=f"{topic_number:02d}.{item_number}",
                    material_type=(
                        "Conceitos" if path.name == "01-conceitos.html" else "Exercício"
                    ),
                )
            )

    system_design = SOURCE / "system-design"
    for topic_dir in numbered_topic_dirs(system_design):
        path = topic_dir / "index.html"
        if not path.exists():
            continue
        topic_number, topic_title = topic_metadata(topic_dir.name)
        rel = path.relative_to(SOURCE)
        exercises.append(
            Exercise(
                title=title_from_html(path),
                category="System Design",
                group=topic_title,
                kind="System Design",
                href=f"content/{rel.as_posix()}",
                source_path=rel.as_posix(),
                topic_number=topic_number,
                topic_slug=topic_dir.name,
                item_number=1,
                item_label=f"{topic_number:02d}.1",
                material_type="Cockpit",
            )
        )

    return exercises


def grouped_exercises(
    exercises: list[Exercise],
) -> list[tuple[tuple[str, int, str], list[Exercise]]]:
    groups: dict[tuple[str, int, str], list[Exercise]] = {}
    for exercise in exercises:
        key = (exercise.kind, exercise.topic_number, exercise.topic_slug)
        groups.setdefault(key, []).append(exercise)
    return list(groups.items())


def render_card(exercise: Exercise) -> str:
    search_blob = (
        f"{exercise.item_label} {exercise.material_type} {exercise.title} "
        f"{exercise.category} {exercise.group} {exercise.kind} "
        f"{exercise.topic_slug} {exercise.source_path}"
    ).lower()
    return f"""
          <article class="card" data-kind="{html.escape(exercise.kind)}"
            data-search="{html.escape(search_blob)}">
            <div class="card-meta">
              <span class="item-position">{html.escape(exercise.item_label)}</span>
              <span class="material-type">{html.escape(exercise.material_type)}</span>
            </div>
            <h3>{html.escape(exercise.title)}</h3>
            <p class="card-context">{html.escape(exercise.category)} · {html.escape(exercise.group)}</p>
            <a href="{html.escape(exercise.href)}">Abrir HTML</a>
          </article>"""


def render_topic_sections(exercises: list[Exercise]) -> str:
    sections = []
    totals = {"DSA": 17, "System Design": 5}
    for (kind, topic_number, topic_slug), items in grouped_exercises(exercises):
        track_slug = "dsa" if kind == "DSA" else "system-design"
        topic_id = f"topic-{track_slug}-{topic_number:02d}"
        cards = "\n".join(render_card(item) for item in items)
        material_label = "material" if len(items) == 1 else "materiais"
        sections.append(
            f"""
        <section class="topic-group" data-track="{html.escape(kind)}"
          data-topic="{topic_number:02d}" aria-labelledby="{topic_id}">
          <header class="topic-header">
            <div>
              <div class="topic-kicker">
                <span class="topic-sequence">Tópico {topic_number:02d} de {totals[kind]:02d}</span>
                <span class="topic-category">{html.escape(items[0].category)}</span>
              </div>
              <h2 id="{topic_id}">{html.escape(items[0].group)}</h2>
            </div>
            <span class="topic-count">{len(items)} {material_label}</span>
          </header>
          <div class="topic-grid">{cards}
          </div>
        </section>"""
        )
    return "\n".join(sections)


def render_index(exercises: list[Exercise]) -> str:
    total = len(exercises)
    dsa = sum(1 for item in exercises if item.kind == "DSA")
    system_design = sum(1 for item in exercises if item.kind == "System Design")
    initial_material_label = "material visível" if total == 1 else "materiais visíveis"
    topic_sections = render_topic_sections(exercises)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Portal estático de estudo para entrevistas: DSA e System Design.">
  <title>Interview Prep — Portal de Estudos</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101210;
      --panel: #181d19;
      --panel-2: #222820;
      --ink: #f2eadf;
      --muted: #aaa196;
      --line: #3d463d;
      --gold: #f0b35b;
      --mint: #8fd6aa;
      --blue: #8fc7e8;
      --red: #ef7664;
      --shadow: 0 22px 70px rgba(0, 0, 0, .35);
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      --serif: Georgia, Cambria, "Times New Roman", serif;
      --sans: "Trebuchet MS", "Gill Sans", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(rgba(255,255,255,.02) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.02) 1px, transparent 1px),
        radial-gradient(circle at 86% 10%, rgba(240,179,91,.16), transparent 28rem),
        radial-gradient(circle at 8% 35%, rgba(143,214,170,.10), transparent 30rem),
        var(--bg);
      background-size: 34px 34px, 34px 34px, auto, auto, auto;
      font-family: var(--sans);
      line-height: 1.55;
    }}
    a {{ color: var(--mint); text-underline-offset: .2em; }}
    a:hover {{ color: var(--ink); }}
    .shell {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
    .shell > header {{ padding: clamp(2.5rem, 7vw, 6rem) 0 2rem; }}
    .eyebrow, .stat span, .filter button, .card-meta, .note strong,
    .topic-kicker, .topic-count {{
      font: .72rem var(--mono);
      letter-spacing: .12em;
      text-transform: uppercase;
    }}
    .eyebrow {{ color: var(--gold); }}
    h1 {{
      max-width: 840px;
      margin: .35rem 0 1rem;
      font: clamp(3.1rem, 9vw, 7rem)/.88 var(--serif);
      letter-spacing: -.06em;
    }}
    .lead {{ max-width: 760px; color: var(--muted); font-size: 1.08rem; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1px;
      margin: 2rem 0;
      border: 1px solid var(--line);
      background: var(--line);
      box-shadow: var(--shadow);
    }}
    .stat {{ padding: 1rem; background: rgba(24,29,25,.96); }}
    .stat strong {{ display: block; font: 2rem var(--serif); color: var(--ink); }}
    .stat span {{ color: var(--muted); }}
    .toolbar {{
      position: sticky;
      top: 0;
      z-index: 3;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: .8rem;
      padding: .9rem 0;
      background: linear-gradient(var(--bg) 75%, rgba(16,18,16,0));
    }}
    input {{
      width: 100%;
      border: 1px solid var(--line);
      padding: .9rem 1rem;
      color: var(--ink);
      background: rgba(24,29,25,.94);
      font: 1rem var(--sans);
    }}
    input:focus {{ outline: 3px solid rgba(240,179,91,.45); border-color: var(--gold); }}
    .filter {{ display: flex; gap: .5rem; }}
    .filter button {{
      border: 1px solid var(--line);
      padding: .85rem .9rem;
      color: var(--ink);
      background: var(--panel);
      cursor: pointer;
    }}
    .filter button[aria-pressed="true"] {{
      color: #111;
      background: var(--gold);
      border-color: var(--gold);
    }}
    .topic-sections {{
      padding: 1rem 0 4rem;
    }}
    .topic-group {{
      --track-accent: var(--gold);
      border-top: 3px solid var(--track-accent);
      padding: clamp(1.4rem, 3vw, 2.4rem) 0 clamp(3rem, 7vw, 5.5rem);
    }}
    .topic-group[data-track="System Design"] {{
      --track-accent: var(--blue);
    }}
    .topic-header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
      gap: 1.25rem;
      margin-bottom: 1.25rem;
    }}
    .topic-header > div {{ min-width: 0; }}
    .topic-kicker {{
      display: flex;
      flex-wrap: wrap;
      gap: .35rem 1rem;
      margin-bottom: .45rem;
      color: var(--muted);
    }}
    .topic-sequence {{ color: var(--gold); font-weight: 700; }}
    .topic-category {{ color: var(--ink); }}
    .topic-header h2 {{
      margin: 0;
      font: clamp(2rem, 5vw, 3.8rem)/.95 var(--serif);
      letter-spacing: -.045em;
      overflow-wrap: anywhere;
    }}
    .topic-count {{
      border: 1px solid var(--track-accent);
      padding: .45rem .6rem;
      color: var(--ink);
      background: var(--panel);
      white-space: nowrap;
    }}
    .topic-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1rem;
    }}
    .topic-grid > * {{ min-width: 0; }}
    .card {{
      display: grid;
      align-content: start;
      min-height: 14rem;
      border: 1px solid var(--line);
      padding: 1rem;
      background: linear-gradient(150deg, rgba(255,255,255,.035), transparent), var(--panel);
      box-shadow: var(--shadow);
    }}
    .card[hidden] {{ display: none; }}
    .card-meta {{ display: flex; flex-wrap: wrap; gap: .4rem; color: var(--muted); }}
    .card-meta span {{
      border: 1px solid var(--line);
      padding: .18rem .4rem;
      background: var(--panel-2);
    }}
    .card-meta .item-position {{
      border-color: var(--gold);
      color: var(--gold);
      font-weight: 700;
    }}
    .card-meta .material-type {{ color: var(--ink); }}
    .card h3 {{
      margin: 1rem 0 .4rem;
      font: 1.55rem/1.08 var(--serif);
      letter-spacing: -.025em;
    }}
    .card-context {{
      margin: 0 0 1.2rem;
      color: var(--muted);
      font: .78rem/1.45 var(--mono);
      overflow-wrap: anywhere;
    }}
    .card a {{
      align-self: end;
      justify-self: start;
      margin-top: auto;
      border: 1px solid var(--mint);
      padding: .55rem .75rem;
      color: #0d1510;
      background: var(--mint);
      text-decoration: none;
      font: .78rem var(--mono);
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .note {{
      margin: 0 0 1.2rem;
      border-left: 4px solid var(--red);
      padding: .9rem 1rem;
      color: var(--muted);
      background: rgba(239,118,100,.08);
    }}
    .note strong {{ color: var(--red); }}
    footer {{ border-top: 1px solid var(--line); padding: 1.5rem 0 2rem; color: var(--muted); }}
    @media (max-width: 900px) {{
      .topic-grid, .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .toolbar {{ grid-template-columns: minmax(0, 1fr); position: static; }}
    }}
    @media (max-width: 620px) {{
      .topic-grid, .stats {{ grid-template-columns: minmax(0, 1fr); }}
      .topic-header {{ grid-template-columns: minmax(0, 1fr); align-items: start; }}
      .topic-count {{ justify-self: start; white-space: normal; }}
      .filter {{ flex-wrap: wrap; }}
      .filter button {{ flex: 1 1 auto; overflow-wrap: anywhere; }}
      h1 {{ font-size: clamp(2.8rem, 18vw, 4.2rem); }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="eyebrow">portal estático · entrevista prep</div>
      <h1>Treino de entrevistas em HTML.</h1>
      <p class="lead">Índice pesquisável dos exercícios interativos de algoritmos e dos cockpits de System Design. Cada link abre um HTML autocontido para estudar ou apresentar diretamente no navegador.</p>
      <div class="stats" aria-label="Resumo do conteúdo publicado">
        <div class="stat"><strong>{total}</strong><span>HTMLs publicados</span></div>
        <div class="stat"><strong>{dsa}</strong><span>Algoritmos e Estruturas de Dados (DSA)</span></div>
        <div class="stat"><strong>{system_design}</strong><span>System Design</span></div>
      </div>
      <p class="note"><strong>Escopo publicado:</strong> este site inclui somente artefatos de estudo em <code>interview-prep/</code>. Fontes raw, metadados autenticados, relatórios internos e notas de processo não fazem parte do artefato Pages.</p>
    </header>

    <main>
      <section class="toolbar" aria-label="Busca e filtros">
        <label>
          <span class="eyebrow">buscar exercício</span>
          <input id="search" type="search" placeholder="Ex.: graph, URL, autocomplete, stack..." autocomplete="off">
        </label>
        <div class="filter" role="group" aria-label="Filtrar por categoria">
          <button type="button" data-filter="all" aria-pressed="true">todos</button>
          <button type="button" data-filter="DSA" aria-pressed="false">Algoritmos e Estruturas de Dados (DSA)</button>
          <button type="button" data-filter="System Design" aria-pressed="false">System Design</button>
        </div>
        <span id="result-count" role="status" aria-live="polite" aria-atomic="true">{total} {initial_material_label}</span>
      </section>
      <div class="topic-sections" id="cards">
{topic_sections}
      </div>
    </main>

    <footer>
      Gerado por <code>site/build.py</code>. Publicação estática sem backend e sem dependências externas de runtime.
    </footer>
  </div>
  <script>
    (() => {{
      const cards = Array.from(document.querySelectorAll(".card"));
      const groups = Array.from(document.querySelectorAll(".topic-group"));
      const search = document.getElementById("search");
      const buttons = Array.from(document.querySelectorAll("[data-filter]"));
      const resultCount = document.getElementById("result-count");
      let activeFilter = "all";

      function normalizeSearch(value) {{
        return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      }}

      function applyFilters() {{
        const query = normalizeSearch(search.value.trim());
        let visible = 0;
        cards.forEach((card) => {{
          const matchesKind = activeFilter === "all" || card.dataset.kind === activeFilter;
          const matchesSearch = !query || normalizeSearch(card.dataset.search).includes(query);
          const show = matchesKind && matchesSearch;
          card.hidden = !show;
          if (show) visible += 1;
        }});
        groups.forEach((group) => {{
          group.hidden = !group.querySelector(".card:not([hidden])");
        }});
        const materialLabel = visible === 1 ? "material visível" : "materiais visíveis";
        const resultLabel = `${{visible}} ${{materialLabel}}`;
        resultCount.textContent = resultLabel;
        document.getElementById("cards").setAttribute("aria-label", resultLabel);
      }}

      search.addEventListener("input", applyFilters);
      buttons.forEach((button) => {{
        button.addEventListener("click", () => {{
          activeFilter = button.dataset.filter;
          buttons.forEach((candidate) => {{
            candidate.setAttribute("aria-pressed", String(candidate === button));
          }});
          applyFilters();
        }});
      }});
      applyFilters();
    }})();
  </script>
</body>
</html>
"""


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing source directory: {SOURCE}")
    copy_content()
    exercises = discover_exercises()
    if not exercises:
        raise SystemExit("no HTML exercises found")
    (PUBLIC / "index.html").write_text(render_index(exercises), encoding="utf-8")
    print(f"built {len(exercises)} HTML entries into {PUBLIC}")


if __name__ == "__main__":
    main()
