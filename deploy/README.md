# Empire AI — Self-Hosted SaaS Deployments

White-labeled open-source products deployed via Docker Compose.
Created 2026-06-21.

## Products

| Product | Source | Port | Status | Key Value |
|---------|--------|------|--------|-----------|
| **Empire Sign** | [DocuSeal](https://github.com/docusealco/docuseal) | 8090 | ✅ Live | Fee contracts → collectible revenue |
| **Empire Workspace** | [Affine](https://github.com/toeverything/affine) | 8091 | ⚠️ Init needed | Team docs + kanban + whiteboards |
| **Empire Analytics** | [Apache Superset](https://github.com/apache/superset) | 8092 | ⚠️ Config needed | BI dashboards for contractors |
| **Empire Studio** | [Penpot](https://github.com/penpot/penpot) | 8094 | ⚠️ Exporter fix | Design tool for marketing assets |

## Quick Start

### Empire Sign (Document Signing)
```bash
cd deploy/empire-sign
docker compose up -d
# Access: http://localhost:8090
```

**Verified working** — HTTP 302 redirect to login. Uses `docuseal/docuseal:latest` + `postgres:16`.

### Empire Workspace (Team Collaboration)
```bash
cd deploy/empire-workspace
docker compose up -d
# Access: http://localhost:8091
```

**Known issue:** Prisma P2021 — `app_configs` table missing. Needs `npx prisma migrate deploy` run inside the container after postgres is healthy.

### Empire Analytics (BI Dashboards)
```bash
cd deploy/empire-analytics
docker compose up -d
# Access: http://localhost:8092
```

**Known issue:** SQLAlchemyError during init. Superset's docker image uses SQLite by default; needs `superset_config.py` with proper PostgreSQL URI. Admin auto-created (admin/admin).

### Empire Studio (Design Tool)
```bash
cd deploy/empire-studio
docker compose up -d
# Access: http://localhost:8094 (frontend)
```

**Known issue:** `penpot-exporter` container restarting (exit 255). Frontend nginx references exporter upstream — if exporter is down, frontend won't serve. Backend runs fine on its own.

## Architecture

Each product runs in its own Docker network with isolated PostgreSQL and Redis:
- `empire-sign` network (app + postgres:16)
- `empire-workspace` network (affine + pgvector + redis)
- `empire-analytics` network (superset + postgres:15 + redis)
- `empire-studio` network (backend + frontend + exporter + postgres:15 + redis)

## Nginx Routing (Planned)

Subdomain → port mapping for when these go live:
```
sign.empire-ai.co.uk      → 127.0.0.1:8090
workspace.empire-ai.co.uk → 127.0.0.1:8091
analytics.empire-ai.co.uk → 127.0.0.1:8092
studio.empire-ai.co.uk    → 127.0.0.1:8094
```

Requires Let's Encrypt cert expansion to cover subdomains. See `nginx-empire-products.conf` template.

## Resource Usage

| Product | Containers | ~RAM | ~Disk |
|---------|-----------|------|-------|
| Empire Sign | 2 (app + postgres) | 400MB | 200MB |
| Empire Workspace | 3 (affine + pgvector + redis) | 1GB | 500MB |
| Empire Analytics | 3 (superset + postgres + redis) | 1.5GB | 1GB |
| Empire Studio | 5 (backend + frontend + exporter + postgres + redis) | 2GB | 1GB |
| **Total** | **13 containers** | **~5GB** | **~2.7GB** |

Server: 7.3GB available RAM, 24GB free disk, 8 cores — can run all four simultaneously.

## MRR Pricing

| Product | Starter $997 | Growth $2,997 | Pro $7,997 | Enterprise $19,997 |
|---------|:---:|:---:|:---:|:---:|
| Empire Sign | | ✅ | ✅ | ✅ |
| Empire Workspace | | ✅ | ✅ | ✅ |
| Empire Studio | | | ✅ | ✅ |
| Empire Analytics | | | | ✅ |
