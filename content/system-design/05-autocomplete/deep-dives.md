# Autocomplete — deep dives de estruturas, rebuild e serving

Este documento não repete a arquitetura inteira do [guia principal](README.md). Ele investiga as decisões que costumam separar uma resposta superficial de uma resposta sênior: por que a estrutura de dados muda com a escala, como top-k é construído, onde a memória realmente vai, como publicar uma versão sem corromper reads e como controlar hotspots e frescor.

Rastreabilidade:

- **Aula local:** decisão explicitamente apresentada na aula.
- **Complemento:** detalhamento operacional ou algorítmico adicional.
- **Hipótese:** exemplo numérico para raciocínio, não dado real.

## 1. Lista ordenada versus mapa de prefixos versus trie

### 1.1 O problema escondido em “retorne top-k”

O prefixo reduz o universo de candidatos, mas não informa quais são os mais populares. Há duas operações:

1. localizar o conjunto de strings que começa com `p`;
2. escolher os `k` maiores scores desse conjunto.

Uma estrutura pode ser boa na primeira e ruim na segunda. Esse é o motivo para guardar top-k pré-computado em vez de ordenar no request.

### 1.2 Lista ordenada

**Aula local:** mantenha as palavras em ordem lexicográfica, use busca binária para achar o primeiro candidato e um min-heap de tamanho `k` para reter os melhores durante a varredura.

Para encontrar o intervalo completo, podemos buscar:

```text
lower_bound(prefix)
lower_bound(prefix + maior_sentinela)
```

Depois, para `m` candidatos e `k` pequeno:

```text
busca do intervalo: O(log N)
seleção top-k:      O(m log k)
memória extra:      O(k)
```

Com `k = 10`, `log k` é pequeno, mas `m` pode ser enorme para prefixos como `a`. A lista funciona muito bem quando o corpus cabe localmente e o pior intervalo ainda é aceitável. Ela também é excelente como baseline: simples, compacta, fácil de reconstruir e de validar.

**Falha típica:** alguém diz que busca binária torna toda a consulta `O(log N)`. Ela encontra a borda; não resolve a seleção dos mais frequentes.

### 1.3 Mapa de prefixos

Pré-computar:

```text
"u"    -> [uber, united states, ...]
"ub"   -> [uber, ubuntu, ...]
"ube"  -> [uber, uber eats, ...]
```

torna a leitura quase trivial. A complexidade aparece no espaço. Para uma string de tamanho `L`, materializar as próprias chaves ocupa:

```text
1 + 2 + ... + L = L(L + 1) / 2 caracteres
```

Ainda há `k` referências por prefixo. Compartilhamento interno da implementação do mapa pode ajudar, mas o modelo lógico continua repetitivo. Em um dicionário de 200 mil palavras, essa troca pode ser totalmente razoável. Para consultas multi-word e cauda longa global, deixa de ser.

**Quando usar:** catálogo limitado, build barato, memória previsível e prioridade absoluta para simplicidade do serving.

### 1.4 Trie

Uma trie compartilha o caminho de prefixos:

```text
root
 └─ u
    └─ b
       └─ e
          └─ r*
```

O lookup percorre `p` caracteres. Se cada nó contém top-k, o resultado já está pronto:

```text
tempo de lookup: O(p)
seleção online:  O(k) para ler/decode
```

Mas “trie economiza memória” não é universal. Uma implementação ingênua com um mapa de 26 ponteiros por nó pode gastar mais do que uma lista compacta. O ganho depende da representação:

- filhos esparsos, não array cheio;
- offsets de 32 bits quando o shard permite;
- arrays contíguos;
- path compression para cadeias sem ramificação;
- IDs em vez de strings;
- poda de nós que não terão resposta útil;
- top-k menor ou adaptativo na cauda.

### 1.5 Matriz de decisão

| Estrutura | Read | Build | Memória | Atualização | Melhor contexto |
|---|---:|---:|---:|---:|---|
| Lista + heap | variável com intervalo | simples | baixa | simples | dicionário local |
| Mapa de prefixos | muito rápido | médio | alta por duplicação | rebuild | corpus pequeno |
| Trie + top-k | `O(p + k)` | complexo | controlável com compressão | snapshot | busca global |

**Decisão de entrevista:** comece pela lista para demonstrar o baseline, evolua ao mapa para trocar CPU por memória e finalize na trie porque ela compartilha prefixos e suporta top-k por nó. A explicação da evolução vale mais do que nomear a estrutura final.

## 2. Como construir top-k por prefixo

### 2.1 Inserção direta

Para cada termo com score, percorra seus prefixos e atualize um heap limitado em cada nó:

```text
para termo em termos:
  para nó no caminho(termo):
    heap[nó].offer(termo, score)
    se tamanho > k: remover menor
```

É intuitivo, mas executa trabalho proporcional à soma dos comprimentos. Em build distribuído isso pode gerar grande volume intermediário.

### 2.2 Propagação pós-ordem

Outra abordagem:

1. folhas conhecem o termo terminal e score;
2. cada nó recebe os top-k dos filhos;
3. faz um merge k-way;
4. retém apenas os melhores.

Como cada filho entrega no máximo `k`, o pai não precisa conhecer toda a subárvore. Para alfabetos limitados, o volume por nó é contido.

### 2.3 Top-k distribuído

No pipeline:

1. agregadores calculam score por termo;
2. termos são particionados por range lexical;
3. cada partição constrói uma subtrie e top-k local;
4. prefixos que cruzam limites precisam de uma etapa de merge;
5. o builder valida que cada nó está ordenado e sem IDs inválidos.

Um bom particionamento alinha fronteiras com prefixos suficientemente longos, reduzindo merges globais.

### 2.4 Margem para filtros

Se o serving pode bloquear um candidato, armazenar exatamente 10 itens pode devolver só 7. Um complemento prático é guardar `k + r`, por exemplo 15 candidatos para retornar 10. A margem tem custo multiplicado por todos os nós; deve ser medida.

### 2.5 Empates e estabilidade

Sem desempate estável, duas versões com contagens iguais podem reordenar sugestões arbitrariamente. Use uma chave determinística:

```text
(-score, termId)
```

ou preserve a ordem anterior como sinal secundário. Estabilidade melhora experiência e reduz ruído em testes.

## 3. Compressão: onde estão os bytes

### 3.1 Strings repetidas

**Aula local:** uma sugestão popular aparece no top-k de muitos ancestrais. Guardar a string completa em cada nó multiplica seu tamanho pelo número de prefixos em que ela se mantém relevante. Substituir a string por um ID inteiro e decodificar no fim reduz duplicação; a aula ilustra uma queda da ordem de vários terabytes para centenas de gigabytes.

### 3.2 Dicionário + IDs

```text
termId 42 -> "uber eats perto de mim"
nó "u"    -> [42, 91, 305]
nó "ub"   -> [42, 91, 777]
```

Cuidados:

- IDs de 16 bits só suportam 65.536 valores; a escala global exige 32 ou 64 bits, ou IDs locais por shard.
- ID local por shard reduz bytes, mas complica merge e migração.
- o dicionário deve pertencer à mesma versão do índice;
- listas top-k e dicionário precisam de checksum conjunto.

### 3.3 Representação dos filhos

Alternativas:

- **array fixo:** lookup direto, desperdício em nós esparsos;
- **vetor ordenado de pares:** compacto, busca binária em poucos filhos;
- **bitmap + offsets:** rápido para alfabeto conhecido;
- **double-array trie:** compacta e boa localidade, build mais complexo;
- **radix tree/path compression:** colapsa cadeias de um único filho.

Não há vencedor universal. A pergunta correta é: qual representação minimiza bytes por nó sem estourar o orçamento de CPU do p99?

### 3.4 Scores compactos

Se serving precisa apenas da ordem, talvez não precise armazenar score. Se precisa:

- quantizar para 8 ou 16 bits;
- armazenar delta;
- manter score somente no builder e publicar rank;
- usar score bruto apenas para `k + margem`.

### 3.5 Cauda longa

Termos raros podem não merecer presença em todo prefixo. Políticas:

- frequência mínima;
- limite por locale;
- expiração por ausência;
- profundidade máxima;
- não materializar top-k para nós sem tráfego;
- fallback para busca mais lenta em cauda, se requisito existir.

**Trade-off:** poda reduz memória e melhora cache, mas diminui cobertura. A métrica é taxa de prefixos sem resultado e impacto na seleção.

## 4. Cache, debounce e CDN como um sistema único

### 4.1 Debounce

**Aula local:** esperar 150–200 ms após a última tecla reduz requests. Três detalhes tornam isso correto:

1. cancelar timer anterior;
2. abortar fetch em voo;
3. descartar resposta cujo prefixo não é mais atual.

Sem o terceiro, uma resposta lenta para `ub` pode sobrescrever a resposta rápida de `ube`.

### 4.2 Cache do cliente

Uma sessão costuma navegar por estados relacionados:

```text
u -> ub -> ube -> ub -> uber
```

Backspace pode reutilizar respostas anteriores. O cache deve ter TTL curto e chave por locale/versão lógica. Ele não substitui cancelamento.

### 4.3 CDN

Prefixos curtos têm alto compartilhamento e ótimo hit ratio. Prefixos longos são mais numerosos e privados.

Política possível:

- 0–2 caracteres: TTL maior e forte cache;
- 3–5: TTL moderado;
- acima de 5: cache interno, ou CDN com TTL curto;
- prefixos sensíveis: `Cache-Control: private` ou bypass conforme política.

A chave deve incluir:

```text
prefixo normalizado + locale + limit + política/versão
```

### 4.4 Stampede

Após publicação ou expiração, milhões de requests para `a` podem atravessar simultaneamente.

Mitigações:

- stale-while-revalidate;
- request coalescing;
- jitter de TTL;
- pré-aquecimento;
- promoção gradual;
- limite de concorrência na origem.

### 4.5 Cache negativo

Prefixos sem resultado também podem ser cacheados por pouco tempo. Porém uma versão nova pode passar a conhecê-los; associe o negativo à versão.

## 5. Partição lexical, skew e hotspots

### 5.1 Por que hash não combina com trajetória

**Aula local:** hashear `u`, `ub`, `ube` e `uber` independentemente espalha passos por servidores. Mesmo que a API consulte só o prefixo inteiro, o builder, a localidade de cache e possíveis cursores incrementais ficam piores. Range lexical mantém famílias de prefixos juntas.

### 5.2 Letras fixas não balanceiam

Distribuição de linguagem não é uniforme; distribuição de tráfego é ainda menos. Uma celebridade, evento ou produto pode tornar um prefixo quente em minutos. Dividir `A–F`, `G–L` etc. é apenas um desenho inicial.

### 5.3 Mapa de ranges

```text
RoutingMap version 81
[a, ap)      -> replicas 1,2,3
[ap, b)      -> replicas 4,5,6
[b, search)  -> replicas 7,8,9
[search, t)  -> replicas 10,11,12
[t, z]       -> replicas 13,14,15
```

Workers recebem snapshots. A versão do mapa acompanha métricas e logs.

### 5.4 Split de hotspot

Quando `[s, t)` está quente:

1. observar QPS, CPU, bytes e p99;
2. escolher fronteira com histograma, por exemplo `[s, search)` e `[search, t)`;
3. copiar dados para novas réplicas;
4. validar checksums;
5. publicar mapa com sobreposição controlada;
6. drenar rota antiga;
7. remover cópia obsoleta.

### 5.5 Replicar ou dividir?

- **Replicar:** melhor quando o gargalo é leitura e o shard cabe em memória.
- **Dividir:** melhor quando memória, build ou tráfego superam capacidade de uma unidade.
- **CDN:** melhor para poucos prefixos globais.

Muitas vezes a resposta é combinar as três.

### 5.6 Hotspot de prefixo curto

O prefixo `s` não pode ser dividido lexicamente sem mudar a unidade lógica da resposta, pois seu top-k agrega todo o range. Soluções:

- replicar a resposta pré-computada de `s`;
- servi-la de cache/edge;
- manter nós raiz em uma camada global altamente replicada;
- shardear apenas abaixo de uma profundidade, como dois ou três caracteres.

Essa distinção é importante: particionar subárvores não significa que o topo da trie também precise ser remoto.

## 6. Pipeline offline e rebuild

### 6.1 Contrato dos estágios

**Aula local:** query logger → Kafka → processamento → HDFS → Spark diário → builder → swap.

Uma decomposição operacional:

1. **Coleta:** valida evento e publica rapidamente.
2. **Ingestão:** normaliza schema, deduplica de forma limitada e grava dados brutos.
3. **Agregação:** conta termos por janela e locale.
4. **Scoring:** combina frequência, recência e políticas.
5. **Builder:** cria dicionário, shards e top-k.
6. **Validação:** verifica estrutura e qualidade.
7. **Publicação:** promove versão.

Cada estágio escreve saída imutável e checkpoint. Assim, falha no builder não exige repetir coleta.

### 6.2 Exatamente uma vez?

Para ranking por frequência, “efetivamente uma vez” pode bastar:

- produtor com retry idempotente;
- ID de evento;
- dedupe por janela;
- agregação reprocessável;
- auditoria entre contagem bruta e agregada.

Buscar semântica perfeita de exactly-once pode custar mais do que a imprecisão tolerada. A decisão deve ser explícita.

### 6.3 Dados atrasados

Eventos podem chegar depois do fechamento diário. Estratégias:

- watermark e janela de tolerância;
- recomputar últimos dias;
- carregar atraso no próximo ciclo;
- manter delta corretivo.

O snapshot deve declarar a janela usada, por exemplo `[D-7, D)`.

### 6.4 Falha do rebuild

Nunca afete serving. A versão ativa permanece. Alertas:

- idade da versão;
- etapa parada;
- queda anormal de termos;
- explosão de tamanho;
- checksum inválido;
- mudança excessiva no top-k.

Recuperação recomeça do último artefato válido.

## 7. Publicação atômica e rollback

### 7.1 O perigo da atualização in-place

Se metade dos nós vier da versão N+1 e o dicionário ainda for N, IDs podem decodificar para strings erradas. Se shards trocarem em momentos arbitrários, um prefixo pode alternar entre universos incompatíveis.

### 7.2 Modelo de snapshot

```text
/indexes/2026-06-22T02/
  manifest.json
  pt-BR/range-000.trie
  pt-BR/range-000.dict
  ...

/active/pt-BR -> 2026-06-22T02
```

O ponteiro ativo é pequeno. A promoção troca o ponteiro, não o conteúdo.

### 7.3 Ciclo de promoção

1. upload completo;
2. checksum;
3. parser estrutural;
4. golden queries;
5. verificação de políticas;
6. carga canário;
7. comparação de qualidade e latência;
8. promoção de poucos workers;
9. rollout regional;
10. promoção global;
11. retenção da versão anterior.

### 7.4 Consistência durante rollout

Não é obrigatório que o planeta mude no mesmo milissegundo. É obrigatório que cada worker use um conjunto coerente de shard + dicionário + routing map. Um request carrega implicitamente uma versão; todas as leituras internas permanecem nela.

### 7.5 Rollback

Trocar o ponteiro de volta é rápido, mas caches podem conter N+1. Soluções:

- versão na cache key;
- purge seletivo;
- TTL curto no rollout;
- dupla leitura em canário.

## 8. Frescor, tendências e consistência eventual

### 8.1 Snapshot diário

É a solução inicial recomendada: previsível, auditável, barata no read path e coerente com a **aula local**. O pior atraso aproximado é duração da janela + build + rollout.

### 8.2 Delta intradiário

Para tendências rápidas:

```text
ranking = snapshot estável + delta de curta duração
```

O delta pode ser um mapa top-k por prefixo em memória, atualizado por microbatch. Ele precisa:

- expirar;
- ter limite de impacto;
- ser filtrado contra abuso;
- sobreviver parcialmente a falhas;
- não exigir merge caro por request.

Uma opção é pré-computar respostas combinadas para prefixos quentes a cada poucos minutos.

### 8.3 Eventual consistency visível

Possíveis sintomas:

- usuário A vê ordem diferente de B;
- uma sugestão aparece e some entre teclas;
- CDN serve versão anterior;
- região isolada fica mais stale.

Mitigações:

- versão na resposta;
- afinidade curta de sessão;
- estabilidade como sinal de ranking;
- TTL coordenado;
- rollout gradual;
- monitorar *rank churn*.

### 8.4 Quando exigir consistência mais forte?

Raramente no autocomplete geral. Pode ser necessária para:

- remoção legal urgente;
- bloqueio de termo perigoso;
- campanhas editoriais com horário exato.

Nesses casos, use uma camada de política/denylist de propagação rápida, em vez de transformar toda a trie em banco fortemente consistente.

## 9. Drill de falhas e recuperação

### Cenário A — CDN cai

Origem recebe pico. Rate limit, autoscaling e cache local absorvem parte. Se necessário, aumentar debounce via configuração e servir stale.

### Cenário B — hot trie perde nós

Workers caem para snapshot local. Hit ratio diminui, mas corretude permanece. Circuit breaker evita retry agressivo.

### Cenário C — shard lexical sobrecarrega

Roteador distribui entre réplicas; edge segura prefixos mais quentes; operação divide ou replica o range.

### Cenário D — Kafka acumula 12 horas

Serving não muda. Pipeline mede lag, aumenta consumidores e fecha snapshot com watermark explícita ou atrasa publicação.

### Cenário E — versão nova reduz cobertura em 30%

Validação ou canário barra promoção. Se já promovida, rollback do manifesto. Dados e artefatos permanecem para investigação.

### Cenário F — bots manipulam um termo

Detecção de anomalia reduz peso da origem, pipeline recalcula score e bloqueio emergencial remove o candidato no serving.

## 10. Como conduzir o deep dive na entrevista

Escolha um eixo e vá até o fim:

### Opção 1 — memória

Trie ingênua → IDs → representação compacta → poda → impacto em decode → métricas de bytes/nó e page faults.

### Opção 2 — hotspots

Range lexical → skew → nós raiz globais → réplica versus split → mapa versionado → migração e falha.

### Opção 3 — publicação

Pipeline imutável → validação → canário → swap atômico → cache versionado → rollback.

Uma resposta madura sempre inclui:

- decisão e contexto;
- alternativa rejeitada;
- falha provável;
- recuperação;
- métrica que prova se funcionou.

## 11. Perguntas de aprofundamento

### Como uma trie distribuída responde a prefixo de um caractere?

Nós rasos podem ser replicados globalmente. A partição começa abaixo de uma profundidade escolhida; respostas de prefixos curtos não fazem fan-out a todos os shards.

### Por que não guardar só top-k e descartar a trie?

Um mapa de prefixos com top-k é possível e pode ser melhor em corpus pequeno. A trie economiza chaves compartilhadas e oferece estrutura para compressão e ranges.

### Como validar top-k?

Amostre nós, recompute a partir dos descendentes e compare. Verifique ordenação, unicidade, score monotônico, IDs válidos e políticas.

### O cache deve ser invalidado ou versionado?

Versionamento reduz corrida e permite rollback. Invalidação ainda pode ser usada para economizar memória, mas não como único mecanismo de corretude.

### Quando usar WebSocket?

Quando medições mostrarem overhead relevante, quando houver sessão longa ou cursor incremental valioso e quando o custo de conexões stateful for aceitável. Não é pré-requisito da trie.

## 12. Checklist de decisão

- [ ] O baseline de lista foi explicado corretamente?
- [ ] O custo quadrático das chaves do mapa foi reconhecido?
- [ ] A trie usa representação compacta, não “26 ponteiros sempre”?
- [ ] Top-k é pré-computado e tem desempate estável?
- [ ] Filtros contam com margem de candidatos?
- [ ] IDs e dicionário pertencem à mesma versão?
- [ ] Debounce cancela timer, request e resposta obsoleta?
- [ ] CDN tem chave, TTL, stale e proteção contra stampede?
- [ ] Nós rasos e prefixos curtos têm estratégia especial?
- [ ] Range lexical considera skew, réplica e split?
- [ ] Pipeline é reprocessável por estágio?
- [ ] Dados atrasados têm política?
- [ ] Publicação não atualiza arquivos in-place?
- [ ] Canário e rollback incluem caches?
- [ ] Frescor urgente não força consistência forte em todo o sistema?
- [ ] Cada deep dive contém trade-off, falha, recuperação e métrica?
