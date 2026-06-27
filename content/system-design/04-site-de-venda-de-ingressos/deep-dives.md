# Deep dives — inventário, reservas e picos em venda de ingressos

Este documento não repete o roteiro geral do [guia principal](./README.md). Ele entra nos mecanismos que costumam decidir a entrevista: invariantes, concorrência, relógios, idempotência, falhas parciais, hotspots e justiça.

> **Rastreabilidade:** trechos marcados como **Aula local** vêm da aula-fonte; **Complemento** é aprofundamento adicional; **Hipótese pedagógica** é uma premissa de exercício.

## 1. Inventário: a invariável antes da tecnologia

Antes de dizer “Redis”, “lock” ou “Kafka”, escreva a propriedade que não pode ser violada:

> Para cada unidade vendável, a quantidade de claims ativos mais vendas confirmadas nunca excede a capacidade.

Para assento numerado, capacidade = 1. Para um setor geral, capacidade = N. Essa formulação permite trocar a implementação sem perder o objetivo.

### Assento individual

Uma unidade passa por:

```text
AVAILABLE --claim atômico--> HELD --confirmação--> SOLD
     ^                          |
     |-------- expiração -------|
```

O erro clássico é:

```text
SELECT state;        -- retorna AVAILABLE para A e B
if available:
  UPDATE state;      -- A e B acreditam que venceram
```

O check e a mutação precisam formar uma operação indivisível. Três alternativas:

1. `SELECT ... FOR UPDATE`: serializa candidatos na linha.
2. `UPDATE ... WHERE state = 'AVAILABLE'`: vitória definida pelo número de linhas alteradas.
3. Restrição de unicidade para claim ativo: duas inserções concorrentes, uma falha.

O update condicional costuma ser uma boa explicação em entrevista porque deixa a condição de vitória visível. Lock pessimista é intuitivo, mas sob contenção cria filas dentro do banco, aumenta timeout e pode gerar deadlock quando reservas pedem assentos em ordens diferentes.

### Múltiplos assentos

Se uma compra pede A10, A11 e A12, o produto normalmente espera tudo ou nada. Ordene IDs para reduzir deadlock, execute a aquisição em uma transação e confira a cardinalidade:

```text
BEGIN
  claim(A10, A11, A12)
  if affected_rows != 3: ROLLBACK
  create reservation + items + outbox
COMMIT
```

Não mantenha a transação aberta durante o pagamento. A reserva transforma uma espera externa de minutos em um estado durável, liberando locks do banco em milissegundos.

### Setor de capacidade

Para pista sem assento:

```sql
UPDATE inventory_pool
SET available = available - :qty,
    version = version + 1
WHERE event_id = :event_id
  AND section_id = :section_id
  AND available >= :qty;
```

Se nenhuma linha mudar, não há capacidade suficiente. O trade-off é que uma única linha vira hotspot. É possível repartir capacidade em buckets, mas isso complica a escolha de bucket, devolução e leitura do total. Só introduza buckets quando a contenção medida justificar.

### Redis versus banco

**Aula local:** propõe uma chave por ticket em Redis, criação condicional, TTL e nova checagem do estado comprado no banco.

**Complemento:** trate Redis como *guard rail*, não como constituição. Ele reduz tráfego perdedor e fornece expiração operacional. A invariável final continua no armazenamento durável porque:

- um lock pode expirar enquanto o dono ainda executa;
- failover pode perder escrita não replicada;
- partição pode criar visões divergentes;
- uma pausa longa do processo pode retomar código obsoleto;
- excluir a chave cedo demais reabre a disputa.

Versionamento/fencing reduz o risco: cada claim recebe um token monotônico, e escritas posteriores só são aceitas se apresentarem a versão corrente. Em muitos desenhos de entrevista, um compare-and-set no banco já cumpre esse papel com menos peças.

### Como explicar a decisão

“Uso Redis para rejeitar cedo e administrar TTL, mas a reserva só existe quando a transação no banco altera exatamente as unidades pedidas. Se Redis estiver errado, perco performance; se o banco estiver errado, perco inventário.”

## 2. Reserva temporária: TTL é política, não só expiração

TTL parece simples até envolver relógios, pagamento e usuário.

### Três tempos diferentes

1. **Prazo comercial:** até quando o usuário tem direito ao inventário.
2. **TTL do cache:** quando a chave operacional desaparece.
3. **Momento de limpeza:** quando o registro durável é normalizado.

Eles não precisam coincidir exatamente. O prazo comercial deve estar persistido como `expires_at` e ser avaliado no servidor. O TTL de Redis pode conter margem. O sweeper pode rodar mais tarde porque sua função é higiene e emissão de eventos, não a única forma de determinar disponibilidade.

**Aula local:** mostra o problema do cron como mecanismo crítico: se atrasar, ingressos ficam presos. Com Redis/TTL, o job pode rodar mais devagar e limpar estados antigos.

### Relógio

Use relógio do servidor/banco para decisões. O countdown do browser é informativo. Se o cliente diz “faltam 12 segundos”, isso não concede direito além de `expires_at`.

Evite depender de sincronização perfeita entre muitos serviços. Uma forma é fazer o banco calcular `expires_at = CURRENT_TIMESTAMP + interval`. Outra é aceitar pequena tolerância, mas aplicar a decisão em um único componente autoritativo.

### Expiração preguiçosa e ativa

- **Preguiçosa:** ao tentar reservar, um hold com `expires_at < now()` pode ser reclamado atomicamente.
- **Ativa:** sweeper encontra expirados, muda estado, publica evento e atualiza projeções.

Usar ambas evita depender da pontualidade do job sem abandonar limpeza/auditoria.

### Extensão de reserva

Renovar TTL a cada atividade parece amigável, mas permite sequestrar inventário indefinidamente. Se produto exigir extensão:

- limite número e duração total;
- não estenda apenas por heartbeat;
- exija avanço real no fluxo;
- registre motivo;
- aplique política diferente quando o provedor está processando.

### Corrida expirar versus confirmar

Considere dois workers:

- E tenta `HELD -> EXPIRED`;
- P tenta `HELD -> CONFIRMED`.

Ambos usam transição condicional por status e versão. Apenas um vence. O perdedor lê o estado final e executa compensação apropriada. Não basta “checar antes”, pois a condição pode mudar entre leitura e escrita.

Decisões possíveis:

| Política | Vantagem | Risco |
|---|---|---|
| Deadline estrito | Inventário previsível | Cobrança tardia exige refund |
| Grace period curta | Absorve atraso do provedor | Hold efetivo fica maior |
| Autorizar antes, capturar ao confirmar | Compensação mais barata | Nem todo método suporta |

Não há resposta universal; há uma decisão de produto e pagamento que deve ser explicitada.

## 3. Fila virtual e admission control

A fila não aumenta capacidade. Ela transforma um burst incontrolável em uma taxa de chegada que o caminho crítico consegue sustentar.

### Onde colocá-la

```text
Edge -> Waiting Room -> Admission Service -> Booking/Reservation -> Inventory DB
```

Colocar a fila somente dentro do Booking Service é tarde: conexões, threads, pools e banco já estão sob ataque. A borda deve recusar chamadas diretas sem token válido.

**Aula local:** posiciona a fila antes do Booking Service para eventos populares, sugere Redis e atualizações por WebSocket ou SSE.

### Token de admissão

O usuário admitido recebe token assinado com:

- `event_id`;
- identidade/sessão;
- `issued_at` e `expires_at`;
- nonce;
- escopo, por exemplo “até 8 unidades”;
- política/coorte;
- versão da regra.

Booking valida assinatura, evento, prazo e reutilização. Token não deve ser transferível por simples cópia. Vincular ao dispositivo é útil, mas precisa permitir recuperação razoável de sessão para não punir falhas de rede.

### Taxa de admissão adaptativa

Uma taxa fixa funciona apenas enquanto capacidade é estável. Um controlador simples observa:

- p95/p99 de reserva;
- utilização e lock wait do banco;
- taxa de conflito;
- saturação de pool;
- erro do provedor;
- profundidade de filas internas.

Se latência/erro sobem, reduz admissões. Se há folga, aumenta gradualmente. É melhor admitir 2 mil usuários/s com estabilidade do que 10 mil/s e entrar em colapso com retries.

### Posição da fila

Posição exata é cara e enganosamente precisa. É aceitável enviar faixa/estimativa:

- “aproximadamente 8 minutos”;
- “12 mil pessoas à frente”;
- “você está no próximo lote”.

SSE atende bem atualizações unidirecionais e reconecta nativamente. WebSocket faz sentido se o cliente também envia eventos frequentes. Long polling é fallback simples. A escolha de transporte não muda a autoridade do token.

### Justiça na abertura

FIFO de timestamps de chegada favorece baixa latência, automação e proximidade geográfica. Alternativas:

- usuários presentes antes de T0 entram em um lote randomizado;
- depois de T0, FIFO;
- cotas separadas para pré-venda, acessibilidade ou patrocinadores;
- limite de uma posição por conta/dispositivo;
- janela de reconexão.

“Justo” é uma política verificável, não uma propriedade emergente da fila.

### Falha da fila

Preserve no mínimo:

- identidade da entrada;
- coorte/ordem lógica;
- tokens já emitidos;
- contadores de admissão.

Em falha, o edge deve fechar novas admissões; não liberar todo o tráfego. Tokens emitidos podem continuar por uma janela curta se Booking ainda estiver saudável. Recuperação deve evitar duplicar tokens ou mover usuários silenciosamente para trás.

## 4. Idempotência de ponta a ponta

Retries são inevitáveis. Sem idempotência, confiabilidade de transporte vira duplicação de negócio.

### Intenção versus requisição

O cliente gera uma chave para “reservar A10 e A11 neste evento”. Se recebe timeout, repete a mesma chave. O servidor persiste:

```text
(actor, operation, idempotency_key)
payload_hash
status: IN_PROGRESS | COMPLETED | FAILED_FINAL
resource_id
response_snapshot
expires_at
```

Regras:

- mesma chave + mesmo payload: retorna o resultado original;
- mesma chave + payload diferente: `409 Conflict`;
- chave em andamento: aguarda, retorna `202`, ou orienta polling;
- erro transitório não cria nova intenção;
- retenção da chave cobre o maior período de retry plausível.

### Reserva

A criação do registro idempotente e da reserva deve estar na mesma transação. Caso contrário, o processo pode criar a reserva e cair antes de registrar a chave.

### Pagamento

Use uma chave estável ao chamar o provedor, derivada de `payment_attempt_id`, não gere uma nova em cada retry. Guarde `provider_reference` com unicidade.

### Webhook

Deduplicar pelo identificador do evento do provedor é útil, mas insuficiente se o provedor reenviar o mesmo fato com IDs diferentes. O handler também precisa de uma máquina monotônica:

```text
INITIATED < AUTHORIZED < CAPTURED
INITIATED < FAILED
CAPTURED -> REFUNDED
```

Eventos antigos não revertem estados mais fortes. “FAILED depois de CAPTURED” pode significar falha de outra tentativa, chargeback ou semântica específica; mapeie por tentativa e tipo.

### Resposta perdida

Se o banco confirma e o processo cai antes da resposta, o retry encontra a mesma chave e devolve o `reservation_id`/estado. Esse caso demonstra por que idempotência é parte da API, não apenas proteção do pagamento.

## 5. Saga, compensação e reconciliação

Inventário e pagamento não compartilham commit. A saga descreve passos locais e ações compensatórias.

### Estados úteis

```text
Reservation: HELD -> PAYMENT_PENDING -> CONFIRMED
                           |              |
                           v              v
                       CANCELED        REFUND_PENDING*

Payment: INITIATED -> AUTHORIZED -> CAPTURED
              |            |          |
              v            v          v
            FAILED       VOIDED     REFUNDED
```

### Estratégia autorizar/capturar

Quando o provedor suporta:

1. segurar inventário;
2. autorizar valor;
3. confirmar inventário;
4. capturar;
5. se confirmação falhar, cancelar autorização.

Isso reduz refunds, mas aumenta etapas e depende do método. Para métodos instantâneos ou assíncronos, a sequência muda.

### Estado desconhecido

Timeout não significa falha. Marque `UNKNOWN` e:

1. consulte por idempotency key/reference;
2. espere webhook por janela limitada;
3. reconcilie por relatório;
4. decida void/refund se inventário não puder ser confirmado.

Retry cego de `charge()` com chave nova é a pior resposta.

### Transactional outbox

Ao confirmar:

```text
BEGIN
  reservation = CONFIRMED
  inventory = SOLD
  payment_attempt = CAPTURED
  INSERT outbox("OrderConfirmed")
COMMIT
```

Um relay publica a outbox. Se cair após publicar e antes de marcar `published_at`, pode publicar novamente; consumidores precisam ser idempotentes. O ganho é não perder o evento entre commit e broker.

### Compensações

- pagamento autorizado, inventário perdido: void;
- pagamento capturado, inventário perdido: refund + comunicação;
- inventário segurado, pagamento falhou: expirar/liberar;
- confirmação local, emissão falhou: retry de emissão; não desfazer venda automaticamente;
- preço divergente: preservar snapshot e abrir exceção, não recalcular silenciosamente.

Compensação não “apaga” o fato. Ela cria novos fatos auditáveis.

### Reconciliação

Reconciliação compara:

- reservas confirmadas versus pagamentos capturados;
- pagamentos capturados versus pedidos confirmados;
- total financeiro por período/provedor;
- holds expirados versus unidades ainda `HELD`;
- eventos de outbox versus efeitos derivados.

Resultados devem cair em categorias acionáveis:

- corrigível automaticamente;
- precisa de consulta ao provedor;
- precisa de refund;
- precisa de análise manual.

Métrica crítica: idade do item não reconciliado mais antigo.

## 6. Hotspots: o evento que quebra médias

Um sistema pode operar a 5% de CPU e ainda falhar porque um único evento concentra:

- todas as reservas no mesmo shard;
- uma linha de capacidade;
- mesmas chaves de cache;
- mesma partição de fila;
- atualização do mesmo mapa de assentos;
- invalidações simultâneas.

### Proteções por camada

1. **Edge:** rate limit e fila por evento.
2. **Aplicação:** limite de concorrência por `event_id`.
3. **Cache:** coalescing de leitura para impedir stampede.
4. **Banco:** índices adequados, transações curtas, timeout baixo.
5. **Partição:** isolamento de evento excepcional.
6. **UX:** reduzir refresh agressivo e mostrar disponibilidade aproximada.

### Single-flight

Se 50 mil requisições pedem o mesmo detalhe ausente no cache, uma busca ao banco deve preencher o resultado enquanto as demais aguardam ou recebem stale data. Sem request coalescing, cache miss vira avalanche.

### Mapa de assentos

Não envie uma consulta pesada e resposta completa a cada segundo. Possibilidades:

- snapshot por setor + deltas;
- bitmap comprimido de disponibilidade;
- paginação/tiles do mapa;
- SSE para invalidações, seguido de reconsulta localizada;
- “seleção automática” durante sobrecarga.

### Sharding

Shard por `event_id` preserva localidade, mas não divide o maior evento. Subshard por setor ajuda se carrinhos não cruzarem setores. Subshard por faixa de assentos distribui mais, porém uma compra multi-faixa exige coordenação ou restrição de produto.

Escolha o limite de domínio que mantém a transação mais comum local.

## 7. Justiça, bots, fraude e limites

### Ameaças distintas

- **Bot de fila:** cria milhares de posições.
- **Bot de reserva:** segura inventário e abandona para negar serviço.
- **Scalper:** compra no limite para revender.
- **Fraude de pagamento:** usa instrumentos roubados.
- **Bypass:** chama endpoint de reserva sem passar pela fila.
- **Account farm:** contorna limite por conta.

### Controles

| Ameaça | Controle principal | Custo |
|---|---|---|
| Muitas posições | identidade/dispositivo + rate limit | falsos positivos em redes compartilhadas |
| Hold abuse | limite de holds ativos + reputação | pode afetar famílias/grupos |
| Bypass | token assinado verificado no booking | gestão de chaves e expiração |
| Scalping | limite por identidade/cartão/endereço | privacidade e suporte |
| Automação | desafio adaptativo | fricção e acessibilidade |
| Fraude | scoring + 3DS/provedor | conversão e latência |

Limite importante precisa ser aplicado na mesma fronteira autoritativa da compra. Uma regra só no gateway pode ser contornada por corrida entre instâncias.

### Privacidade e acessibilidade

Antibot não justifica coletar dados ilimitados. Minimize retenção, proteja identificadores e explique finalidade. CAPTCHA pode bloquear tecnologias assistivas; ofereça alternativas. Justiça inclui não excluir usuários com conexão instável ou necessidades de acessibilidade.

### Sinais de abuso operacional

- taxa de criação de conta por dispositivo;
- muitas reservas sem pagamento;
- rotação de IP com fingerprint estável;
- cartões distintos para mesma identidade;
- padrão de assentos sistemático;
- latência impossível entre admissão e reserva;
- reutilização de token;
- concentração de compras em endereços.

Use múltiplos sinais e revisão, pois nenhum é prova isolada.

## 8. Consistência forte no caminho crítico

“Consistência forte” precisa ser localizada. Não torne todo o sistema síncrono.

### Fronteira forte

Dentro da transação de reserva:

- validar capacidade;
- claim de inventário;
- criar reservation/items;
- registrar idempotência;
- gravar outbox.

Dentro da confirmação:

- validar estado e versão;
- aplicar resultado do pagamento;
- mudar unidades para `SOLD`;
- confirmar reserva/order;
- gravar outbox.

### Fronteira eventual

Depois do commit:

- enviar e-mail;
- gerar PDF/QR;
- atualizar analytics;
- atualizar índice;
- invalidar caches;
- notificar websocket/SSE.

Cada consumidor reprocessa com segurança.

### Réplicas

Não leia réplica atrasada para decidir se assento está disponível. Réplicas servem para histórico, detalhes não críticos e analytics. Após criar reserva, leitura do próprio estado deve ir ao primário ou usar mecanismo de read-your-writes.

### Multi-região

Active-active irrestrito para a mesma unidade torna a invariável difícil. Alternativas:

- região líder por evento/shard;
- encaminhar reserva à região dona;
- replicação síncrona dentro da região e assíncrona entre regiões;
- failover com fencing para impedir dois líderes.

Durante incerteza de liderança, falhar fechado é coerente com a prioridade de consistência.

### Disponibilidade não é binária

Mesmo quando booking falha fechado, o produto pode continuar:

- servindo busca;
- mostrando detalhes;
- preservando lugar na fila;
- exibindo estado “compra temporariamente indisponível”;
- retomando a partir da reserva existente.

A arquitetura usa consistência forte apenas no pequeno núcleo que protege inventário e dinheiro.

## 9. Modos de falha em sequência

### Cenário A — processo cai após reservar

1. Transação cria hold e commit.
2. Processo cai antes da resposta.
3. Cliente repete com mesma chave.
4. Idempotency record devolve a reserva.

Sem idempotência, o cliente criaria outro hold.

### Cenário B — Redis diz livre, banco diz vendido

1. Chave evaporou por failover/TTL.
2. Tentativa adquire chave.
3. Update condicional no banco altera zero linhas.
4. Reserva falha e chave é removida.

Perde-se uma tentativa, não a invariável.

### Cenário C — pagamento capturado após expiração

1. Sweeper vence a transição e libera inventário.
2. Webhook de captura chega.
3. Handler não reverte `EXPIRED`.
4. Consulta se inventário ainda está livre e política permite re-hold; caso contrário, cria `REFUND_PENDING`.
5. Reconciliação acompanha até terminal.

### Cenário D — outbox publica duas vezes

1. Relay publica.
2. Cai antes de marcar publicado.
3. Publica novamente.
4. Consumidor deduplica por `outbox_event_id`.

At-least-once exige consumidor idempotente.

### Cenário E — evento quente derruba o índice de busca

Busca pode degradar para páginas pré-computadas/cache/CDN. A fila e booking não devem depender da saúde do índice para quem já tem `event_id`.

## 10. Como conduzir o deep dive na entrevista

Escolha dois eixos, não oito superficialmente.

### Se o entrevistador aponta para consistência

1. Declare a invariável.
2. Mostre transação/update condicional.
3. Resolva múltiplos assentos.
4. Introduza hold e expiração.
5. Discuta Redis como otimização.
6. Resolva TTL versus webhook.

### Se aponta para escala

1. Mostre skew por evento.
2. Coloque fila antes do booking.
3. Defina token de admissão.
4. Controle taxa pela saúde do backend.
5. Discuta shard/hotspot.
6. Mencione cache stampede e mapa de assentos.

### Se aponta para confiabilidade

1. Separe reserva e pagamento.
2. Use idempotency key.
3. Modele `UNKNOWN`.
4. Mostre saga/compensação.
5. Adicione outbox.
6. Feche com reconciliação e alertas.

### Se aponta para abuso

1. Liste ameaça concreta.
2. Aplique controle em camadas.
3. Garanta limite no caminho autoritativo.
4. Discuta justiça, privacidade e falsos positivos.

Uma resposta sênior termina cada mecanismo com falha e trade-off:

> “Essa decisão reduz contenção, mas adiciona estado duplicado; por isso mantenho o banco como autoridade e monitoro divergência.”

## 11. Perguntas de decisão rápida

### “Lock pessimista ou otimista?”

Pessimista simplifica concorrência moderada e espera curta. Otimista evita filas longas e funciona bem quando a maioria das tentativas não colide. Em evento quente, a fila deve reduzir concorrência antes que qualquer estratégia chegue ao banco.

### “TTL no Redis ou banco?”

Nos dois com papéis diferentes: Redis para expiração/rejeição rápida; banco para prazo comercial e auditoria. Sweeper reconcilia.

### “Kafka resolve overselling?”

Não sozinho. Serializar comandos por unidade/evento pode simplificar a ordem, mas ainda é preciso estado durável, idempotência, tratamento de partição e confirmação. A fila pode reduzir concorrência, não substitui a invariável.

### “Exactly once?”

Na prática, combine entrega at-least-once com efeitos idempotentes, chaves únicas e estados monotônicos. “Exactly once” de broker não cobre banco + provedor externo.

### “SSE ou WebSocket?”

SSE para posição/status servidor→cliente; WebSocket se houver bidirecionalidade frequente. Ambos precisam de reconexão, autorização e estado recuperável.

### “Como testar?”

- concorrência com milhares de tentativas para a mesma unidade;
- propriedade: vendas confirmadas nunca excedem capacidade;
- relógio controlado para expiração;
- webhooks duplicados/fora de ordem;
- timeout após commit;
- falha de Redis;
- failover de banco;
- carga concentrada em um evento;
- reconciliação com divergências sintéticas.

## 12. Rastreabilidade com a aula

**Aula local:** inventário pré-gerado, transação de reserva, estados reservado/confirmado/cancelado, cron, Redis lock com TTL, rechecagem durável, fila virtual, WebSocket/SSE, cache, busca e pagamento terceirizado.

**Complementos deste documento:** invariantes formalizadas, updates condicionais, capacity pool, fencing/versionamento, relógios, expiração preguiçosa, admission token, controle adaptativo, idempotency record, estados monotônicos, saga, outbox, compensação, reconciliação, proteção contra hotspots, justiça, bots/fraude, multi-região e testes de propriedade.

**Hipóteses pedagógicas:** qualquer TTL, taxa, limite ou política mencionada deve ser negociada. O valor durável deste deep dive é o método: invariável → mecanismo → falha → recuperação → trade-off.
