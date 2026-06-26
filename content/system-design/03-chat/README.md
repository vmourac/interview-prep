# System Design de Chat

Este guia prepara uma resposta de entrevista para um sistema de chat com conversas individuais e em grupo, entrega quase em tempo real, histórico, usuários offline e múltiplos dispositivos. A meta não é desenhar “o WhatsApp inteiro”, e sim construir uma linha de raciocínio defensável: fechar o escopo, escolher garantias explícitas, desenhar o caminho mínimo e só então evoluí-lo onde as estimativas exigirem.

> **Rastreabilidade.** A aula local está catalogada como **Use Cases - Chat**, mas o título do vídeo e todo o conteúdo da gravação tratam de um **Notification System**. Neste documento:
>
> - **Aula local** identifica ideias realmente presentes na gravação: clarificação, progressão requisitos → arquitetura → deep dive, aceitação assíncrona, filas, prioridade, retries, callbacks, reconciliação e retenção.
> - **Complemento** identifica conhecimento consolidado de design de chat que não aparece na aula: WebSocket, presença, ordenação, recibos, sincronização multi-device, fan-out e mídia.
> - **Hipótese pedagógica** identifica números escolhidos apenas para exercitar capacidade. Eles não descrevem sistemas reais da Uber, Ada ou qualquer produto.

Material relacionado: [deep dives](deep-dives.md) e [cockpit interativo](index.html).

## 1. Enquadramento do problema

Uma boa abertura seria: “Vou desenhar um chat de consumidor com mensagens de texto e anexos, conversas 1:1 e grupos moderados. O envio precisa ser durável e aparecer em segundos; presença e recibos podem ser eventualmente consistentes. Vou começar pelo fluxo de texto e depois discutir escala, offline e falhas.”

Essa frase faz três coisas úteis. Primeiro, transforma “chat” em um produto concreto. Segundo, separa o caminho crítico — aceitar e preservar mensagens — de sinais efêmeros, como “digitando”. Terceiro, reserva tempo para os deep dives que realmente diferenciam este problema.

O sistema deve permitir que um remetente envie uma mensagem uma vez e que cada dispositivo destinatário converja para o mesmo histórico, mesmo após desconexão, retry ou troca de gateway. A experiência desejada é “quase exatamente uma vez”, mas a infraestrutura normalmente oferece entrega **pelo menos uma vez**; idempotência e deduplicação fecham essa diferença.

## 2. Perguntas de clarificação

Nos primeiros cinco minutos, pergunte e anote as respostas:

1. O chat é 1:1, grupos, canais públicos ou todos? Qual o tamanho máximo de grupo?
2. Precisamos apenas de texto ou também anexos, edição, remoção, reações e busca?
3. “Entregue” significa persistida no servidor, recebida em algum dispositivo ou lida pelo usuário?
4. A ordem precisa ser global, por conversa ou apenas por remetente?
5. Quantos usuários ativos e conexões simultâneas devemos suportar?
6. Qual latência é aceitável para envio, entrega, reconexão e carregamento do histórico?
7. Por quanto tempo mensagens e mídia são retidas? Existe exclusão por usuário ou requisito legal?
8. Um usuário pode usar vários dispositivos? Eles devem sincronizar recibos e histórico?
9. Há criptografia ponta a ponta? O servidor precisa moderar, indexar ou buscar conteúdo?
10. Podemos perder presença, “digitando” e recibos durante uma falha sem perder mensagens?

Se o entrevistador não responder, declare hipóteses. Não esconda ambiguidade atrás de tecnologia.

## 3. Requisitos funcionais

### Dentro do escopo

- criar conversas 1:1 e grupos;
- enviar mensagens de texto com uma chave idempotente gerada pelo cliente;
- receber novas mensagens por conexão persistente;
- listar histórico por cursor;
- entregar mensagens acumuladas quando um dispositivo reconectar;
- manter múltiplos dispositivos por usuário;
- registrar estados `accepted`, `delivered` e `read` com semântica definida;
- exibir presença aproximada e sinal de digitação;
- enviar anexos por upload direto ao armazenamento de objetos;
- permitir retry sem criar mensagens visíveis duplicadas.

### Fora do escopo inicial

- chamadas de voz e vídeo;
- busca global, moderação automática e recomendação;
- edição colaborativa de documentos;
- grupos com milhões de membros;
- protocolo completo de criptografia ponta a ponta;
- retenção jurídica específica por país.

Esses itens podem virar extensões. Excluí-los evita que a arquitetura mínima nasça como uma coleção de serviços prematuros.

## 4. Requisitos não funcionais

- **Durabilidade:** após o ACK de aceitação, a mensagem não pode desaparecer.
- **Latência:** alvo pedagógico de p95 abaixo de 300 ms para aceitar texto na mesma região e abaixo de 1 s para entrega online.
- **Disponibilidade:** envio e histórico são mais importantes que presença e recibos.
- **Ordenação:** ordem total apenas dentro de uma conversa; nenhuma ordem global.
- **Semântica:** entrega interna pelo menos uma vez, com efeito idempotente no cliente e nos consumidores.
- **Consistência:** forte o bastante para atribuir uma posição por conversa; eventual para presença, entrega, leitura e contadores.
- **Escalabilidade:** conexões persistentes, escrita e fan-out devem escalar independentemente.
- **Segurança:** autenticação curta, autorização por conversa, limites, proteção contra abuso e mídia isolada.
- **Operação:** deploy gradual, compatibilidade de eventos, reconciliação e métricas por estágio.

## 5. Estimativas que mudam o desenho

As estimativas abaixo são **hipóteses pedagógicas**, não dados da aula:

- 10 milhões de usuários ativos por dia;
- 2 milhões de conexões simultâneas no pico;
- 100 milhões de mensagens de texto por dia;
- pico de 10 vezes a média;
- 1 KB por mensagem persistida, incluindo índices e metadados;
- 3 dispositivos por usuário ativo;
- 1% das mensagens com anexo médio de 1 MB;
- 30 dias de retenção quente para texto.

Consequências:

- `100 M / 86.400 ≈ 1.160` mensagens/s em média e cerca de `12 mil/s` no pico;
- com fan-out para três dispositivos, o pico de tentativas de entrega pode passar de `36 mil/s`, antes de considerar grupos;
- texto bruto ocupa cerca de `100 GB/dia`; com réplicas e índices, planeje múltiplos disso;
- 30 dias de texto representam aproximadamente `3 TB` brutos;
- anexos chegam perto de `1 TB/dia`, portanto não devem atravessar nem permanecer no banco de mensagens;
- se uma conexão consumir 50 KB entre socket, TLS, buffers e estado, 2 milhões exigem aproximadamente `100 GB` distribuídos na frota;
- a média de mensagens é modesta comparada ao custo de manter milhões de conexões e multiplicar entregas.

A decisão arquitetural mais importante nasce daí: **connection gateways**, armazenamento de mensagens e fan-out precisam ser planos separados.

## 6. Entidades

- **User:** identidade lógica.
- **Device:** instalação autenticada, com cursor próprio.
- **Conversation:** domínio de ordenação e política.
- **Membership:** vínculo do usuário com a conversa, papel e data de entrada/saída.
- **Message:** conteúdo ou referência de mídia, remetente, chave idempotente e sequência.
- **Receipt:** progresso de entrega/leitura por usuário ou dispositivo.
- **Connection:** rota efêmera entre dispositivo e gateway.
- **Attachment:** metadados, estado de upload, hash, tamanho e chave no object storage.

Uma distinção sênior é não confundir `user_id` com `device_id`: entrega ocorre em dispositivos, enquanto leitura e produto podem ser agregados por usuário.

## 7. APIs e protocolo

### Criar mensagem

```http
POST /v1/conversations/{conversation_id}/messages
Authorization: Bearer <token>
Idempotency-Key: 8b8d...-device-42
Content-Type: application/json

{
  "client_message_id": "8b8d...-device-42",
  "type": "text",
  "body": "Chego em 10 minutos",
  "reply_to": null
}
```

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "message_id": "msg_01J...",
  "conversation_id": "conv_73",
  "sequence": 18421,
  "status": "accepted",
  "accepted_at": "2026-06-22T18:10:02.104Z"
}
```

Neste contrato de chat, o servidor só responde `201 Created` depois de autenticar, autorizar, deduplicar e criar duravelmente o recurso `Message` no domínio de ordenação. O estado `accepted` significa que publicação, fan-out e entrega ainda seguem de forma assíncrona; não significa que a API apenas enfileirou a criação. Se o endpoint só aceitasse uma solicitação para processamento antes de criar duravelmente a mensagem, `202 Accepted` seria o contrato adequado — como no padrão de aceitação assíncrona apresentado pela aula local de **Notification System**. O ACK não promete que todos receberam; promete que o sistema assumiu responsabilidade durável.

### Histórico e sincronização

```http
GET /v1/conversations/{conversation_id}/messages?after_sequence=18350&limit=100
GET /v1/sync?cursor=device_cursor_abc&limit=500
POST /v1/conversations/{conversation_id}/receipts
```

`after_sequence` evita paginação por offset e torna buracos detectáveis. O cursor global do dispositivo aponta para mudanças que ele ainda não materializou.

### WebSocket

```text
C → S  auth {token, device_id, last_sync_cursor}
C → S  send_message {conversation_id, client_message_id, body}
S → C  message_accepted {message_id, sequence}
S → C  message_created {message_id, conversation_id, sequence, body}
C → S  delivered {conversation_id, up_to_sequence}
C → S  read {conversation_id, up_to_sequence}
C ↔ S  ping / pong
```

Os eventos carregam `event_id` e versão de schema. O cliente deve tolerar repetição, eventos desconhecidos e reconexão.

### Anexos

1. `POST /v1/attachments:init` retorna URL de upload com prazo e escopo;
2. cliente envia bytes diretamente ao object storage;
3. `POST /v1/attachments/{id}:complete` valida tamanho, hash e inspeção;
4. a mensagem referencia `attachment_id`, nunca os bytes.

## 8. Modelo de dados

```text
conversations(
  conversation_id PK, type, created_at, last_sequence, policy_version
)

memberships(
  conversation_id PK-part, user_id PK-sort,
  role, joined_sequence, left_sequence, muted_until
)

messages(
  conversation_id PK-part, sequence PK-sort,
  message_id UNIQUE, sender_user_id, sender_device_id,
  client_message_id, type, payload_ref, created_at
)

device_cursors(
  device_id PK, sync_cursor, updated_at
)

receipts(
  conversation_id PK-part, user_id PK-sort,
  delivered_up_to, read_up_to, updated_at
)

idempotency(
  sender_device_id PK-part, client_message_id PK-sort,
  message_id, expires_at
)
```

`conversation_id` é a chave natural de partição porque as leituras são por conversa e a ordenação também. A combinação `(sender_device_id, client_message_id)` impede duplicação em retries. Recibos usam high-water marks (`read_up_to=18420`) em vez de uma linha por mensagem, reduzindo escrita.

Em uma versão inicial, um banco relacional particionado atende conversas e memberships. Em escala, mensagens podem ir para um wide-column/log-structured store, mantendo metadados transacionais onde relações importam. A escolha segue acesso e garantias, não o rótulo “SQL versus NoSQL”.

## 9. Arquitetura mínima

```text
Cliente
  │ HTTPS / WebSocket
  ▼
API + Connection Gateway
  │ autentica e autoriza
  ▼
Chat Service
  ├── grava Conversation / Message / Idempotency
  ├── publica message.created
  └── responde accepted
             │
             ▼
         Event Bus
             │
             ▼
       Delivery Worker
             │
             ├── dispositivo online → gateway atual
             └── offline → fica disponível no histórico/sync
```

Esta versão cobre o happy path sem fingir escala. O Chat Service pode ser um processo replicado; o banco serializa por conversa; o event bus desacopla persistência de entrega. Presença pode ser derivada da tabela efêmera de conexões. Um worker de push móvel é opcional para acordar usuários offline, sem transportar o conteúdo como fonte de verdade.

## 10. Evolução para escala e desempenho

### Plano de conexões

Gateways WebSocket são stateful apenas durante a conexão. Um balanceador distribui novas sessões; o gateway registra `device_id → gateway_id` em um Connection Registry com TTL. Heartbeats renovam o lease. Em reconexão, qualquer gateway pode assumir o dispositivo.

### Plano de escrita e ordenação

O Message Service roteia cada `conversation_id` para um shard líder. Esse dono lógico valida a chave idempotente, incrementa `sequence`, persiste e publica o evento. Todos os eventos da conversa entram na mesma partição do log, preservando ordem local.

### Plano de fan-out

O Fan-out Service lê `message.created`, resolve memberships e produz tarefas de entrega. Para 1:1 e grupos pequenos, fan-out on write entrega imediatamente aos dispositivos. Para grupos grandes, fan-out on read evita materializar milhões de cópias; clientes puxam a partir do log da conversa. Um limiar híbrido impede que um único grupo domine filas.

### Caches

- cache de membership e autorização com versão/TTL curto;
- cache de rota de conexão, sempre descartável;
- cache de últimas mensagens para reconexões frequentes;
- nunca usar cache como única fonte de mensagens aceitas.

### Backpressure

Gateways limitam fila por conexão. Consumidor lento recebe lotes, coalescimento de presença/recibos e, por fim, desconexão controlada com cursor para retomada. Filas têm limites e DLQ; retries usam backoff com jitter. A prioridade protege mensagens de texto contra tempestades de sinais efêmeros.

## 11. Confiabilidade, disponibilidade e recuperação

O caminho de envio usa a mesma evolução defendida na **aula local** para notificações: aceite rápido, processamento assíncrono, retry, dead-letter e reconciliação. A aplicação ao chat é um **complemento**.

- **Gateway cai:** o socket fecha; cliente reconecta, autentica e envia o último cursor.
- **ACK se perde:** cliente repete `client_message_id`; o servidor retorna a mensagem já criada.
- **Evento é publicado duas vezes:** consumidores deduplicam por `event_id` ou fazem writes idempotentes.
- **Event bus atrasa:** mensagem já está durável; entrega fica atrasada e SLO de lag alerta a operação.
- **Recipient gateway cai:** tarefa é repetida; o cliente também recupera pelo sync.
- **Banco perde líder:** eleição pausa writes daquele shard; não se atribuem sequências concorrentes.
- **Push provider falha:** chat continua no histórico; push é apenas dica de disponibilidade.
- **Job de retry falha:** reconciliador compara mensagens persistidas, offsets e receipts.

Use outbox transacional ou log integrado ao banco para evitar “gravei a mensagem, mas não publiquei o evento”. Se isso não estiver disponível, um reconciliador reemite mensagens sem marcador de publicação.

## 12. Consistência e particionamento

Garantias recomendadas:

- ordem monotônica por conversa, representada por `sequence`;
- read-your-writes para o remetente após `accepted`;
- nenhuma ordem entre conversas;
- presença e “digitando” best effort;
- recibos monotônicos e eventualmente consistentes;
- membership autorizado no momento do envio, com versão auditável.

Durante uma partição, manter dois líderes para a mesma conversa criaria sequências conflitantes. A escolha segura é preservar consistência do log: o lado sem quorum rejeita ou suspende o envio, mas ainda pode mostrar histórico em cache como potencialmente desatualizado. Em contraste, presença pode privilegiar disponibilidade e aceitar inconsistência temporária.

Esse é um ponto de entrevista forte: não existe uma escolha CAP para “o sistema inteiro”; há escolhas por fluxo.

## 13. Segurança e abuso

- tokens de conexão curtos, renováveis e vinculados a usuário/dispositivo;
- autorização de membership em todo send, sync e download de mídia;
- TLS em trânsito e criptografia em repouso;
- IDs não enumeráveis e URLs de mídia assinadas com expiração;
- rate limit por usuário, dispositivo, IP, conversa e criação de grupos;
- cotas de tamanho, tipo MIME real, hash e malware scan de anexos;
- proteção contra replay via chave idempotente e janela de retenção;
- bloqueio, denúncia, mute e controles anti-spam;
- logs sem corpo de mensagem, token ou URL assinada;
- exclusão com tombstone e pipeline que alcance réplicas, índices e objetos.

Criptografia ponta a ponta muda radicalmente moderação, busca, preview, recuperação de conta e multi-device. Se exigida, trate-a como um protocolo próprio, não como uma checkbox.

## 14. Observabilidade e operação

Meça o funil, não apenas CPU:

- latência `send → accepted`, `accepted → published`, `published → delivered`;
- taxa de deduplicação e retries por causa;
- lag por partição e idade da mensagem mais antiga;
- conexões ativas, reconexões/minuto e heartbeats expirados;
- fila por gateway e desconexões por consumidor lento;
- diferença entre `last_sequence` e cursores de dispositivos;
- erro de autorização, rate limit e abuso;
- taxa de upload incompleto, scan falho e objetos órfãos;
- disponibilidade por região e por fluxo.

Trace cada mensagem com IDs técnicos, nunca com conteúdo. Dashboards devem separar 1:1, grupos pequenos e grupos grandes, porque médias escondem hotspots. Runbooks cobrem queda de gateway, lag do bus, shard quente, falha de storage e tempestade de reconexão.

## 15. Manutenção e evolução

- versionar eventos e aceitar campos desconhecidos;
- usar expand/contract em schemas;
- fazer canary por shard ou região;
- drenar gateways antes de deploy para reduzir reconexões simultâneas;
- reequilibrar partições com limites de movimento;
- manter feature flags para recibos, presença e fan-out híbrido;
- executar repair jobs idempotentes;
- testar compatibilidade entre clientes antigos e servidor novo;
- definir retenção de chaves de idempotência e tombstones.

Uma arquitetura operável prevê como mudar sem interromper milhões de sockets.

## 16. Alternativas e trade-offs

| Decisão | Ganho | Custo | Quando escolher |
|---|---|---|---|
| WebSocket | entrega bidirecional eficiente | estado de conexão e operação mais complexa | chat online frequente |
| Long polling | infraestrutura simples | overhead e latência maiores | MVP ou redes restritas |
| Ordem por conversa | semântica compreensível | hotspot em conversa gigante | padrão recomendado |
| Ordem global | modelo aparentemente simples | coordenação cara e desnecessária | quase nunca |
| Fan-out on write | leitura e entrega rápidas | amplificação de escrita | 1:1 e grupos pequenos |
| Fan-out on read | escrita barata | leitura e merge mais caros | canais/grupos enormes |
| Receipt por mensagem | detalhe máximo | explosão de storage/escrita | auditoria excepcional |
| High-water mark | compacto e monotônico | menos detalhe por dispositivo | padrão de produto |
| ACK após persistência | durabilidade clara | mais latência | mensagens normais |
| ACK antes de persistir | latência aparente menor | risco de perda | não recomendado |

## 17. Gargalos, falhas e armadilhas comuns

- desenhar somente WebSocket e esquecer histórico durável;
- prometer “exactly once” sem idempotência;
- ordenar por timestamp de cliente;
- usar presença como dado autoritativo;
- uma fila global que destrói paralelismo;
- particionar por usuário e depois tentar ordenar grupos;
- fan-out on write sem limite para grupos gigantes;
- carregar anexos pelo Chat Service;
- manter uma fila ilimitada por socket lento;
- confundir push notification com entrega da mensagem;
- não definir o significado de `sent`, `delivered` e `read`;
- ignorar reconexão em massa depois de incidente;
- dizer “NoSQL escala” sem explicar chave, consulta e garantia.

## 18. Roteiro de entrevista de 45 minutos

| Tempo | Objetivo | Entrega visível |
|---|---|---|
| 0–5 min | clarificar produto e garantias | escopo, exclusões, semântica de entrega |
| 5–10 min | listar requisitos e números | 4–6 requisitos, DAU, conexões, mensagens/s |
| 10–15 min | definir API e dados | send idempotente, sync por cursor, entidades |
| 15–23 min | desenhar arquitetura mínima | gateway, service, store, bus, delivery |
| 23–32 min | escalar | gateways, sharding por conversa, fan-out |
| 32–39 min | deep dive escolhido | offline/multi-device ou ordem/deduplicação |
| 39–43 min | falhas, segurança e observabilidade | matriz de falha e SLOs |
| 43–45 min | fechar | requisitos cobertos, trade-offs e extensão |

Narre transições: “O happy path está coberto; agora vou usar as estimativas para separar conexões, escrita e entrega.”

## 19. Perguntas do entrevistador

**Como garante ordem?** Um único dono lógico atribui sequência por conversa; partições do log usam a mesma chave. Timestamp de cliente é apenas metadado.

**Como evita duplicatas após timeout?** O cliente repete `client_message_id`; a chave composta com `sender_device_id` retorna o mesmo `message_id`.

**O que ocorre quando o destinatário está offline?** A mensagem permanece no log durável. Push pode acordar o app; a fonte de verdade é o sync por cursor.

**Como sincroniza celular e desktop?** Cada dispositivo tem cursor próprio; estado de leitura pode ser agregado monotonicamente por usuário e retransmitido aos dispositivos.

**E um grupo com um milhão de membros?** Classifico como produto diferente: fan-out on read ou híbrido, cache de membership, proteção de shard e possivelmente canais sem receipts individuais.

**Por que não Kafka diretamente no cliente?** O protocolo interno não substitui autenticação, autorização, backpressure, compatibilidade e roteamento de sockets.

**Como lida com falha entre banco e bus?** Outbox transacional ou CDC; reconciliador fecha lacunas.

**Você escolheria disponibilidade ou consistência?** Consistência para atribuir ordem no log da conversa; disponibilidade best effort para presença e sinais efêmeros.

## 20. Checklist de encerramento

- [ ] Escopo e exclusões foram confirmados?
- [ ] Semântica de `accepted`, `delivered` e `read` está explícita?
- [ ] Estimativas alteraram alguma decisão?
- [ ] Envio é idempotente?
- [ ] A ordem é somente por conversa?
- [ ] Mensagem aceita está durável?
- [ ] Offline e reconexão usam cursor, não memória do gateway?
- [ ] Multi-device foi distinguido de multiusuário?
- [ ] Fan-out tem estratégia para grupos grandes?
- [ ] Anexos não atravessam o serviço de mensagens?
- [ ] Há backpressure, retry, DLQ e reconciliação?
- [ ] Segurança, abuso e observabilidade foram cobertos?
- [ ] Pelo menos um trade-off foi quantificado?
- [ ] A arquitetura mínima e a escalada foram separadas?

## 21. Relação com a aula-fonte

### Fundamentado no material local

A gravação ensina a começar por perguntas, explicitar requisitos funcionais e não funcionais, construir uma arquitetura simples e só depois introduzir escala. Também demonstra aceitação assíncrona, filas para desacoplamento, workers replicados, isolamento de prioridade, retry, dead-letter, callback de entrega, job de reconciliação e retenção quente seguida de arquivo.

A aula usa como hipóteses 10 milhões de usuários ativos/dia, 50 milhões de notificações/dia, latência tolerável em segundos, alta disponibilidade e retenção quente de 30 dias. Esses números pertencem ao exercício de **notificações**, não são transferidos como fatos para chat.

### Complemento para o tópico Chat

Todo o desenho específico de WebSocket, registro de conexões, heartbeat, sequência por conversa, idempotência, receipts, sync offline, múltiplos dispositivos, fan-out híbrido, anexos e decisões de consistência foi acrescentado para cumprir o tópico de chat solicitado.

### Hipóteses pedagógicas

DAU, concorrência, volume de mensagens, tamanho médio, pico, número de dispositivos e volume de mídia foram escolhidos neste guia para tornar consequências arquiteturais calculáveis. Em entrevista, substitua-os pelos números fornecidos e refaça as contas em voz alta.
