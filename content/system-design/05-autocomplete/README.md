# Autocomplete — guia de entrevista de system design

> **Objetivo:** desenhar um serviço de sugestões que responda enquanto a pessoa digita, ordene resultados por relevância global e continue rápido sob tráfego e vocabulário muito grandes.
>
> **Legenda de rastreabilidade**
>
> - **Aula local:** conteúdo apresentado ou diretamente sustentado pela aula `Use Cases - Autocomplete`.
> - **Complemento:** aprofundamento consolidado de system design adicionado para tornar a resposta operacional e completa.
> - **Hipótese pedagógica:** número escolhido apenas para exercitar estimativas; deve ser renegociado com o entrevistador.

Este guia segue a narrativa recomendada na **aula local**: começar pelo problema e pelos requisitos, introduzir estimativas quando elas mudarem uma decisão, definir interfaces e dados, construir a arquitetura mínima, validá-la e só então aprofundar escala e requisitos não funcionais. O erro clássico é desenhar caixas antes de saber o que elas precisam garantir.

Materiais relacionados: [deep dives](deep-dives.md) e [cockpit interativo](index.html).

## 1. Enquadramento do problema

Autocomplete, ou *typeahead suggestion*, recebe um prefixo e retorna as melhores continuações antes de a pessoa concluir a entrada. O mesmo nome esconde dois produtos de escalas distintas:

- **Aula local — dicionário no dispositivo:** cerca de 100–200 mil palavras relativamente estáveis, adequadas a uma lista, mapa ou trie local.
- **Aula local — sugestões de busca global:** termos com várias palavras, aproximadamente 20 caracteres em média e um universo que pode chegar à ordem de um bilhão de consultas únicas por dia.

Para a entrevista, adotaremos o segundo caso. O sistema sugere consultas globais, não corrige ortografia, não busca documentos e não personaliza por usuário. A qualidade do ranking será aproximada pela frequência global recente, segmentada opcionalmente por localidade ou idioma. A exclusão deliberada de personalização é importante: ela evita transformar um problema de leitura global em um sistema de ranking individual, privacidade e armazenamento de perfil.

A operação crítica é a leitura. Se o serviço ficar indisponível, o usuário ainda pode terminar de digitar e pesquisar; portanto autocomplete é degradável, mas a experiência perde fluidez. Se uma sugestão estiver algumas horas desatualizada, o produto continua funcional. Isso orienta a escolha por **alta disponibilidade e baixa latência**, aceitando **consistência eventual**.

## 2. Perguntas de clarificação

Comece negociando o escopo em voz alta. Perguntas úteis:

1. Estamos completando palavras locais ou consultas globais com múltiplas palavras?
2. Quantas sugestões retornamos: top 3, top 5 ou top 10?
3. O ranking é apenas por frequência global ou inclui idioma, região, recência e personalização?
4. Qual é a expectativa de frescor: segundos, horas ou atualização diária?
5. O sistema recebe cada tecla ou o cliente aplica debounce?
6. Precisamos sugerir com prefixo vazio, exibindo tendências globais?
7. Devemos filtrar conteúdo impróprio, ilegal, sensível ou manipulado?
8. Há uma meta explícita de latência no percentil 95 ou 99?
9. O envio da busca concluída para treinamento pode ser perdido ou precisa de durabilidade?
10. O serviço deve funcionar durante a publicação de uma nova versão do índice?

Uma resposta de escopo concisa seria:

> “Vou projetar sugestões globais de consultas, com top 10, segmentação por locale, ranking por frequência e recência agregadas, atualização diária e sem personalização. Priorizarei p95 baixo e disponibilidade; atraso de até um ciclo de rebuild é aceitável.”

## 3. Requisitos funcionais

### Essenciais

- **Aula local:** receber um prefixo e retornar as principais sugestões enquanto o usuário digita.
- **Aula local:** aceitar palavras isoladas e consultas com múltiplas palavras.
- **Aula local:** ordenar por frequência global.
- **Aula local:** atualizar as tendências aproximadamente uma vez por dia.
- **Aula local:** registrar a consulta final submetida para alimentar o próximo ranking.
- Respeitar `locale` ou mercado quando fornecido.
- Retornar uma lista vazia de forma válida quando não houver candidato.
- Suportar prefixo vazio como consulta opcional de tendências.

### Fora de escopo inicial

- Personalização por usuário.
- Correção ortográfica e busca difusa.
- Busca semântica e embeddings.
- Sugestões patrocinadas.
- Indexação de documentos ou execução da busca.
- Atualização síncrona da trie a cada evento.

Esses itens podem ser extensões, mas anunciá-los cedo protege o tempo da entrevista.

## 4. Requisitos não funcionais

### Prioridades

- **Latência:** alvo pedagógico de p95 abaixo de 100 ms no backend e experiência percebida abaixo de 250 ms após a última tecla.
- **Disponibilidade:** o caminho de leitura deve permanecer disponível durante falhas de worker, cache, partição e rebuild.
- **Escala de leitura:** cada sessão gera várias requisições; o volume de leitura supera o de buscas submetidas.
- **Frescor:** versão diária é suficiente no núcleo; tendências intradiárias podem existir como camada separada.
- **Consistência eventual:** diferentes regiões podem servir versões adjacentes por um intervalo curto.
- **Durabilidade do feedback:** perda pequena pode ser tolerável estatisticamente, mas a fila e o armazenamento devem impedir perdas sistemáticas.
- **Segurança e privacidade:** logs de consulta podem conter dados pessoais; coleta, retenção e acesso precisam ser controlados.
- **Manutenção:** a versão servida deve ser identificável, reversível e validada antes da promoção.

### SLOs pedagógicos

**Hipóteses pedagógicas**, não números da aula:

- disponibilidade mensal de leitura: 99,99%;
- p95 do backend: 80 ms; p99: 150 ms;
- taxa de erro: menor que 0,1%;
- publicação de versão: concluída em até 30 minutos após o artefato ficar pronto;
- idade máxima normal do índice: 30 horas;
- rollback: menos de 10 minutos.

## 5. Estimativas que alteram decisões

A **aula local** recomenda evitar cálculos ritualísticos. Faça a conta perto da decisão que ela justifica.

### 5.1 Amplificação por tecla

**Hipótese pedagógica:** 500 milhões de buscas concluídas por dia, 8 caracteres observados antes da seleção, debounce que elimina metade dos estados intermediários.

```text
requisições/dia ≈ 500 M × 8 × 0,5 = 2 bilhões
QPS médio       ≈ 2 B / 86.400 ≈ 23 mil
pico 5×         ≈ 116 mil QPS
```

Consequência: workers stateless, cache multinível e respostas pequenas são necessários. O debounce não é detalhe de frontend; ele reduz diretamente a frota.

### 5.2 Universo de consultas

A **aula local** usa a ordem de um bilhão de consultas únicas por dia e 20 caracteres médios. Materializar todos os prefixos com strings repetidas explode memória. Mesmo que cada entrada lógica pareça pequena, uma consulta de 20 caracteres participa de até 20 prefixos.

**Hipótese pedagógica simplificada:**

```text
1 B termos × 20 prefixos × top 10 × 4 bytes por ID
= 800 GB apenas para IDs de candidatos
```

Isso ignora nós, ponteiros, scores, dicionário de strings, alinhamento e replicação. Consequência: compressão, poda de cauda longa, particionamento e armazenamento somente do top-k realmente necessário.

### 5.3 Tamanho da resposta

Se cada resposta tiver 10 sugestões de 40 bytes em média, mais metadados:

```text
≈ 600 bytes/resposta × 116 mil QPS de pico ≈ 70 MB/s
```

Antes de TLS e overhead de rede. Consequência: CDN para prefixos populares, compressão de transporte quando compensar e evitar scores internos desnecessários no payload.

### 5.4 Pipeline de eventos

Se apenas consultas efetivamente submetidas entram no feedback, 500 milhões/dia representam cerca de 5,8 mil eventos/s em média, talvez 30 mil/s no pico. Esse caminho é menor que o read path, porém acumula dados suficientes para exigir fila, armazenamento distribuído e agregação paralela.

## 6. Entidades

- **Prefixo:** texto normalizado digitado até o momento.
- **Sugestão:** consulta candidata exibível.
- **Score:** valor usado para ordenar; pode combinar frequência, recência e regras editoriais.
- **Locale:** idioma, país ou mercado que seleciona o corpus.
- **Evento de busca:** consulta final submetida, timestamp, locale e identificador técnico de deduplicação.
- **Versão do índice:** artefato imutável com ID, janela de dados, checksum, esquema e status.
- **Partição lexical:** intervalo de chaves associado a um conjunto de réplicas.
- **Política de segurança:** bloqueios e limites aplicados antes da publicação ou da resposta.

## 7. API e interfaces

### 7.1 Leitura

```http
GET /v1/suggestions?prefix=uber%20e&locale=pt-BR&limit=10
```

Resposta:

```json
{
  "prefix": "uber e",
  "locale": "pt-BR",
  "suggestions": [
    {"text": "uber eats", "rank": 1},
    {"text": "uber eats mercado", "rank": 2}
  ],
  "indexVersion": "2026-06-22T02:00:00Z",
  "ttlSeconds": 120
}
```

Decisões:

- `GET` facilita cache por URL; normalize ordem e encoding dos parâmetros.
- `limit` deve ter teto, por exemplo 10, para proteger CPU e payload.
- Não exponha frequência bruta: ela facilita manipulação e pode revelar padrões sensíveis.
- `indexVersion` torna depuração e rollout observáveis.
- Para prefixos vazios ou de um caractere, o TTL pode ser maior, pois são muito cacheáveis.

### 7.2 Registro de busca concluída

O cliente não precisa bloquear a navegação esperando confirmação:

```http
POST /v1/query-events
Idempotency-Key: 018f...
Content-Type: application/json

{
  "query": "uber eats mercado",
  "locale": "pt-BR",
  "submittedAt": "2026-06-22T12:34:56Z"
}
```

**Complemento:** o serviço valida tamanho e encoding, remove ou tokeniza identificadores quando aplicável, anexa metadados técnicos e publica o evento na fila. A chave idempotente evita contagem dupla por retry, embora deduplicação perfeita não seja obrigatória para um ranking estatístico.

### 7.3 HTTP versus WebSocket

A **aula local** apresenta WebSocket como otimização: reduz headers repetidos e permite manter um cursor da trie. A escolha inicial recomendada é HTTP com keep-alive/HTTP/2 ou HTTP/3, debounce e CDN, porque preserva workers stateless e simplifica operação. WebSocket passa a valer quando medições mostram que overhead, latência de conexão ou estado incremental dominam o custo.

## 8. Modelo de dados

### 8.1 Índice de serving

Representação lógica de um nó:

```text
TrieNode {
  children: mapa compacto caractere -> childOffset
  topIds: [termId; K]
  topScores: [scoreQuantizado; K]
  terminal: boolean
}
```

Dicionário separado:

```text
TermDictionary {
  termId -> string normalizada
}
```

Manifesto:

```text
IndexManifest {
  version
  locale
  lexicalRange
  objectUris
  checksums
  nodeCount
  termCount
  builtFrom
  schemaVersion
}
```

**Aula local:** IDs inteiros substituem strings repetidas nas listas top-k.  
**Complemento:** offsets compactos, arrays contíguos e artefatos imutáveis melhoram localidade de cache, carregamento e rollback.

### 8.2 Eventos e agregados

```text
QueryEvent(eventId, normalizedQuery, locale, submittedAt, partitionDate)
DailyCount(normalizedQuery, locale, date, count)
CandidateScore(termId, locale, score, sourceWindow)
```

Os eventos brutos ficam particionados por data e locale. Agregados diários podem ser reprocessados sem reler toda a história. O índice final é derivado, portanto pode ser reconstruído.

### 8.3 Normalização

Antes de agregar:

- aplicar Unicode normalization;
- definir política de caixa;
- colapsar espaços;
- limitar comprimento;
- preservar ou remover acentos conforme locale;
- rejeitar caracteres de controle;
- aplicar filtros de segurança;
- evitar transformar consultas diferentes em uma única chave de forma destrutiva.

## 9. Evolução das estruturas de leitura

### 9.1 Lista ordenada + busca binária + min-heap

**Aula local:** palavras ficam em ordem lexicográfica. Busca binária encontra o início do intervalo do prefixo; uma varredura coleta candidatos e um min-heap limitado mantém o top-k.

- Ganho: implementação simples e ótima para dicionário pequeno.
- Custo: a consulta ainda varre todos os candidatos do intervalo.
- Quando usar: teclado local, corpus estável, memória modesta.

### 9.2 Mapa de prefixos

Cada prefixo aponta diretamente para seu top-k.

- Ganho: lookup simples, aproximadamente proporcional ao tamanho do prefixo para computar a chave.
- Custo: materializa `a`, `ap`, `app`, `appl`, `apple` e repete listas.
- Quando usar: corpus pequeno, limites rígidos de tamanho e rebuild simples.

### 9.3 Trie com top-k por nó

**Aula local:** prefixos comuns compartilham caminho. Depois de percorrer `p` caracteres, o nó já contém o top-k.

- Ganho: lookup `O(p)` e compartilhamento de prefixos.
- Custo: muitos nós, ponteiros e listas top-k; precisa de representação compacta.
- Quando usar: grande volume, prefixos compartilhados e leitura muito frequente.

A entrevista fica mais forte quando mostra a evolução, em vez de apresentar a trie como resposta mágica.

## 10. Arquitetura mínima

Para um primeiro desenho:

```text
Cliente
  -> debounce
  -> Suggestion Service stateless
  -> índice de trie em memória

Busca submetida
  -> Query Logger
  -> fila
  -> agregação diária
  -> novo índice
```

Passo a passo do read path:

1. O cliente espera 150–200 ms após a última tecla, conforme a **aula local**.
2. Cancela a requisição anterior se um novo caractere chegar.
3. Envia prefixo normalizado e locale.
4. O worker percorre a trie da versão ativa.
5. Lê IDs top-k do nó.
6. Decodifica IDs pelo dicionário.
7. Aplica filtros finais e retorna.

Essa arquitetura já cobre sugestões, multi-word, top-k e atualização offline. Ainda não cobre escala global, cache, publicação segura e falhas de partição.

## 11. Arquitetura escalada

```text
Cliente
  -> debounce/cancelamento
  -> CDN / edge cache
  -> balanceador regional
  -> Suggestion Workers stateless
       -> cache local de prefixos
       -> hot trie / Redis
       -> shard lexical da versão ativa

Busca concluída
  -> Query Logger
  -> Kafka
  -> ingestão/validação
  -> data lake/HDFS particionado
  -> agregação diária distribuída
  -> cálculo de scores e top-k
  -> Trie Builder
  -> validação
  -> registry de versões
  -> canário
  -> troca atômica do manifesto
  -> aquecimento e rollout regional
```

### Camadas de cache

1. **Cliente:** resultados da sessão para backspace e prefixos repetidos.
2. **CDN:** prefixos curtos e populares; chave inclui locale e versão lógica.
3. **Worker:** cache LRU de respostas já decodificadas.
4. **Hot trie/Redis:** partições quentes compartilhadas.
5. **Índice persistente ou memory-mapped:** fonte local da versão completa do shard.

Não se deve colocar uma chamada remota por caractere percorrido. O shard precisa responder ao prefixo inteiro localmente.

## 12. Top-k e ranking

Durante o rebuild, cada termo tem um score. Uma fórmula pedagógica:

```text
score = log(1 + frequência_7d)
      + α × log(1 + frequência_1d)
      + β × tendência
      - penalidades_de_abuso
```

**Complemento:** o score exato é domínio de produto. Para o system design, importa que:

- o cálculo ocorra offline;
- cada nó mantenha somente k candidatos;
- merges distribuídos sejam associativos quando possível;
- empates tenham critério estável;
- o serving não faça ordenação global cara;
- filtros possam remover um item sem quebrar a resposta — por isso pode-se armazenar `k + margem`.

No builder, uma travessia pós-ordem pode propagar os melhores candidatos dos filhos para o pai. Em larga escala, partições calculam top-k locais e uma etapa de merge produz o top-k final de cada prefixo.

## 13. Escalabilidade e particionamento

### Partição lexical

A **aula local** prefere intervalos lexicais porque hashing de cada prefixo poderia enviar `u`, `ub`, `ube` e `uber` a servidores diferentes. Um intervalo mantém a trajetória do prefixo no mesmo shard.

Exemplo:

```text
[a, car)   -> shard 1
[car, m)   -> shard 2
[m, uber)  -> shard 3
[uber, z]  -> shard 4
```

Os limites reais não devem ser letras fixas. Distribuição linguística e popularidade são enviesadas. Prefixos como `a`, `s` ou termos de uma notícia podem concentrar QPS e memória.

### Skew e hotspots

Mitigações:

- dividir ranges quentes em subranges mais finos;
- replicar ranges de leitura quentes sem reparticionar imediatamente;
- usar CDN para prefixos de baixa cardinalidade;
- manter histogramas de QPS, bytes e latência por range;
- mover limites apenas em mudanças controladas;
- permitir sobreposição temporária durante migração;
- versionar o mapa de roteamento;
- proteger origem com request coalescing e limites.

**Complemento:** um coordenador pode distribuir o mapa de shards, mas o read path não deve consultar o coordenador a cada requisição. Workers usam snapshots versionados.

## 14. Publicação atômica do índice

A **aula local** menciona rebuild e swap diário. Para torná-lo operacional:

1. O builder grava artefatos imutáveis em um namespace da nova versão.
2. Calcula checksums e manifesto.
3. Executa validações: ordenação, top-k, cobertura de locales, tamanho, conteúdo proibido e amostras conhecidas.
4. Carrega a versão em workers canário.
5. Compara latência, erros e qualidade com a versão ativa.
6. Promove alterando um ponteiro/manifesto pequeno e atômico.
7. Workers novos passam a abrir a nova versão; os antigos concluem requisições na anterior.
8. Após estabilização, expira caches antigos e retém pelo menos uma versão para rollback.

Nunca sobrescreva arquivos da versão ativa. Uma publicação parcial misturaria nós e dicionários incompatíveis.

## 15. Confiabilidade, disponibilidade e recuperação

### Falha de worker

O balanceador remove o worker; requisições são reencaminhadas. Como o índice é imutável, o worker pode reiniciar e recarregar a versão.

### Falha do cache

Degrade para índice local/persistente, com circuit breaker para evitar tempestade. Se o hot cache falhar globalmente, reduza TTL apenas depois de controlar a origem; caso contrário, todos os misses viram sobrecarga.

### Falha de shard

Cada range tem réplicas em zonas distintas. O roteador tenta réplica saudável. Se todas falharem, pode retornar cache stale, sugestões de prefixo ancestral ou lista vazia — nunca deve bloquear a busca principal.

### Falha no pipeline

Continue servindo a versão anterior. A idade do índice aumenta e gera alerta, mas o produto permanece disponível. Reprocessamento parte do log durável e de checkpoints.

### Versão ruim

Rollback troca o manifesto para a versão anterior. Caches incluem a versão na chave ou são invalidados de forma segura.

### Evento duplicado ou fora de ordem

Contagens estatísticas toleram alguma imprecisão. Use IDs, janelas e deduplicação limitada para impedir retries sistemáticos de inflar tendências.

### Região isolada

Sirva a última versão local. A consistência eventual é preferível a depender de uma região central em cada tecla.

## 16. Desempenho

Orçamento pedagógico de backend:

```text
edge/routing             10–20 ms
fila no worker            0–10 ms
lookup cache/trie          1–15 ms
decode + filtros           1–10 ms
serialização e retorno     2–10 ms
folga de cauda            20–40 ms
```

O trabalho de otimização deve mirar p99, não só média:

- evitar alocação por nó;
- usar arrays e offsets contíguos;
- limitar prefixo e `limit`;
- cancelar requisições obsoletas;
- pré-decodificar respostas muito quentes;
- fazer warmup antes de receber tráfego;
- coalescer misses idênticos;
- separar pools de prefixos caros;
- aplicar timeout menor que o orçamento da interface.

WebSocket é uma opção, não requisito. HTTP moderno com conexão reutilizada pode ser suficiente.

## 17. Consistência e frescor

O índice é um snapshot. Durante rollout:

- dois usuários podem receber versões diferentes;
- o mesmo usuário pode mudar de versão entre teclas;
- a ordem pode mudar levemente;
- uma tendência recente pode demorar até o próximo ciclo.

Isso é aceitável se cada resposta individual for internamente consistente. Para reduzir “pisca-pisca”, o cliente pode manter estabilidade de ranking durante uma sessão curta, e o roteamento pode favorecer a mesma versão por conexão.

Tendências urgentes podem usar uma camada delta:

```text
score final = score do snapshot + delta intradiário limitado
```

Mas esse complemento aumenta risco de abuso, invalidação e inconsistência. Comece com rebuild diário e só adicione delta se o requisito de frescor exigir.

## 18. Segurança, privacidade e abuso

Autocomplete pode amplificar conteúdo perigoso e expor consultas privadas.

- Limitar tamanho, caracteres e taxa por cliente/IP.
- Não registrar cada prefixo como intenção do usuário; registrar preferencialmente a busca final.
- Redigir PII, segredos e identificadores antes da retenção analítica.
- Criptografar tráfego e dados armazenados.
- Separar acesso operacional de acesso a consultas brutas.
- Definir retenção e deleção.
- Filtrar conteúdo ilegal, assédio e termos proibidos antes da publicação.
- Detectar *trend poisoning*: bots podem repetir termos para subir no ranking.
- Aplicar pesos por origem, limites por entidade e detecção de anomalias.
- Não retornar scores brutos nem detalhes que facilitem engenharia reversa.
- Proteger endpoints contra enumeração maciça e scraping.

O filtro deve existir no pipeline e, para emergências, também no serving. O filtro online é uma barreira de contenção; o índice limpo continua sendo a defesa principal.

## 19. Observabilidade e operação

### Read path

- QPS e taxa de erro por região, locale e range;
- p50/p95/p99 end-to-end e por componente;
- hit ratio de cliente, CDN, worker e hot trie;
- prefixos sem resultado;
- respostas vazias após filtro;
- tamanho de payload;
- saturação de CPU, memória, page faults e fila;
- versão do índice por resposta;
- cancelamentos por debounce e requisições obsoletas.

### Pipeline

- lag da fila;
- eventos aceitos, rejeitados, duplicados e atrasados;
- duração de cada estágio;
- número de termos e nós por versão;
- distribuição de score e top-k;
- checksum e taxa de falha da validação;
- idade do índice ativo;
- progresso do rollout e rollback.

### Qualidade e negócio

- taxa de seleção de sugestões;
- posição selecionada;
- abandono após mostrar sugestão;
- cobertura por locale;
- estabilidade de ranking;
- detecção de conteúdo impróprio;
- discrepância entre versão canário e ativa.

Evite labels com o prefixo completo em métricas: cardinalidade e privacidade explodiriam. Use buckets, amostragem e IDs controlados.

## 20. Manutenção e evolução

- Versionar esquema do índice e manter leitor compatível durante rollout.
- Automatizar rebuild reproduzível a partir de dados particionados.
- Ter *golden queries* para regressão de qualidade.
- Fazer capacity planning por range, não apenas global.
- Recompactar dicionário e remover termos abaixo do limiar.
- Testar restore e rollback periodicamente.
- Documentar política de normalização e conteúdo.
- Separar configuração de ranking do binário de serving.
- Usar feature flags para delta intradiário ou novos scores.
- Planejar migração de ranges sem dupla contagem nem buraco de roteamento.

## 21. Alternativas e trade-offs

| Decisão | Ganho | Custo | Escolha inicial |
|---|---|---|---|
| Lista ordenada | Simplicidade e baixo overhead | Varredura do intervalo | Apenas corpus pequeno |
| Mapa de prefixos | Lookup direto | Duplicação de chaves e listas | Dicionário limitado |
| Trie top-k | Lookup `O(p)` e prefixos compartilhados | Complexidade e memória por nó | Serving global |
| HTTP | Stateless, cacheável, simples | Headers e requisições repetidas | Sim |
| WebSocket | Estado incremental, menos overhead | Conexões stateful e operação | Só com evidência |
| Rebuild diário | Isola writes, previsível | Frescor limitado | Sim |
| Atualização online | Frescor alto | Concorrência, invalidação, abuso | Não inicialmente |
| Hash sharding | Distribuição simples | Perde localidade do prefixo | Não para nós |
| Range lexical | Localidade | Skew e rebalanceamento | Sim |
| Strings no top-k | Decodificação simples | Duplicação extrema | Não |
| IDs no top-k | Compactação | Lookup de dicionário | Sim |

## 22. Gargalos, falhas e armadilhas comuns

- Começar pelo diagrama e esquecer requisitos.
- Confundir consultas submetidas com requisições por tecla.
- Dizer que trie resolve memória sem discutir overhead.
- Atualizar a trie global sincronicamente a cada busca.
- Usar hash por prefixo e criar múltiplos saltos por palavra.
- Particionar `A–F`, `G–L` etc. e ignorar skew.
- Publicar sobrescrevendo a versão ativa.
- Invalidar todos os caches ao mesmo tempo.
- Expor frequência como score público.
- Ignorar consultas privadas e manipulação de tendências.
- Colocar CDN sem explicar chave, TTL e locale.
- Escolher WebSocket por moda, sem medir.
- Fazer top-k no request em vez de pré-computá-lo.
- Não definir fallback quando a sugestão falha.
- Prometer consistência forte onde stale é aceitável.

## 23. Roteiro de entrevista de 45 minutos

### 0–5 min — Escopo

Defina consultas globais, top 10, locale, ranking global, atualização diária, sem personalização. Confirme latência e disponibilidade.

### 5–10 min — Requisitos e estimativas

Liste leitura, logging e rebuild. Calcule amplificação por tecla e explique por que debounce, cache e pré-cálculo importam.

### 10–15 min — API e dados

Desenhe `GET /suggestions`, evento de busca e entidades. Explique normalização e snapshot versionado.

### 15–25 min — Arquitetura mínima

Cliente → serviço stateless → trie; logging → fila → agregação → rebuild. Valide requisitos funcionais.

### 25–35 min — Escala

Adicione CDN, caches, shards lexicais, réplicas e pipeline distribuído. Explique lista → mapa → trie e top-k.

### 35–41 min — Deep dive

Escolha um: compressão, hotspots/rebalanceamento ou publicação atômica. Vá até falhas, métricas e recuperação.

### 41–45 min — Fechamento

Revise SLOs, consistência eventual, segurança, rollback, gargalos e extensões. Convide o entrevistador a escolher o próximo aprofundamento.

## 24. Perguntas do entrevistador

### “Por que não consultar um banco ordenado por frequência?”

Porque o filtro por prefixo mais ordenação de grande cardinalidade em cada tecla cria trabalho repetido e cauda de latência. O trie pré-computa top-k por prefixo.

### “Como você calcula top-k sem guardar tudo?”

Agregadores mantêm heaps limitados por prefixo; no builder, candidatos dos filhos são mesclados e apenas `k + margem` sobrevivem.

### “E se uma letra concentrar metade do tráfego?”

CDN, réplicas adicionais e split do range por prefixos mais longos. O mapa de ranges é versionado e distribuído aos roteadores.

### “Como publica sem downtime?”

Artefato imutável, validação, canário e troca atômica de um manifesto. A versão anterior permanece disponível para rollback.

### “Por que eventual consistency?”

Uma sugestão um pouco antiga não impede a busca; indisponibilidade e latência prejudicam mais. Cada resposta ainda precisa ser coerente com uma versão.

### “Como suportaria tendências em minutos?”

Adicionar delta intradiário limitado sobre o snapshot, com antiabuso e expiração. Só faria isso após confirmar requisito e custo.

### “CDN funciona se o prefixo muda a cada tecla?”

Prefixos curtos têm altíssima reutilização global. A chave inclui locale e parâmetros; prefixos longos tendem a cair para caches internos.

### “WebSocket é melhor?”

Pode reduzir overhead e manter cursor, mas adiciona estado e dificulta CDN. HTTP moderno é a opção inicial; métricas decidem a troca.

### “Como evita sugestões ofensivas?”

Políticas e classificadores no pipeline antes da publicação, lista de bloqueio emergencial no serving, auditoria e observabilidade.

### “O que acontece se o rebuild atrasar?”

Servimos a versão anterior, alertamos pela idade do índice e reprocessamos a partir de dados duráveis.

## 25. Checklist de encerramento

- [ ] Escopo global versus local foi explicitado?
- [ ] Personalização ficou dentro ou fora de forma deliberada?
- [ ] Requisitos funcionais e não funcionais foram priorizados?
- [ ] A amplificação por tecla apareceu nas estimativas?
- [ ] API, limite, locale e versão foram definidos?
- [ ] Lista, mapa e trie foram comparados?
- [ ] Top-k é pré-computado?
- [ ] O read path cabe no orçamento de latência?
- [ ] O write path é assíncrono e reconstruível?
- [ ] Cache e CDN têm chave e fallback?
- [ ] Particionamento lexical considera skew e hotspots?
- [ ] Há réplica, degradação e recuperação?
- [ ] A publicação é atômica e reversível?
- [ ] Consistência eventual e frescor foram justificados?
- [ ] Segurança, privacidade e trend poisoning foram discutidos?
- [ ] Métricas cobrem serving, pipeline e qualidade?
- [ ] Pelo menos um deep dive chegou a trade-offs e falhas?
- [ ] A arquitetura foi revalidada contra os requisitos?

## 26. Relação com a aula-fonte

### Fundamentado no material local

- distinção entre dicionário de palavras e busca global;
- ordem de grandeza de 200 mil palavras e um bilhão de queries únicas/dia;
- top 3/top 10, multi-word, frequência global e atualização diária;
- exclusão de personalização;
- prioridade de leitura rápida, disponibilidade e consistência eventual;
- API GET, locale opcional, debounce de 150–200 ms e CDN;
- evolução lista ordenada + min-heap → mapa de prefixos → trie;
- top-k armazenado nos nós;
- logger, Kafka, Flink ou equivalente, HDFS, Spark e rebuild diário;
- Redis/hot trie, armazenamento persistente e swap;
- compressão por IDs inteiros;
- WebSocket como alternativa;
- range partitioning, skew, hotspot e rebalanceamento.

### Complementos deste guia

- SLOs explícitos e orçamento de latência;
- contrato de evento e idempotência;
- formato de manifesto e versionamento;
- publicação atômica, canário e rollback;
- estratégia detalhada de falhas e degradação;
- camada delta opcional para tendências intradiárias;
- privacidade, segurança, abuso e moderação;
- métricas de operação e qualidade;
- práticas de manutenção e migração de ranges.

### Hipóteses pedagógicas

Os números de 500 milhões de buscas/dia, 8 teclas, debounce de 50%, pico 5×, tamanhos de payload e SLOs são exemplos para conectar cálculos a decisões. Não são apresentados como dados reais da Uber, Ada, Kinescope ou de qualquer buscador.
