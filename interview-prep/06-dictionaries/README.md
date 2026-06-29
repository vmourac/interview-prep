---
title: 06 Dictionaries
type: interview-prep-topic
stage: synthesis
domain: uber-interviews
updated: 2026-06-22
language: pt-BR
tags:
  - uber-interviews
  - interview-prep
  - dictionaries
  - hash-map
---

As duas primeiras aulas possuem transcript e sustentam diretamente a intuicao sobre pares chave-valor, direct access tables, hashing e contagem de frequencia. A terceira aula, sobre colisoes, nao tem captions; por isso a parte de collision handling abaixo combina o que aparece no metadata do curso com conhecimento publico padrao de entrevistas.

## Como estudar este topico

1. Leia [01-conceitos](./01-conceitos.md) para montar o modelo mental de hash map do jeito que um entrevistador espera ouvir.
2. Resolva os problemas em markdown tentando justificar em voz alta o salto da versao ingenua para a versao otimizada.
3. Abra os HTMLs para treino local em formato de prompt, hints, caminho ingenuo, caminho otimizado e solucao final.

## Conceitos

- [01-conceitos](./01-conceitos.md)

## Problemas

- [Group Anagrams](./problems/group-anagrams.md)
- [Top K Frequent Elements](./problems/top-k-frequent-elements.md)
- [Subarray Sum Equals K](./problems/subarray-sum-equals-k.md)

## HTML

- [Group Anagrams HTML](./html/group-anagrams.html)
- [Top K Frequent Elements HTML](./html/top-k-frequent-elements.html)
- [Subarray Sum Equals K HTML](./html/subarray-sum-equals-k.html)

## Fontes

- [Manifesto do piloto](../manifest.md)
- [Contexto do bundle](../README.md)

## Lacunas da fonte

- `01 Introduction to Dictionaries` tem transcript e cobre pares chave-valor, lookup tables, frequencia e Big O medio `O(1)`.
- `02 Data at Top (DAT) and Hash` tem transcript e cobre direct access tables, hash functions, distribuicao uniforme e a nocao de colisao.
- `03 Handling collisions` esta marcado como `no-captions`, entao nao ha transcript para citar encadeamento separado, open addressing ou detalhes especificos da aula.

Por isso, este pacote fica estritamente ancorado no que foi observado e, quando precisa completar a ponte para problemas classicos, sinaliza que esta usando conhecimento publico padrao de entrevistas.
