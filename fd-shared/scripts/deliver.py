#!/usr/bin/env python3
# Copyright 2026 Gabriel Ribeiro
# SPDX-License-Identifier: Apache-2.0
"""deliver.py -- manda UM arquivo que o dono aprovou pelo nome.

Caminho principal: anexo de verdade no iMessage. A API da Plow tem tres passos
-- declarar o anexo, subir os bytes numa URL assinada, e so entao mandar a
mensagem citando o uid. Este script faz os tres e para no primeiro que falhar,
porque a ordem importa: a mensagem sai com 201 mesmo se o upload tiver
falhado, e ai o dono recebe uma bolha vazia dizendo "segue o arquivo". Foi o
primeiro erro que apareceu testando isto contra a API de verdade.

A segunda armadilha, do mesmo teste: a URL de upload e uma URL ASSINADA da
S3. Mandar o `Authorization: Bearer` da Plow junto faz a S3 responder 400
InvalidArgument ("only one auth mechanism allowed"). O PUT leva os
`upload_headers` que a Plow devolveu e MAIS NADA.

Separado do find.py de proposito, e o motivo e o mesmo que separa buscar de
enviar em qualquer agente que toca coisa do dono: a busca e barata, roda o
tempo todo e nao tem consequencia; a entrega tira uma copia de um arquivo dele
da maquina dele. Duas capacidades em dois arquivos e o que torna a frase "ele
so manda o que voce mandou ele mandar" conferivel por quem le o repo em vez de
uma promessa no README. Este script nunca esta num cron, e nao existe caminho
que o chame sozinho.
"""
import argparse, json, mimetypes, os, re, ssl, smtplib, sys, tempfile, time
import urllib.error, urllib.request, zipfile
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find import SEGREDO, carregar_config, dentro, raizes, humano   # noqa: E402

MAX_BYTES = 100 * 1024 * 1024        # o teto da propria Plow: 100 MiB
API_PADRAO = "https://api.plow.co"

# O `content_type` do anexo nao e livre: a Plow so aceita os valores desta
# lista, e ela e a lista do que o iMessage sabe exibir. Um `.py` nao esta nela
# -- mas um `.py` E texto, entao ele viaja como text/plain com o nome
# preservado. O que nao e texto e nao esta na lista vira um .zip, e o agente diz
# isso na mensagem em vez de deixar o dono descobrir sozinho.
PERMITIDO = {
    ".pdf": "application/pdf", ".epub": "application/epub+zip",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pages": "application/x-iwork-pages-sffpages",
    ".numbers": "application/x-iwork-numbers-sffnumbers",
    ".key": None,   # NUNCA: .key e chave privada antes de ser Keynote. Vai zipado.
    ".zip": "application/zip", ".gz": "application/x-gzip",
    ".json": "application/json", ".csv": "text/csv", ".md": "text/markdown",
    ".txt": "text/plain", ".rtf": "text/rtf", ".html": "text/html",
    ".xml": "text/xml", ".ics": "text/calendar", ".vcf": "text/vcard",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".heic": "image/heic", ".heif": "image/heif",
    ".webp": "image/webp", ".tiff": "image/tiff", ".tif": "image/tiff",
    ".bmp": "image/bmp", ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".mp3": "audio/mp3", ".m4a": "audio/x-m4a", ".wav": "audio/x-wav",
    ".aac": "audio/aac", ".aiff": "audio/aiff", ".mid": "audio/midi",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
    ".avi": "video/x-msvideo", ".mpeg": "video/mpeg", ".3gp": "video/3gpp",
}
TEXTO_PLANO = {".py", ".jl", ".pl", ".lean", ".tex", ".bib", ".yaml", ".yml",
               ".toml", ".ini", ".cfg", ".log", ".sh", ".sql", ".r", ".c", ".h",
               ".cpp", ".rs", ".go", ".js", ".ts", ".tsx", ".rb", ".java",
               ".swift", ".m", ".tsv", ".markdown", ".srt", ".conf"}


def env(*nomes):
    for nome in nomes:
        valor = (os.environ.get(nome) or "").strip()
        if valor:
            return valor
    return ""


def conferir(caminho, config):
    """As tres perguntas antes de qualquer byte sair daqui."""
    real = os.path.realpath(caminho)
    if not os.path.isfile(real):
        sys.exit(f"deliver: {caminho} nao e um arquivo que eu consiga abrir")
    pontos = [r["mount"] for r in raizes(config)]
    if not pontos:
        sys.exit("deliver: nenhuma raiz montada -- nao ha de onde mandar arquivo")
    if not dentro(real, pontos):
        # A mensagem nao ecoa o caminho pedido: um caminho recusado costuma vir
        # de dentro de um arquivo, e repetir ele no chat e repetir o texto de
        # quem escreveu aquele arquivo.
        sys.exit("deliver: esse caminho esta fora das pastas registradas. Recusando.")
    if SEGREDO.search("/" + real) or SEGREDO.search("/" + os.path.basename(real)):
        sys.exit("deliver: esse arquivo esta na lista do que nunca sai daqui. Recusando.")
    tamanho = os.path.getsize(real)
    if tamanho == 0:
        sys.exit("deliver: o arquivo esta vazio")
    return real, tamanho


def empacotar(caminho):
    """Zipa o que o iMessage nao sabe exibir, preservando o nome de dentro."""
    destino = os.path.join(tempfile.mkdtemp(prefix="finder-"),
                           os.path.basename(caminho) + ".zip")
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(caminho, arcname=os.path.basename(caminho))
    return destino


def tipo(caminho):
    """Devolve (caminho_a_enviar, content_type, foi_zipado)."""
    ext = os.path.splitext(caminho)[1].lower()
    permitido = PERMITIDO.get(ext)
    if permitido:
        return caminho, permitido, False
    if ext in TEXTO_PLANO:
        return caminho, "text/plain", False
    zipado = empacotar(caminho)
    return zipado, "application/zip", True


def http(url, dados=None, metodo="GET", headers=None, cru=False, timeout=120):
    cabecalhos = dict(headers or {})
    corpo = None
    if dados is not None and cru:
        corpo = dados
    elif dados is not None:
        corpo = json.dumps(dados).encode("utf-8")
        cabecalhos["content-type"] = "application/json"
    pedido = urllib.request.Request(url, data=corpo, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            texto = resposta.read().decode("utf-8", "replace")
            return resposta.status, texto
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        # Sem traceback: um traceback do urllib carrega a URL assinada inteira.
        sys.exit(f"deliver: nao consegui alcancar o servidor ({type(exc).__name__})")


def por_chat(caminho, nota):
    """Os tres passos, na ordem, parando no primeiro que falhar."""
    base = (env("PLOW_API_BASE") or API_PADRAO).rstrip("/")
    chat = env("PLOW_HOME_CHANNEL", "PLOW_CHAT_CHAT_UID")
    token = env("PLOW_AGENT_TOKEN", "PLOW_CHAT_TOKEN")
    if not chat or not token:
        sys.exit("deliver: sem configuracao de chat neste ambiente. Recusando ANTES\n"
                 "  de subir bytes: um upload que nao vira mensagem deixa uma copia\n"
                 "  do arquivo do dono num bucket e nao entrega nada. Rode isto de\n"
                 "  dentro de um turno, que herda o ambiente do gateway.")
    auth = {"authorization": "Bearer " + token}

    enviar, content_type, zipado = tipo(caminho)
    bytes_ = open(enviar, "rb").read()
    if len(bytes_) > MAX_BYTES:
        sys.exit(f"deliver: {humano(len(bytes_))} passa do teto de 100 MiB do anexo")

    status, corpo = http(f"{base}/v1/chats/{chat}/attachments",
                         {"filename": os.path.basename(enviar),
                          "content_type": content_type,
                          "size_bytes": len(bytes_)}, "POST", auth)
    if status != 201:
        sys.exit(f"deliver: a Plow recusou declarar o anexo ({status})")
    anexo = json.loads(corpo)

    # SO os headers que a Plow devolveu. Mandar o Bearer dela junto faz a S3
    # responder 400 InvalidArgument -- duas autenticacoes na mesma requisicao.
    status, _ = http(anexo["upload_url"], bytes_, "PUT", anexo["upload_headers"], cru=True)
    if status not in (200, 201, 204):
        sys.exit(f"deliver: o upload dos bytes falhou ({status}); nao vou mandar a\n"
                 "  mensagem, porque ela sairia com uma bolha vazia anexada")

    status, corpo = http(f"{base}/v1/chats/{chat}/messages",
                         {"body": nota, "attachment_uids": [anexo["uid"]]}, "POST", auth)
    if status != 201:
        sys.exit(f"deliver: os bytes subiram mas a mensagem nao saiu ({status})")
    print(f"deliver: enviado pelo chat -- {os.path.basename(enviar)} "
          f"({humano(len(bytes_))}){', zipado' if zipado else ''}")
    return 0


def por_email(caminho, nota):
    destino = env("FINDER_EMAIL_TO", "SMTP_FROM", "IMAP_USER")
    host = env("SMTP_HOST")
    senha = env("SMTP_PASSWORD")
    usuario = env("SMTP_USER", "SMTP_FROM", "IMAP_USER")
    if not (destino and host and senha and usuario):
        sys.exit("deliver: o modo e-mail precisa de SMTP_HOST, SMTP_USER, SMTP_PASSWORD\n"
                 "  e FINDER_EMAIL_TO no .env -- veja o .env.example do repo")
    mensagem = EmailMessage()
    mensagem["From"] = env("SMTP_FROM", "SMTP_USER")
    mensagem["To"] = destino
    mensagem["Subject"] = f"[finder] {os.path.basename(caminho)}"
    mensagem.set_content(nota or "Segue o arquivo que voce pediu por mensagem.")
    palpite = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
    principal, _, sub = palpite.partition("/")
    with open(caminho, "rb") as fh:
        mensagem.add_attachment(fh.read(), maintype=principal, subtype=sub or "octet-stream",
                                filename=os.path.basename(caminho))
    try:
        with smtplib.SMTP(host, int(env("SMTP_PORT") or 587), timeout=60) as servidor:
            servidor.starttls(context=ssl.create_default_context())
            servidor.login(usuario, senha)
            servidor.send_message(mensagem)
    except smtplib.SMTPAuthenticationError:
        sys.exit("deliver: o servidor SMTP recusou o login (conta com 2FA precisa de senha de app)")
    except Exception as exc:
        sys.exit(f"deliver: nao consegui enviar o e-mail ({type(exc).__name__})")
    print(f"deliver: enviado por e-mail pra {destino} -- {os.path.basename(caminho)}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", required=True, help="o arquivo que o dono aprovou")
    parser.add_argument("--mode", default="", choices=["", "chat", "email"],
                        help="vazio = o que estiver na config (padrao: chat)")
    parser.add_argument("--note", default="", help="a linha que vai junto do anexo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    config = carregar_config()
    real, tamanho = conferir(args.path, config)
    modo = args.mode or (config.get("delivery") or "chat")
    if modo not in ("chat", "email"):
        modo = "chat"
    nota = args.note.strip() or f"segue o {os.path.basename(real)}"

    if args.dry_run:
        enviar, content_type, zipado = tipo(real)
        print(json.dumps({"mode": modo, "file": os.path.basename(real),
                          "size": humano(tamanho), "content_type": content_type,
                          "zipped": zipado, "note": nota}, ensure_ascii=False))
        return 0
    return por_chat(real, nota) if modo == "chat" else por_email(real, nota)


if __name__ == "__main__":
    raise SystemExit(main())
