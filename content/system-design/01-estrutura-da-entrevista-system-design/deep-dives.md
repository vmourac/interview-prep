# Deep dives: condução e sinais em entrevistas de System Design

Este material não repete o catálogo arquitetural do guia principal. Ele trata a entrevista como uma atividade operacional: como controlar o relógio, negociar um contrato, desenhar incrementalmente, reagir a feedback e tornar visível o nível de julgamento técnico.

> **Rastreabilidade:** princípios atribuídos à **aula local** são explicitamente identificados. Técnicas, scripts e matrizes são **complementos**. Tempos e números são **hipóteses pedagógicas**, nunca dados reais do curso ou de empresas.

## 1. Gestão de tempo como controle de risco

**Aula local.** O candidato conduz grande parte da entrevista e precisa administrar o tempo. Um checkpoint sugerido é ter, perto de 20 minutos, um design inicial que cubra os requisitos funcionais.

O erro mais comum é tratar tempo como cronômetro, quando ele é orçamento de incerteza. Se você consome quinze minutos enumerando requisitos, sobra pouco espaço para demonstrar profundidade. Se desenha uma solução escalada no minuto dois, assume detalhes ainda não negociados e cria dívida de explicação.

**Complemento — orçamento de marcos.** Para uma entrevista de 45 minutos, use marcos recuperáveis:

| Marco | Alvo pedagógico | Evidência de saída | Plano de recuperação |
|---|---:|---|---|
| contrato fechado | 8 min | dentro/fora + prioridades | reduzir para 2 jornadas |
| interfaces e dados | 14 min | APIs, entidades, acessos | adiar campos e tecnologia |
| design funcional | 21 min | todos os fluxos percorridos | fundir componentes |
| deep dive principal | 32 min | gargalo + decisão + custo | comparar só 2 alternativas |
| revisão de falhas | 40 min | degradação e recuperação | listar riscos priorizados |
| síntese | 45 min | cobertura e próximos passos | interromper desenho e resumir |

Faça “checagens de cabine” curtas:

> “Vou pausar por dez segundos: cobrimos criação e leitura; ainda falta recuperação. Tenho vinte minutos e proponho aprofundar o hotspot de leitura antes de voltar a falhas.”

Isso sinaliza consciência situacional. Não peça desculpas pelo relógio nem narre ansiedade. Replaneje.

### Quando cortar

Corte uma discussão quando:

- ela não altera a arquitetura;
- não está ligada a requisito;
- exige conhecimento de produto ainda não fornecido;
- a decisão é reversível e barata;
- já demonstrou o sinal técnico esperado.

Uma saída elegante:

> “Há detalhes de tuning nessa tecnologia, mas a decisão relevante aqui é a semântica: preciso de entrega ao menos uma vez e consumidores idempotentes. Vou manter o produto abstrato para completar o fluxo.”

## 2. Negociação de escopo sem parecer evasivo

**Aula local.** Fechar escopo é uma negociação. O candidato não deve tentar modelar em uma hora tudo que um produto real levou anos para construir. Também deve explicitar o que fica de fora.

Negociação madura não é “recusar complexidade”; é construir um recorte que preserve a parte tecnicamente interessante. Use quatro movimentos:

1. **mapear:** “Vejo publicação, feed, mídia, chat, recomendações e moderação.”
2. **propor:** “Para fechar um fluxo completo, sugiro publicação textual e feed.”
3. **justificar:** “Esse recorte ainda exercita escrita, leitura assimétrica, ordenação e escala.”
4. **confirmar:** “Há alguma capacidade que você quer manter obrigatoriamente?”

### Matriz de seleção

Pontue mentalmente cada requisito:

- é central para o produto?
- cria uma decisão arquitetural distinta?
- cabe no tempo?
- combina com o foco sugerido pelo entrevistador?

Escolha requisitos que maximizem cobertura de sinais, não quantidade de features. “Upload de vídeo” pode dominar a conversa com mídia; se o foco é consistência do feed, deixe-o fora com uma fronteira bem definida.

### Escopo reaberto no meio

Quando o entrevistador adiciona “agora suporte celebridades” ou “precisa ser global”, não interprete como invalidação. Trate como mudança de premissa:

> “Essa nova restrição quebra minha hipótese de distribuição uniforme. Vou preservar a interface e trocar o fan-out puro por uma estratégia híbrida. Antes de alterar, confirmo: priorizamos latência de leitura mesmo com maior complexidade operacional?”

Esse movimento mostra controle de mudanças: identifica qual hipótese caiu, preserva o que continua válido e localiza a alteração.

## 3. Estimativas sem ritualismo

**Aula local.** Cálculos são úteis quando sustentam uma decisão, não porque existe um checklist que manda calcular tudo no começo.

Use o protocolo **pergunta → hipótese → conta → limiar → decisão**:

1. Pergunta: uma única instância suporta o pico?
2. Hipótese pedagógica: 50 milhões de leituras/dia, pico 10×.
3. Conta: média ≈ 580/s, pico ≈ 5.800/s.
4. Limiar: a capacidade segura por instância é menor e precisa de margem.
5. Decisão: serviço stateless replicado, balanceamento e teste de capacidade.

Se a conta não leva ao passo 5, não a faça ou diga por que será adiada.

### Precisão apropriada

Entrevista pede ordem de grandeza. Arredonde explicitamente, preserve unidades e declare fatores ignorados:

> “Vou arredondar 86.400 segundos para 100 mil para calcular mentalmente. Isso subestima um pouco a taxa; compenso usando um fator de pico conservador. O objetivo é saber se estamos em centenas ou dezenas de milhares por segundo.”

Não transforme um número inventado em autoridade. O sinal de senioridade está em reconhecer sensibilidade:

> “Se o tamanho médio for 10× maior, o gargalo muda de CPU para rede/armazenamento. Eu mediria a distribuição real antes de fechar a capacidade.”

### Três estimativas de alto retorno

- **taxa de pico:** decide replicação, limites e absorção de rajadas;
- **crescimento armazenado:** decide retenção, particionamento e tiering;
- **amplificação:** decide se fan-out, índices ou réplicas tornam o caminho inviável.

## 4. Evolução do diagrama mínimo

**Aula local.** A abordagem é top-down: primeiro um sistema minimamente funcional que cobre requisitos; depois refinamentos orientados por qualidades, escala e falhas.

Um diagrama evolutivo é uma prova, não uma ilustração. Cada mudança deve responder a uma pressão.

### Estado A — fronteira funcional

```text
Cliente → Serviço → Dados
```

Explique duas jornadas. Não desenhe cache, fila, CDN e sharding “por padrão”.

### Estado B — responsabilidades

```text
Cliente → API → Leitura → Dados
              ↘ Escrita ↗
```

Separe quando os padrões de escala, latência ou consistência forem diferentes. Se não forem, mantenha unido.

### Estado C — pressão quantitativa

```text
Cliente → Edge → Leitura → Cache → Réplicas
              ↘ Escrita → Primário
```

Agora a assimetria e o pico justificam replicas e cache. Marque quais setas aceitam dado antigo.

### Estado D — trabalho desacoplado

```text
Escrita → Log/Fila → Workers → Visões derivadas
```

Adicione somente se o trabalho pode atrasar. Anote idempotência, retry, backlog e DLQ ao lado da fila; do contrário, o diagrama esconde o principal custo.

### Estado E — falha

Sobreponha falhas sem redesenhar tudo:

- risque uma instância e mostre o balanceador desviando;
- marque réplica atrasada;
- mostre a fila crescendo;
- declare o fallback que o usuário recebe;
- aponte quem reconcilia após recuperação.

**Complemento.** Num quadro limitado, use convenção visual: linha contínua para síncrono, tracejada para assíncrono, dupla para replicação e vermelha para falha. Diga a legenda. Clareza vale mais que ornamentação.

## 5. Comunicação de trade-offs

Trade-off não é listar prós e contras genéricos. É escolher sob um contexto.

Use esta forma:

> “Como **[requisito]** tem prioridade e assumimos **[evidência]**, escolho **[opção]**. Ganho **[propriedade]**, pago **[custo]** e reduzo o risco com **[mitigação]**. Se **[premissa]** mudar, reconsidero **[alternativa]**.”

Exemplo:

> “Como leitura de feed domina e tolera segundos de atraso, materializo parte do feed assincronamente. Ganho latência previsível, pago amplificação de escrita e armazenamento. Mitigo celebridades com fan-out na leitura. Se a consistência imediata se tornar obrigatória, reviso essa fronteira.”

### Trade-offs falsos

Evite:

- “SQL versus NoSQL” sem padrão de acesso;
- “microsserviços versus monólito” sem fronteira organizacional ou de escala;
- “consistência versus disponibilidade” sem partição e operação concreta;
- “custo versus performance” sem SLO ou orçamento;
- “Kafka versus RabbitMQ” sem semântica de entrega e retenção.

O entrevistador pode discordar da escolha e ainda avaliar bem o raciocínio. Defenda a cadeia de premissas, não a identidade pessoal com uma solução.

## 6. Feedback e redirecionamento do entrevistador

**Aula local.** A entrevista é colaborativa; ouvir e reagir ao entrevistador é parte do sinal. Aprofundar um assunto favorito que não está no foco pode prejudicar a condução.

Classifique o redirecionamento em segundos:

- **nova restrição:** “e se houver um bilhão de usuários?”
- **teste de falha:** “e se o banco cair?”
- **pedido de profundidade:** “como particionaria?”
- **correção:** “não precisamos de consistência forte.”
- **sinal de tempo:** “vamos avançar.”

Resposta em três passos:

1. reconhecer: “Entendi; disponibilidade é mais importante neste fluxo.”
2. localizar impacto: “Isso altera a leitura e o failover, não a durabilidade da escrita.”
3. adaptar: “Vou permitir réplica com atraso e explicitar read-your-writes para o autor.”

Não finja que já tinha previsto tudo. Uma correção bem incorporada vale mais que resistência elegante.

### Quando o feedback parece contraditório

Pergunte pela prioridade:

> “Para eu não otimizar os dois lados de forma inconsistente: durante partição, devemos rejeitar a operação para preservar uma visão única ou responder com a melhor versão disponível?”

Isso converte contradição aparente em decisão de produto.

## 7. Sinais de senioridade

Senioridade não é quantidade de nomes técnicos. É julgamento sob restrição.

Sinais observáveis:

- transforma ambiguidade em contrato;
- separa fato, hipótese e pergunta aberta;
- conecta requisitos a componentes;
- escolhe nível de abstração adequado ao momento;
- calcula somente para cruzar limiares;
- identifica distribuição enviesada, não apenas médias;
- discute degradação e recuperação, não só redundância;
- trata retries como fonte de duplicidade;
- define dono da consistência e da reconciliação;
- considera operação, deploy, observabilidade e custo;
- muda de ideia quando uma premissa muda;
- encerra com riscos priorizados.

Sinais fracos:

- arquitetura “de catálogo” igual para qualquer problema;
- componentes sem fluxo;
- promessas absolutas de disponibilidade;
- sharding sem chave;
- cache sem invalidação;
- fila sem idempotência;
- replicação sem lag e failover;
- “eventual consistency” sem janela ou experiência do usuário;
- segurança e privacidade como apêndice vazio;
- resposta longa que ignora o redirecionamento.

### A análise crítica como fechamento

**Aula local.** Não é realista chegar ao sistema perfeito. Reconhecer fraquezas e caminhos de melhoria demonstra maturidade.

Faça um “registro de riscos” verbal:

1. maior risco de capacidade;
2. maior risco de correção;
3. maior risco operacional;
4. experimento ou métrica que reduziria incerteza.

Exemplo:

> “Meu maior risco de capacidade é fan-out de celebridades; de correção, duplicidade no consumo; operacional, promoção de réplica. Eu validaria distribuição de seguidores e lag sob carga antes de escolher os limites.”

## 8. Roteiro reutilizável para diferentes problemas

O roteiro abaixo é um algoritmo de conversa. As durações são **hipóteses pedagógicas**.

### Passo 1 — enquadrar

> “Vou começar pelo contrato do produto, depois interfaces e dados, então uma arquitetura mínima. Uso escala e qualidades para escolher os aprofundamentos e termino com falhas e trade-offs.”

### Passo 2 — formar o contrato

Preencha:

```text
Usuários:
Jornadas dentro:
Fora de escopo:
Prioridade de latência:
Prioridade sob falha:
Consistência por operação:
Escala aproximada:
```

### Passo 3 — tornar fluxos concretos

Para cada jornada:

```text
entrada → validação → decisão → persistência → resposta
```

Liste entidade, API e padrão de acesso. Isso impede caixas sem propósito.

### Passo 4 — provar o mínimo

Percorra cada requisito no diagrama. Se uma jornada não tem caminho, o design não está completo. Se uma caixa não participa de jornada nem requisito não funcional, questione sua presença.

### Passo 5 — selecionar deep dives

Ordene pressões:

```text
capacidade | latência | consistência | disponibilidade | segurança | operação
```

Escolha uma ou duas com maior impacto. Confirme com o entrevistador.

### Passo 6 — evoluir por deltas

Para cada mudança:

```text
pressão → alteração → ganho → custo → falha introduzida → observabilidade
```

Esse formato funciona para chat, ingressos, autocomplete, armazenamento e redes sociais.

### Passo 7 — fechar

> “Cobrimos as jornadas acordadas. A arquitetura mínima evoluiu por causa de X e Y. Priorizamos A sobre B neste fluxo. Permanecem os riscos C e D; com mais tempo, eu validaria E e implementaria F.”

## 9. Exercícios deliberados

Treine em sessões de 12 minutos:

1. três minutos para negociar escopo;
2. quatro para desenhar o mínimo;
3. três para uma mudança de escala;
4. dois para falha e fechamento.

Depois avalie:

- cada seta tem semântica?
- cada número levou a decisão?
- ficou claro o que é hipótese?
- você falou de uma falha observável pelo usuário?
- respondeu ao feedback ou apenas continuou o roteiro?
- conseguiu parar no tempo?

Varie o redirecionamento:

- “latência agora é 100 ms”;
- “não podemos perder pedidos”;
- “um usuário tem metade do tráfego”;
- “a região principal caiu”;
- “precisamos reduzir custo em 40%”.

O objetivo não é memorizar arquiteturas. É tornar automática a sequência de enquadrar, provar, pressionar, escolher e revisar.

## 10. Relação com a fonte

Da **aula local** vêm a colaboração contínua, a negociação de escopo, o contrato de requisitos funcionais, o checkpoint aproximado de 20 minutos, as estimativas direcionadas, a preferência por conceitos antes de produtos, os deep dives guiados por requisitos não funcionais e a análise de falhas e trade-offs.

São **complementos** deste deep dive o orçamento de marcos, scripts verbais, protocolo de estimativa, estados incrementais do diagrama, classificação de feedback, registro de riscos e exercícios deliberados. Eles operacionalizam o material sem afirmar que foram prescritos literalmente pelos professores.

Volte ao [guia principal](README.md) para o conteúdo arquitetural completo ou pratique no [cockpit interativo](index.html).
