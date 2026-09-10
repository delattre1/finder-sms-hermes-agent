---
name: fd-setup
description: Primeira conversa. Descobre quais pastas voce enxerga e como o dono quer receber os arquivos.
---

# Colocar o finder de pe

Tres perguntas, nesta ordem, uma mensagem cada. **Nunca peca uma senha pelo
chat** -- nada aqui precisa de uma.

Se `$HERMES_HOME/finder/config.json` ja existe, isto e um ajuste e nao uma
primeira conversa: mande o `fd-config` cuidar.

## Antes de perguntar qualquer coisa, veja o que chegou montado

```
python3 "$HERMES_HOME/skills/fd-shared/scripts/find.py" --roots
```

As pastas nao sao escolhidas por voce nem pelo chat: elas sao montadas pelo
`compose.yml` a partir do `.env` que o dono escreveu antes de subir o container,
sempre com `:ro`. Isso e proposital -- montar uma pasta nova e uma decisao que
uma frase numa mensagem nao deve poder tomar, porque uma mensagem pode ter sido
escrita por qualquer um que alcance aquele numero.

**Se a lista voltar vazia**, nenhum `FINDER_ROOT_` foi preenchido. Diga isso em
uma linha, sem jargao, e nao siga com o resto do setup -- sem pasta, tudo que
voce perguntar depois e hipotetico:

> ainda nao enxergo pasta nenhuma sua. no `.env` da pasta do agente, aponta
> `FINDER_ROOT_A` pra pasta que voce quer que eu ache (ex:
> `/Users/voce/Documents`) e roda `docker compose up -d` de novo. eu aviso
> quando enxergar.

## 1. Como ele chama cada pasta

Mostre o que veio montado usando o caminho do host, e pergunte se os nomes
servem:

> enxergo duas pastas suas: `/Users/gabe/Documents` e `/Users/gabe/Projetos`.
> vou chamar de **Documents** e **Projetos** -- serve? pode trocar o nome de
> qualquer uma.

O rotulo nao e enfeite: e como ele vai dizer "procura so nos Projetos", e como
voce vai dizer de onde veio o arquivo. Se ele nao ligar, aceite o padrao e siga.

## 2. Como ele quer receber os arquivos

Explique as duas formas em uma frase cada, e diga qual e o padrao:

> quando eu achar, mando de dois jeitos: **anexo aqui na conversa** (padrao,
> nao precisa configurar nada) ou **por e-mail** (precisa de uma senha de app no
> `.env`). posso tambem **perguntar toda vez**. qual voce prefere?

Grave `chat`, `email` ou `ask`. Anote as duas coisas que ele vai descobrir
sozinho na primeira semana, agora, em meia linha cada: o anexo do chat para em
**100 MiB**, e o que nao for tipo que o iMessage exibe (um `.tar`, um `.whl`)
**vai zipado**.

Se ele escolher `email` e o `.env` nao tiver `SMTP_PASSWORD`, diga na hora que
falta isso pro modo funcionar e deixe `chat` valendo enquanto ele nao poe -- em
vez de gravar uma preferencia que vai falhar na primeira entrega.

## 3. O que ficar de fora

Uma pergunta so, e aceite "nada" como resposta:

> tem alguma pasta dentro dessas que voce prefere que eu ignore? (cache, build,
> backup antigo)

Diga junto, em uma linha, o que ja fica de fora sem ele pedir: `node_modules`,
`.git`, caches, e **chave privada, `.env`, keychain e cookie de navegador --
esses nunca aparecem e nao tem como voce me fazer mandar**. E a frase mais
importante do setup inteiro: e o que ele precisa saber pra confiar em apontar
isto pra pasta dele.

Nao pergunte mais nada.

## Escrever a configuracao

```json
{
  "roots": [
    {"mount": "/files/a", "label": "Documents", "host": "/Users/gabe/Documents", "enabled": true},
    {"mount": "/files/b", "label": "Projetos",  "host": "/Users/gabe/Projetos",  "enabled": true}
  ],
  "excludes": ["node_modules", ".git", ".venv", "venv", "__pycache__", ".cache",
               "site-packages", ".trash", "library", "applications", ".ds_store"],
  "delivery": "chat"
}
```

Em `$HERMES_HOME/finder/config.json`. Preencha `mount` e `host` com o que o
`--roots` devolveu, nunca com o que voce imaginou. Se ele pediu exclusoes, some
elas na lista existente em vez de substituir.

## Nao registre cron nenhum

Este agente nao tem um. Se voce se pegar prestes a criar um, pare: nao ha
trabalho periodico aqui, e um cron que varre a pasta de alguem de hora em hora
gasta token sem trabalho e olha arquivos que ninguem pediu.

## Fechar

Duas linhas: o que voce enxerga, como o arquivo vai chegar, e um exemplo de
pedido no formato que ele usaria de verdade -- "manda o pdf do contrato da ana"
-- pra ele saber que nao precisa aprender sintaxe. Nao faca uma busca de teste
por conta propria.
