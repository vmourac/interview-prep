# System Design para Entrevistas

Esta trilha transforma as aulas locais de system design em dossiês de preparação para entrevistas. O material segue uma abordagem top-down: primeiro fechar escopo e requisitos, depois propor a arquitetura mínima, validar os fluxos funcionais e somente então evoluir a solução para escala, confiabilidade e operação.

Cada tópico contém:

- `README.md`: guia principal para construir a resposta durante a entrevista;
- `deep-dives.md`: análise detalhada dos pontos técnicos que mais diferenciam o problema;
- `index.html`: cockpit interativo e autocontido para revisão ativa e simulação.

Os arquivos HTML não exigem instalação, build ou servidor. Abra qualquer `index.html` diretamente no navegador. Todo o CSS, JavaScript e conteúdo visual está no próprio arquivo.

## Ordem recomendada

### 1. Estrutura da entrevista

Comece pelo método: clarificação, negociação de escopo, requisitos, estimativas orientadas a decisões, arquitetura mínima, deep dives e fechamento.

- [Guia principal](01-estrutura-da-entrevista-system-design/README.md)
- [Deep dives](01-estrutura-da-entrevista-system-design/deep-dives.md)
- [Cockpit interativo](01-estrutura-da-entrevista-system-design/index.html)

### 2. Encurtador de URL

Um problema compacto para praticar assimetria entre leitura e escrita, geração de identificadores, cache, expiração, particionamento e proteção contra abuso.

- [Guia principal](02-encurtador-de-url/README.md)
- [Deep dives](02-encurtador-de-url/deep-dives.md)
- [Cockpit interativo](02-encurtador-de-url/index.html)

### 3. Chat

Um sistema orientado a conexões persistentes e eventos, com desafios de presença, ordenação, entrega, mensagens offline, sincronização entre dispositivos e grupos.

- [Guia principal](03-chat/README.md)
- [Deep dives](03-chat/deep-dives.md)
- [Cockpit interativo](03-chat/index.html)

### 4. Site de venda de ingressos

Um exercício de concorrência e consistência no caminho crítico: inventário escasso, reservas temporárias, filas virtuais, pagamentos idempotentes e reconciliação.

- [Guia principal](04-site-de-venda-de-ingressos/README.md)
- [Deep dives](04-site-de-venda-de-ingressos/deep-dives.md)
- [Cockpit interativo](04-site-de-venda-de-ingressos/index.html)

### 5. Autocomplete

Um caso de baixa latência e leitura intensiva que conecta estruturas de dados, pré-computação, cache, distribuição de trie, processamento offline e publicação de versões.

- [Guia principal](05-autocomplete/README.md)
- [Deep dives](05-autocomplete/deep-dives.md)
- [Cockpit interativo](05-autocomplete/index.html)

## Como estudar

1. Leia o guia principal e tente responder em voz alta às perguntas de clarificação.
2. Refaça as estimativas usando hipóteses próprias e explique quais decisões elas alteram.
3. Desenhe a arquitetura mínima sem consultar o material.
4. Abra o cockpit e percorra os fluxos, perguntas e comparações.
5. Use os deep dives para treinar redirecionamentos do entrevistador.
6. Termine com uma simulação cronometrada de 45 minutos.

## Convenções do conteúdo


Estimativas de tráfego, armazenamento e latência são hipóteses pedagógicas. Elas existem para justificar decisões e não representam números internos reais de empresas ou produtos. Cada guia explicita quando está usando a aula local, quando está aprofundando o tema e quando está assumindo números para raciocínio.

## Critério de uma resposta forte

Uma resposta não é forte porque contém muitos componentes. Ela é forte quando:

- o escopo está explícito;
- cada requisito funcional possui um fluxo completo;
- as estimativas influenciam escolhas concretas;
- estados, APIs e dados são coerentes;
- falhas e recuperação são tratadas;
- os principais trade-offs são comunicados com contexto;
- o candidato consegue explicar como a arquitetura evolui sem fingir que existe uma solução única.
