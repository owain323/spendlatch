# Deploying SpendPilot to a public domain

This directory contains everything needed to run the public demo on a
single Linux VPS behind nginx:

- `spendpilot-web.service` — the FastAPI app (`python -m agent.backend`),
  which serves the web UI, the static assets, and the chat API on
  `127.0.0.1:8200`.
- `spendpilot-mcp.service` — the self-hosted MCP server
  (`python -m mcp_server.server`, Streamable HTTP) on `127.0.0.1:8101`.
- `nginx-spendpilot.conf` — TLS termination + reverse proxy for the
  domain, including SSE-friendly settings for the MCP endpoint.

Both processes bind to loopback only; nginx is the only public face.
No credentials exist anywhere in the stack: every provider is a
simulated adapter and all data is synthetic.

## 1. Server prerequisites

Ubuntu 22.04+ (or any systemd distro) with Python >= 3.11:

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
sudo useradd --system --home /opt/spendpilot --shell /usr/sbin/nologin spendpilot
sudo git clone https://github.com/owain323/spendpilot.git /opt/spendpilot
cd /opt/spendpilot
sudo python3 -m venv .venv
sudo .venv/bin/pip install .
sudo chown -R spendpilot:spendpilot /opt/spendpilot
```

## 2. systemd services

```bash
sudo cp deploy/spendpilot-web.service deploy/spendpilot-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now spendpilot-web spendpilot-mcp
systemctl status spendpilot-web spendpilot-mcp --no-pager
```

Smoke-check from the box itself:

```bash
curl -fsS http://127.0.0.1:8200/ | head -5      # web UI
curl -fsS http://127.0.0.1:8101/mcp -o /dev/null -w '%{http_code}\n'  # MCP endpoint
```

## 3. nginx + TLS

```bash
sudo cp deploy/nginx-spendpilot.conf /etc/nginx/sites-available/spendpilot.conf
sudo ln -sf /etc/nginx/sites-available/spendpilot.conf /etc/nginx/sites-enabled/
```

The config expects a certificate at
`/etc/letsencrypt/live/spendpilot.owain32380.cn/`. Easiest path is
certbot (run after DNS resolves):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d spendpilot.owain32380.cn
sudo nginx -t && sudo systemctl reload nginx
```

If you use a cloud-issued certificate instead, drop the files in place
of the Let's Encrypt paths and adjust `ssl_certificate` lines.

## 4. DNS

In your DNS provider, add:

```
spendpilot.<your-domain>.  A  <VPS_PUBLIC_IP>
```

Propagate, then verify from outside:

```bash
curl -fsS https://spendpilot.<your-domain>/ | head -5
curl -fsS https://spendpilot.<your-domain>/api/health -o /dev/null -w '%{http_code}\n'
```

## 5. Operational notes (honest boundaries)

- **Shared demo state** — the demo runs one shared instance; every
  visitor sees the same synthetic ledger (`data/state.json`). That is
  acceptable for a hackathon demo, but expect state drift when many
  people play at once. A daily reset keeps the demo story clean:
  `sudo systemctl restart spendpilot-web spendpilot-mcp` (state lives
  only in `data/state.json`; nothing else persists).
- **No auth by design** — the public demo intentionally has no login.
  There is nothing to steal: adapters are simulated, data is synthetic,
  and no outbound calls are made to any real provider.
- **Upgrades** — `cd /opt/spendpilot && sudo -u spendpilot git pull &&
  sudo -u spendpilot .venv/bin/pip install . && sudo systemctl restart
  spendpilot-web spendpilot-mcp`. CI on the repo must be green before
  you pull.
- The integrity manifest (`python tools/make_sha256sums.py --check`)
  matches the git-tracked file set, so a fresh clone always verifies.
