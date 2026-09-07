# Deployment

The repository is prepared for the intended split deployment without changing the four agent implementations.

## Vercel frontend

Set the Vercel project root directory to `frontend`.

- Build command: `npm run build`
- Output directory: `dist`
- Install command: `npm install`
- Environment variable: `VITE_API_URL` = the eventual Render API URL

`frontend/vercel.json` handles SPA fallback routing.

## Render API

`render.yaml` defines the FastAPI web service.

Required secret environment variables:

- `PROVIDER_PRIVATE_KEY`
- `WALLET_PASSWORD`
- `AGENT_HOST` = the eventual Render service URL
- `RPC_URL` (optional override)
- `CORS_ORIGINS` = the eventual Vercel origin; comma-separated if more than one

The service starts with:

`uvicorn 03_provider:app --host 0.0.0.0 --port $PORT`

Health check: `/status`

Agent card: `/.well-known/agent-card.json`

A2A endpoint: `/a2a`

## Important

No Vercel or Render deployment is configured by this change. URLs are intentionally placeholders until the services are actually created.
