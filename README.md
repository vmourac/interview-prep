# Interview Prep

Portal público de estudo para entrevistas técnicas.

Conteúdo publicado:

- exercícios interativos de DSA/algoritmos;
- cockpits HTML de System Design;
- guias Markdown de apoio dentro de `interview-prep/`.

Conteúdo não publicado:

- fontes brutas de extração;
- índices internos;
- relatórios internos;
- notas de processo;
- metadados autenticados.

O deploy é feito por GitHub Pages via `.github/workflows/pages.yml`. O workflow executa `python3 site/build.py` e publica somente o diretório gerado `public/`.
