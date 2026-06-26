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
    group: str
    kind: str
    href: str
    source_path: str


def humanize_slug(value: str) -> str:
    value = re.sub(r"^\d+[-_ ]*", "", value)
    words = value.replace("_", "-").replace("ç", "c").split("-")
    small = {"da", "de", "do", "das", "dos", "and", "of", "e"}
    return " ".join(word if word in small else word.capitalize() for word in words if word)


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

    for path in sorted(SOURCE.glob("[0-9][0-9]-*/html/*.html")):
        topic = path.parents[1].name
        rel = path.relative_to(SOURCE)
        exercises.append(
            Exercise(
                title=title_from_html(path),
                group=humanize_slug(topic),
                kind="DSA",
                href=f"content/{rel.as_posix()}",
                source_path=rel.as_posix(),
            )
        )

    for path in sorted((SOURCE / "system-design").glob("[0-9][0-9]-*/index.html")):
        topic = path.parent.name
        rel = path.relative_to(SOURCE)
        exercises.append(
            Exercise(
                title=title_from_html(path),
                group=humanize_slug(topic),
                kind="System Design",
                href=f"content/{rel.as_posix()}",
                source_path=rel.as_posix(),
            )
        )

    return exercises


def render_cards(exercises: list[Exercise]) -> str:
    cards = []
    for exercise in exercises:
        search_blob = f"{exercise.title} {exercise.group} {exercise.kind} {exercise.source_path}".lower()
        cards.append(
            f"""
          <article class="card" data-kind="{html.escape(exercise.kind)}" data-search="{html.escape(search_blob)}">
            <div class="card-meta">
              <span>{html.escape(exercise.kind)}</span>
              <span>{html.escape(exercise.group)}</span>
            </div>
            <h3>{html.escape(exercise.title)}</h3>
            <p>{html.escape(exercise.source_path)}</p>
            <a href="{html.escape(exercise.href)}">Abrir HTML</a>
          </article>"""
        )
    return "\n".join(cards)


def render_index(exercises: list[Exercise]) -> str:
    total = len(exercises)
    dsa = sum(1 for item in exercises if item.kind == "DSA")
    system_design = sum(1 for item in exercises if item.kind == "System Design")
    cards = render_cards(exercises)
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
      min-width: 320px;
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
    header {{ padding: clamp(2.5rem, 7vw, 6rem) 0 2rem; }}
    .eyebrow, .stat span, .filter button, .card-meta, .note strong {{
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
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1rem;
      padding: 1rem 0 4rem;
    }}
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
    .card h3 {{
      margin: 1rem 0 .4rem;
      font: 1.55rem/1.08 var(--serif);
      letter-spacing: -.025em;
    }}
    .card p {{
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
      .grid, .stats {{ grid-template-columns: 1fr 1fr; }}
      .toolbar {{ grid-template-columns: 1fr; position: static; }}
    }}
    @media (max-width: 620px) {{
      .grid, .stats {{ grid-template-columns: 1fr; }}
      .filter {{ flex-wrap: wrap; }}
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
        <div class="stat"><strong>{dsa}</strong><span>DSA / algoritmos</span></div>
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
          <button type="button" data-filter="DSA" aria-pressed="false">DSA</button>
          <button type="button" data-filter="System Design" aria-pressed="false">System Design</button>
        </div>
      </section>
      <section class="grid" id="cards" aria-live="polite">
{cards}
      </section>
    </main>

    <footer>
      Gerado por <code>site/build.py</code>. Publicação estática sem backend e sem dependências externas de runtime.
    </footer>
  </div>
  <script>
    (() => {{
      const cards = Array.from(document.querySelectorAll(".card"));
      const search = document.getElementById("search");
      const buttons = Array.from(document.querySelectorAll("[data-filter]"));
      let activeFilter = "all";

      function applyFilters() {{
        const query = search.value.trim().toLowerCase();
        let visible = 0;
        cards.forEach((card) => {{
          const matchesKind = activeFilter === "all" || card.dataset.kind === activeFilter;
          const matchesSearch = !query || card.dataset.search.includes(query);
          const show = matchesKind && matchesSearch;
          card.hidden = !show;
          if (show) visible += 1;
        }});
        document.getElementById("cards").setAttribute("aria-label", `${{visible}} exercícios visíveis`);
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
