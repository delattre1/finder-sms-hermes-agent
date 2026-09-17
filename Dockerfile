# Finder SMS -- imagem do agente, derivada da base cloud da Plow.
#
# Sem conteudo de agente proprio na base: a persona e os skills copiados abaixo
# sao os arquivos versionados que este repo possui. O contexto e a raiz do repo,
# entao essas copias sao o produto: `docker build .`
#
# A tag e um `base-<sha>` imutavel nomeando um commit do repo-fonte da base,
# plow-pbc/plow-hermes-agent, fixado tambem por digest. Ela nunca e movida: toda
# VM inquilina herda exatamente este filesystem enquanto segura a credencial
# Plow daquele dono, e uma tag movel trocaria codigo por baixo deles.
# A base e publicada SO pra linux/amd64. Sem declarar isso, o build num Mac
# Apple Silicon imprime um aviso de plataforma incompativel -- inofensivo (o
# Docker Desktop emula) mas ele aparece no PRIMEIRO build de todo instalador em
# Mac ARM, que e exatamente o momento em que a pessoa decide se algo quebrou.
#
# Um ARG e nao uma constante: `FROM --platform=linux/amd64` dispara o lint
# FromPlatformFlagConstDisallowed, que existe porque fixar plataforma no FROM
# costuma ser engano. Aqui nao e -- e a unica que a base tem -- entao o ARG diz
# isso e ainda deixa alguem sobrescrever (`--build-arg BASE_PLATFORM=...`) no dia
# em que a Plow publicar arm64.
ARG BASE_PLATFORM=linux/amd64
FROM --platform=${BASE_PLATFORM} public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-51f83158a70a383f03a4d03dbd8b6ea102cf0361@sha256:253d7ed3409effa7fa59113d93b4b79bb731d8264cdaf4cd60294924d0110a2e

# Substitui o SOUL.md da propria base; o primeiro boot reafirma a posse root
# nesse arquivo, e e a isso que o chmod no fim responde.
COPY runtime/SOUL.md /var/lib/hermes/SOUL.md
COPY LICENSE NOTICE /usr/share/doc/finder-sms/

# Entregues em /opt/hermes/skills, fora de toda casa, pra que uma casa
# bind-montada ainda receba e uma atualizacao de imagem ainda alcance um skill
# nao customizado -- as duas coisas via reconcile do runtime da base.
COPY fd-setup/   /opt/hermes/skills/fd-setup/
COPY fd-find/    /opt/hermes/skills/fd-find/
COPY fd-config/  /opt/hermes/skills/fd-config/
COPY fd-shared/  /opt/hermes/skills/fd-shared/

# Os pontos de montagem das pastas do dono, criados na imagem em vez de deixar o
# Docker cria-los no `up`. E a diferenca entre um diretorio root:root 0755 que o
# agente le, e um diretorio criado pelo daemon com o modo que ele escolher.
# Vazios aqui de proposito: quem os preenche e o bind `:ro` do compose, e um
# slot que o dono deixou em branco no `.env` continua vazio -- que e exatamente
# como o `find.py` distingue "montada" de "declarada e nao preenchida".
RUN mkdir -p /files/a /files/b /files/c /files/d \
 && chmod 0755 /files /files/a /files/b /files/c /files/d

# Normaliza os modos que o checkout carregou, preservando o bit de executavel:
# varios SKILL.md invocam um script por caminho nu, entao um 0644 geral os faz
# falhar com Permission denied. A posse fica como root.
# -mindepth 1: a raiz de skills e da base, root-owned e sticky; recursar sobre
# ela resetaria esse modo e deixaria o diretorio nao-gravavel pro proprio
# install de skills do gateway, que entao nao varre nada.
RUN find /opt/hermes/skills -mindepth 1 -type d -exec chmod 0755 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f ! -perm -u+x -exec chmod 0644 {} + \
 && find /opt/hermes/skills -mindepth 1 -type f -perm -u+x -exec chmod 0755 {} + \
 && chmod 0644 /var/lib/hermes/SOUL.md

# NAO ha copia root-owned de fd-shared em /opt/plow, e a ausencia e a decisao.
#
# Os agentes irmaos deste repo tem uma: eles agendam scripts sob o supervisor, e
# o que roda sem ninguem olhando nao pode ser o arquivo que um turno reescreveu
# -- senao uma unica edicao por prompt-injection vira codigo que roda sozinho
# pra sempre, segurando a credencial. Aqui nao existe nada agendado: o finder so
# roda quando o dono pede um arquivo. Sem trabalho periodico, nao ha copia
# privilegiada a manter, e a superficie que ela protegeria nao existe.
#
# Se algum dia este agente ganhar um cron, esta copia volta junto -- as duas
# coisas sao a mesma decisao vista de dois lados.

# O reporter de uso, buscado no build a partir do commit que vendor/client.pin
# nomeia e conferido contra o hash ao lado. Buscado em vez de commitado porque
# plow-pbc/agent-index-client e o dono do arquivo; pinado em vez de seguir um
# branch porque isto roda dentro de um agente com credencial viva, e uma
# referencia movel substituiria codigo nao revisado por baixo dele. O checksum
# e a segunda metade: um sha numa URL so vale o quanto vale o host que serve.
COPY vendor/client.pin /opt/plow/agent-index-client.pin
RUN set -eu; \
    sha="$(sed -n 's/^sha=//p' /opt/plow/agent-index-client.pin)"; \
    want="$(sed -n 's/^sha256=//p' /opt/plow/agent-index-client.pin)"; \
    path="$(sed -n 's/^path=//p' /opt/plow/agent-index-client.pin)"; \
    curl -fsS --max-time 60 -o /opt/plow/agent-index-client.py \
      "https://raw.githubusercontent.com/plow-pbc/agent-index-client/${sha}/${path}"; \
    got="$(sha256sum /opt/plow/agent-index-client.py | cut -d' ' -f1)"; \
    [ "$got" = "$want" ] || { echo "agent-index client e $got, o pin diz $want" >&2; exit 1; }; \
    chmod 0644 /opt/plow/agent-index-client.py

COPY image/s6-overlay/ /etc/s6-overlay/
