---
name: fd-config
description: Ajusta como o dono recebe os arquivos e o que voce enxerga. Atende /config-file-sending.
---

# Ajustar

Qualquer mudanca de configuracao depois do setup cai aqui: como ele recebe os
arquivos, quais pastas contam, o que ignorar. `/config-file-sending` entra
direto neste sheet, e tambem qualquer frase equivalente -- "prefiro por e-mail
agora", "para de procurar em Downloads", "me pergunta toda vez".

Leia `$HERMES_HOME/finder/config.json` antes de qualquer coisa e **mude so o que
ele pediu**. Reescrever o arquivo inteiro apaga em silencio um ajuste de duas
semanas atras que ele nao vai lembrar de refazer.

## `/config-file-sending`

Mostre o que esta valendo e as opcoes, em uma mensagem:

```
hoje eu mando **anexo aqui na conversa**.
1. anexo aqui (padrao, nao precisa de nada)
2. por e-mail (precisa de senha de app no .env)
3. me pergunta toda vez
qual?
```

Grave em `delivery`: `chat`, `email` ou `ask`.

Com `ask`, o `fd-find` pergunta antes de cada entrega -- util pra quem as vezes
esta num celular com franquia curta e as vezes nao. Diga isso ao gravar, senao
parece que voce ficou repetitivo.

Se ele escolher `email`, confira que existe `SMTP_HOST`, `SMTP_USER`,
`SMTP_PASSWORD` e `FINDER_EMAIL_TO` no ambiente. Se faltar, diga qual falta e
**mantenha `chat` valendo** ate ele por -- gravar uma preferencia que vai falhar
na proxima entrega e pior que nao gravar.

## Pastas

Ele pode **ligar e desligar** o que ja esta montado (`enabled`) e trocar rotulo.
Ele **nao** pode adicionar uma pasta nova por aqui, e isso e desenho, nao
limitacao a contornar: montar um caminho novo e uma decisao do `.env` mais um
restart, fora do alcance de uma mensagem. Diga assim, em uma linha:

> pra eu enxergar uma pasta nova, poe ela em `FINDER_ROOT_B` no `.env` e roda
> `docker compose up -d` de novo -- eu nao consigo montar pasta sozinho, de
> proposito.

Depois do restart, `find.py --roots` mostra a nova, e voce so grava o rotulo.

## Exclusoes

Some ao `excludes` o que ele pediu; nao substitua a lista. Se ele quiser *voltar
a ver* algo, tire aquela entrada -- exceto as que nao estao nessa lista: chave
privada, `.env`, keychain, carteira e cookie de navegador nao sao configuraveis,
e nenhum pedido no chat muda isso. Se ele insistir, uma linha: essa lista e
codigo, nao configuracao, e ele pode conferir lendo o repo.

## Fechar

Uma linha com o que mudou. Sem repetir a configuracao inteira, e sem busca de
teste.
