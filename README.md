# Finder SMS

**The file is on your computer. You are not. Text it the description and it
texts back the file — as a real attachment.**

You're on the train, at a client's office, standing in a queue. Someone needs
the signed contract, the invoice, the slide from last quarter. It's sitting on
the machine at home, twelve metres and four hours away.

```
you:   manda o pdf do contrato que a ana assinou
agent: two contracts with Ana's name:
       1. contrato-ana-assinado.pdf — Documents/juridico, 14 May
       2. contrato-ana-v2.pdf — Downloads, 2 May
       which one?
you:   1
agent: [contrato-ana-assinado.pdf — 240 KB]
       found it: Documents/juridico, last touched 14 May.
```

That last line is not a link and not a screenshot. It's the file, in the
message, the way a person would have sent it to you.

## Read-only is not a promise here

Your folders are mounted `:ro`. That is the kernel refusing writes, not a
sentence in a README. This agent cannot rename, move, tidy, or delete anything
of yours — there is no chat command for it, because there is no code path for
it. Ask it to and it tells you it can only read.

**It never leaves the folders you named.** Every path is resolved with
`realpath` and checked against your roots *before* it is opened, so a symlink
pointing out of the mount drops off the list instead of becoming a door.

**Some things it will never show you, even when you ask by name.** Private keys,
`.env` files, keychains, wallets, browser cookies. They don't appear in results,
they can't be delivered, and no message can widen that list — it lives in code,
not config, and you can read it in
[`find.py`](fd-shared/scripts/find.py#L45). An agent that can be talked into
texting an SSH key is an agent that shouldn't be installed.

**Finding and sending are different files.** `find.py` reads and ranks;
`deliver.py` is the only thing that puts a copy of your file anywhere, it is in
no cron, and nothing calls it until you've said which file you meant. You can
check that by reading the repo rather than trusting this paragraph.

## No clock runs it

There's no polling loop and no scheduled job — the container ships one
supervised service and it's the usage reporter. The agent wakes when you ask for
a file and never otherwise.

That's on purpose twice over. A search agent that crawls your folders hourly
would burn tokens with no work behind them *and* read files nobody asked about.
Here the cost tracks the request.

## How the file actually gets to you

**As an attachment in the chat** (default). Three steps against the Plow API:
declare the attachment, PUT the bytes to a signed URL, then send the message
citing it. Nothing else to configure — it uses the credential the container
already holds. Ceiling is **100 MiB**, and anything iMessage can't display (a
`.tar`, a `.whl`) is zipped first and the agent says so.

**By email** (optional). An app password in `.env` and it attaches the file to a
mail instead. Useful when the file is big, or when you want it on a laptop
rather than a phone.

**Ask me every time.** For people whose data plan has opinions.

Change it whenever, in the chat: `/config-file-sending`, or just say "send by
email from now on".

## Install (about 5 minutes)

### Before you start (2 minutes, once per machine)

You need **Docker**, **git**, **Python 3**, and a **Plow account**. Then:

```sh
git clone https://github.com/plow-pbc/plow-agents.git
export PATH="$PWD/plow-agents/bin:$PATH"
plow-agents login     # authenticates by texting you a code
```

If you've already done this for another agent, skip it.

### 1. Get the agent a phone line

```sh
plow-agents lines            # pick a free ln_... id
plow-agents mint ln_xxxxx    # writes ./plow-credentials — run it BEFORE `up`
```

### 2. Clone, point it at a folder, start

```sh
git clone https://github.com/gabe-rbo/finder-sms-hermes-agent.git
cd finder-sms-hermes-agent
mv ../plow-credentials .     # or run `mint` from inside this directory
cp .env.example .env
$EDITOR .env                 # set FINDER_ROOT_A to a folder you want reachable
docker compose up --build -d
```

`FINDER_ROOT_A` is the only line you have to fill in. Start with one real
folder — `~/Documents`, or wherever your work actually lives. You can point it
at your whole home directory, but don't: the search stops at a 25-second budget
and hands you a partial answer, and a narrow root finds the right file faster.

The first build pulls the Plow base image and takes a few minutes. After that:

```sh
docker compose logs -f agent   # wait for the gateway to come up
```

### 3. Text it

Text the number `plow-agents lines` showed you. Say anything — `oi`, `hey`. It
tells you which folders it can reach and asks how you want files delivered.
**Nothing is configured by editing files** except which folders exist, and that
one is deliberate: mounting a new path should take a restart you performed, not
a sentence someone texted to that number.

### Stopping

```sh
docker compose down       # keeps its memory and setup
docker compose down -v    # forgets everything, starts fresh
plow-agents revoke        # releases the line
```

## When it doesn't work

**`no such file or directory: ./plow-credentials`** — you ran `docker compose up`
before `plow-agents mint`. Compose created a *directory* at that path. Remove it,
run `mint`, then `up` again:

```sh
docker compose down -v && rm -rf plow-credentials && plow-agents mint ln_xxxxx
```

**It says it can't see any folders** — `FINDER_ROOT_A` is empty, or points
somewhere that doesn't exist. A bind mount with a missing source doesn't fail the
`up`; Docker quietly creates an empty directory, which is why the agent reports
this in the chat instead of the container dying. Fix `.env`, then
`docker compose up -d`.

**It finds nothing, and the folder definitely has the file** — check whether the
name is what you think. Try the content search by describing what's *written
inside* ("the pdf that talks about Lyapunov") rather than the filename.

**The build fails pulling the base image** — `docker logout public.ecr.aws`. A
stale credential in Docker's config makes an anonymous public pull fail.

**The attachment never arrives** — `docker compose logs agent | grep deliver`.
The three delivery steps fail loudly and in order; the agent will not send the
message if the upload failed, because that would hand you an empty bubble saying
"here's your file".

**Nothing shows up on the Agent Index** — the reporter runs every 5 minutes, not on boot.
`docker compose logs agent | grep agent-index` tells you what it did.

## The Agent Index

The Plow base image ships the AI Worth Using usage reporter as a supervised service. It
registers once and reports token counts every 5 minutes, and it reports **nothing else** —
no prompts, no message text, and in particular **no file names and no paths**.
The `AGENT_ID` in `compose.yml` is what it reports under.

## License

Apache-2.0. Built on the Plow Hermes base image (Apache-2.0, © 2026 The Plow
Collective) and Nous Research's Hermes Agent. Not affiliated with either;
"Plow" and "Hermes" are their marks and this license grants no rights to them.
