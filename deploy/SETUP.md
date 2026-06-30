# SETUP — deploy fixings-service on the Raspberry Pi

Runbook for deploying as an app behind the [`proxy-auth`](../../proxy-auth) Authelia/nginx stack.
The flow has three layers, same as `proxy-auth/sample-app`: bring up the fixings stack, wire it into
the auth stack, expose it at the edge.

Secrets are **generated on the Pi, never committed.** The fixings data is re-derivable, so the
`db-data` volume is the only state and the Pi stays disposable.

---

## 0. Prerequisites (on the Pi)

- **The auth stack is up** — `cd ~/<proxy-auth>/auth && docker compose up -d`. This creates the
  external `proxy` network the app joins, and the docker nginx that fronts it.
- **DNS** — point `fixings.<DOMAIN>` at the Pi's public IP.
- **Docker + compose** installed (already present from the auth setup).

## 1. Get the repo onto the Pi

```sh
git clone https://github.com/FrenchCommando/fixings-service.git ~/fixings-service
cd ~/fixings-service
```

## 2. Create the secrets (on the Pi — never committed)

```sh
mkdir -p secrets
openssl rand -hex 24 > secrets/db_password             # fresh DB password
cp theta_creds.json.example secrets/theta_creds.json   # then fill in your ThetaData email/password
nano secrets/theta_creds.json
chmod 600 secrets/*
```

## 3. Bring up the fixings stack

```sh
docker compose up -d --build      # builds the arm64 image natively on the Pi
```

That's the whole app + db. **No manual DB steps**: the `db` container creates the `fixings`
database/role/password from the env + secret, and the service auto-creates the table on first
startup (idempotent `CREATE TABLE IF NOT EXISTS`). Verify:

```sh
docker compose ps
docker compose logs -f app        # should show it bind to :5000
```

## 4. Wire it into the auth stack

```sh
# nginx server block:
cp ~/fixings-service/deploy/nginx/fixings.conf ~/<proxy-auth>/auth/nginx/conf.d/fixings.conf
# edit server_name -> fixings.<DOMAIN>
docker compose -f ~/<proxy-auth>/auth/compose.yml exec nginx nginx -s reload
```

Then add one Authelia rule in `auth/authelia/configuration.yml` under `access_control.rules`:

```yaml
- domain: fixings.<DOMAIN>
  policy: two_factor
```

```sh
docker compose -f ~/<proxy-auth>/auth/compose.yml restart authelia   # picks up the new rule
```

## 5. Expose at the edge (host nginx + TLS)

On the Pi's native edge nginx, add a server block for `fixings.<DOMAIN>` that proxies to
`127.0.0.1:8080`, preserving `Host` + `X-Forwarded-*` (the exact per-host recipe is in
`proxy-auth/SETUP.md §6`). Then issue the cert:

```sh
sudo certbot certonly --webroot -w <webroot> -d fixings.<DOMAIN> --email <CERTBOT_EMAIL> --agree-tos
sudo nginx -t && sudo systemctl reload nginx
```

## 6. Verify

Browse to `https://fixings.<DOMAIN>` → Authelia login (enroll TOTP) → the service. First requests
return "No entry found" until data exists (see seeding below).

---

## Seeding data

The Pi DB starts empty (local data isn't migrated, and it's re-derivable anyway). The fastest
path is the bundled seeder — it fetches the last 364 days for every symbol in `seed_tickers.txt`,
which both registers the tickers and fills their history in one pass:

```sh
docker compose exec app python -m seed     # idempotent; re-run after editing seed_tickers.txt
```

After that, `/refresh` keeps every seeded ticker current. Alternatives:

- Hit `/entry/{ticker}/{date}` URLs — each backfills on demand, which also seeds the ticker list
  (handy for a one-off symbol not in `seed_tickers.txt`).
- Migrate an existing table with `pg_dump` / `pg_restore` for the history immediately.

## Updating later

```sh
git pull && docker compose up -d --build
```

The `db-data` volume (and your data) persists across rebuilds; the image is just code.
