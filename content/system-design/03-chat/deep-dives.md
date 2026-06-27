# Deep dives de Chat

Este complemento aprofunda as decisões que costumam consumir a segunda metade de uma entrevista. Ele não repete o desenho top-down do [guia principal](README.md); parte de invariantes, estados e modos de falha.

> **Proveniência.** A aula local, apesar do nome de catálogo “Chat”, é sobre sistema de notificações. Filas, retries, prioridade, callbacks e reconciliação são ideias da aula que podem ser reaplicadas. Os mecanismos específicos abaixo são **complemento de chat**. Todos os números são **hipóteses pedagógicas**.

## 1. WebSocket é um plano de conexões, não o banco do chat

WebSocket resolve comunicação bidirecional sobre uma sessão longa. Ele não resolve durabilidade, ordenação, autorização nem recuperação. O erro clássico é desenhar “cliente ↔ WebSocket server” e considerar o problema encerrado.

### Ciclo de vida de uma conexão

1. O cliente obtém um token HTTPS curto.
2. Abre o socket e envia `auth(device_id, token, last_sync_cursor)`.
3. O gateway valida identidade, versão do protocolo e limites.
4. Registra `device_id → gateway_id/connection_id` com lease.
5. Faz catch-up a partir do cursor antes ou em paralelo ao tráfego ao vivo.
6. Renova o lease por heartbeat.
7. Ao fechar, remove a rota somente se o `connection_id` ainda for o atual.

O último detalhe evita uma race: a conexão A cai, a B reconecta e registra nova rota; o cleanup atrasado de A não pode apagar B. Uma comparação condicional por `connection_id` resolve.

### Sticky session ou registro externo?

- **Sticky session** simplifica reconexões curtas, mas não ajuda outro serviço a localizar um destinatário e fica frágil em deploy/falha.
- **Connection Registry** externo permite roteamento para qualquer gateway, ao custo de uma consulta e de estado efêmero adicional.
- **Roteamento por hash de usuário** reduz lookup, mas rebalanceamentos movem muitas conexões e um usuário com vários dispositivos ainda precisa de uma coleção de rotas.

Uma solução prática combina balanceamento normal, registry com TTL e cache local. O registry não é fonte de verdade de presença; é uma dica de roteamento.

### Capacidade e backpressure

Se 2 milhões de sockets consomem 50 KB cada, são aproximadamente 100 GB antes de headroom. O limite real por nó depende de file descriptors, TLS, runtime, buffers de kernel, tráfego e GC. Em vez de afirmar “50 mil por servidor”, diga que fará benchmark e dimensionará por:

- conexões ativas;
- bytes/s de entrada e saída;
- eventos/s;
- memória por conexão;
- p99 de event-loop;
- fila máxima por socket.

Quando um cliente é lento, o gateway não pode acumular memória sem limite. Ele coalesce sinais substituíveis (`typing`, presença, receipt), envia mensagens em lote e fecha a sessão se a fila exceder o orçamento. O close inclui um código recuperável; o cliente reconecta usando cursor.

**Decisão de entrevista:** WebSocket para sessão online; HTTPS para bootstrap, histórico, upload e fallback. Long polling é alternativa defensável para um MVP, mas não para milhões de usuários frequentemente ativos.

## 2. Presença e heartbeat: verdade aproximada

Presença não deve ser derivada de login/logout explícito. Aplicativos móveis dormem, redes desaparecem sem FIN e processos morrem. O sistema observa leases:

```text
device envia pong → gateway renova lease(device, connection, expires_at)
lease válido       → dispositivo provavelmente online
nenhum lease       → offline ou desconhecido
```

Use intervalos com jitter para evitar que todos os clientes enviem heartbeat no mesmo segundo. Por exemplo, ping a cada 25–35 s e expiração após duas ou três janelas. Um intervalo curto detecta falhas rápido, mas aumenta bateria, rádio móvel e carga.

### Presença por dispositivo e por usuário

Um usuário está “online” se ao menos um dispositivo tem lease válido. “Visto por último” não deve ser atualizado a cada heartbeat no banco durável; agregue transições ou use processamento assíncrono. Para privacidade, a resposta pode ser `online`, `recently`, `hidden` ou `unknown`, não um timestamp preciso.

### Fan-out de presença

Transmitir cada mudança para todos os contatos cria uma tempestade. Alternativas:

- clientes consultam presença apenas para pessoas visíveis;
- gateways assinam um conjunto limitado de usuários;
- mudanças são coalescidas por janela;
- grupos grandes não recebem presença membro a membro.

`typing` é ainda mais efêmero: TTL de poucos segundos, sem persistência e sem retry. Sob pressão, descarte-o antes de mensagens.

**Falha aceitável:** durante partição do registry, dois dispositivos podem aparecer online por alguns segundos. É melhor que bloquear envio de mensagem por uma informação decorativa.

## 3. Ordenação por conversa sem relógio mágico

Relógios de cliente divergem e pacotes tomam caminhos diferentes. Portanto, `created_at` não pode definir a ordem autoritativa.

### Sequência atribuída pelo dono da conversa

Cada conversa é roteada para um dono lógico — shard líder, actor ou partição serial. Ele processa:

```text
authorize membership
dedupe(sender_device_id, client_message_id)
next = last_sequence + 1
persist message(sequence=next) + update last_sequence
emit message.created(sequence=next)
```

O armazenamento pode usar compare-and-set, transação ou log append. A garantia é uma sequência monotônica dentro da conversa. Conversas diferentes avançam em paralelo.

### Buracos e exibição otimista

O remetente pode mostrar uma bolha local “enviando” antes do ACK. Após `message_accepted`, substitui o ID temporário pelo `message_id` e `sequence`. Se o cliente recebe sequência 104 depois da 102, ele não deve assumir que 103 não existe; aguarda brevemente ou busca `after_sequence=102`.

Buracos podem resultar de atraso, autorização removida, mensagem apagada ou evento perdido. O protocolo deve distinguir:

- `missing`: ainda não recebido;
- `tombstone`: sequência existe, conteúdo indisponível;
- `not_visible`: usuário não tem permissão histórica.

### Hotspot em conversa gigante

Particionar por conversa cria um ponto serial, mas isso é coerente com a garantia de ordem. Para grupos enormes:

- reduza garantias ou use canais append-only;
- faça batching no sequenciador;
- separe atribuição de sequência da materialização;
- elimine receipts individuais;
- limite taxa por conversa.

Dividir uma única conversa em vários writers e “ordenar depois” troca latência por complexidade e pode quebrar experiência. Só faça se o requisito justificar.

**Pergunta do entrevistador:** “E se duas regiões aceitarem a mesma conversa?” Resposta: escolha home region/líder por conversa; a região secundária encaminha writes. Em partição, o lado sem quorum não cria uma história concorrente.

## 4. Entrega, confirmação e deduplicação

“Exactly once” é uma propriedade de efeito observável, não de transporte. Socket fecha depois de o servidor persistir, ACK se perde, cliente repete. Filas também repetem após timeout do consumidor.

### Três confirmações diferentes

- **Accepted:** servidor persistiu e assumiu responsabilidade.
- **Delivered:** ao menos um dispositivo destinatário confirmou materialização local.
- **Read:** produto recebeu intenção explícita de leitura até certa sequência.

“Enviado ao gateway” não é “entregue ao dispositivo”. Se o produto quiser essa distinção, pode manter `dispatched` internamente sem expô-lo.

### Idempotência no ingresso

O cliente cria um `client_message_id` estável por tentativa lógica. O servidor mantém:

```text
(sender_device_id, client_message_id) → message_id, sequence, result
```

O check e a criação precisam ser atômicos. Um índice unique ou transação impede que duas réplicas criem mensagens distintas. A chave expira após uma janela maior que o retry máximo e o período offline esperado.

### Idempotência nos consumidores

Delivery workers podem repetir `message.created`. O gateway inclui `message_id`; o cliente mantém um conjunto/janela de IDs já aplicados e, principalmente, materializa por `(conversation_id, sequence)`. Receipts são monotônicos:

```text
delivered_up_to = max(old, received)
read_up_to      = max(old, received)
```

Isso torna repetição e reordenação inofensivas. Um receipt menor nunca move estado para trás.

### Outbox e reconciliação

Transação:

```text
BEGIN
  INSERT message
  INSERT outbox(message.created)
COMMIT
```

Um relay publica a outbox e marca progresso. Se publicar duas vezes, consumidores deduplicam. Se o relay parar, a idade da outbox cresce e alerta. Um reconciliador compara `messages` e eventos publicados.

Essa evolução ecoa a **aula local**: processamento assíncrono, retry e job periódico para itens atrasados. A semântica de chat é complemento.

## 5. Offline e sincronização entre dispositivos

Não crie uma fila infinita por usuário offline. O histórico durável já é a fila. O dispositivo mantém um cursor de sincronização e busca mudanças desde o último ponto confirmado.

### Dois cursores úteis

- **Cursor por conversa:** ótimo para paginação e detecção de buraco.
- **Cursor global por dispositivo:** ótimo para descobrir quais conversas mudaram desde a última sessão.

Um change log por usuário pode conter referências compactas:

```text
user 42, cursor 991 → conversation 73 advanced to sequence 18421
user 42, cursor 992 → membership changed in conversation 12
```

Na reconexão:

1. autenticar e registrar nova conexão;
2. chamar sync desde o cursor global;
3. para cada conversa alterada, buscar ranges ausentes;
4. aplicar de forma idempotente;
5. enviar novo cursor confirmado;
6. iniciar stream ao vivo sem janela perdida.

A fronteira entre catch-up e live exige cuidado. Uma opção é capturar um watermark no servidor, sincronizar até ele e depois consumir eventos posteriores. Outra é iniciar o stream, bufferizar eventos e drenar após o snapshot.

### Multi-device

Cada dispositivo possui cursor e estado de entrega próprios. O estado de leitura de produto pode ser por usuário:

```text
user_read_up_to = max(phone, desktop, tablet)
```

Depois, o servidor propaga esse high-water mark aos outros dispositivos. Se o produto precisa de “lido neste aparelho”, mantenha também o detalhe por dispositivo — com custo maior.

### Push móvel

Push é um wake-up hint: “há atividade na conversa 73”. Ele pode atrasar, duplicar ou ser bloqueado. O app sempre sincroniza com o servidor; nunca confia no payload como histórico autoritativo. Sob criptografia ponta a ponta, o preview pode ser omitido.

**Degradação:** se o serviço de sync estiver sobrecarregado após incidente, limite lotes, priorize mensagens recentes e entregue um aviso de “sincronizando histórico”; não aceite perder mensagens silenciosamente.

## 6. Fan-out, grupos e hotspots

O custo não é apenas mensagens/s de entrada:

```text
fan_out_cost ≈ mensagens × membros elegíveis × dispositivos online
```

Uma mensagem para 100 mil membros não pode gerar 300 mil writes síncronos antes do ACK.

### Fan-out on write

Após persistir, o worker resolve membros e cria tarefas por destinatário/dispositivo. Vantagens: entrega online rápida, inbox pronta e leitura barata. Custos: amplificação, filas enormes e trabalho desperdiçado para offline.

### Fan-out on read

A mensagem fica somente no log da conversa. O usuário consulta as conversas de que participa e busca novos ranges. Vantagens: escrita constante. Custos: merge/read mais complexo, maior latência e cache necessário.

### Híbrido

- 1:1 e grupos até um limiar: fan-out on write;
- grupos grandes: notificar apenas gateways com membros online e manter histórico compartilhado;
- canais gigantes: fan-out on read, sem receipts individuais;
- usuários celebridade: limites e filas isoladas.

O limiar é operacional, baseado em custo observado, não um número mágico. Pode considerar membros, ativos recentes e dispositivos online.

### Membership consistente

O evento deve carregar `membership_version` ou o worker consultar uma visão coerente. Perguntas difíceis:

- Quem saiu antes do envio recebe?
- Quem entrou depois vê histórico anterior?
- Uma remoção urgente deve invalidar cache?

Defina política. Exemplo: autorização de envio usa versão atual; visibilidade histórica usa `joined_sequence` e `left_sequence`. Assim, consultas são auditáveis.

### Hot partition

Detecte taxa por `conversation_id`, lag e tamanho de batch. Mitigações: rate limit, batching, cache de membership, workers dedicados e produto degradado (sem typing/receipts). Não migre um shard quente de modo incessante; cada migração pode piorar cache e ordem.

## 7. Anexos e mídia

O serviço de chat controla metadados; object storage controla bytes.

### Fluxo seguro

1. Cliente pede `attachment:init` com tamanho e MIME declarados.
2. Serviço autoriza membership, aplica quota e cria registro `pending`.
3. Retorna URL assinada para uma chave temporária.
4. Cliente faz multipart upload diretamente.
5. Storage/evento dispara validação de tamanho, hash, MIME real e malware.
6. Serviço move estado para `ready` e gera variantes.
7. Mensagem referencia o attachment.

Se uma mensagem tentar usar attachment de outro usuário/conversa, rejeite. URLs de download são curtas e reautorizadas; a chave interna nunca é pública.

### Estados

```text
pending → uploaded → scanning → ready
                    ↘ rejected
pending ──TTL──────→ expired
ready ──delete─────→ tombstoned → purged
```

Um garbage collector remove uploads nunca concluídos e objetos sem referência. O pipeline de exclusão precisa alcançar thumbnails, transcodes, CDN e backups conforme política.

### Desempenho

CDN atende downloads; thumbnails evitam baixar vídeo para montar lista. A mensagem pode aparecer com uma prévia neutra enquanto a mídia processa. Texto não deve esperar transcode. Limites de tamanho e concorrência protegem egress e scan.

### Trade-off com E2EE

Se mídia é criptografada no cliente, o servidor não consegue fazer malware scan ou thumbnails sem protocolos adicionais. A entrevista ganha qualidade quando você conecta a decisão de segurança às perdas de produto e operação.

## 8. Consistência, disponibilidade e degradação sob falha

Classifique dados por criticidade:

| Fluxo | Preferência | Comportamento em falha |
|---|---|---|
| criar mensagem | consistência + durabilidade | rejeitar no lado sem quorum |
| ler histórico | disponibilidade com staleness sinalizada | servir réplica/cópia recente |
| receipts | disponibilidade eventual | acumular e reconciliar |
| presença/typing | disponibilidade best effort | descartar ou mostrar desconhecido |
| membership/remoção | consistência e segurança | fail closed para novo acesso |
| push | disponibilidade sem garantia | retry limitado; sync corrige |

### Tempestade de reconexão

Após queda regional, milhões de clientes voltam. Mitigações:

- exponential backoff com jitter no cliente;
- admission control no handshake;
- tokens pré-validados/cacheados;
- sync em lotes;
- prioridade para texto recente;
- shedding de presença, typing e receipts;
- limites por conta/IP para evitar amplificação maliciosa.

### Região indisponível

Conversas têm home region e réplica. Leituras podem sair da réplica. Writes exigem promoção coordenada para não criar dois líderes. O RTO define quanto se espera antes do failover; o RPO deve ser zero para mensagens já confirmadas se o ACK exige réplica/quorum.

### Storage lento

Não responda `accepted` antes da durabilidade. Aumentar fila na memória só adia a falha. Aplique backpressure, limite admissão e retorne erro retryable com a mesma chave idempotente. Mensagens em composição permanecem no cliente.

### Bus indisponível

Com outbox, o send pode continuar até um limite de backlog: mensagens ficam aceitas, mas entrega atrasa. Exponha estado “enviado, aguardando entrega”. Se a outbox ameaça o banco, reduza admissão. A escolha deve estar ligada a um orçamento mensurável.

### Registry indisponível

Gateways mantêm sockets existentes e cache local. Novas rotas podem ser publicadas com atraso; delivery cai no sync. Presença vira `unknown`. Isso é degradação funcional controlada.

## 9. Como conduzir o deep dive na entrevista

Escolha um eixo e declare a invariável:

- **Conexões:** “qualquer gateway pode assumir uma reconexão sem perder histórico.”
- **Ordem:** “cada conversa tem sequência monotônica; não prometo ordem global.”
- **Entrega:** “retry não produz efeito duplicado.”
- **Offline:** “o servidor converge qualquer dispositivo a partir de cursor.”
- **Grupos:** “custo de fan-out é limitado e grupos gigantes mudam de estratégia.”
- **Falha:** “mensagem confirmada é durável; sinais efêmeros podem degradar.”

Depois siga quatro perguntas:

1. Qual estado existe e onde?
2. Quem é o dono da decisão?
3. Qual operação precisa ser atômica?
4. Como o sistema se recupera quando o ACK ou o componente falha?

### Sinais de senioridade

- definir semântica antes de nomear tecnologia;
- separar usuário, dispositivo, conexão e conversa;
- quantificar amplificação de fan-out;
- admitir que presença é aproximada;
- usar monotonicidade e idempotência para simplificar retries;
- desenhar degradação explícita;
- conectar segurança a autorização de membership e mídia;
- incluir backpressure, reconciliação e deploy;
- dizer o que não faria e por quê.

### Perguntas rápidas para praticar

1. Como impedir que cleanup de socket antigo apague uma conexão nova?
2. Como evitar a janela entre sync e eventos ao vivo?
3. Quanto tempo manter a chave de idempotência?
4. Quem atribui sequência após failover regional?
5. Quando trocar fan-out on write por on read?
6. Como representar leitura sem uma linha por mensagem e usuário?
7. O que é descartado primeiro em overload?
8. Como remover mídia já distribuída por CDN?

Uma resposta boa não precisa resolver tudo. Precisa manter invariantes coerentes, reconhecer custos e mostrar um caminho de recuperação.
