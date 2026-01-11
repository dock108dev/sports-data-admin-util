# Edge Proxy (Caddy) Routing

In production, the admin UI and API are typically served behind an edge proxy (often Caddy) with Cloudflare in front.

## Goal

- `/` → Next.js (web)
- `/api/*` → FastAPI (api)

The **browser** should never call `http://localhost:8000` in production.

## Caddyfile example

```caddy
sports-data-admin.dock108.ai {
  encode gzip

  # API routes (preserve /api prefix)
  handle /api/* {
    reverse_proxy localhost:8000
  }

  # Web app
  handle {
    reverse_proxy localhost:3000
  }
}
```

## Common pitfall: `handle_path`

Avoid:

```caddy
handle_path /api/* {
  reverse_proxy localhost:8000
}
```

`handle_path` strips the matched prefix, so `/api/admin/sports/games` becomes `/admin/sports/games` upstream and FastAPI returns 404.

