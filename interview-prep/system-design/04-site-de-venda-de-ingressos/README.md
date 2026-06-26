# Site de venda de ingressos — guia de entrevista de System Design

Este guia ensina a conduzir, de cima para baixo, uma entrevista de System Design para uma plataforma de busca e compra de ingressos. O desafio não é apenas desenhar uma página de eventos: é separar um caminho de descoberta, dominado por leituras e tolerante a algum atraso, de um caminho de compra no qual uma decisão incorreta vende o mesmo ingresso duas vezes.

> **Legenda de rastreabilidade**
>
> - **Aula local:** decisão ou exemplo explicitamente presente na aula-fonte.
> - **Complemento:** aprofundamento de engenharia acrescentado para tornar o guia abrangente.
> - **Hipótese pedagógica:** número assumido apenas para estimar capacidade; não representa dado real de Uber, Ada, Ticketmaster ou qualquer outra empresa.


## 1. Enquadramento do problema

Uma resposta forte começa identificando que “vender ingressos” reúne dois sistemas com perfis diferentes:

1. **Descoberta:** pesquisar eventos, abrir detalhes, consultar mapa e disponibilidade aproximada. É um caminho intensivo em leitura, sensível a latência e que pode usar cache, CDN e índice de busca.
2. **Transação:** reservar um conjunto específico de ingressos, cobrar o cliente e confirmar a compra. É um caminho de baixa tolerância a inconsistência, no qual concorrência, repetição de requisições e falhas parciais são o centro do problema.

**Aula local:** a aula escolhe três jornadas — buscar eventos, visualizar detalhes e comprar ingressos — e ressalta que busca/detalhes priorizam disponibilidade, enquanto booking prioriza consistência para impedir overbooking. Também caracteriza o produto como muito mais intensivo em leituras do que em escritas.

**Complemento:** a tese arquitetural deste guia é: *dados promocionais podem estar defasados; a autoridade para vender uma unidade de inventário não pode estar*. Busca e cache ajudam o usuário a chegar ao evento, mas somente o serviço de inventário, respaldado por uma transação durável, decide se a reserva foi conquistada.

Uma boa frase de abertura na entrevista:

> “Vou tratar descoberta e compra como caminhos com objetivos de consistência diferentes. Primeiro fecho escopo e números; depois desenho a arquitetura mínima; por fim aprofundo reserva, pagamento e picos de venda.”

## 2. Perguntas de clarificação

Faça perguntas que alterem o desenho, não perguntas cosméticas.

### Produto e inventário

- O ingresso representa **assento numerado**, **setor com capacidade** ou ambos?
- Uma compra pode conter vários ingressos? Ela é atômica: ou reserva todos, ou nenhum?
- O usuário escolhe assentos específicos ou pede “melhores assentos disponíveis”?
- Há janela de reserva antes do pagamento? Qual é o TTL desejado?
- Precisamos suportar cancelamento e reembolso ou apenas compra?
- A confirmação precisa emitir um ingresso digital imediatamente?

### Tráfego e lançamento

- Quantos eventos ativos e ingressos existem?
- O tráfego é contínuo ou há aberturas de venda com horário marcado?
- Qual pico de tentativas por segundo em um evento muito popular?
- A fila deve ser estritamente FIFO ou pode priorizar pré-venda, acessibilidade ou parceiros?
- É aceitável mostrar disponibilidade alguns segundos atrasada na página do evento?

### Pagamento e operação

- O provedor de pagamento confirma de forma síncrona, por webhook ou ambos?
- Pode haver resposta desconhecida: cobrança feita, mas timeout antes da confirmação?
- Há múltiplos provedores, moedas, parcelamento ou métodos assíncronos?
- Qual experiência o produto deseja quando pagamento termina após o TTL?
- Quais exigências de auditoria, fraude e contestação são relevantes?

### Decisão explícita para prosseguir

Se o entrevistador não especificar, declare:

**Hipótese pedagógica:** suportaremos eventos com assentos numerados e setores gerais; uma reserva pode conter até 8 ingressos e é atômica; o hold dura 10 minutos; pagamento é terceirizado e confirmado por webhook; cancelamento pós-compra e mercado secundário ficam fora do escopo.

## 3. Requisitos funcionais

### Dentro do escopo

1. Buscar eventos por texto, cidade, artista e intervalo de data.
2. Abrir os detalhes de um evento.
3. Consultar setores/assentos e sua disponibilidade.
4. Criar uma reserva temporária de um ou mais ingressos.
5. Iniciar pagamento e receber sua confirmação assíncrona.
6. Confirmar a compra sem vender a mesma unidade duas vezes.
7. Expirar reservas abandonadas e devolver inventário.
8. Para eventos quentes, colocar usuários em fila virtual e admitir tráfego de maneira controlada.

**Aula local:** os três primeiros fluxos centrais são busca, detalhes e compra. A reserva, os estados `reserved`, `confirmed` e `canceled`, o pagamento terceirizado, a expiração e a fila virtual aparecem na evolução do desenho.

**Complemento:** fila, idempotência e reconciliação são formuladas aqui como capacidades explícitas porque tornam os casos de falha testáveis. A aula menciona filas, retry e circuit breaker ao falar de indisponibilidade do pagamento, mas não fecha um protocolo completo.

### Fora do escopo inicial

- Cadastro e administração de eventos.
- Cadastro e gestão de usuários.
- Recomendações personalizadas.
- Transferência e revenda de ingressos.
- Cancelamento voluntário após confirmação e política de reembolso.
- Contabilidade completa do organizador.
- Implementação interna do adquirente ou provedor de pagamento.

**Aula local:** gerenciamento de usuário, CRUD de eventos, autenticação detalhada, histórico, cancelamento e reembolso são citados como possíveis, mas deixados fora do exercício.

## 4. Requisitos não funcionais

### Caminho de descoberta

- Alta disponibilidade.
- Baixa latência: objetivo ilustrativo de p95 abaixo de 300 ms para busca e detalhes em condições normais.
- Escala horizontal para grandes volumes de leitura.
- Consistência eventual aceitável para texto, imagem e contagem aproximada.
- Degradação graciosa: se a busca avançada cair, detalhes por ID ainda podem funcionar.

### Caminho de compra

- **Segurança de inventário:** nunca confirmar duas vendas para a mesma unidade.
- Atomicidade para reservas de múltiplos ingressos.
- Idempotência em criação de reserva, início de pagamento e webhook.
- Estado durável e auditável.
- Recuperação de falhas parciais por compensação e reconciliação.
- Disponibilidade deliberadamente menor que a integridade: sob partição, é preferível recusar temporariamente uma compra a vender em duplicidade.

### Operação

- Observabilidade por evento, partição, provedor e etapa do funil.
- Proteção contra bots, fraude, abuso de fila e esgotamento de recursos.
- Rastreabilidade de mudanças de estado e decisões de admissão.
- RTO/RPO definidos para inventário e reservas.

**Aula local:** evitar overbooking, priorizar consistência na compra, baixa latência e disponibilidade na descoberta, serviços replicados e tratamento de falha do pagamento são pontos explícitos.

## 5. Estimativas que alteram decisões

Estimativas servem para revelar assimetrias e hotspots. Não gaste a entrevista calculando precisão fictícia.

### Números de partida

**Aula local:** usa aproximadamente 100 mil eventos e 20 milhões de usuários ativos diários como ordens de grandeza ilustrativas.

**Hipóteses pedagógicas adicionais:**

- 20 milhões de DAU.
- 20 buscas por usuário/dia: 400 milhões de buscas/dia.
- 5 visualizações detalhadas por usuário/dia: 100 milhões/dia.
- 2% dos usuários concluem uma compra/dia: 400 mil compras/dia.
- 2,5 ingressos por compra: 1 milhão de ingressos vendidos/dia.
- Pico comum = 10 vezes a média.
- Abertura de venda quente = até 100 mil tentativas/s para um único evento.
- 100 mil eventos ativos; média de 2 mil unidades por evento: 200 milhões de registros de ingresso ativos.

### Conversão em capacidade

| Fluxo | Média aproximada | Pico comum | Consequência |
|---|---:|---:|---|
| Busca | 4,6 mil req/s | 46 mil req/s | Índice de busca, cache e paginação |
| Detalhes | 1,2 mil req/s | 12 mil req/s | Cache por evento e conteúdo estático separado |
| Compras concluídas | 4,6 req/s | 46 req/s | Média engana; consistência domina o desenho |
| Evento quente | não faz sentido usar média | 100 mil tentativas/s/evento | Fila virtual e admission control por evento |

O principal insight é que a média global de compras é pequena, porém o sistema sofre **skew temporal e por chave**. À meia-noite, milhões podem disputar poucos milhares de assentos do mesmo `event_id`. Escalar Booking Service horizontalmente não resolve sozinho: todas as instâncias convergem para as mesmas linhas, partições e chaves.

### Armazenamento

**Hipótese pedagógica:** se cada registro de ingresso, com índices e overhead, ocupar cerca de 500 bytes, 200 milhões de unidades ativas consomem aproximadamente 100 GB antes de réplicas. Reservas, pagamentos, auditoria e histórico tornam o volume significativamente maior. Isso ainda é compatível com bancos relacionais particionados, mas exige:

- índices pequenos e alinhados aos acessos;
- particionamento por `event_id` ou grupo de eventos;
- arquivamento de eventos encerrados;
- réplicas de leitura apenas para dados não autoritativos;
- evitar consultas que façam varredura de todos os assentos em cada refresh.

## 6. Entidades do domínio

- **Event:** evento, horário, status de venda, regras e referências a local/artistas.
- **Venue:** local, cidade, setores, capacidade e mapa.
- **Performance/Session:** ocorrência específica do evento quando há várias datas.
- **InventoryUnit:** assento ou unidade vendável individual.
- **InventoryPool:** capacidade agregada para setor sem assento marcado.
- **Reservation:** intenção temporária com `expires_at`.
- **ReservationItem:** unidades contidas na reserva.
- **Order:** compromisso comercial confirmado.
- **PaymentAttempt:** tentativa de cobrança e resposta do provedor.
- **AdmissionToken:** autorização temporária para entrar no fluxo de compra.
- **IdempotencyRecord:** resultado associado a uma chave de repetição.
- **OutboxEvent:** evento durável a publicar para processos assíncronos.
- **AuditEntry:** transição de estado, ator, motivo e correlação.

**Aula local:** eventos, locais, artistas, tickets pré-gerados e booking formam o modelo relacional base. O booking liga usuário, ticket, evento, data, preço e status.

**Complemento:** `Reservation`, `Order` e `PaymentAttempt` separados evitam sobrecarregar uma única tabela “booking” com significados temporários e financeiros diferentes. Em uma entrevista curta, é aceitável manter `booking` como agregado e explicar essa evolução verbalmente.

## 7. APIs e contratos

### Superfície mínima da aula

**Aula local:**

```http
GET /events/{eventId}
GET /events?query=...&city=...&start=...&end=...&limit=...&offset=...
POST /book/{eventId}
```

O `POST /book/{eventId}` recebe IDs de ingressos e dados de pagamento e inicia a compra.

### Contrato recomendado para explicitar etapas

**Complemento:**

```http
GET /v1/events?query=&city=&from=&to=&cursor=
GET /v1/events/{eventId}
GET /v1/events/{eventId}/availability?section=

POST /v1/events/{eventId}/reservations
Idempotency-Key: 6b14...
{
  "inventory_unit_ids": ["seat-A-10", "seat-A-11"],
  "admission_token": "signed-token"
}

POST /v1/reservations/{reservationId}/payment-attempts
Idempotency-Key: 91af...
{
  "payment_method_token": "provider-token"
}

GET /v1/reservations/{reservationId}
POST /v1/webhooks/payments/{provider}
```

Resposta de reserva:

```json
{
  "reservation_id": "rsv_123",
  "status": "HELD",
  "expires_at": "2026-06-22T20:10:00Z",
  "price_snapshot": {
    "currency": "BRL",
    "subtotal": 50000,
    "fees": 7500,
    "total": 57500
  }
}
```

### Regras de contrato

- `Idempotency-Key` identifica a intenção do cliente, não uma tentativa de rede.
- Repetir a mesma chave e o mesmo payload retorna o mesmo resultado.
- Reusar a chave com payload diferente retorna conflito.
- A API não promete que a disponibilidade exibida continua válida; somente uma reserva `HELD` assegura as unidades até `expires_at`.
- O cliente nunca confirma a compra apenas porque voltou da página do provedor; ele consulta o estado ou recebe atualização do servidor.
- Webhooks são autenticados, deduplicados e podem chegar fora de ordem.
- Paginação por cursor é preferível em feeds mutáveis; offset é aceitável no desenho inicial.

## 8. Modelo de dados

Uma modelagem relacional atende bem às relações e restrições do domínio.

```text
event(
  event_id PK, venue_id, starts_at, sales_status, version, metadata...
)

inventory_unit(
  inventory_unit_id PK,
  event_id,
  section_id,
  seat_label,
  state,              -- AVAILABLE | HELD | SOLD
  reservation_id NULL,
  hold_expires_at NULL,
  version,
  price_cents
)

reservation(
  reservation_id PK,
  event_id,
  user_id,
  status,             -- HELD | PAYMENT_PENDING | CONFIRMED | EXPIRED | CANCELED
  expires_at,
  idempotency_key,
  price_snapshot_json,
  created_at,
  updated_at,
  UNIQUE(user_id, idempotency_key)
)

reservation_item(
  reservation_id,
  inventory_unit_id,
  price_cents,
  PRIMARY KEY(reservation_id, inventory_unit_id),
  UNIQUE(inventory_unit_id, active_claim_marker)
)

payment_attempt(
  payment_attempt_id PK,
  reservation_id,
  provider,
  provider_reference,
  idempotency_key,
  status,             -- INITIATED | AUTHORIZED | CAPTURED | FAILED | UNKNOWN | REFUNDED
  amount_cents,
  UNIQUE(provider, provider_reference),
  UNIQUE(reservation_id, idempotency_key)
)

outbox_event(
  event_id PK,
  aggregate_type,
  aggregate_id,
  event_type,
  payload,
  published_at NULL
)
```

### Garantia contra overselling

**Complemento:** o banco é a autoridade de integridade. Para assentos individuais, a reserva executa uma transação com atualização condicional:

```sql
UPDATE inventory_unit
SET state = 'HELD',
    reservation_id = :reservation_id,
    hold_expires_at = :expires_at,
    version = version + 1
WHERE inventory_unit_id IN (:requested_ids)
  AND event_id = :event_id
  AND (
    state = 'AVAILABLE'
    OR (state = 'HELD' AND hold_expires_at < CURRENT_TIMESTAMP)
  );
```

Se o número de linhas alteradas for diferente do número solicitado, a transação faz rollback. Outra opção é bloquear linhas com `SELECT ... FOR UPDATE`. Para setores agregados, um update atômico condiciona `available_count >= requested_quantity`.

**Aula local:** propõe marcar todos os tickets como reservados em uma transação e usa Redis como lock distribuído com TTL, seguido de nova verificação do estado durável.

**Complemento importante:** Redis reduz contenção e libera holds rapidamente, mas não deve ser a única barreira de correção. Failover, expiração, pausa de processo e partição podem invalidar suposições de lock. Uma restrição/transação no banco mantém a invariável mesmo se o cache falhar.

### Índices

- `inventory_unit(event_id, section_id, state)` para disponibilidade.
- `inventory_unit(reservation_id)` para confirmar ou expirar.
- `reservation(status, expires_at)` para sweeper/reconciliação.
- `payment_attempt(provider, provider_reference)` para webhook.
- `outbox_event(published_at)` parcial para eventos pendentes.
- Índice de busca externo por texto, cidade, artista e data.

## 9. Arquitetura mínima

Comece com o menor desenho que cobre os requisitos:

```text
Cliente
   |
API Gateway
   |------------------|------------------|
Event Service     Search Service     Booking Service
   |                  |                  |
   |---------------- Banco relacional --|
                                      |
                              Provedor de pagamento
                                      |
                                  Webhook
```

### Fluxo de descoberta

1. `Search Service` consulta o banco com filtros.
2. O usuário escolhe um `event_id`.
3. `Event Service` lê evento, tickets e bookings para compor disponibilidade.

### Fluxo de compra

1. `Booking Service` recebe `event_id` e IDs dos tickets.
2. Verifica e reserva todas as unidades em uma transação.
3. Cria a reserva com prazo.
4. Inicia pagamento em provedor terceiro.
5. Webhook confirma o pagamento.
6. Booking muda a reserva para confirmada e torna as unidades `SOLD`.
7. Se o prazo expira, muda para cancelada/expirada e libera as unidades.

**Aula local:** esse é o núcleo do desenho apresentado, incluindo API Gateway, Event Service, caminho separado de busca, Booking Service, banco relacional e pagamento por terceiro.

O ponto que o candidato deve dizer em voz alta: “A arquitetura mínima ainda não está pronta para um onsale popular; agora vou evoluí-la pelos gargalos.”

## 10. Evolução para escala e desempenho

```text
Cliente
  |
CDN / WAF / Edge rate limit
  |
API Gateway
  |--------------------------- descoberta ---------------------------|
  |                                                                 |
Search Service -> Search Index      Event Service -> Event Cache -> DB/read model
                         ^                              ^
                         | CDC / eventos                | invalidação/eventos
                         |                              |
  |----------------------------- compra --------------------------------|
  |
Virtual Queue -> Admission Service -> Reservation Service -> Inventory DB
                                           |              -> Redis (contenção/TTL)
                                           |
                                      Payment Orchestrator -> Provedor
                                           |
                                  Outbox / Event Bus / Workers
                                    |           |          |
                              confirmação  expiração  reconciliação
```

### Descoberta

- **Cache de detalhes:** eventos populares são ideais para cache; separar metadados estáticos de disponibilidade volátil aumenta hit rate.
- **Índice invertido:** busca textual migra para mecanismo dedicado.
- **CDC:** alterações do banco alimentam o índice de busca e read models.
- **CDN:** imagens, descrições e assets estáticos ficam na borda.
- **Disponibilidade aproximada:** a lista pode mostrar “poucos ingressos”; a seleção final revalida no serviço autoritativo.

**Aula local:** cache LRU para eventos populares, Elasticsearch/índice invertido, CDC e CDN são evoluções explícitas.

### Compra

- **Fila virtual por evento:** absorve o burst antes do Booking Service.
- **Token de admissão assinado:** limita quem pode chegar à reserva e por quanto tempo.
- **Controle adaptativo:** admite conforme latência do banco, taxa de conflito, erro do pagamento e capacidade disponível.
- **Particionamento por evento:** mantém uma reserva e suas unidades no mesmo shard quando possível.
- **Redis:** deduplicação rápida, rate limit, posição da fila e redução de tentativas concorrentes.
- **Banco relacional primário:** decisão final sobre inventário.
- **Outbox:** publica confirmação/expiração sem dual write inseguro.

## 11. Máquina de estados da reserva

```text
                         pagamento aprovado
AVAILABLE -> HELD -> PAYMENT_PENDING ----------------> CONFIRMED
              |              |                            |
              | TTL          | falha definitiva           | refund*
              v              v                            v
           EXPIRED        CANCELED                    REFUNDED*
              |
              +--------------------> inventário AVAILABLE
```

`REFUNDED` fica fora do escopo mínimo, mas é útil para responder a uma extensão.

### Invariantes

1. Uma `InventoryUnit` só pode ter um claim ativo.
2. `CONFIRMED` exige pagamento capturado/autorizado segundo a política definida.
3. Uma transição terminal não regride por webhook antigo.
4. Expiração e confirmação concorrentes são serializadas por versão/lock transacional.
5. O valor cobrado usa o snapshot de preço da reserva.
6. Toda transição relevante gera auditoria e evento de outbox na mesma transação.

### Corrida crítica: TTL versus webhook

Se o webhook chega exatamente quando a reserva expira:

- carregue a reserva no primário com lock ou compare-and-set;
- se ainda estiver `HELD/PAYMENT_PENDING` e dentro da política de tolerância, confirme;
- se já estiver `EXPIRED` e as unidades foram realocadas, não tente “desexpirar”;
- consulte/cancele/estorne a cobrança conforme a política;
- envie o caso para reconciliação quando o estado externo for incerto.

Não existe escolha universal entre “honrar pagamento tardio” e “expirar estritamente”. A política precisa preservar a invariável de inventário e definir a compensação financeira.

## 12. Reserva temporária, TTL e liberação

### Versão simples

Um job periódico procura reservas `HELD` com `expires_at < now()` e as cancela.

**Aula local:** considera essa solução razoável para entrevista, mas identifica a janela de indisponibilidade se o cron atrasar ou cair.

### Versão robusta

- O estado durável inclui `expires_at`.
- Leituras autoritativas tratam hold vencido como reclamável.
- Uma chave Redis `hold:{inventory_unit_id}` usa criação condicional e TTL para rejeição rápida.
- O banco revalida e grava a reserva atomicamente.
- Um sweeper assíncrono normaliza linhas vencidas.
- Confirmação e expiração usam transições idempotentes.

O TTL em Redis não é um relógio financeiro nem uma prova de cancelamento. É um mecanismo operacional. O banco e a política de estados determinam o que pode ser vendido.

Detalhes adicionais estão em [deep-dives.md](./deep-dives.md).

## 13. Pagamento, idempotência e saga

O pagamento cruza dois domínios que não compartilham transação ACID: inventário local e provedor externo. Modele-o como uma saga orquestrada.

### Caminho feliz

1. Criar reserva `HELD`.
2. Persistir `PaymentAttempt(INITIATED)`.
3. Chamar o provedor com chave idempotente estável.
4. Receber resposta ou webhook.
5. Em transação local, marcar pagamento e reserva confirmados, unidades vendidas e evento de outbox.
6. Emitir ingresso/notificação de forma assíncrona.

### Falhas relevantes

- Timeout antes de saber se o provedor cobrou.
- Cliente repete `POST`.
- Webhook duplicado.
- Webhook chega antes da resposta síncrona.
- Webhooks `failed` e `captured` chegam fora de ordem.
- Reserva expira com pagamento em processamento.
- Banco confirma, mas processo cai antes de responder.

### Respostas

- Idempotência em todas as fronteiras.
- Estados monotônicos e precedência de eventos.
- Consulta ao provedor para resolver `UNKNOWN`.
- Compensação: void/refund quando houve cobrança sem inventário.
- Reconciliação periódica entre ledger local e relatórios do provedor.
- Dead-letter queue e alerta para casos não resolvidos.

**Complemento:** a aula introduz webhook, retry, circuit breaker e possível fila, mas idempotência, saga e reconciliação são aprofundamentos adicionados.

## 14. Consistência e particionamento

### Onde exigir consistência forte

- Transição de uma unidade para `HELD`.
- Reserva atômica de múltiplas unidades.
- Transição de `HELD` para `SOLD`.
- Aplicação de webhook ao `PaymentAttempt`.
- Deduplicação de uma intenção idempotente.
- Contador de capacidade em setor geral.

### Onde aceitar consistência eventual

- Índice de busca.
- Cache de descrição.
- Contagem aproximada na página/lista.
- Posição estimada na fila.
- Analytics e dashboards.
- E-mail e emissão assíncrona, desde que recuperáveis.

### Estratégia de partição

Particionar inventário por `event_id` concentra tudo que precisa ser transacionado junto. A vantagem é preservar atomicidade local. O custo é criar hotspots extremos para eventos populares. Mitigações:

- fila e admission control antes do shard;
- divisão por setor quando uma compra não cruza setores;
- particionamento de assentos por faixas, aceitando coordenação extra para carrinhos mistos;
- filas de trabalho por evento;
- limite de concorrência por chave;
- isolamento físico de eventos excepcionais.

Evite prometer “sharding resolve escala” sem discutir skew. Um hash uniforme distribui eventos, não distribui a carga dentro do evento mais quente.

## 15. Confiabilidade, disponibilidade e recuperação

### Modos de falha

| Falha | Efeito | Recuperação |
|---|---|---|
| Cache indisponível | Mais carga e latência | Bypass controlado, rate limit, banco continua autoritativo |
| Redis de holds reinicia | Locks rápidos desaparecem | Banco impede duplicidade; reconstruir/reaquecer sem assumir disponibilidade |
| Search index atrasado | Evento novo não aparece | Detalhe por ID funciona; monitorar lag de CDC |
| Banco primário indisponível | Reserva não pode ser garantida | Falhar fechado no booking; descoberta serve cache |
| Webhook duplicado | Risco de dupla transição | Chave única e handler idempotente |
| Timeout do provedor | Estado de cobrança desconhecido | Marcar `UNKNOWN`, consultar e reconciliar |
| Sweeper atrasado | Holds vencidos permanecem visíveis | `expires_at` avaliado no caminho autoritativo; sweeper faz higiene |
| Fila virtual cai | Burst chega ao backend | Edge fecha admissão; restaurar tokens/posição do log durável |
| Worker cai após commit | Cliente não recebe resposta | Retry com mesma chave retorna resultado persistido |
| Região perde conectividade | Risco de split-brain | Uma região escritora por partição; compras falham fechado |

### RTO e RPO

**Hipótese pedagógica:** para descoberta, RTO de minutos e dados eventualmente consistentes são aceitáveis. Para inventário confirmado, RPO deve tender a zero por replicação síncrona dentro da região e log durável; recuperação multi-região deve evitar dois líderes para o mesmo shard.

### Degradação graciosa

- Busca pode mostrar cache antigo com indicação de atualização.
- Mapa pode ser substituído por escolha automática de quantidade/setor.
- Pagamento indisponível não deve prolongar holds indefinidamente.
- Em overload, preserve usuários já admitidos e reduza novas admissões.
- Se não for possível provar posse do inventário, responda indisponibilidade, não sucesso otimista.

## 16. Segurança, justiça, bots, fraude e limites

### Camadas de proteção

- WAF, reputação de IP/dispositivo e rate limit na borda.
- Limites por conta, cartão, documento, dispositivo e endereço.
- CAPTCHA ou prova de trabalho apenas sob risco elevado.
- Token de fila assinado, vinculado a evento, sessão, prazo e nonce.
- Prevenção de múltiplas posições por identidade/dispositivo.
- Limite de ingressos por usuário e evento aplicado no banco, não só no cliente.
- Detecção de velocidade: muitas reservas, cartões ou falhas em curto período.
- 3DS/controles do provedor quando aplicável.
- Auditoria de mudanças manuais e ações administrativas.
- Nunca armazenar dados brutos de cartão; usar tokenização do provedor e reduzir escopo PCI.

### Justiça

“FIFO” não é automaticamente justo: latência de rede, reconexão e bots alteram a chegada observada. Defina uma política:

- lote aleatório entre usuários presentes antes da abertura;
- FIFO após abertura;
- cotas explícitas para pré-venda;
- prioridade acessível documentada;
- recuperação curta de sessão sem perder lugar;
- transparência de limites e critérios.

**Complemento:** segurança, fraude e política de justiça não são desenvolvidas na aula, embora rate limiting no gateway seja mencionado.

## 17. Observabilidade e operação

### Métricas do funil

- buscas e detalhes por segundo;
- cache hit ratio e latência por camada;
- lag do CDC e idade do documento no índice;
- entradas, admissões, abandono e espera p50/p95/p99 da fila;
- tentativas de reserva, sucesso, conflito e expiração;
- contenção/lock wait por `event_id`;
- reservas ativas e inventário disponível;
- conversão `HELD -> CONFIRMED`;
- latência e erro por provedor/método;
- webhooks duplicados, fora de ordem e atrasados;
- pagamentos `UNKNOWN`;
- compensações e divergências de reconciliação;
- suspeitas de bot/fraude e falsos positivos.

### Logs e traces

Propague `correlation_id`, `reservation_id`, `payment_attempt_id`, hash da `idempotency_key`, `event_id` e `admission_token_id`. Não registre cartão, documento completo, segredo de webhook ou token reutilizável.

### Alertas úteis

- overselling detectado: severidade máxima;
- crescimento de `UNKNOWN` ou divergência financeira;
- taxa de conflito anormal por evento;
- reservas expiradas não limpas;
- lag do índice/CDC;
- saturação do shard do evento;
- queda na admissão com backend saudável;
- aumento de pagamento aprovado sem confirmação de pedido.

### Runbooks

Tenha procedimentos para pausar admissão, isolar evento, trocar provedor, reprocessar webhook, executar reconciliação, liberar hold órfão e comunicar degradação. Uma operação manual deve produzir auditoria.

## 18. Alternativas e trade-offs

| Decisão | Ganho | Custo | Quando escolher |
|---|---|---|---|
| Ticket pré-gerado | Identidade e lock por unidade | Muitas linhas | Assento numerado ou inventário individual |
| Contador agregado | Menos armazenamento | Não escolhe assento; contenção no contador | Setor geral |
| `SELECT FOR UPDATE` | Modelo claro e forte | Espera e deadlock sob pico | Concorrência moderada |
| Update condicional otimista | Evita espera longa | Mais conflitos/retries | Picos curtos e operações simples |
| Redis lock + banco | Rejeição rápida e TTL | Dois estados para coordenar | Otimização com banco autoritativo |
| Cron de expiração | Simplicidade | Liberação atrasada | MVP/entrevista inicial |
| TTL + sweeper | Liberação rápida e higiene | Mais complexidade | Produção com holds curtos |
| WebSocket para fila | Bidirecional | Conexões e operação mais complexas | Cliente também envia eventos frequentes |
| SSE para fila | Simples servidor→cliente | Canal unidirecional | Atualização de posição/status |
| Fila FIFO | Explicável | Sensível a bots e corrida inicial | Tráfego regular |
| Loteria de lote inicial | Reduz vantagem de milissegundos | Usuário não vê ordem estrita | Abertura extremamente disputada |
| Banco único relacional | Transações simples | Limite vertical/hotspot | Escala inicial |
| Shard por evento | Atomicidade local | Evento quente concentra carga | Inventário naturalmente agrupado |

O entrevistador avalia se você nomeia o custo da solução, não se cita a maior quantidade de tecnologias.

## 19. Gargalos, falhas e armadilhas comuns

1. **Usar cache como fonte de verdade.** Cache pode mentir; venda exige validação autoritativa.
2. **Check-then-act sem transação.** Duas instâncias leem “disponível” e ambas gravam.
3. **Lock sem fencing/versionamento.** Um dono antigo pode continuar após expiração.
4. **Confirmar pelo redirect do browser.** O cliente é não confiável e pode fechar.
5. **Retry sem idempotência.** Cria reservas ou cobranças duplicadas.
6. **TTL apenas em memória.** Reinício perde o prazo e a capacidade fica presa ou livre cedo demais.
7. **Cron como única liberação.** Atraso operacional vira indisponibilidade de inventário.
8. **Webhook tratado como ordenado e único.** Provedores repetem e atrasam eventos.
9. **Particionar sem tratar hotspot.** Um evento ainda derruba um shard.
10. **Fila sem token de admissão.** Usuários contornam a página e chamam booking diretamente.
11. **Mostrar contagem exata via cache.** Cria falsa promessa e tempestade de invalidação.
12. **Segurar transação durante pagamento.** Locks por minutos destroem throughput.
13. **Apagar reserva cancelada.** Perde auditoria e dificulta reconciliação.
14. **Deixar hold ativo enquanto provedor está indefinido.** Inventário fica sequestrado.
15. **Não separar dado da aula de complemento.** Em estudo, isso gera falsa atribuição.

## 20. Roteiro sugerido para 45 minutos

### 0–5 min — Escopo

- Confirmar busca, detalhes, reserva e compra.
- Perguntar sobre assento versus setor, TTL, pico e pagamento.
- Excluir administração, reembolso e revenda.

### 5–9 min — Não funcionais e estimativas

- Separar descoberta de compra.
- Declarar 100 mil eventos e 20 milhões de DAU como números da aula.
- Estimar QPS médio e destacar o pico por evento.
- Fixar invariável: zero venda duplicada.

### 9–14 min — API e dados

- Desenhar endpoints.
- Mostrar `Event`, `InventoryUnit`, `Reservation`, `PaymentAttempt`.
- Explicar idempotency key e `expires_at`.

### 14–23 min — Arquitetura mínima

- Gateway, Event, Search, Booking, banco e provedor.
- Percorrer busca e compra.
- Desenhar a máquina `AVAILABLE -> HELD -> CONFIRMED/EXPIRED`.

### 23–35 min — Deep dive principal

- Reserva atômica de vários assentos.
- Banco como autoridade; Redis como proteção/TTL.
- Corrida entre confirmação e expiração.
- Pagamento idempotente, webhook e estado desconhecido.

### 35–41 min — Escala e falhas

- Fila virtual e admission control.
- Hotspot por evento e particionamento.
- Cache, search index, CDC e CDN.
- Saga, compensação e reconciliação.

### 41–45 min — Fechamento

- Segurança/bots e observabilidade.
- Repassar requisitos.
- Nomear dois trade-offs.
- Dizer o que faria com mais tempo.

**Aula local:** recomenda que requisitos consumam cerca de 10–15 minutos no máximo e que o desenho comece simples antes dos deep dives. Este roteiro comprime a abertura para preservar tempo para concorrência e falhas.

## 21. Perguntas do entrevistador

### “Como garante que duas pessoas não comprem o mesmo assento?”

Com uma transação no banco autoritativo: lock de linha ou update condicional que só muda `AVAILABLE`/hold vencido para `HELD`. Para vários assentos, todos devem ser alterados na mesma transação; contagem diferente faz rollback. Redis pode rejeitar cedo, mas não substitui a restrição durável.

### “O que acontece quando o usuário abandona o pagamento?”

A reserva tem `expires_at`. O caminho autoritativo considera holds vencidos reclamáveis; Redis pode expirar a chave rapidamente e um sweeper normaliza o banco. Preservamos o registro como `EXPIRED/CANCELED` para auditoria.

### “E se o pagamento foi feito, mas a resposta se perdeu?”

A tentativa fica `UNKNOWN`. Repetimos consultas idempotentes ao provedor, processamos webhook e reconciliamos. Se a reserva já expirou e o inventário foi vendido, fazemos void/refund; nunca confirmamos uma segunda venda.

### “Por que não usar somente Redis?”

Porque TTL e lock em cache são excelentes para contenção, mas failover/partição podem violar exclusão percebida. O banco relacional aplica a invariável final e registra o histórico auditável.

### “Como escalar uma abertura de venda?”

Fila virtual antes do booking, token de admissão assinado, rate limit por evento e admissão adaptativa baseada na saúde do shard. O objetivo não é processar 100 mil reservas/s; é reduzir a entrada ao throughput seguro.

### “Como atualizar a posição da fila?”

SSE é suficiente para atualizações servidor→cliente; WebSocket serve se houver comunicação bidirecional frequente. Posição pode ser aproximada, mas o token de admissão deve ser verificável e não reutilizável.

### “Como particionar?”

Por `event_id` para manter transações locais; eventos excepcionais podem ganhar isolamento ou subdivisão por setor. A fila protege o shard quente. Explico o custo de compras que cruzam partições.

### “Busca precisa ser consistente?”

Não com o inventário em tempo real. Busca e detalhes podem usar cache/índice eventual. A reserva revalida a unidade no primário.

### “Como impedir bots?”

Defesa em camadas: WAF, rate limit por identidade/dispositivo, token de fila, limites de compra no banco, análise de velocidade, desafio adaptativo e controles do pagamento. Nenhum sinal isolado é suficiente.

### “Como saber se o sistema está saudável?”

Além de CPU, acompanho espera na fila, taxa de admissão, conflitos de reserva, hold expirado, conversão, `UNKNOWN`, lag de webhook/CDC, divergência financeira e saturação por evento.

## 22. Checklist de encerramento

### Escopo

- [ ] Busca, detalhe e compra estão cobertos.
- [ ] Assento/setor, quantidade máxima e TTL foram definidos.
- [ ] Fora de escopo foi declarado.

### Correção

- [ ] A autoridade de inventário está explícita.
- [ ] Reserva de múltiplas unidades é atômica.
- [ ] Máquina de estados e invariantes foram explicadas.
- [ ] Idempotência cobre cliente, provedor e webhook.
- [ ] Corrida TTL versus confirmação tem política.

### Escala

- [ ] Média e pico por evento foram separados.
- [ ] Fila virtual e admission control protegem booking.
- [ ] Hotspot e estratégia de partição foram discutidos.
- [ ] Busca/cache/CDC/CDN aparecem no caminho de leitura.

### Falhas e operação

- [ ] Timeout com cobrança desconhecida foi tratado.
- [ ] Saga, compensação e reconciliação foram citadas.
- [ ] Banco/Redis/provedor/fila têm modos de falha.
- [ ] Métricas de negócio e técnicas foram propostas.
- [ ] Bots, fraude, limites e justiça foram considerados.

### Comunicação

- [ ] O desenho mínimo veio antes da escala.
- [ ] Cada tecnologia tem uma razão e um custo.
- [ ] Conteúdo da aula, complementos e hipóteses não foram misturados.
- [ ] O fechamento revisitou os requisitos.

## 23. Relação com a aula-fonte

### Fundamentado no material local

- metodologia: requisitos → APIs → desenho mínimo → deep dives;
- busca, detalhes e compra como escopo central;
- 100 mil eventos e 20 milhões de DAU como números ilustrativos;
- leitura muito maior que escrita;
- consistência no booking e disponibilidade/latência na descoberta;
- REST, API Gateway, Event/Search/Booking Services;
- banco relacional e tickets pré-gerados;
- estados reservado, confirmado e cancelado;
- transação para reservar múltiplos tickets;
- pagamento terceirizado e callback/webhook;
- cron de expiração e sua janela de falha;
- Redis como lock distribuído com TTL e rechecagem durável;
- cache LRU, índice invertido/Elasticsearch, CDC e CDN;
- fila virtual, Redis, WebSocket/SSE;
- replicação, load balancing, retry, circuit breaker e filas para pagamento.

### Complementos deste guia

- banco como última barreira de integridade mesmo com Redis;
- APIs separadas de reserva e tentativa de pagamento;
- idempotency keys e deduplicação de webhook;
- modelagem de `PaymentAttempt`, outbox e audit log;
- saga, compensação, estado `UNKNOWN` e reconciliação;
- fencing/versionamento e corrida TTL versus webhook;
- admission token, controle adaptativo e política de justiça;
- análise de hotspot e particionamento;
- segurança, bots, fraude, observabilidade e runbooks;
- RTO/RPO e recuperação regional.

### Hipóteses pedagógicas

Todos os QPS, tamanhos, percentuais, TTL de 10 minutos, limite de 8 ingressos e objetivos de latência deste guia são números de exercício. Eles existem para tornar decisões explícitas e devem ser renegociados com o entrevistador.

### Limitações da fonte

A aula-fonte foi transcrita automaticamente do áudio porque não havia captions expostas. A própria nota de origem registra ruído em termos técnicos, nomes e pontuação; o whiteboard visual não foi extraído integralmente. Este guia preserva o sentido documentado no overview e nos timestamps, sem inventar detalhes como se fossem falas exatas.
