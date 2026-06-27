# Encurtador de URL — guia de entrevista de System Design

Este dossiê prepara uma resposta de entrevista, não uma arquitetura interna real de qualquer empresa. O objetivo é mostrar raciocínio: começar pelo contrato do problema, desenhar o mínimo que funciona e só então evoluir o sistema quando escala, latência, disponibilidade ou operação justificarem cada componente.

> **Rastreabilidade**
>
> - **Aula local:** decisões explicitamente apresentadas em `01-use-cases-encurtador-de-url.md`, incluindo escopo e exclusões de autenticação, analytics e bots/fraude/abuso, `302`, Base62, contador, cache-aside, separação e replicação do serviço de redirect, alocação de faixas e limpeza periódica.
> - **Complemento:** aprofundamento que não aparece, ou não é desenvolvido, na aula: idempotência, cache stampede, negative caching, topologias e consistência de replicação, controles detalhados de abuso, enumeração, SLOs e recuperação.
> - **Hipótese pedagógica:** número escolhido apenas para fazer estimativas na entrevista. Deve ser confirmado com o entrevistador e nunca tratado como dado real.

Material complementar: [deep dives](deep-dives.md). Cockpit para praticar: [index.html](index.html).

## 1. Enquadramento do problema

Um encurtador mantém um mapeamento entre um código curto e uma URL de destino:

```text
https://cur.ta/aZ91kQ  →  https://exemplo.com/artigos/system-design?campanha=junho
```

Há dois caminhos com perfis radicalmente diferentes:

1. **Criação:** recebe a URL longa, valida a entrada, escolhe ou gera um código único e persiste o mapeamento.
2. **Redirect:** recebe o código, encontra o destino válido e responde com um redirecionamento HTTP.

O ponto mais importante para abrir a conversa é a assimetria. Criações são escritas relativamente raras e podem tolerar mais trabalho. Redirects são leituras numerosas, sensíveis a latência e diretamente visíveis ao usuário. Essa diferença orienta cache, replicação, SLOs, isolamento de falhas e escala independente.

Uma boa frase de abertura:

> “Vou primeiro fechar criação, redirect, expiração e escala esperada. Depois desenho um serviço único que cumpra a função e evoluo separadamente os caminhos de escrita e leitura.”

## 2. Perguntas de clarificação

Não comece por Redis, Kafka ou sharding. Transforme o enunciado aberto em contrato.

### Produto e semântica

- Qualquer pessoa pode criar links ou apenas usuários autenticados?
- Devemos aceitar aliases customizados?
- Uma mesma URL longa pode gerar vários códigos? A aula local assume que sim.
- Links expiram? Há expiração padrão ou apenas opcional?
- O criador pode editar ou apagar um link depois?
- Precisamos de analytics de cliques, preview ou QR code?
- O redirect deve usar `301`, `302`, `307` ou `308`?
- Links recém-criados precisam funcionar imediatamente em todas as regiões?

### Escala e qualidade

- Quantos links totais e quantas criações por dia?
- Quantos redirects por dia e qual o fator de pico?
- Qual latência desejada, por exemplo p95 ou p99?
- Qual disponibilidade é exigida para criação e para redirect?
- O produto é regional ou global?
- Quanto tempo os dados precisam ser retidos após expiração?

### Segurança e operação

- Devemos bloquear destinos maliciosos?
- Existe limite por usuário, IP ou domínio?
- Códigos podem ser enumeráveis ou precisam ser difíceis de adivinhar?
- Um alias expirado pode ser reutilizado? A resposta mais segura costuma ser “não imediatamente”.

Autenticação, analytics e bots/fraude/abuso são perguntas e decisões de escopo da aula local. Os mecanismos concretos para implementá-los, quando mencionados neste guia, são complementos.

Ao final, recapitule: “Vou incluir criação, alias opcional, expiração e redirect; deixarei analytics e autenticação como sistemas externos, salvo se você quiser aprofundá-los.”

## 3. Requisitos funcionais

### Dentro do escopo principal

1. Criar uma URL curta a partir de uma URL original válida.
2. Gerar um código único quando o cliente não fornecer alias.
3. Aceitar alias customizado, se acordado, e rejeitar conflito.
4. Aceitar data de expiração opcional.
5. Redirecionar um código ativo para a URL original.
6. Retornar uma resposta definida para código inexistente ou expirado.

### Extensões negociáveis

- apagar ou desabilitar links;
- editar destino;
- domínios customizados;
- links privados;
- analytics;
- preview seguro antes do redirect.

Na aula local, autenticação, analytics e bots/fraude/abuso são discutidos e explicitamente retirados do escopo principal para caber em 40–50 minutos. Neste guia, os controles detalhados de segurança e abuso são complemento: mostram onde essas fronteiras entram sem transformar a conversa em outro problema.

## 4. Requisitos não funcionais

- **Unicidade:** nenhum código ativo pode apontar acidentalmente para dois destinos.
- **Baixa latência:** o redirect deve ser rápido; proponha uma meta mensurável, como p99 abaixo de 100 ms dentro da região, e confirme-a.
- **Alta disponibilidade:** falhar o redirect de links populares tem impacto amplo. A criação pode ter SLO inferior e degradação mais conservadora.
- **Durabilidade:** uma criação confirmada não deve desaparecer após reinício.
- **Escalabilidade:** leitura e escrita precisam escalar de forma independente.
- **Consistência:** criação de alias customizado exige decisão atômica; propagação para caches e réplicas pode ser eventual.
- **Manutenibilidade:** geração de ID, redirect e políticas de abuso devem ter fronteiras claras e operação observável.
- **Segurança:** impedir esquemas perigosos, abuso de criação e redirecionamento conhecido para malware ou phishing.

**Proveniência:** a aula local pede considerar autenticação, analytics e bots/fraude/abuso ao fechar o escopo. Metas numéricas de SLO, atomicidade por operação e os mecanismos específicos de segurança abaixo são complementos.

Uma formulação madura evita “escolher AP” de forma genérica. Durante partição, o redirect de dados já conhecidos pode privilegiar disponibilidade; a criação de um alias customizado não pode aceitar duas reservas concorrentes. O trade-off ocorre por operação.

## 5. Estimativas que mudam decisões

### Hipóteses pedagógicas

Use os números da aula como ponto de partida, sinalizando sua origem:

- 1 bilhão de URLs armazenadas;
- 100 milhões de usuários ativos por dia;
- 5 redirects por usuário por dia;
- aproximadamente 700 bytes por registro, estimativa conservadora da aula.

### Tráfego de redirect

```text
100 milhões × 5 = 500 milhões de redirects/dia
500.000.000 ÷ 86.400 ≈ 5.800 redirects/s em média
```

A aula conclui uma ordem de grandeza próxima de 5 mil requests/s. O transcript automático contém um passo intermediário aritmético inconsistente, mas a conclusão aproximada fica correta usando 86.400 segundos por dia. Para dimensionar pico, adote apenas como hipótese:

```text
pico de 10× a média ≈ 58 mil redirects/s
```

**Consequência arquitetural:** um único processo é um risco; o redirect precisa de múltiplas instâncias, balanceamento, cache e proteção contra picos.

### Tráfego de criação

A fonte não fornece taxa de criação. Declare uma hipótese, por exemplo 5 milhões de novos links por dia:

```text
5.000.000 ÷ 86.400 ≈ 58 criações/s em média
pico de 10× ≈ 580 criações/s
```

**Consequência:** a escrita é muito menor que a leitura. Podemos gastar uma transação ou uma restrição de unicidade por criação, mas não por redirect.

### Armazenamento

```text
1 bilhão × 700 bytes ≈ 700 GB de dados lógicos
```

A conclusão da aula é importante: capacidade bruta, sozinha, não obriga sharding. Como complemento, índices, versões, WAL, overhead do banco, réplicas e backups podem multiplicar o espaço físico. Se estimarmos 2–4×, o footprint operacional já chega a terabytes.

**Consequência:** não shardear apenas porque “um bilhão parece grande”. Avalie throughput, tamanho de índices, janela de backup, recuperação e crescimento.

### Espaço de códigos

Base62 usa `0-9`, `a-z` e `A-Z`:

```text
62⁶ ≈ 56,8 bilhões
62⁷ ≈ 3,52 trilhões
```

Sete caracteres acomodam folgadamente um bilhão de códigos, embora geração aleatória exija margem para colisões. Um contador convertido para Base62 não depende da probabilidade de colisão, mas expõe sequência e volume aproximado.

## 6. Entidades

- **ShortLink:** código, URL original, estado, criação e expiração.
- **Owner:** referência opcional ao criador; autenticação pode ficar fora do desenho.
- **Domain:** domínio curto usado, relevante se houver marcas ou clientes diferentes.
- **IdempotencyRecord:** complemento para evitar duplicação em retries de criação.
- **BlockLease:** complemento para registrar uma faixa de IDs alocada a uma instância.
- **AbuseDecision:** complemento para permitir, bloquear, revisar ou desabilitar um destino.

Não crie uma tabela de cliques se analytics está fora do escopo. Isso demonstra disciplina.

## 7. API e contratos

### Criar link

```http
POST /v1/links
Content-Type: application/json
Idempotency-Key: 78b8...

{
  "originalUrl": "https://exemplo.com/artigo",
  "customAlias": "guia-sd",
  "expiresAt": "2026-07-31T23:59:59Z"
}
```

Resposta:

```http
HTTP/1.1 201 Created

{
  "code": "guia-sd",
  "shortUrl": "https://cur.ta/guia-sd",
  "expiresAt": "2026-07-31T23:59:59Z"
}
```

Erros relevantes:

- `400` para URL, alias ou data inválidos;
- `409` para alias já reservado;
- `422` para destino recusado por política;
- `429` para rate limit;
- `503` se não for seguro confirmar uma criação.

`Idempotency-Key` é complemento. Evita que retry após timeout crie dois links diferentes.

### Redirecionar

```http
GET /{code}
```

Resposta principal:

```http
HTTP/1.1 302 Found
Location: https://exemplo.com/artigo
Cache-Control: no-store
```

A aula escolhe `302` em vez de `301` para que todos os acessos voltem ao serviço e a expiração continue controlável. Em uma entrevista, diga que `301/308` reduzem carga por cache no cliente, mas dificultam revogação, alteração, expiração e analytics. `302/307` preservam controle; `307` também mantém o método original, pouco relevante em um `GET`.

Para códigos ausentes use `404`. Para links conhecidos, mas expirados ou desabilitados, `410 Gone` comunica melhor a semântica; se segurança exigir não revelar existência, uniformize em `404`.

## 8. Modelo de dados

Uma representação relacional simples:

```sql
short_links (
  code            varchar(...) primary key,
  original_url    text not null,
  owner_id        bigint null,
  status          varchar(...) not null,
  created_at      timestamp not null,
  expires_at      timestamp null,
  destination_hash binary(...) null,
  version         bigint not null
)
```

Índices:

- chave primária ou índice único em `code`;
- índice em `expires_at` apenas se sustentar limpeza eficiente;
- índice em `owner_id, created_at` somente se listagem por usuário estiver no escopo.

O lookup crítico é por código, então o acesso pode ser modelado como chave–valor mesmo em banco relacional. A escolha SQL versus NoSQL não deve virar torcida: SQL oferece unicidade e transações convenientes; um store distribuído chave–valor oferece particionamento e throughput previsíveis. Escolha a partir dos requisitos.

Regras:

- alias customizado é inserido com restrição única, não com “verifica e depois grava” sem atomicidade;
- `expires_at = null` significa sem expiração, se permitido;
- `status` permite bloqueio ou deleção lógica imediata;
- código expirado não deve ser reciclado cedo, evitando que um link antigo passe a apontar para outro destino.

## 9. Arquitetura mínima

Comece com três caixas:

```text
Cliente ──POST/GET──> Serviço de URL ──read/write──> Banco de links
```

### Criação mínima

1. validar URL, alias e expiração;
2. gerar código ou tentar reservar alias;
3. inserir o registro com unicidade;
4. retornar a URL curta.

### Redirect mínimo

1. extrair e normalizar o código;
2. buscar por chave indexada;
3. retornar `404` se ausente;
4. verificar `status` e `expires_at`;
5. retornar `302` com `Location`.

Essa arquitetura cobre os requisitos funcionais e é deliberadamente insuficiente para o volume. Dizer isso é parte da resposta: primeiro prove correção funcional, depois localize gargalos.

## 10. Evolução para escala e desempenho

```text
                         ┌──> Creation Service ──> ID Allocator
Cliente ─> API Gateway ──┤             │
                         │             └────────> Banco primário
                         │
                         └──> Redirect Service ──> Cache distribuído
                                      │ miss            │
                                      └─────────────────> Réplicas/Banco

Cleanup Worker ──> expiração/arquivamento
Abuse Pipeline ──> status BLOCKED/version ──> invalidação de cache
                                      └─────> denylist no Redirect Service
```

### Separar criação e redirect

A aula local propõe serviços separados porque o volume de leitura domina. Benefícios:

- autoscaling e recursos diferentes;
- deploys independentes;
- isolamento de falha;
- políticas de timeout distintas;
- proteção da leitura quando a escrita está degradada.

O custo é operacional: mais componentes, roteamento, observabilidade e compatibilidade de contratos.

### Cache-aside no redirect

Fluxo:

1. buscar `code` no cache;
2. em hit, validar que o valor ainda está ativo e responder;
3. em miss, consultar o banco;
4. validar estado e expiração;
5. popular cache com TTL limitado;
6. responder.

Use LRU ou política semelhante para favorecer links quentes. O TTL efetivo deve ser:

```text
min(TTL operacional, expires_at - agora)
```

Complementos importantes: jitter no TTL, request coalescing contra stampede e negative caching curto para códigos inexistentes sob ataque.

### Geração de IDs

Aula local:

- prefixo da URL é rejeitado por colisões;
- hash truncado + Base62 funciona com detecção e retries;
- contador + Base62 é preferido por unicidade determinística;
- em múltiplas instâncias, um serviço distribui blocos, por exemplo 1.000 IDs.

O contador central não deve ser chamado por criação. Cada instância reserva `[início, fim]`, consome localmente e pede outro bloco. Blocos parcialmente usados podem gerar buracos; buracos são aceitáveis porque o requisito é unicidade, não continuidade.

Veja a comparação detalhada em [deep-dives.md](deep-dives.md).

### CDN

A aula trata CDN como extensão: reduz latência e tráfego no origin, mas torna invalidação, expiração e futura deleção menos triviais. Só adicione se alcance global e links muito quentes justificarem o custo. Para redirects revogáveis, prefira TTL curto e purge; não prometa invalidação instantânea sem mecanismo explícito.

## 11. Confiabilidade, disponibilidade e recuperação

### Redirect

- múltiplas instâncias em zonas diferentes;
- balanceador com health checks;
- cache distribuído com replicação;
- banco ou réplicas de leitura com failover;
- timeouts curtos, retries limitados e com jitter;
- circuit breaker para evitar cascata;
- capacidade de servir dados quentes durante falha parcial do banco.

Se cache e banco falham, não invente destino nem sirva valor expirado indefinidamente. Uma política opcional de stale cache precisa de limite e não pode ultrapassar expiração ou bloqueio conhecido.

### Criação

- confirmação somente após persistência durável;
- idempotência para retries do cliente;
- reserva atômica de alias;
- allocator de IDs altamente disponível ou blocos locais grandes o bastante para sobreviver a uma indisponibilidade curta;
- fila de reanálise de abuso fora do caminho síncrono, se a política permitir.

### Recuperação

- backups verificados por restauração, não apenas “backup habilitado”;
- réplicas e point-in-time recovery;
- reconstrução de cache a partir do banco;
- persistência do high-water mark do allocator;
- runbook para cache flush, failover, link malicioso viral e corrupção de mapeamento.

RPO e RTO devem ser diferentes por componente. Perder links confirmados é pior que perder cache, que pode ser reconstruído.

## 12. Consistência, particionamento e replicação

**Aula local:** o caminho de redirect deve ser replicado para suportar o volume dominante de leitura. **Complemento:** a estratégia detalhada de réplica de dados, lag, read-after-write, versionamento e topologia regional.

Consistência por operação:

- **reserva de código:** forte/atômica no namespace do código;
- **leitura logo após criação:** pode usar leitura no primário, atualização síncrona de cache ou token de consistência para o criador;
- **redirect comum:** pode usar réplica e cache eventualmente consistentes;
- **bloqueio por abuso:** requer propagação rápida e invalidação;
- **expiração:** deve ser aplicada no request, não depender apenas do job de limpeza.

Particione por hash do código para distribuir carga uniformemente:

```text
shard = hash(code) mod N
```

Rendezvous hashing ou consistent hashing reduzem movimentação em mudanças de topologia. Range lexical é simples, mas pode criar distribuição desigual dependendo da estratégia de ID. Um contador Base62 crescente também pode concentrar inserts se a chave física preservar ordem; hash da chave de partição evita hotspot.

Replicação assíncrona melhora disponibilidade e leitura, mas cria lag. Mitigações:

- write-through ou preenchimento do cache após commit;
- leitura no primário por uma janela após criação;
- versionamento para impedir que atualização antiga sobrescreva nova;
- monitorar replication lag como sinal de produto.

## 13. Segurança e abuso

Um encurtador oculta o destino e é atraente para phishing, malware, spam e rastreamento abusivo.

**Aula local:** autenticação, analytics e bots/fraude/abuso aparecem na discussão de escopo. **Complemento:** as camadas e os mecanismos operacionais detalhados nesta seção.

### Controles no caminho de criação

- aceitar apenas `http` e `https`;
- normalizar e limitar tamanho;
- bloquear credenciais embutidas e esquemas perigosos;
- rate limit por identidade, IP, dispositivo e domínio;
- reputação de destino e listas de bloqueio;
- desafio ou revisão para padrões suspeitos;
- proteção contra SSRF se o sistema buscar preview do destino.

### Controles no redirect

- consulta rápida a estado de bloqueio;
- interstitial de aviso para destinos suspeitos;
- cabeçalhos seguros e página de erro sem refletir entrada;
- não registrar query strings sensíveis sem redaction;
- kill switch e invalidação de cache para links virais maliciosos.

### Enumeração

Contadores em Base62 produzem códigos previsíveis. Isso é ótimo para simplicidade, mas permite varredura do namespace e revela aproximadamente o volume criado. Alternativas:

- permutar ou cifrar reversivelmente o contador;
- adicionar salt/obfuscation;
- usar IDs aleatórios mais longos;
- manter rate limit e resposta uniforme.

Obfuscação não substitui autorização: links realmente privados precisam de token com entropia suficiente e política de acesso.

## 14. Observabilidade e operação

### Sinais do redirect

- throughput, p50/p95/p99;
- taxa de `2xx/3xx`, `404`, `410`, `429` e `5xx`;
- cache hit ratio e latência de hit/miss;
- latência e erro por shard/réplica;
- links quentes e distribuição de chaves;
- replication lag;
- bloqueios de abuso e tempo de propagação.

### Sinais da criação

- taxa de sucesso e conflitos `409`;
- retries e deduplicação por idempotência;
- colisões por estratégia de ID;
- latência do allocator e blocos restantes;
- taxa de rejeição por política;
- commits e erros do banco.

Trace apenas amostras e não exponha URLs completas sem necessidade. Logs devem carregar `request_id`, código truncado ou hash, região, decisão de cache e motivo de erro. Alertas devem refletir SLO: erro de redirect e p99 importam mais que CPU isolada.

Manutenção inclui migração de schema compatível, rotação de chaves de obfuscação, expansão de shards, teste de restauração, atualização de listas de abuso e revisão de TTLs.

## 15. Alternativas e trade-offs

| Decisão | Ganho | Custo | Quando escolher |
|---|---|---|---|
| Contador + Base62 | Unicidade simples, código curto | Previsível; allocator precisa coordenação | Escopo didático e alta taxa de criação controlada |
| ID aleatório | Sem coordenador central; menos enumerável | Colisões, retries, códigos maiores | Criação distribuída e privacidade do namespace |
| Hash da URL | Pode deduplicar destinos | Mesma URL tende ao mesmo código; colisão truncada | Se deduplicação for requisito explícito |
| `302` | Controle de expiração e bloqueio | Todo clique chega ao serviço | Links revogáveis e observáveis |
| `301` | Menos carga e menor latência após cache | Revogação e analytics difíceis | Destinos realmente permanentes |
| SQL | Unicidade e transações fáceis | Escala horizontal pode exigir trabalho | Escala inicial e aliases customizados |
| KV distribuído | Lookup e sharding naturais | Semântica transacional mais limitada | Grande throughput por chave |
| Cache-aside | Simples e resiliente a cache vazio | Miss inicial e risco de stampede | Caminho de leitura dominante |
| CDN | Proximidade global | Invalidação e custo operacional | Tráfego global muito quente |

O entrevistador avalia se você conecta decisão ao requisito, não se escolhe a tecnologia “mais famosa”.

## 16. Gargalos, falhas e armadilhas comuns

### Gargalos prováveis

- banco sob cache miss massivo;
- chave viral concentrando tráfego;
- allocator central sem blocos;
- índice maior que memória;
- réplica atrasada logo após criação;
- cleanup fazendo scan completo;
- serviço de reputação bloqueando criação;
- invalidação lenta de link malicioso.

### Armadilhas de entrevista

- desenhar a arquitetura global antes de fechar o escopo;
- afirmar “Base62 evita colisão”: Base62 só codifica um número; a origem do número define colisão;
- fazer `SELECT` e depois `INSERT` para alias customizado sem unicidade atômica;
- usar cache sem explicar miss, TTL, expiração e invalidação;
- expirar apenas com cron job;
- escolher `301` sem discutir perda de controle;
- shardear porque há “um bilhão de linhas”, ignorando acesso e operação;
- dizer “CAP, então AP” sem analisar a operação;
- esquecer abuso e enumeração;
- tratar média diária como pico;
- adicionar analytics depois de tê-lo removido do escopo.

## 17. Roteiro sugerido para 45 minutos

### 0–5 min — contrato

- identificar criador e visitante;
- confirmar criação, alias, expiração e redirect;
- remover analytics/autenticação se necessário;
- registrar metas de latência, disponibilidade e escala.

### 5–10 min — estimativas

- calcular redirects médios e pico;
- estimar armazenamento;
- dimensionar espaço Base62;
- declarar quais números são hipóteses.

### 10–15 min — API e dados

- `POST /v1/links`;
- `GET /{code}`;
- `201`, `302`, `404/410`, `409`, `429`;
- registro `code → original_url`, estado e expiração.

### 15–22 min — arquitetura mínima

- cliente, serviço, banco;
- narrar criação;
- narrar redirect;
- provar cobertura dos requisitos funcionais.

### 22–35 min — escala

- separar Creation e Redirect Services;
- introduzir gateway/load balancer;
- índice e cache-aside;
- comparar ID aleatório, hash e contador;
- alocação de blocos;
- replicação e particionamento.

### 35–41 min — falhas e segurança

- cache/banco/allocator indisponíveis;
- lag e read-after-write;
- TTL, limpeza e invalidação;
- abuso, links maliciosos e enumeração.

### 41–45 min — fechamento

- revisar cada requisito;
- declarar trade-offs e gargalo residual;
- citar métricas e recuperação;
- convidar o entrevistador a escolher um deep dive.

## 18. Perguntas do entrevistador — respostas prováveis

**Como garante unicidade?**  
Restrição única no código. Com contador, IDs são disjuntos por blocos; com aleatório ou hash truncado, a inserção atômica detecta colisão e o serviço tenta novamente com limite.

**Por que Base62?**  
É uma representação compacta e URL-safe usando letras e dígitos. Não garante unicidade sozinha.

**O contador é single point of failure?**  
Pode ser se chamado por request. Aloco blocos duráveis para cada instância, replico o allocator e permito que criadores continuem enquanto houver IDs locais.

**O que ocorre logo após a criação?**  
Após commit, posso preencher cache e, para o criador, ler do primário por uma janela. Outras regiões podem convergir eventualmente se isso foi acordado.

**Como evita redirect de link expirado em cache?**  
TTL nunca ultrapassa `expires_at`, e o valor contém expiração para verificação defensiva no serviço.

**Por que não colocar tudo em CDN?**  
CDN reduz latência, mas purge, bloqueio, atualização e expiração ficam mais difíceis. Uso quando alcance global justifica essa complexidade.

**Como apagaria um link malicioso viral?**  
Atualizo estado durável, publico invalidação, removo cache/CDN e mantenho denylist rápida no redirect. Monitoro tempo até bloqueio global.

**Como shardearia?**  
Hash do código como chave de partição; replicação por shard; roteamento consistente e plano de rebalanceamento.

**O que faz se o banco cair?**  
Links quentes podem continuar pelo cache dentro do TTL e da validade. Para misses, falho de forma explícita; não sirvo destino desconhecido. Criação pode pausar para não confirmar dados não duráveis.

## 19. Checklist de encerramento

- [ ] Separei claramente criação e redirect?
- [ ] Confirmei alias, expiração, deleção e analytics?
- [ ] Dei meta mensurável de latência e disponibilidade?
- [ ] Marquei estimativas como hipóteses?
- [ ] Calculei média e pico?
- [ ] Expliquei que Base62 codifica, mas não gera unicidade?
- [ ] Garanti alias customizado com operação atômica?
- [ ] Narrei hit, miss, stampede, TTL e invalidação do cache?
- [ ] Apliquei expiração no request, independentemente do cleanup?
- [ ] Diferenciei consistência de reserva e de propagação?
- [ ] Cobri replicação, particionamento e recuperação?
- [ ] Cobri abuso, malware, rate limit e enumeração?
- [ ] Expliquei `302` versus `301`?
- [ ] Dei métricas por caminho?
- [ ] Apontei pelo menos um gargalo residual?

## 20. Relação com a aula-fonte

### Fundamentado no material local

- entrevista em três movimentos: escopo, high-level design e deep dives;
- dois papéis: criador e visitante;
- criação, alias opcional, expiração e redirect;
- autenticação, analytics e bots fora do escopo principal;
- códigos únicos, baixa latência e alta disponibilidade;
- hipótese de 1 bilhão de URLs e 100 milhões de usuários ativos/dia;
- API de criação e redirect com preferência por `302`;
- serviço único + banco como arquitetura mínima;
- alias, URL original, usuário, criação e expiração como dados;
- Base62, hash com colisão e contador determinístico;
- índice, cache-aside e LRU;
- estimativa de 700 GB lógicos;
- separação entre criação e redirect;
- replicação horizontal do serviço de redirect;
- gateway/load balancer;
- allocator distribuindo blocos de 1.000 IDs;
- TTL limitado pela expiração;
- CDN como extensão com custo de invalidação;
- job periódico de limpeza ou arquivamento.

### Complemento deste guia

- idempotência, SLOs por caminho e fator de pico;
- `404` versus `410`;
- request coalescing, jitter e negative caching;
- topologias e consistência detalhada de replicação de dados, read-after-write e versionamento;
- sharding por hash e hotspots;
- controles detalhados de segurança e abuso: reputação, SSRF, enumeração e kill switch;
- observabilidade, runbooks, RPO/RTO e restauração;
- trade-offs operacionais de SQL, KV e CDN.

### Hipóteses pedagógicas adicionadas

- 5 milhões de criações por dia;
- pico de 10×;
- p99 regional abaixo de 100 ms;
- overhead físico de 2–4× sobre dados lógicos.

Troque essas hipóteses pelos números dados pelo entrevistador. O sinal de senioridade é ajustar o desenho quando a premissa muda, não defender o primeiro diagrama.
