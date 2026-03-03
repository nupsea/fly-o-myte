# Security — Fly-O-Myte

## Threat Model

Fly-O-Myte is a local-first single-user CLI tool. It has no server, no web UI, no multi-user access. The threat model is:

- **Primary risk**: API key leakage via config file or logs
- **Not in scope**: Network attacks, multi-user auth, SQL injection (single user, parameterised queries)

## API Key Storage

| Key | Storage | Risk |
|-----|---------|------|
| `TEQUILA_API_KEY` | `~/.fly-o-myte/config.yaml` or `.env` | Plaintext YAML — file permissions are the only protection |
| `ANTHROPIC_API_KEY` | Same | Same |
| SMTP credentials | Same | Same |

**Recommendation**: Set `~/.fly-o-myte/config.yaml` permissions to `600`:
```bash
chmod 600 ~/.fly-o-myte/config.yaml
```

**Future**: Migrate secrets to OS keychain (macOS Keychain / Linux Secret Service). Tracked as `TD-001` in `docs/exec-plans/tech-debt-tracker.md`.

## Data Privacy

- All flight search parameters (origin, destination, travel dates) are sent to Tequila API. No personal names or payment data.
- LLM prompts contain only route and price data — no family member names, DOBs, or emails. This is enforced in `insights.py` prompt construction.
- No telemetry or analytics are sent anywhere. All data stays in `~/.fly-o-myte/`.
- `~/.fly-o-myte/fly-o-myte.db` contains trip labels, dates, and price history. Back it up with your home directory.

## Log Sanitisation

`fly-o-myte.log` must not contain API keys. The logger in `cli.py` uses `logging.getLogger(__name__)` — structured output only. Never log raw HTTP request headers that might contain Authorization tokens.

## `.env` File

`.env` is in `.gitignore`. Never commit it. The `.env.example` shows variable names without values.
