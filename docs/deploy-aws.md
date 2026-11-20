# Deploy ArogyaVaani on AWS (EC2 + Docker + Caddy)

One `t3.small` instance runs two containers: the app (FastAPI + built web app + `/llm` + `/clinic/v1`) and Caddy for automatic HTTPS.
Agora cloud must reach `https://<host>/llm/chat/completions`, so HTTPS on a public hostname is required. We use a free
`sslip.io` hostname that resolves to your Elastic IP, so no DNS setup is needed.

## 1. Launch the instance

1. EC2 -> Launch instance -> **Ubuntu 24.04**, **t3.small**, 20 GB gp3, key pair of your choice.
2. Security group inbound: **22** (your IP), **80** and **443** (anywhere).
3. Allocate an **Elastic IP** and associate it. Say it is `13.233.10.5`; your hostname is `13-233-10-5.sslip.io`.

## 2. Install Docker and fetch the code

```bash
ssh -i key.pem ubuntu@13.233.10.5
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu && newgrp docker
git clone https://github.com/<you>/arogyavaani.git && cd arogyavaani
```

## 3. Configure

```bash
cp server/.env.example server/.env.local
nano server/.env.local        # fill every key; set the two URLs below
#   CUSTOM_LLM_URL=https://13-233-10-5.sslip.io/llm/chat/completions
#   PUBLIC_BASE_URL=https://13-233-10-5.sslip.io
#   CUSTOM_LLM_API_KEY=<long random string>
#   CONSOLE_PASSWORD=<something only you know>
```

## 4. Run

```bash
export DOMAIN=13-233-10-5.sslip.io
docker compose --profile https up -d --build
curl -s https://$DOMAIN/healthz            # expect "status":"ok" and every key check true
curl -s -X POST https://$DOMAIN/api/demo/reset   # seed doctors + Lakshmi
```

Open `https://13-233-10-5.sslip.io/?demo=1` (patient app + demo controls) and `/console/` (nurse console).

**Verify from your phone on mobile data** that `https://<host>/llm/health` loads; that is the exact URL Agora's cloud calls.

## Updating

```bash
git pull && docker compose --profile https up -d --build
```

## Optional AWS services (roadmap, not required for the demo)

- **Amazon Bedrock**: put an OpenAI-compatible gateway (for example the Bedrock Access Gateway) in front and set `LLM_BASE_URL`/`LLM_MODEL`.
- **SNS** for SMS and **EventBridge Scheduler** for the reminder/feedback calls instead of in-process APScheduler.
- **App Runner** also works: build the same `Dockerfile`, port 8000, health check `/healthz`; it terminates HTTPS for you
  (no Caddy), but use an EFS/RDS-backed `AROGYA_DB_PATH` if you need state to survive deploys.

## Notes

- State (SQLite + voice notes) lives in the `arogya-data` volume. `POST /api/demo/reset` clears bookings and re-seeds the demo patient.
- Set `DEMO_MODE=0` to disable `/api/demo/*` once you are done presenting.
- The token endpoints are public by design (the browser needs them). Add rate limiting before any real deployment.
