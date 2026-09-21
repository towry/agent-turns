# agent-turns

Static site for GitHub Pages. The homepage is the current week. Completed weeks, months, and years are files under `data/`.

Hourly from 09:00 through 22:00 Asia/Shanghai (01:00–14:00 UTC). No run after 22:00.

- `GET {FLYAGENT_URL}/v1/metrics/turns/days/{yesterday}`
- `GET {FLYAGENT_URL}/v1/metrics/turns/days/{today}`

Repository secrets:

| Name | Purpose |
|---|---|
| `FLYAGENT_URL` | e.g. `https://flyagent.example.com` |
| `FLYAGENT_TOKEN` | Bearer token with `metrics:read` |

`day` is a UTC calendar date. Today is overwritten on each run, not summed.
