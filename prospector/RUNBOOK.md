# Runbook: running the AI employee

All commands run on the server in `/opt/sogixel`.

| I want to… | Do this |
|---|---|
| See if it's healthy | `https://<domain>/status` (from the cockpit), or `docker compose exec employee python -m sogixel check --live` |
| Read what it did | `docker compose logs --since 24h employee` (one JSON line per event: `inbound`, `notify`, `job_done`, `job_failed`) |
| Go live / back to test | `.env`: `SETTER_MODE=live` or `shadow`, then `docker compose up -d` |
| Stop the bot on one conversation | Tag the contact `bot-pause` in GHL (or just write to the prospect yourself) |
| Give a conversation back to the bot | Remove the `bot-pause` tag, then `docker compose exec employee python -m sogixel unpause <contact_id>` |
| Stop everything now | `docker compose stop employee` (webhooks fail and GHL keeps the messages; nothing is lost on your side) |
| Release a new version | Merge to `main`, wait for the GitHub Action, then `scripts/deploy.sh user@server` |
| Roll back | `.env`: `EMPLOYEE_IMAGE=ghcr.io/fella118/sogixel-employee:<previous sha>`, then `docker compose up -d` |
| Rotate a key | Change it in `.env`, `docker compose up -d`. New `WEBHOOK_KEY` → update the GHL webhook URL. New `COCKPIT_KEY` → the next morning message has the new link |
| Restore a backup | `docker compose stop employee`, copy `data/backups/<date>/*` into `data/`, `docker compose start employee` |

## When something breaks

| Symptom | Likely cause | Fix |
|---|---|---|
| WhatsApp "Je n'ai pas pu répondre à un prospect" | GHL or Claude unreachable 3 times in a row | Answer that prospect yourself; check logs for `inbound_failed` |
| `GHL ... -> 401` in logs | GHL token revoked or expired | New Private Integration token in `.env` |
| `Claude API 401/403` | Anthropic key revoked or out of credit | Check console.anthropic.com |
| "La tâche daily a échoué" | Places key/quota, or empty master list | `check --live`; first `pull` done? |
| "Plafond quotidien de réponses IA atteint" | More than `max_ai_replies_day` replies | Good problem: raise it in `config.toml` |
| No drafts / replies at all | GHL workflow off, or wrong `WEBHOOK_KEY` in its URL | GHL workflow history shows the webhook status |
| Meta ad history missing | Meta token expired (60 days) | New token in `.env` |
