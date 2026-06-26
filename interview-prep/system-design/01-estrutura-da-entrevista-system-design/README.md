# Estrutura da entrevista de System Design

Este guia ensina a conduzir uma entrevista de System Design como uma conversa técnica com direção, e não como uma corrida para desenhar muitas caixas. O objetivo é construir, em ordem, um contrato de requisitos, uma arquitetura mínima que o cumpra e uma evolução justificada por escala, confiabilidade e operação.

> **Legenda de rastreabilidade**
>
> - **Aula local:** ideia explicitamente presente na aula-fonte, ainda que reescrita e organizada.
> - **Complemento:** aprofundamento consolidado para transformar a aula em um roteiro praticável.
> - **Hipótese pedagógica:** número ou premissa inventada apenas para exercitar uma decisão; deve ser confirmada com o entrevistador em uma entrevista real.

## 1. Enquadramento: o que está sendo avaliado

**Aula local.** Uma entrevista de System Design normalmente não pede código. Ela apresenta um problema propositalmente aberto — “desenhe uma rede social”, “desenhe um chat”, “desenhe um encurtador de URLs” — e observa como o candidato reduz a ambiguidade, seleciona componentes lógicos, conecta fluxos e justifica decisões. O diagrama final não é o único produto. O processo de raciocínio, a comunicação e a capacidade de reagir à conversa são sinais centrais.

O candidato forte atua como condutor colaborativo:

1. transforma uma frase vaga em um problema delimitado;
2. negocia dois ou três requisitos funcionais relevantes;
3. explicita o que fica fora do escopo;
4. identifica as qualidades do sistema que realmente importam;
5. desenha o caminho feliz mínimo para cada requisito;
6. usa números apenas quando eles mudam uma decisão;
7. aprofunda gargalos selecionados;
8. reconhece perdas, falhas e melhorias pendentes.

**Complemento.** Pense na entrevista como uma sequência de decisões verificáveis. Para cada caixa ou seta, o entrevistador deve conseguir responder: “qual requisito exige isto?”, “que hipótese sustenta isto?” e “qual custo foi aceito?”. Se uma decisão não se conecta a requisito, restrição ou evidência, provavelmente está prematura.

## 2. Perguntas de clarificação

Comece pelo comportamento do produto, não pela tecnologia. Uma boa abertura é:

> “Antes de desenhar, quero alinhar quem usa o sistema, quais jornadas são essenciais e quais qualidades devemos priorizar. Depois eu proponho um escopo que caiba no tempo.”

Perguntas úteis, em ordem:

- Quem são os clientes: pessoas, sistemas internos, parceiros ou todos?
- Qual é a jornada principal que precisamos completar de ponta a ponta?
- Quais operações são leitura e quais são escrita?
- O conteúdo é texto, mídia ou ambos?
- Há restrições geográficas, regulatórias ou de privacidade?
- Qual ordem de grandeza de usuários, tráfego e dados?
- O tráfego é uniforme ou tem picos e hotspots?
- Qual latência é aceitável para cada operação?
- Podemos retornar dados temporariamente desatualizados?
- O que deve acontecer durante uma partição ou indisponibilidade parcial?
- Há requisitos explícitos de retenção, auditoria, segurança ou combate a abuso?

**Aula local.** A comunicação é contínua. Não se trata de disparar uma lista e esperar respostas completas, mas de formular perguntas, resumir o que foi entendido e obter confirmação.

**Complemento.** Evite perguntas sem consequência, como “qual é a escala?” sem explicar por que importa. Prefira: “Se estivermos falando de dezenas de milhares de requisições por segundo, vou considerar replicação e particionamento; qual ordem de grandeza devemos assumir?” Isso demonstra intenção arquitetural.

## 3. Requisitos funcionais: o contrato mínimo

**Aula local.** Dois ou três requisitos funcionais bem escolhidos costumam ser mais úteis que uma lista extensa. Eles formam o contrato mínimo: a arquitetura de alto nível deve mostrar um fluxo completo para cada requisito acordado.

No exemplo pedagógico de uma rede social textual:

- publicar uma postagem de texto;
- ler um feed com postagens de pessoas seguidas;
- opcionalmente, seguir ou deixar de seguir alguém.

Fora do escopo:

- mensagens diretas;
- upload e processamento de vídeo;
- publicidade;
- recomendação avançada;
- moderação humana completa.

Feche o acordo verbalmente:

> “Então vou cobrir publicação textual e leitura do feed. Vou modelar a relação de seguidores somente no nível necessário para o feed. Vídeo, chat e anúncios ficam fora. Está de acordo?”

Cada requisito deve virar um fluxo testável no quadro:

| Requisito | Entrada | Saída observável | Fluxo a demonstrar |
|---|---|---|---|
| Publicar | autor + texto | postagem aceita com identificador | cliente → API → serviço de escrita → dados |
| Ler feed | usuário + cursor | página ordenada de postagens | cliente → API → serviço de leitura → cache/dados |
| Seguir | seguidor + seguido | relação atualizada | cliente → API → serviço social → dados |

## 4. Requisitos não funcionais: critérios de decisão

**Aula local.** Requisitos não funcionais descrevem como o sistema entrega as funcionalidades: latência, escala, disponibilidade, consistência, tolerância a partições, resiliência e uso eficiente de recursos. Eles orientam a evolução do design inicial.

Pergunte e registre prioridades, de preferência com diferenças por operação:

- **Latência:** leitura do feed precisa ser mais rápida que publicação?
- **Disponibilidade:** uma leitura degradada é preferível a uma falha total?
- **Consistência:** uma postagem precisa aparecer imediatamente para o próprio autor? E para todos os seguidores?
- **Durabilidade:** depois de confirmar a publicação, podemos perdê-la?
- **Escala:** leituras superam escritas em qual ordem de grandeza?
- **Recuperação:** qual perda de dados e tempo de indisponibilidade são toleráveis?
- **Eficiência:** o custo de pré-computar feeds é aceitável?

**Aula local.** CAP é apresentado como um framework de trade-offs sob partição: em sistemas distribuídos, certas operações priorizam consistência, enquanto outras podem favorecer disponibilidade com consistência eventual. Operações financeiras tendem a exigir garantias mais fortes; contagens sociais podem aceitar atraso.

**Complemento.** Não use CAP como slogan para classificar o sistema inteiro. Discuta a garantia por fluxo e durante falhas concretas. Um produto pode exigir consistência forte para autorização e consistência eventual para contadores.

## 5. Estimativas que alteram decisões

**Aula local.** Cálculos de guardanapo não precisam ocorrer automaticamente no início. Faça-os quando houver uma pergunta arquitetural: uma instância basta? Precisamos replicar? Os dados cabem em um nó? A rede suporta o fan-out? O armazenamento cresce rápido demais?

**Hipótese pedagógica — não é dado da aula nem do Uber.** Suponha:

- 20 milhões de usuários ativos por dia;
- 10% publicam 2 vezes ao dia: 4 milhões de postagens/dia;
- cada postagem persistida ocupa, com metadados e índices, cerca de 1 KiB;
- cada usuário abre o feed 20 vezes ao dia: 400 milhões de leituras/dia;
- pico igual a 8 vezes a média.

Derivações aproximadas:

- escrita média: `4.000.000 / 86.400 ≈ 46/s`; pico ≈ `370/s`;
- leitura média: `400.000.000 / 86.400 ≈ 4.630/s`; pico ≈ `37.000/s`;
- novos dados primários: cerca de `4 GiB/dia`, antes de réplicas, índices e logs.

Consequências:

- a assimetria leitura/escrita justifica escalar o caminho de leitura separadamente;
- dezenas de milhares de leituras por segundo motivam cache e múltiplas instâncias;
- o volume anual, multiplicado por réplicas e índices, exige política de retenção e talvez particionamento;
- se o fan-out por postagem for alto, a distribuição assíncrona precisa de limites e tratamento de celebridades.

Frase útil:

> “Não preciso de precisão contábil; quero verificar se cruzamos um limiar que muda a arquitetura. Com esse pico, uma única instância deixa de ser uma hipótese segura, então adiciono distribuição e explico a estratégia.”

## 6. Entidades

**Complemento aplicado ao exemplo.** Modele apenas o necessário para sustentar os fluxos:

- `User`: identidade, estado e preferências mínimas;
- `Post`: autor, conteúdo, instante de criação e estado;
- `Follow`: relação dirigida entre seguidor e seguido;
- `FeedEntry`: referência materializada opcional entre usuário e postagem;
- `Cursor`: posição estável para paginação;
- `IdempotencyRecord`: resultado de uma tentativa de escrita repetível, se a API exigir.

**Aula local.** O modelo de dados pode evoluir durante a conversa. Comprometer-se cedo demais com um produto específico ou esquema detalhado pode desviar o foco antes de o sistema mínimo existir.

## 7. APIs ou interfaces

Interfaces dão precisão aos limites sem transformar a entrevista em implementação:

```text
POST /v1/posts
Idempotency-Key: <token>
{ author_id, text }
→ 201 { post_id, created_at }

GET /v1/users/{user_id}/feed?cursor=<cursor>&limit=50
→ 200 { items: [...], next_cursor }

PUT /v1/users/{follower_id}/following/{followed_id}
→ 204
```

Discuta:

- autenticação e autorização;
- idempotência em escrita;
- paginação por cursor em coleções mutáveis;
- limites de tamanho;
- códigos para sobrecarga, indisponibilidade e conflito;
- versionamento e compatibilidade.

**Complemento.** O valor da API na entrevista é revelar semântica. `POST /posts` obriga a discutir confirmação, duplicidade e durabilidade; `GET /feed` obriga a discutir ordenação, paginação e frescor.

## 8. Modelo de dados

Uma primeira representação conceitual:

```text
User(user_id, status, created_at)
Post(post_id, author_id, body, created_at, state)
Follow(follower_id, followed_id, created_at)
FeedEntry(owner_id, rank_key, post_id, source_author_id)
```

Decisões a verbalizar:

- `Follow` tem chave composta e dois padrões de acesso: “quem sigo?” e “quem me segue?”;
- `Post` precisa de acesso por autor e por identificador;
- `FeedEntry` só existe se escolhermos materialização; ela troca custo de escrita e armazenamento por leitura mais previsível;
- `rank_key` precisa preservar paginação estável mesmo com novas postagens;
- deleção e privacidade exigem propagação para caches e materializações.

**Aula local.** Conceitos vêm antes de nomes de tecnologia. Dizer “há entidades relacionadas e preciso de transações nesta fronteira” é mais informativo que anunciar um banco sem justificar.

## 9. Arquitetura mínima que cobre os requisitos

Desenhe primeiro a versão funcional:

```text
[Cliente]
    |
[API / autenticação]
    |--------------------------|
[Serviço de postagem]   [Serviço de feed]
    |                          |
    +---------[Banco]----------+
                |
         [relações Follow]
```

Fluxo de publicação:

1. cliente envia autor e texto;
2. API autentica, valida tamanho e encaminha;
3. serviço de postagem grava `Post`;
4. resposta confirma identificador e instante.

Fluxo de leitura:

1. cliente pede o feed com cursor;
2. serviço consulta relações de follow;
3. busca postagens recentes dos autores;
4. ordena, pagina e responde.

Fluxo de follow:

1. API valida que o usuário pode alterar sua própria relação;
2. serviço grava ou remove `Follow`;
3. leituras futuras passam a considerar a mudança.

**Aula local.** Por volta dos primeiros 20 minutos, a meta sugerida é ter um high-level design que percorra todos os requisitos funcionais. Ele ainda pode funcionar apenas em pequena escala. O checkpoint protege o tempo restante para aprofundamentos.

## 10. Evolução para escala e desempenho

Agora confronte a arquitetura mínima com os requisitos não funcionais e as estimativas:

1. coloque balanceamento e instâncias stateless nos serviços;
2. separe leitura e escrita quando a assimetria justificar escalabilidade independente;
3. adicione cache para objetos e páginas quentes, definindo TTL e invalidação;
4. replique dados para leitura e recuperação, declarando o atraso aceitável;
5. particione por uma chave alinhada aos padrões de acesso;
6. introduza processamento assíncrono somente onde atraso e reexecução forem aceitáveis;
7. para feed, compare fan-out na escrita, na leitura ou híbrido;
8. use CDN apenas para conteúdo cacheável e geograficamente distribuído.

Arquitetura escalada de referência:

```text
                         +--> [Cache de feed] --+
[Cliente] -> [Edge/API] -+                     +-> [Serviço de feed]
                         +--> [Post service] ---+         |
                                  |                       v
                              [Posts DB]           [Feed store]
                                  |                       ^
                                  +-> [Log/Fila] -> [Workers]
                                           |
                                      [retries/DLQ]
```

**Complemento.** Cada adição deve vir com condição de uso. Fila não é decoração: ela desacopla trabalho, absorve picos e habilita retries, mas aumenta atraso, duplicidade possível e dificuldade de observar o fluxo completo.

## 11. Confiabilidade, disponibilidade e recuperação

Para cada componente, faça três perguntas:

1. como detectamos que falhou?
2. o que o usuário observa?
3. como recuperamos sem corromper ou duplicar?

Exemplos:

- múltiplas instâncias atrás do balanceador reduzem falha de processo;
- réplica de dados permite failover, mas requer promoção segura e consciência de lag;
- timeout, retry com backoff e jitter evitam espera infinita e tempestade sincronizada;
- circuit breaker pode impedir cascata, mas precisa de fallback explícito;
- fila exige operação idempotente, política de retry e dead-letter queue;
- backup só é argumento se restauração for testada;
- reconciliação corrige divergências que não cabem no caminho síncrono.

**Aula local.** Uma conclusão madura reconhece pontos únicos de falha, gargalos, redundância, réplicas, recuperação e reconciliação, mesmo quando não há tempo para desenhar todas as melhorias.

## 12. Consistência e particionamento

Evite dizer apenas “consistência eventual”. Especifique:

- qual objeto pode ficar desatualizado;
- por quanto tempo;
- quem pode observar a divergência;
- como o sistema converge;
- que ação não pode ser aceita durante incerteza.

No exemplo:

- a criação de `Post` exige durabilidade antes de confirmar;
- o autor pode exigir read-your-writes;
- seguidores podem ver a postagem com atraso;
- contadores podem convergir assincronamente;
- a relação `Follow` pode exigir comportamento monotônico para não “ressuscitar” uma remoção.

Ao particionar, conecte chave e hotspot:

- posts por `author_id` facilitam timeline de autor, mas celebridades concentram carga;
- feed por `owner_id` distribui leitores, mas usuários muito ativos geram partições quentes;
- hash distribui melhor, enquanto faixa temporal simplifica varreduras e expiração;
- resharding, rebalanceamento e roteamento fazem parte do custo.

## 13. Segurança e abuso

Mesmo quando não é o foco, cubra a superfície proporcionalmente:

- autenticação de cliente e identidade de serviço;
- autorização por recurso;
- criptografia em trânsito e, quando exigida, em repouso;
- gestão e rotação de segredos;
- rate limiting por usuário, dispositivo, IP e operação;
- validação de entrada e limites de payload;
- proteção contra enumeração de IDs;
- auditoria de ações sensíveis;
- retenção e deleção de dados pessoais;
- moderação, spam e automação abusiva.

**Complemento.** Segurança não deve consumir dez minutos de uma entrevista que prioriza latência global, mas ignorá-la por completo produz um desenho incompleto. Faça uma passagem curta e escolha um deep dive se o domínio for financeiro, identidade, saúde ou conteúdo público.

## 14. Observabilidade e operação

Um sistema operável responde “está funcionando?”, “para quem está falhando?” e “por quê?”.

Defina:

- métricas de taxa, erro e duração por endpoint;
- saturação de CPU, memória, conexões, filas e pools;
- lag de replicação e backlog de consumidores;
- logs estruturados com identificadores de correlação;
- tracing entre fronteiras síncronas e assíncronas;
- SLOs por jornada, não apenas por serviço;
- alertas acionáveis vinculados a runbooks;
- deploy gradual, rollback e feature flags;
- testes de restauração e capacidade.

Exemplo de SLI: percentual de leituras de feed respondidas em menos de 300 ms, sem erro, medido na borda. **Hipótese pedagógica:** o limiar de 300 ms é ilustrativo e precisa ser negociado.

## 15. Alternativas e trade-offs

Use a fórmula **contexto → escolha → ganho → custo → mitigação**.

| Decisão | Quando ajuda | Ganho | Custo | Mitigação |
|---|---|---|---|---|
| síncrono | resposta imediata é necessária | semântica simples | acoplamento e cascata | timeouts, limites e fallback |
| assíncrono | trabalho pode atrasar | absorve picos e desacopla | atraso, duplicidade e operação complexa | idempotência, lag e DLQ |
| fan-out na escrita | leitura domina e seguidores são moderados | feed rápido | amplificação de escrita | estratégia híbrida |
| fan-out na leitura | escrita precisa ser barata | menos materialização | leitura cara e variável | cache e pré-cálculo seletivo |
| banco relacional | relações e invariantes importam | transação e modelo claro | escalada horizontal mais trabalhosa | particionamento dirigido |
| armazenamento distribuído por chave | alto volume e acesso por chave | escala horizontal | consultas e transações limitadas | denormalização consciente |
| cache | leituras repetidas e tolerância a frescor | baixa latência e descarga | invalidação e staleness | TTL, versionamento e métricas |

**Aula local.** Não há decisão “ganha-ganha” universal. O entrevistador procura a compreensão do que se ganha, do que se perde e por que a troca atende aos requisitos.

## 16. Gargalos, falhas e armadilhas comuns

Armadilhas de condução:

- desenhar antes de fechar escopo;
- aceitar requisitos demais;
- fazer contas que não influenciam nada;
- citar produtos como resposta (“Kafka”, “Kubernetes”, “MongoDB”) sem semântica;
- aprofundar um tema favorito que não atende ao foco;
- cobrir apenas o caminho feliz;
- ocultar incerteza em vez de declarar hipótese;
- defender o primeiro desenho contra feedback;
- gastar o final adicionando caixas em vez de revisar riscos.

Gargalos arquiteturais a procurar:

- banco único no caminho de todas as operações;
- partição quente;
- fan-out sem limite;
- cache stampede;
- consumidor lento acumulando backlog;
- retry sem idempotência;
- dependência síncrona em cadeia;
- failover manual e não testado;
- observabilidade que termina na borda da fila.

## 17. Roteiro sugerido para uma entrevista de 45 minutos

**Hipótese pedagógica.** A aula menciona entrevistas de aproximadamente 40–50 minutos e um design inicial por volta de 20 minutos. A sequência canônica usada no cockpit interativo tem 6 janelas; subdivisões mais finas são apenas variantes dentro dessas janelas:

- **00–08 min — escopo e contrato:** repetir o problema, usuários, jornadas, dois ou três requisitos, fora de escopo e prioridades não funcionais.
- **08–12 min — hipóteses e limiares:** registrar escala, tráfego, tamanho de dado e perguntas de capacidade que podem voltar depois do HLD.
- **12–16 min — API e dados:** entidades, APIs, autorização, paginação, idempotência e padrões de acesso.
- **16–27 min — HLD mínimo, contas decisivas e escala:** cobrir todos os fluxos funcionais, chegar ao checkpoint aproximado de 20 minutos e adicionar somente deltas justificados.
- **27–40 min — deep dives e falhas:** por exemplo, feed, fan-out, consistência, filas, hotspots, failover e reconciliação.
- **40–45 min — síntese e riscos:** requisitos cobertos, trade-offs, riscos residuais, observabilidade e próximos passos.

Controle de fluxo verbal:

> “Temos cerca de 20 minutos. O caminho funcional está completo. Vou usar os números para escolher entre aprofundar leitura do feed e distribuição de escrita; há alguma área que você prefere explorar?”

## 18. Perguntas do entrevistador

- O que muda se o tráfego crescer dez vezes?
- Onde está o primeiro gargalo?
- Por que separar leitura e escrita?
- Como garante que uma escrita repetida não duplica dados?
- O que acontece se a fila ficar indisponível?
- Como o usuário lê o próprio dado logo após escrever?
- Qual é sua chave de particionamento e onde surgem hotspots?
- Como você faz failover do banco?
- Como sabe que uma réplica está atrasada?
- Que alternativa você descartou e por quê?
- Como reduziria custo sem quebrar o SLO?
- O que acontece durante uma partição de rede?
- Se eu exigir consistência forte neste fluxo, o que você mudaria?
- Qual parte você deixaria para uma segunda iteração?

Ao responder, não salte direto para a caixa. Reancore:

> “Como a prioridade acordada é disponibilidade de leitura, durante a falha eu aceito dados um pouco antigos, sinalizo a degradação e preservo a escrita durável. Se a prioridade mudar para consistência, bloqueio ou redireciono a operação até restabelecer uma autoridade.”

## 19. Checklist de encerramento

- [ ] Repeti o escopo acordado e o que ficou de fora.
- [ ] Mostrei um fluxo para cada requisito funcional.
- [ ] Conectei deep dives aos requisitos não funcionais.
- [ ] Marquei como hipóteses todos os números inventados.
- [ ] Expliquei ao menos duas decisões com ganho e custo.
- [ ] Identifiquei gargalo, ponto único de falha e hotspot.
- [ ] Cobri timeout, retry, idempotência e recuperação onde aplicável.
- [ ] Declarei a semântica de consistência por fluxo.
- [ ] Mencionei autenticação, autorização e abuso proporcionalmente.
- [ ] Incluí métricas, SLO, alertas e estratégia de deploy.
- [ ] Resumi riscos não resolvidos e próxima evolução.
- [ ] Convidei o entrevistador a escolher o último aprofundamento.

## 20. Relação com a aula-fonte e complementos

O **material local** é a aula “Estrutura da Entrevista System Design”, com cerca de 50 minutos, obtida da trilha autenticada da Ada e transcrita localmente por áudio porque não havia legendas do provedor. A transcrição automática tem possíveis erros de reconhecimento; por isso, este guia se apoia também no outline e nos conceitos extraídos no próprio arquivo-fonte.

Fundamentado diretamente na aula-fonte:

- entrevista como exercício arquitetural aberto, normalmente sem código;
- colaboração e pensamento em voz alta;
- negociação de escopo e seleção de dois ou três requisitos;
- requisitos funcionais como contrato mínimo;
- requisitos não funcionais como guia dos aprofundamentos;
- CAP como estrutura para discutir consistência, disponibilidade e partições;
- abordagem top-down e checkpoint do design inicial por volta de 20 minutos;
- estimativas feitas quando sustentam decisões;
- conceitos antes de tecnologias nomeadas;
- trade-offs, falhas, recuperação e análise crítica no fechamento.

São **complementos** deste guia:

- perguntas organizadas por consequência;
- interfaces HTTP, entidades e esquema do exemplo;
- padrões de idempotência, paginação, observabilidade, segurança e operação;
- matriz de alternativas;
- roteiro detalhado de 45 minutos;
- checklist e formulações verbais reutilizáveis.

São **hipóteses pedagógicas**, não fatos do curso nem dados reais de qualquer empresa:

- volumes de usuários, leituras, escritas, bytes e picos;
- metas numéricas de latência;
- distribuição exata de minutos do roteiro de 45 minutos;
- arquitetura específica da rede social usada como exercício.

Para aprofundar a técnica de condução, leia [deep-dives.md](deep-dives.md). Para praticar em formato sequencial, abra [index.html](index.html) diretamente no navegador.
