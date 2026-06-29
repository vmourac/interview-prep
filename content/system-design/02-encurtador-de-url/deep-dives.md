# Encurtador de URL — deep dives de decisão

Este documento não repete o fluxo completo do guia principal. Ele oferece módulos de aprofundamento para quando o entrevistador escolhe um ponto e pergunta “como isso funciona sob concorrência, falha ou escala?”. A aula local já apresenta limpeza periódica, replicação do redirect e autenticação/analytics/bots/fraude/abuso como decisões de escopo. As estratégias operacionais detalhadas abaixo são complementos.

## 1. IDs, colisões e o que Base62 realmente resolve

Há três problemas diferentes que candidatos frequentemente misturam:

1. **gerar um identificador em um espaço grande;**
2. **garantir que esse identificador ainda não está reservado;**
3. **representá-lo de forma curta e segura em URL.**

Base62 resolve apenas o terceiro. Se a entrada é única, como um contador global, a saída Base62 também será única. Se a entrada é aleatória ou um hash truncado, Base62 preserva as colisões que já existiam.

Alfabeto típico:

```text
0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
```

Uma decisão que parece cosmética — diferenciar maiúsculas de minúsculas — afeta operação. Proxies, ferramentas, digitação humana e políticas de normalização precisam preservar case. Se o produto exige aliases fáceis de falar, Base36 ou um alfabeto sem caracteres ambíguos pode ser melhor, ao custo de códigos maiores.

### Capacidade versus probabilidade

Para comprimento `k`, o espaço é `N = 62ᵏ`. Porém, IDs aleatórios começam a colidir muito antes de preencher `N`, por causa do efeito aniversário. Uma aproximação para a probabilidade de ao menos uma colisão após `n` amostras é:

```text
p ≈ 1 - exp(-(n × (n - 1)) / (2N))
```

Isso não significa que geração aleatória é inviável. Significa que o sistema deve:

- usar espaço com folga;
- criar o código com restrição única;
- tentar novamente em conflito;
- medir collision rate;
- limitar retries e falhar de modo controlado.

Nunca use “consultar antes de inserir” como garantia. Duas instâncias podem observar ausência e inserir simultaneamente. A decisão final deve ocorrer no storage por compare-and-set, conditional put ou índice único.

## 2. Contador distribuído versus aleatório

### Contador + Base62

Fluxo lógico:

```text
next_id = 12.345.678
base62(next_id) = "PNfq"
```

Vantagens:

- unicidade determinística;
- códigos mínimos para o maior ID atual;
- sem retries por colisão;
- fácil estimar capacidade.

Desvantagens:

- coordenação para alocar IDs;
- namespace enumerável;
- exposição aproximada do volume;
- possibilidade de hotspot se a chave ordenada for a chave física;
- recuperação do allocator precisa preservar monotonicidade.

### Alocação de blocos

A aula local propõe que um serviço central entregue, por exemplo, 1.000 contadores por vez:

```text
Creator A recebe [1.000.000, 1.000.999]
Creator B recebe [1.001.000, 1.001.999]
```

O allocator persiste o high-water mark antes de confirmar a concessão. A instância consome localmente. Se A cai após usar só 20 IDs, os 980 restantes podem ser abandonados. Isso cria buracos, não colisões.

O tamanho do bloco é um trade-off:

- bloco pequeno reduz desperdício, mas aumenta chamadas e dependência do allocator;
- bloco grande aumenta autonomia durante falha, mas perde mais IDs em crash;
- IDs são baratos, então disponibilidade geralmente vence continuidade.

Uma recuperação segura nunca “devolve” automaticamente a faixa após timeout. A instância antiga pode voltar e continuar usando-a. Para reaproveitar blocos seria necessário fencing token ou lease com garantias rigorosas, complexidade raramente justificável.

### Alta disponibilidade do allocator

Opções:

- sequência transacional em banco;
- consenso via Raft/etcd/ZooKeeper;
- serviço com líder e log replicado;
- ranges pré-alocados por região.

O caminho normal de criação não deve depender de uma chamada por ID. Quando o allocator falha:

- instâncias com bloco continuam;
- instâncias sem bloco recusam ou enfileiram criação;
- redirect permanece isolado e saudável.

Essa assimetria é uma excelente resposta de entrevista: preserve o caminho mais crítico e degrade o menos crítico.

### IDs aleatórios

Cada criador sorteia bytes criptograficamente seguros, codifica em Base62 e tenta inserir. Vantagens:

- geração local;
- sem coordenador;
- distribuição uniforme;
- enumeração mais difícil.

Custos:

- códigos normalmente mais longos;
- colisões probabilísticas;
- retries e métricas;
- entropia precisa ser confiável.

Para link público comum, “difícil de adivinhar” não significa “privado”. Para conteúdo sensível, acrescente autorização ou token com entropia e política explícitas.

### Hash da URL

Hashing da URL parece conveniente, mas introduz semântica:

- a mesma URL canônica gera o mesmo código, se não houver salt;
- parâmetros em ordem diferente podem gerar códigos diferentes;
- normalização pode alterar significado;
- truncamento colide;
- custom alias continua sendo outro namespace.

Escolha hash apenas se deduplicar destinos for requisito. Caso contrário, a criação de múltiplos links para a mesma URL — assumida na aula — favorece contador ou aleatório.

### Opção híbrida

Um complemento útil é gerar contador único e aplicar uma permutação reversível antes de Base62. Isso preserva unicidade e reduz sequencialidade aparente. O custo é gestão de chave, versionamento e migração. Não venda isso como criptografia de dados; é obfuscação do namespace.

## 3. Cache do caminho de redirect

O cache não é apenas “colocar Redis”. A pergunta de entrevista é: qual dado, qual política e qual comportamento quando algo falha?

### Valor em cache

```text
code -> {
  destination,
  expires_at,
  status,
  version
}
```

Guardar expiração e estado permite uma verificação defensiva no processo. `version` ajuda a rejeitar mensagens antigas de invalidação ou preenchimentos concorrentes.

### Cache-aside

```text
GET /abc
  ├─ hit  -> valida -> 302
  └─ miss -> banco -> valida -> SET com TTL -> 302
```

O banco continua source of truth. Se o cache inteiro for perdido, o serviço continua correto, mas pode sobrecarregar o storage. Portanto, recuperação do cache também é um problema de capacidade:

- limitar concorrência de misses;
- aquecer links mais populares;
- aumentar capacidade do banco para um hit ratio degradado;
- usar circuit breaker e load shedding.

### Stampede

Quando um link viral expira no cache, milhares de requests podem consultar o banco ao mesmo tempo. Mitigações:

- **single-flight/request coalescing:** uma busca por chave; as demais aguardam;
- **TTL jitter:** evitar expirações sincronizadas;
- **soft TTL + hard TTL:** um request atualiza enquanto outros usam valor ainda seguro;
- **refresh ahead:** renovar itens quentes antes do vencimento.

Soft TTL jamais autoriza servir além de `expires_at` ou de um bloqueio de segurança.

### Negative caching

Scanners podem consultar milhões de códigos inexistentes. Cachear `NOT_FOUND` por poucos segundos protege o banco. Trade-off: logo após criação, um negative cache antigo pode esconder o novo link.

Mitigações:

- invalidar o código após commit;
- usar TTL negativo muito curto;
- namespace ou versão por região;
- bypass para resposta de criação/read-after-write.

### Hot key

Um único link viral pode saturar um nó de cache ou uma partição. Soluções possíveis:

- replicação local por processo;
- near-cache L1 com TTL curto;
- replicar a chave em múltiplas partições;
- CDN para links realmente quentes;
- proteção contra abuso se o tráfego não for legítimo.

O trade-off é invalidação mais difícil. O entrevistador pode perguntar: “Você prefere uma chave quente simples ou várias cópias inconsistentes?”. Responda em função da frequência de atualização: mapeamentos são quase imutáveis, então replicação agressiva é atraente.

## 4. TTL, expiração, invalidação e limpeza

**Aula local:** expiração no request e limpeza periódica ou arquivamento. **Complemento:** os três relógios, as opções de implementação e o protocolo detalhado de invalidação.

Expiração possui três relógios:

1. **semântica de produto:** após `expires_at`, o link não deve redirecionar;
2. **retenção em cache:** a cópia não deve sobreviver à validade;
3. **remoção física:** o registro pode ser apagado ou arquivado depois.

Misturar esses relógios causa bugs. O job de limpeza pode atrasar horas sem violar produto, desde que o redirect confira `expires_at`.

### TTL efetivo

```text
remaining = expires_at - now
cache_ttl = min(configured_ttl, remaining)
```

Se `remaining <= 0`, não popular o cache com destino ativo. Pode-se gravar tombstone curto para proteger o banco.

### Expiração e relógio

Use timestamps UTC e sincronização de relógio. Em sistemas multirregionais, pequenos skews podem produzir respostas diferentes perto do limite. Para links comuns isso pode ser aceitável; para requisito estrito, aplique margem conservadora ou centralize a decisão.

### Invalidação por mudança

Embora edição e deleção estejam fora do escopo principal da aula, segurança exige bloqueio. Ordem recomendada:

1. persistir novo estado/version;
2. publicar evento de invalidação;
3. remover cache e CDN;
4. manter denylist rápida como defesa;
5. medir propagação.

“Delete cache antes de commit” abre janela em que outro request recarrega o valor antigo. “Commit e depois delete” ainda tem janela, mas versionamento e evento repetível tornam o processo recuperável.

### Limpeza

Evite scan completo diário em tabela enorme. Opções:

- índice por `expires_at` e batches;
- partições temporais descartáveis;
- fila/delay queue de expiração;
- TTL nativo do banco;
- compactação assíncrona.

Cada opção tem falha:

- índice de expiração aumenta custo de escrita;
- delay queue precisa tolerar perda e redelivery;
- TTL nativo pode apagar de forma não imediata;
- partição temporal complica links sem expiração ou com prazos variados.

O job deve ser idempotente, paginado, limitado e observável. Recuperação significa retomar do cursor sem bloquear tráfego online.

### Reutilização de código

Não recicle imediatamente. Links antigos ficam em emails, caches, QR codes e documentos. Reutilizar pode direcionar tráfego histórico a um novo destino, inclusive com impacto de segurança. Uma política segura mantém tombstone por longo período ou torna códigos permanentes no namespace.

## 5. Particionamento e replicação

**Aula local:** replicar o serviço de redirect para escalar a leitura. **Complemento:** particionamento, réplicas de dados, topologias síncrona/assíncrona, lag e read-after-write.

### Quando particionar

A aula corretamente observa que 700 GB lógicos não obrigam sharding. Particione quando um único nó deixa de atender:

- throughput de leitura após cache;
- throughput de escrita;
- tamanho e eficiência do índice;
- janela de backup/restore;
- crescimento previsto;
- requisito regional.

### Chave de partição

Hash do código oferece distribuição uniforme:

```text
partition_key = hash(code)
```

Se códigos vêm de contador e o banco particiona por range do valor bruto, inserts podem se concentrar no shard mais novo. Fazer hash evita esse hotspot, mas perde scans ordenados — irrelevantes para lookup por código.

Aliases customizados podem ter distribuição adversarial. Hash também os uniformiza.

### Rebalanceamento

`hash(code) mod N` é simples, mas mover de N para N+1 remapeia quase tudo. Consistent hashing ou rendezvous hashing reduz movimentação. Bancos gerenciados podem abstrair isso, mas o candidato ainda deve discutir:

- mapa de partições versionado;
- dual read durante migração;
- cópia e verificação;
- corte;
- rollback.

### Réplicas

Réplicas de leitura escalam misses do cache e oferecem failover. Lag cria uma falha visível: o POST confirma, mas o GET imediato em réplica retorna `404`.

Estratégias:

- write-through no cache após commit;
- sticky/read-primary por uma janela;
- token de sessão ou versão mínima;
- replicação síncrona na região, assíncrona entre regiões;
- aceitar atraso explicitamente.

A decisão depende do contrato. A aula argumenta que entre criar e distribuir costuma haver tempo, então consistência eventual pode ser suficiente. Para testes automatizados ou API programática, read-after-write pode ser esperado; confirme.

### Multirregião

Redirect é bom candidato a active-active com dados replicados e caches regionais. Criação é mais difícil:

- allocator global adiciona latência;
- ranges por região preservam unicidade;
- IDs aleatórios evitam coordenação;
- custom alias global ainda exige arbitragem.

Uma saída prática é reservar prefixos/ranges por região para IDs automáticos e usar um namespace global consistente para aliases customizados. Isso mostra que requisitos diferentes podem ter mecanismos diferentes.

## 6. Abuso, links maliciosos e enumeração

**Aula local:** autenticação, analytics e bots/fraude/abuso entram na negociação de escopo. **Complemento:** o modelo de ameaça e os controles detalhados desta seção.

### Modelo de ameaça mínimo

- spammer cria milhares de links;
- phishing oculta domínio parecido;
- malware usa redirects em campanha;
- scanner enumera códigos sequenciais;
- atacante força cache misses;
- destino muda de reputação depois da criação;
- criador usa open redirect para contornar filtros.

### Defesa em camadas

**Criação síncrona:**

- validação de esquema e tamanho;
- canonicalização cuidadosa;
- quotas e rate limit;
- reputação rápida;
- recusa de domínios conhecidos;
- auditoria da identidade quando disponível.

**Análise assíncrona:**

- sandbox/crawler isolado;
- feeds de reputação;
- classificação de comportamento;
- reavaliação periódica;
- fila de revisão.

**Redirect:**

- estado de bloqueio barato de consultar;
- interstitial;
- rate limit contra enumeração;
- uniformidade de erro;
- invalidação emergencial.

Nunca faça fetch arbitrário do destino dentro da rede interna sem proteção de SSRF. Bloqueie endereços privados, metadata endpoints, redirects encadeados perigosos e resolução DNS mutável.

### Enumeração

Com contador, o atacante pode caminhar por códigos próximos. Impactos:

- descoberta de links não publicados;
- coleta de destinos;
- estimativa de volume;
- pressão em cache e banco.

Contramedidas:

- ID aleatório ou permutado;
- códigos mais longos;
- rate limit adaptativo;
- detecção de sequência;
- resposta constante;
- não tratar link público como segredo.

Se o entrevistador pedir “links privados”, mude o contrato: código deve ter entropia suficiente, e o serviço pode exigir autenticação. Obfuscação não é controle de acesso.

### Bloqueio rápido versus falso positivo

Bloquear agressivamente reduz dano, mas pode derrubar links legítimos. Um desenho operacional inclui estados:

```text
ACTIVE -> SUSPECTED -> BLOCKED
        -> REVIEWED  -> ACTIVE
```

O redirect pode mostrar aviso em `SUSPECTED` e negar em `BLOCKED`. A transição precisa de auditoria e rollback. Esse é um trade-off de produto e segurança, não apenas técnico.

## 7. Assimetria entre criação e redirect

Essa é a propriedade mais útil do problema.

| Dimensão | Criação | Redirect |
|---|---|---|
| Volume | Baixo | Muito alto |
| Operação | Write + validação | Read por chave |
| Latência | Centenas de ms podem ser aceitáveis | Dezenas de ms são perceptíveis |
| Consistência | Unicidade forte | Eventual pode bastar |
| Falha segura | Recusar sem confirmar | Servir conhecido válido quando possível |
| Dependências | allocator, política, banco primário | cache, réplica, banco |
| Escala | horizontal moderada | horizontal agressiva/global |

### Isolamento de recursos

Separe pools de conexão, filas, autoscaling e budgets. Uma campanha de criação abusiva não deve esgotar o banco a ponto de interromper redirects. Da mesma forma, um link viral não deve bloquear reservas de alias.

### SLOs distintos

Exemplo pedagógico:

- redirect: 99,99% e p99 < 100 ms;
- criação: 99,9% e p99 < 500 ms.

Não escolha números sem confirmação. O valor da discussão é mostrar que caminhos diferentes merecem objetivos diferentes.

### Load shedding

Sob pressão:

- rejeitar criação anônima antes de afetar redirect;
- desabilitar features secundárias;
- limitar misses concorrentes;
- servir cache válido;
- preservar bloqueios de segurança;
- retornar erro explícito em vez de timeout longo.

Essa priorização é uma decisão de produto. Para um encurtador, links já distribuídos normalmente têm maior urgência que novos links.

## 8. Matriz de falhas e recuperação

| Falha | Efeito | Resposta imediata | Recuperação |
|---|---|---|---|
| Cache indisponível | Mais misses e latência | bypass limitado, proteger banco | recriar cluster e aquecer |
| Banco de leitura lento | Misses falham | circuit breaker, cache válido | failover de réplica |
| Primário indisponível | Criação não durável | pausar criação | promover réplica e reconciliar |
| Allocator indisponível | Instâncias sem faixa param | consumir blocos locais | eleger líder, preservar high-water mark |
| Replication lag | GET imediato dá falso `404` | cache pós-write/read-primary | normalizar réplica e monitorar |
| Evento de invalidação perdido | Link bloqueado ainda em cache | denylist no redirect | replay por versão/outbox |
| Cleanup atrasado | Espaço cresce | sem impacto semântico | retomar batches |
| Hot key | Nó saturado | L1/CDN/replicação | redistribuir e revisar capacidade |
| Feed de reputação fora | Risco na criação | fail-open ou fail-closed acordado | fila para rechecagem |

Uma boa resposta evita retries cegos. Retry pode amplificar falha. Use timeout, orçamento de tentativas, backoff e idempotência.

## 9. Perguntas de aprofundamento para praticar

### “Seu bloco de IDs foi perdido. Você reutiliza?”

Não. Aceito buracos. Reutilização sem fencing pode colidir com uma instância antiga que retornou.

### “Como garante que um alias customizado só tem um vencedor?”

Operação condicional atômica no storage. O perdedor recebe `409`. Cache não participa da decisão.

### “Seu cache hit ratio caiu de 95% para 60%. O que muda?”

Calculo a multiplicação de carga no banco, verifico churn/TTL/hot keys, limito misses e posso aquecer. Hit ratio é métrica de capacidade, não vaidade.

### “Você serviria valor stale quando o banco está fora?”

Somente se o valor estiver antes da expiração e não houver bloqueio conhecido. Defino hard TTL. Para segurança, denylist tem precedência.

### “Como migraria de contador para aleatório?”

O código já é uma chave opaca para consumidores. Gero novos links pela estratégia nova, mantenho lookup único e registro `id_strategy/version` apenas se necessário para operação. Não reescrevo códigos existentes.

### “Como detecta colisão sem duas viagens ao banco?”

Tento conditional insert diretamente. Em conflito, gero outro candidato. A consulta prévia é desnecessária e sujeita a corrida.

### “Qual componente você removeria se a escala fosse 100 redirects/s?”

Começaria com serviço único, índice e banco replicado conforme SLO. Cache distribuído, allocator separado e sharding só entram quando números ou disponibilidade justificarem.

## 10. Fechamento do deep dive

O design mais forte não é o que contém mais caixas. É o que mantém invariantes claros:

- um código tem no máximo um dono;
- redirect nunca ultrapassa expiração conhecida;
- criação confirmada é durável;
- cache pode desaparecer sem perder verdade;
- falha da criação não derruba redirect;
- bloqueio de segurança se propaga e é auditável;
- cada escala adicional paga um problema demonstrado.

Quando o entrevistador mudar uma premissa, volte à decisão afetada. Mais privacidade favorece aleatório; mais simplicidade favorece contador; edição frequente reduz valor de CDN; consistência imediata aumenta coordenação; tráfego pequeno remove componentes. Essa capacidade de ajustar trade-offs é o objetivo real do exercício.
