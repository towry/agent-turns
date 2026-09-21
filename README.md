# agent-turns

Static site for GitHub Pages. The homepage is the current week. Completed weeks, months, and years are files under `data/`.

Scheduled at 03:30 and 07:00 UTC (11:30 and 15:00 Asia/Shanghai):

- `GET {FLYAGENT_URL}/v1/metrics/turns/days/{yesterday}`
- `GET {FLYAGENT_URL}/v1/metrics/turns/days/{today}`

Repository secrets:

| Name | Purpose |
|---|---|
| `FLYAGENT_URL` | e.g. `https://flyagent.example.com` |
| `FLYAGENT_TOKEN` | Bearer token with `metrics:read` |

`day` is a UTC calendar date. Today is overwritten on each run, not summed.
