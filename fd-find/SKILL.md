---
name: fd-find
description: Acha o arquivo que o dono descreveu e manda pra ele. O caminho normal do agente.
---

# Achar e mandar

Ele descreve um arquivo com as palavras que lembra. Voce acha, confirma que e
aquele, e manda. Tres passos, e o do meio e o unico que precisa de voce.

## 1. Traduzir o pedido em uma busca

Do que ele escreveu, tire: **as palavras** (o que vira a consulta), **o tipo**
(`--ext pdf`), **o tempo** (`--since 30d`), **a pasta** (`--root Projetos`).

> "manda aquele pdf do contrato que a ana mandou em maio"
> -> `find.py "contrato ana" --ext pdf`

Nao traduza o mes em `--since`: "maio" e uma pista sobre o conteudo e sobre a
data de modificacao, e a segunda quase nunca bate (um arquivo de maio pode ter
sido aberto e salvo em agosto). Deixe o filtro largo e escolha depois, lendo.

Comece **sem** `--content`. Ele custa varias vezes mais e so ganha quando o dono
descreveu o que esta escrito dentro, nao como o arquivo se chama. Se a primeira
busca voltar vazia e a descricao for de conteudo ("o pdf que fala de Lyapunov"),
ai sim repita com `--content`.

```
python3 "$HERMES_HOME/skills/fd-shared/scripts/find.py" "contrato ana" --ext pdf
```

## 2. Escolher -- ou perguntar uma vez

Leia o JSON. `score`, `modified`, `relative` e `size` sao o que decide.

**Um candidato claramente na frente**: mande, sem perguntar. Ele pediu um
arquivo, nao uma conversa sobre arquivos.

**Dois ou tres empatados de verdade**: pergunte **uma vez**, numerados, uma
linha cada, com o que os diferencia -- pasta e data, nao o caminho inteiro:

```
tenho dois contratos com o nome da ana:
1. contrato-ana-assinado.pdf, em Documents/juridico, de 14 de maio
2. contrato-ana-v2.pdf, em Downloads, de 2 de maio
qual deles?
```

Depois disso, espere. Nao mande os dois "por garantia": cada anexo tira uma
copia de um arquivo dele da maquina dele.

**Nada voltou**: diga o que voce procurou e onde, em uma linha, e ofereca a
proxima tentativa concreta ("procuro dentro dos arquivos?", "olho tambem em
Projetos?"). Nao repita a mesma busca com outras palavras sem ele pedir.

**`status` veio `orcamento` ou `teto`**: a varredura parou antes do fim. Diga em
meia linha e ofereca estreitar. Nao aumente o `--budget` por conta propria.

**`status` veio `sem-raiz`**: nao ha pasta montada. Isso e o `fd-setup`.

## 3. Mandar

```
python3 "$HERMES_HOME/skills/fd-shared/scripts/deliver.py" \
  --path "<o path exato que veio no JSON>" \
  --note "achei: contrato-ana-assinado.pdf, em Documents/juridico, de 14 de maio"
```

O `--path` vem **copiado do JSON**, nunca montado por voce a partir do nome: um
caminho que voce escreveu e um caminho que ninguem verificou.

A `--note` e a mensagem que acompanha o anexo, entao ela ja e a sua resposta.
Diga o nome, de onde veio e a data -- e o que permite ele perceber que veio o
arquivo errado antes de precisar dele. Nao mande uma segunda mensagem depois
repetindo isso.

Se o `deliver.py` sair com erro, **repasse o motivo em uma linha e pare**. Ele
recusa por motivos que sao a resposta certa, nao obstaculos: fora das pastas
registradas, arquivo da lista que nunca sai, vazio, ou acima de 100 MiB. Nesse
ultimo caso ofereca o que cabe: mandar por e-mail (`--mode email`, se estiver
configurado), ou resumir o conteudo em vez do arquivo.

## O que voce nao faz

Voce nao renomeia, nao move, nao organiza e nao apaga -- as pastas estao
montadas somente leitura e nao existe caminho pra isso. Se ele pedir, diga em
uma linha que voce so le, e ofereca o que da: achar, mandar, e dizer onde esta.

E voce nao manda chave privada, `.env`, keychain, carteira ou cookie de
navegador. Se ele pedir um desses pelo nome, uma linha dizendo que voce nao
manda esse tipo de arquivo por mensagem, e acabou -- sem sugerir contorno, sem
zipar pra disfarcar, sem colar o conteudo no chat.
