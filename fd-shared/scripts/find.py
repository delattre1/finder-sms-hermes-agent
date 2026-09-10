#!/usr/bin/env python3
# Copyright 2026 Gabriel Ribeiro
# SPDX-License-Identifier: Apache-2.0
"""find.py -- procura arquivos nas pastas que o dono registrou. SOMENTE LEITURA.

Roda sem modelo nenhum. Recebe as palavras que o dono usou, varre as pastas
montadas, pontua os candidatos e devolve JSON. Quem decide qual dos candidatos
o dono queria e o agente, num turno separado, lendo esta saida.

Essa divisao e o desenho, nao economia de codigo: uma varredura de sistema de
arquivos e barata e deterministica, e escolher entre "contrato-v2.pdf" e
"contrato-final-ASSINADO.pdf" e a unica parte que precisa de julgamento. Gastar
um turno de modelo pra listar diretorio seria pagar caro pelo `ls`.

Quatro propriedades existem de proposito, porque sao o que torna aceitavel
apontar isto pra pasta de arquivos de um estranho:

1. **As pastas sao montadas `:ro` no compose.** Nao e uma promessa de README --
   e o kernel recusando. Este processo nao consegue escrever, mover nem apagar
   nada seu, e nem este script nem o agente tem um caminho pra isso.
2. **Fora das raizes registradas nao existe.** Todo caminho e resolvido com
   realpath e conferido contra as raizes ANTES de ser lido; um symlink que
   aponta pra fora do mount some da lista em vez de virar uma porta.
3. **Existe uma lista de coisas que ele nunca ve.** Chave privada, .env,
   keychain, carteira, cookie de navegador: nao aparecem na busca, nao contam
   como candidato e nao podem ser entregues -- nem se o dono pedir pelo nome.
   Um agente que pode ser convencido a mandar uma chave SSH por mensagem e um
   agente que nao devia estar instalado.
4. **O conteudo lido vem cercado por marcadores de conteudo nao confiavel.** Um
   PDF pode conter uma frase escrita pra dar ordem a quem le. O trecho e prova
   do que ha no arquivo, nunca instrucao pro agente.
"""
import argparse, json, os, re, sys, time, unicodedata

HOME = os.environ.get("HERMES_HOME", "/var/lib/hermes")
CONFIG = os.path.join(HOME, "finder", "config.json")

OPEN, CLOSE = "<<<ARQUIVO_NAO_CONFIAVEL>>>", "<<<FIM_ARQUIVO_NAO_CONFIAVEL>>>"
STRIP = re.compile(r"<<<\s*/?\s*(FIM_)?ARQUIVO_NAO_CONFIAVEL\s*>>>", re.I)

# Nunca listado, nunca lido, nunca entregue. Nao e configuravel de proposito:
# uma lista de negacao que o proprio chat pode afrouxar nao e uma lista de
# negacao, e um pedido educado. Quem quiser mandar a propria chave privada pra
# si mesmo tem `scp`, que nao depende de convencer um modelo.
SEGREDO = re.compile(r"""
    (^|/)\.ssh(/|$)          | (^|/)\.gnupg(/|$)      | (^|/)\.aws(/|$)
  | (^|/)\.docker(/|$)       | (^|/)\.kube(/|$)       | (^|/)\.config/gh(/|$)
  | (^|/)\.env($|\.)         | (^|/)\.netrc$          | (^|/)\.npmrc$
  | (^|/)id_(rsa|dsa|ecdsa|ed25519) | \.(pem|key|p12|pfx|jks|keystore|kdbx|ppk)$
  | (^|/)credentials?($|\.)  | (^|/)secrets?($|\.)    | (^|/)plow-credentials$
  | (^|/)Library/Keychains(/|$)  | \.keychain(-db)?$
  | (^|/)Library/(Cookies|Application\ Support/(Google|Firefox|BraveSoftware))(/|$)
  | (^|/)\.mozilla(/|$)      | (^|/)\.password-store(/|$)
""", re.I | re.X)

# Ruido de build e cache. Diferente do SEGREDO: isto e configuravel, porque e
# gosto (alguem PODE querer procurar dentro de um venv), enquanto aquilo nao e.
RUIDO_PADRAO = ["node_modules", ".git", ".venv", "venv", "__pycache__", ".cache",
                "site-packages", ".trash", "library", "applications", ".ds_store",
                "target/debug", ".next", "dist/.vite", ".gradle", ".m2"]

TEXTO = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
         ".toml", ".ini", ".cfg", ".log", ".tex", ".bib", ".html", ".xml",
         ".py", ".jl", ".pl", ".lean", ".r", ".m", ".c", ".h", ".cpp", ".rs",
         ".go", ".js", ".ts", ".tsx", ".sh", ".sql", ".rb", ".java", ".swift"}

CONTEUDO_MAX = 2 * 1024 * 1024   # ler dentro de arquivo maior que isso custa
SNIPPET = 240                     # mais do que o resultado vale
MAX_VARRIDOS = 400_000            # teto duro em arquivos vistos

# O teto que realmente importa e o RELOGIO, nao a contagem. Isto foi medido, nao
# estimado: apontar a busca pra uma home inteira num Mac com Fotos e Library
# passou de um minuto e derrubou a sessao que estava testando. Uma contagem de
# arquivos nao protege disso -- um diretorio de rede lento gasta o mesmo minuto
# em mil arquivos. O dono esta esperando no celular; uma resposta parcial em 25
# segundos vale mais que a resposta completa que ele nao vai esperar, e o
# `status` da saida diz qual das duas ele recebeu.
ORCAMENTO_PADRAO = 25.0


def carregar_config():
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        sys.exit(f"find: nao consegui ler {CONFIG} ({type(exc).__name__})")


# Onde o compose monta as pastas do dono. Sobrescritivel por ambiente pra que os
# scripts rodem fora do container -- e como eles foram testados contra arquivos
# de verdade antes de existir imagem.
MONTAGENS = os.environ.get("FINDER_MOUNT_BASE", "/files")
LETRAS = ("a", "b", "c", "d")


def montadas():
    """O que o compose montou DE VERDADE, lido do disco e nao da config.

    Existe separado de `raizes()` por causa da ordem em que as coisas nascem: o
    setup precisa dizer ao dono quais pastas ele conseguiu montar ANTES de haver
    config -- e a config e escrita a partir desta lista.

    Um mount cujo `FINDER_ROOT_` ficou em branco no `.env` nao falha o `up`: o
    Docker cria o destino como diretorio VAZIO quando a origem nao existe. Por
    isso "montado" aqui e "existe e tem alguma coisa dentro", e nao apenas
    "existe" -- senao os tres slots aparecem sempre, e o dono e informado de que
    o agente enxerga tres pastas que nao existem.
    """
    saida = []
    for letra in LETRAS:
        ponto = os.path.join(MONTAGENS, letra)
        try:
            if not os.path.isdir(ponto) or not os.listdir(ponto):
                continue
        except OSError:
            continue
        host = (os.environ.get("FINDER_ROOT_" + letra.upper()) or "").strip()
        saida.append({"mount": os.path.realpath(ponto), "slot": letra,
                      "label": os.path.basename(host.rstrip("/")) or letra.upper(),
                      "host": host})
    return saida


def raizes(config):
    """As raizes ATIVAS: montadas de verdade e nao desligadas na config.

    Sem config (antes do setup) valem todas as montadas. Isso nao e permissivo:
    quem montou foi o dono, editando o `.env` e reiniciando o container. A
    config estreita depois; ela nao e o que autoriza.
    """
    disponiveis = {m["mount"]: m for m in montadas()}
    declaradas = config.get("roots") or []
    if not declaradas:
        return list(disponiveis.values())
    saida = []
    for raiz in declaradas:
        ponto = raiz.get("mount")
        if not ponto or raiz.get("enabled") is False:
            continue
        real = os.path.realpath(ponto)
        # Declarada na config e o diretorio existe: vale. Nao ha "autorizacao"
        # a fazer aqui -- quem autoriza e o mount, e dentro do container nao ha
        # caminho algum que o compose nao tenha montado. Um slot que sumiu da
        # lista de montadas (o `.env` mudou depois do setup) cai fora sozinho
        # porque o diretorio deixa de existir.
        if not os.path.isdir(real):
            continue
        conhecida = disponiveis.get(real, {})
        saida.append({"mount": real,
                      "label": raiz.get("label") or conhecida.get("label") or os.path.basename(real),
                      "host": raiz.get("host") or conhecida.get("host") or ""})
    return saida


def dentro(caminho, pontos):
    """True quando o caminho REAL cai dentro de uma raiz registrada.

    realpath antes de comparar, sempre. Sem isso, um symlink dentro da pasta do
    dono apontando pra `/` transforma uma raiz registrada em toda a maquina --
    e symlink e exatamente o tipo de coisa que aparece numa pasta de projeto
    sem ninguem ter posto ali de proposito.
    """
    real = os.path.realpath(caminho)
    return any(real == p or real.startswith(p + os.sep) for p in pontos)


def normal(texto):
    """Sem acento e em minuscula: quem digita no celular escreve 'contrato
    assinatura' pra achar 'Contrato-Assinatura.pdf', e escreve sem acento."""
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def termos(consulta):
    return [t for t in re.split(r"[^\w]+", normal(consulta)) if len(t) > 1]


def prazo(desde):
    """--since aceita 7d, 12h, 3w, 6m. Um numero solto e dias."""
    if not desde:
        return 0.0
    m = re.fullmatch(r"(\d+)\s*([hdwm]?)", desde.strip().lower())
    if not m:
        sys.exit("find: --since aceita 12h, 7d, 3w, 6m")
    n, unidade = int(m.group(1)), m.group(2) or "d"
    return time.time() - n * {"h": 3600, "d": 86400, "w": 604800, "m": 2592000}[unidade]


def trecho(caminho, tamanho):
    if tamanho > CONTEUDO_MAX:
        return ""
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as fh:
            bruto = fh.read(CONTEUDO_MAX)
    except Exception:
        return ""
    return re.sub(r"\s+", " ", STRIP.sub("", bruto)).strip()


def pontuar(nome, relativo, palavras, mtime, ext_pedida, corpo):
    """Nome vale mais que pasta, e recente desempata.

    O peso maior no NOME e o que faz "manda o contrato da ana" achar
    `contrato-ana.pdf` em vez dos quarenta arquivos que moram em `~/ana/`. A
    recencia entra pequena de proposito: ela desempata, nao decide -- quem pede
    um arquivo por mensagem quase sempre quer um que existe ha meses.
    """
    nome_n, rel_n = normal(nome), normal(relativo)
    nota = 0.0
    for palavra in palavras:
        if palavra in nome_n:
            nota += 3.0 + (1.5 if re.search(r"(^|[^a-z0-9])" + re.escape(palavra), nome_n) else 0)
        elif palavra in rel_n:
            nota += 1.0
        if corpo and palavra in corpo:
            nota += 2.0
    if not nota:
        return 0.0
    if ext_pedida and nome_n.endswith("." + ext_pedida.lower().lstrip(".")):
        nota += 2.0
    idade_dias = max(0.0, (time.time() - mtime) / 86400)
    return nota + max(0.0, 1.5 - idade_dias / 120)


def varrer(args, config):
    pontos = [r["mount"] for r in raizes(config)]
    if not pontos:
        return [], "sem-raiz"
    rotulos = {r["mount"]: r["label"] for r in raizes(config)}
    if args.root:
        alvo = normal(args.root)
        pontos = [p for p in pontos if alvo in normal(rotulos[p]) or alvo in normal(p)]
        if not pontos:
            return [], "raiz-desconhecida"

    palavras = termos(args.query)
    ruido = [normal(x) for x in (config.get("excludes") or RUIDO_PADRAO)]
    limite_mtime = prazo(args.since)
    ext = (args.ext or "").lower().lstrip(".")
    achados, vistos, varridos = [], set(), 0
    limite_relogio = time.monotonic() + max(2.0, args.budget)

    for ponto in pontos:
        for pasta, subpastas, arquivos in os.walk(ponto, followlinks=False):
            rel_pasta = normal(os.path.relpath(pasta, ponto))
            # Podar a arvore, nao filtrar depois: `node_modules` tem dezenas de
            # milhares de arquivos e descer nele custa segundos por raiz.
            subpastas[:] = [s for s in subpastas
                            if not s.startswith(".")
                            and not SEGREDO.search(os.path.join(rel_pasta, normal(s)))
                            and not any(r in normal(s) or r in rel_pasta for r in ruido)]
            if time.monotonic() > limite_relogio:
                return sorted(achados, key=lambda a: -a["score"])[:args.limit], "orcamento"
            for nome in arquivos:
                varridos += 1
                if varridos > MAX_VARRIDOS:
                    return sorted(achados, key=lambda a: -a["score"])[:args.limit], "teto"
                if nome.startswith("."):
                    continue
                caminho = os.path.join(pasta, nome)
                relativo = os.path.relpath(caminho, ponto)
                if SEGREDO.search("/" + relativo) or SEGREDO.search("/" + nome):
                    continue
                if ext and not normal(nome).endswith("." + ext):
                    continue
                try:
                    st = os.stat(caminho)          # stat, nao lstat: um link
                except OSError:                    # quebrado sai da lista aqui
                    continue
                if not os.path.isfile(caminho) or st.st_mtime < limite_mtime:
                    continue
                if not dentro(caminho, pontos):    # symlink pra fora do mount
                    continue
                real = os.path.realpath(caminho)
                if real in vistos:                 # a mesma pasta montada duas
                    continue                       # vezes nao vira dois hits
                corpo = ""
                if args.content and os.path.splitext(nome)[1].lower() in TEXTO:
                    corpo = normal(trecho(caminho, st.st_size))
                nota = pontuar(nome, relativo, palavras, st.st_mtime, ext, corpo)
                if nota <= 0:
                    continue
                vistos.add(real)
                achados.append({
                    "path": caminho,
                    "name": nome,
                    "root": rotulos[ponto],
                    "relative": relativo,
                    "size_bytes": st.st_size,
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                    "score": round(nota, 2),
                    "snippet": (OPEN + corpo[:SNIPPET] + CLOSE) if corpo else "",
                })
    return sorted(achados, key=lambda a: -a["score"])[:args.limit], "ok"


def humano(n):
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024.0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query", nargs="?", default="", help="as palavras que o dono usou")
    parser.add_argument("--ext", default="", help="so esta extensao (pdf, xlsx, py)")
    parser.add_argument("--since", default="", help="mexido nos ultimos 7d / 12h / 3w / 6m")
    parser.add_argument("--root", default="", help="so nesta raiz, pelo rotulo")
    parser.add_argument("--content", action="store_true",
                        help="tambem procura DENTRO de arquivos de texto (mais lento)")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--budget", type=float, default=ORCAMENTO_PADRAO,
                        help="segundos de varredura antes de devolver o que ja achou")
    parser.add_argument("--roots", action="store_true", help="lista as raizes ativas e sai")
    args = parser.parse_args(argv)

    config = carregar_config()
    if args.roots:
        print(json.dumps({"roots": raizes(config)}, ensure_ascii=False, indent=2))
        return 0
    if not args.query and not args.since:
        sys.exit("find: sem consulta e sem --since nao ha o que procurar")

    achados, estado = varrer(args, config)
    if estado == "sem-raiz":
        print(json.dumps({"status": "sem-raiz", "results": []}, ensure_ascii=False))
        return 0
    for achado in achados:
        achado["size"] = humano(achado["size_bytes"])
    print(json.dumps({"status": estado, "count": len(achados), "results": achados},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
