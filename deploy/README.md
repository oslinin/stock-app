# VPS deployment

Three containers via Docker Compose: `ib-gateway` (headless IB Gateway with
auto-login), `backend` (the FastAPI screener), and `caddy` (automatic HTTPS).
Only ports 80/443 are published; the IB API socket never leaves the internal
Docker network.

## Prerequisites

- A VPS with Docker and either `docker-compose` or the `docker compose`
  plugin (see the note under Bring-up), and outbound access to IBKR/SMTP.
- A DNS **A record** (e.g. `vix.yourdomain.com`) pointing at the VPS, with
  ports 80 and 443 open. HTTPS is mandatory: the GitHub Pages frontend is
  served over https and browsers block calls to an http API (mixed content).
- IBKR credentials (start with the **paper** account).

## Bring-up

**Run these commands on the VPS itself, over SSH — not on your laptop or
desktop.** `ib_async` connecting to IBKR only proves outbound access works;
it says nothing about whether the internet can reach *this* machine on
443, which is a separate, easy mistake to make (compose comes up cleanly
on any machine, VPS or not).

```bash
ssh <user>@<vps>              # you're on the VPS from here on
cd stock-app/deploy           # or git clone the repo first
cp .env.example .env
# edit .env: DOMAIN, TWS_USERID/TWS_PASSWORD, API_TOKEN, SMTP_*
sudo docker-compose up -d --build
sudo docker-compose logs -f backend   # wait for "connected to IBKR"
```

These commands use `docker-compose` (hyphenated, the standalone binary),
not `docker compose` (space, the newer plugin) — a fresh Ubuntu apt
install typically only has the former (`docker compose` fails with
`unknown shorthand flag: 'd' in -d`). Check with `which docker-compose`;
if this VPS instead only has the plugin (`docker compose version` works),
swap every `docker-compose` below for `docker compose`.

`sudo` is needed unless your user is in the `docker` group — talking to
the Docker daemon otherwise fails with `permission denied ... docker.sock`.
Every `docker-compose`/`docker` command on this page assumes `sudo`; drop
it once you've added yourself to the group (one-time, avoids typing sudo
for every command from then on):

```bash
sudo usermod -aG docker $USER
newgrp docker   # or just log out and back in
```

Verify from anywhere:

```bash
curl https://$DOMAIN/api/v1/health
curl -H "Authorization: Bearer $API_TOKEN" https://$DOMAIN/api/v1/ibkr/status
curl -H "Authorization: Bearer $API_TOKEN" https://$DOMAIN/api/v1/screener/vix_hedge/spread
```

Then open the frontend, go to the Screener page, and paste the API base
(`https://$DOMAIN/api/v1`) and token into its Settings panel once — they are
kept in the browser's localStorage, never in the built site.

## Notes

- **2FA**: with IB mobile-app 2FA the gateway login sits waiting for your
  approval; `TWOFA_TIMEOUT_ACTION=restart` keeps retrying. The gateway also
  restarts nightly (`AUTO_RESTART_TIME`) per IB's session rules.
- **Market data**: without a CBOE (VIX index) + OPRA (options) subscription
  quotes are delayed or empty; the API surfaces this in `warnings` and
  `marketDataType`. Keep `IBKR_USE_DELAYED=true` until subscribed.
- **Order staging**: `ALLOW_ORDER_STAGING=false` means `/orders/ticket`
  returns a manual order spec only. When enabled, orders are placed with
  `transmit=false` — they appear in TWS as untransmitted orders for you to
  review; the backend never transmits. A headless gateway has no UI to show
  staged orders, so either keep the manual flow or run TWS instead.
- **Persistence**: SQLite (alert rules/events, armed state) lives on the
  `backend-data` volume; IB Gateway settings on `ib-settings`.
- **Updates**: `git pull && sudo docker-compose up -d --build`.

## Tear down the stack / start over

To remove just this app's containers/images/volumes from a machine —
e.g. you brought it up on the wrong box (a laptop/desktop instead of the
VPS, an easy mistake since compose comes up cleanly anywhere regardless
of whether it's reachable) — without touching Docker itself:

```bash
cd deploy
sudo docker-compose down -v --rmi local   # stop + remove containers, the
                                           # named volumes (ib-settings,
                                           # backend-data, caddy-data,
                                           # caddy-config), and the locally
                                           # built backend image
rm -f .env                                # delete the local copy of
                                           # IBKR/API secrets — .env is
                                           # gitignored but still sits on
                                           # disk in plaintext
```

Then redo the [Bring-up](#bring-up) steps on the right machine: the VPS
itself, over SSH.

## Uninstall Docker entirely

Only if you want the machine back to a clean slate — e.g. switching from
the distro's `docker.io` package to Docker's official repo, or
decommissioning the box. Run the stack teardown above *first* (this
removes the underlying data those containers/volumes were stored in).

**If Docker came from apt (`docker.io` + a separate `docker-compose`):**

```bash
sudo systemctl stop docker
sudo apt purge -y docker.io docker-compose docker-compose-plugin
sudo apt autoremove -y
sudo rm -rf /var/lib/docker /var/lib/containerd /etc/docker
sudo groupdel docker   # only if no other service needs it
```

**If Docker came from the official repo (`get.docker.com`, `docker-ce`):**

```bash
sudo systemctl stop docker
sudo apt purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo apt autoremove -y
sudo rm -rf /var/lib/docker /var/lib/containerd /etc/docker
sudo rm /etc/apt/sources.list.d/docker.list /etc/apt/keyrings/docker.asc 2>/dev/null
sudo groupdel docker   # only if no other service needs it
```

`/var/lib/docker` holds every image/container/volume on the machine, not
just this stack's — deleting it is irreversible for anything else you may
have running under Docker on this box.
