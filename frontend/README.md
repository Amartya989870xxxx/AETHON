# AETHON Dashboard

Operator dashboard for the AETHON traffic-intelligence backend. React + Vite +
TypeScript + Tailwind, with a Leaflet map and a live alert socket.

The visual language (near-black radial ground, violet accent, frosted-glass
panels with an illuminated top edge, silky `cubic-bezier(0.16, 1, 0.3, 1)`
motion) is adapted from the Argus website.

## Run it

```bash
# 1. bring up the backend (separate terminal, repo root)
pip install -r requirements.txt
./run.sh seed --hours 12 --vehicles-per-hour 70
./run.sh serve                       # API on :8000

# 2. the dashboard
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

CORS on the backend already allows `localhost:5173`. If you run the dev server
on another port, ask backend to add it — don't proxy around CORS.

To see the **live alert socket** do something, start the demo driver from the
Alerts screen ("Start live demo", dev builds only) or:

```bash
curl -X POST 'http://localhost:8000/api/demo/start?duration_s=120&speed=60'
```

Seeded / directly-posted alerts are already in `GET /api/alerts`; only the demo
driver broadcasts over the socket.

## Configuration

One env var. Copy `.env.example` to `.env.local` and change it when the backend
moves off localhost:

| Var | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | REST + (derived) WS base URL |
| `VITE_OPERATOR_NAME` | `demo_frontend` | `actor` / `added_by` on audited calls — **not** auth |

## Scripts

| | |
|---|---|
| `npm run dev` | Vite dev server |
| `npm run build` | typecheck + production build |
| `npm run test` | Vitest (pure-logic units) |
| `npm run typecheck` | `tsc` only |

## Layout

```
src/
  api/          config, fetch wrapper (error-shape normalisation), typed endpoints, WS hook, response types
  lib/          datetime (UTC rules), geo ([lon,lat]→[lat,lng]), format, enum→colour maps, OD + trajectory helpers
  hooks/        useApi (fetch + abort + refetch), useInterval
  components/   glass design system, AppShell/nav, MapView, DataTable, TimeWindow, toast, error boundary
  screens/      CityMap, Trajectory, Alerts, Analytics, Watchlist, Audit
```

## Three things the backend will bite you on

1. **GeoJSON coordinates are `[lon, lat]`.** `<GeoJSON>` handles it;
   hand-built geometry goes through `lib/geo.ts`.
2. **Every timestamp is UTC**, some with no `Z` suffix. All parsing/formatting
   goes through `lib/datetime.ts` (`normalizeIso` appends the `Z`).
3. **`plate_norm` is the identity key**, not `plate_text`. Search input is sent
   as-is (backend normalises); displays use `plate_norm`.

## What isn't real yet

No `/auth` — `actor` / `added_by` are free text logged verbatim. `frame_ref`
is a path string, not a URL; it's rendered as text, never an `<img src>`. The
demo driver is a presentation tool, gated to dev builds in the UI.
