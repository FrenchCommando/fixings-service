# CLAUDE.md — fixings-service (operations & deploy guide for an AI agent)

This file tells a Claude working **in this repo** how to change, build, and deploy the
service correctly. For *why* the code is shaped the way it is, read `VISION.md` (goals) and
`NOTES.md` (decisions). This file is the **how-to-ship**; those are the rationale.

The app is a small aiohttp service (`python -m service`, port **5000**) that serves EOD
"fixings" from Postgres, backfilling on a miss from ThetaData (`thetadata`, native gRPC) with
yfinance as a backup source. It runs behind the **proxy-auth** Authelia stack as
`data.volatility.fit` (policy `two_factor`).

---

## 1. The deploy target is NOT a normal arm64 box — read before building

The production host is a Raspberry Pi at `frenchcommando@raspberrypi` with a **64-bit kernel
but a 32-bit (armv7l) userspace** (`uname -m`=aarch64, `getconf LONG_BIT`=32). Docker there is
the old **20.10**. This breaks the obvious build paths:

- **NEVER build this image natively on the Pi.** Docker pulls `armv7l` wheels; `thetadata`
  hard-depends on `polars>=1.33.1`, and **polars does not compile on 32-bit ARM** (its Rust dep
  `argminmax` fails with hundreds of NEON type errors). No apt `-dev` lib fixes it; there are no
  armv7 polars wheels. A native `docker compose up --build` on the Pi WILL fail, after a long
  compile. Don't try it, and don't try to "add more build deps."
- **NEVER force `platform: linux/arm64` for a *native* Pi build** — the old Docker hits a
  seccomp SIGSYS on arm64 binaries.

The kernel is 64-bit, though, so the Pi **runs** a prebuilt **arm64** image fine (with
`security_opt: [seccomp=unconfined]`). So we build arm64 elsewhere and ship it.

## 2. How to build & deploy — arm64 cross-build from the Windows desktop (the ONLY supported path)

### The build environment: WSL2 on the Windows desktop

The cross-build runs in **WSL2 Ubuntu** on the Windows machine (`C:\Users\Martial`), NOT in
Docker Desktop (we use Docker Engine directly inside the distro). Facts a local Claude needs:

- **Distro:** `Ubuntu` (WSL2). List/inspect from Windows cmd with `wsl -l -v`; it may show
  `Stopped` — any `wsl -d Ubuntu -- ...` command starts it on demand.
- **Run commands in it from Windows cmd** via: `wsl -d Ubuntu -- bash -lc "<cmd>"`. The Windows
  drive is mounted at `/mnt/c`, so this repo is `/mnt/c/Users/Martial/fixings-service`. Build
  from there (NOT from a copy inside the distro) so you're shipping the real working tree.
- **Docker:** Engine (Community, ~29.x) installed *inside* Ubuntu via `get.docker.com`. Ubuntu
  here has **systemd**, so `dockerd` auto-starts and survives — no manual daemon start needed.
  If it's ever down: `wsl -d Ubuntu -- bash -lc "sudo systemctl status docker"`.
- **sudo:** the Linux user is `claudeuser` and is **not** in the `docker` group, so docker
  commands need `sudo` (you'll be prompted for claudeuser's password the first time per shell).
  Keep using `sudo docker ...` consistently — a builder created under sudo (root) and one under
  the plain user are separate. (Optional cleanup: `sudo usermod -aG docker claudeuser` then
  restart the distro to drop the sudo.)
- **Lost the WSL sudo password?** Reset it without knowing it (root needs no password via wsl):
  `wsl -d Ubuntu -u root passwd claudeuser`.
- **Docker Desktop is intentionally NOT used.** Don't install it or switch contexts; the
  engine-in-WSL setup above is the supported one. (Docker Desktop would also work — buildx +
  emulation come preconfigured — but we don't rely on it.)

Prereq (one-time): Docker Engine + buildx in WSL Ubuntu, and arm64 emulation registered:
```
# in WSL Ubuntu, once (sudo password = claudeuser's):
curl -fsSL https://get.docker.com | sh          # ignore its "use Docker Desktop" WSL warning; it installs the engine anyway
sudo docker run --privileged --rm tonistiigi/binfmt --install arm64   # register QEMU so amd64 can build arm64
sudo docker buildx create --name armbuilder --driver docker-container --use   # cross-capable builder w/ tar export
sudo docker buildx inspect --bootstrap          # confirm Platforms lists linux/arm64
```

Build + ship + run (the repeatable cycle — use this after ANY code change):
```
# 1. cross-build an arm64 image to a tar (run from Windows cmd):
wsl -d Ubuntu -- bash -lc "cd /mnt/c/Users/Martial/fixings-service && sudo docker buildx build --platform linux/arm64 -t fixings-service:arm64 -o type=docker,dest=fixings-arm64.tar ."

# 2. copy it to the Pi:
scp "C:\Users\Martial\fixings-service\fixings-arm64.tar" frenchcommando@raspberrypi:~/fixings-service/

# 3. on the Pi: load and recreate just the app (db untouched):
#    ssh frenchcommando@raspberrypi
cd ~/fixings-service && docker load -i fixings-arm64.tar && docker compose up -d --force-recreate app
```
All deps (numpy/pandas/grpcio/asyncpg/zstandard/**polars**) are prebuilt aarch64 wheels, so the
build is ~2 min with no compilation. The `platform (linux/arm64) does not match host
(linux/arm/v7)` warning on the Pi is **expected and harmless** — the 64-bit kernel runs it.

The Pi's `compose.yml` `app` service must use the prebuilt image, NOT a local build:
```yaml
  app:
    image: fixings-service:arm64
    security_opt:
      - seccomp=unconfined
```
(The committed `compose.yml` may still say `build: .` for local/dev use; the Pi copy is edited
to `image:` as above. Don't "helpfully" revert the Pi to `build:`.)

The `Dockerfile` is the clean `python:3.13-slim` one — it needs **no** build toolchain and
**no** polars stub, *because* we build for arm64 where wheels exist. Keep it that way.

## 3. Reverse-proxy contract — links MUST be root-relative

The service is served behind nginx + Authelia at `https://data.volatility.fit`. The browser
never talks to the container directly. Therefore:

- **Any URL the app emits to the browser must be root-relative** (`/all`, `/date/2025-08-08`),
  never absolute (`http://localhost:5000/...`). An absolute `localhost:5000` link is a bug — it
  points the browser at its own machine. The front page is `index.html`, served verbatim by
  `service.py::index_handler`; its `<a href>`s are the usual offender. (Fixed once already.)
- The app listens on **5000** and publishes **no host ports** — reachability is via the `proxy`
  network only (proxy-auth invariant). Don't add `ports:`.
- Don't add auth in the app; Authelia handles it at the edge.

To verify the proxy path without a browser, from the Pi:
```
curl -sI -H "Host: data.volatility.fit" -H "X-Forwarded-Proto: https" http://127.0.0.1:8080/
```
Expect `302` to `auth.volatility.fit` (the `X-Forwarded-Proto: https` header is REQUIRED or
Authelia 4.39 rejects the scheme and nginx 500s). If you changed `index.html`, confirm the
deployed file with `docker compose exec app cat /app/index.html | grep href` — and remember a
stale page in the browser is usually just cache (hard-refresh, Ctrl+Shift+R).

## 4. Secrets & config (never commit these)

Config is env-only; secrets are mounted files, generated on the Pi, gitignored:
`secrets/db_password` (shared by app + postgres) and `secrets/theta_creds.json`
(`{"email","password"}` for ThetaData). See `.env.example` and `NOTES.md` §"Config & secrets".
`python-dotenv` stays in `requirements.txt` to work around a thetadata 1.0.9 packaging bug
(see NOTES.md) even though our code never imports it.

## 5. Open items (as of 2026-06-29)

- ~~The root-relative `index.html` fix may be uncommitted~~ — **committed.** ✓
- ~~Confirm the edge has `data.volatility.fit` cert~~ — **cert is working.** ✓
- **Seeding** the `fixings` DB: a fresh DB returns "No entry found" until populated. Bootstrap
  it with the bundled seeder — `docker compose exec app python -m seed` — which fetches the last
  364 days for every symbol in `seed_tickers.txt` (registers the tickers AND fills history; `/refresh`
  only re-fetches tickers *already* in the table, so it's a no-op on an empty DB). Idempotent —
  re-run after editing the list. A single ad-hoc symbol can still be seeded by hitting its
  `/entry/{ticker}/{date}` URL once. Needs ThetaData creds (the seeder fetches from the source).
