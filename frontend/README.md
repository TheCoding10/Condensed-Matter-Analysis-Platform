# Frontend

React + Vite + TypeScript dashboard for the NHMFL Condensed Matter Analysis
Platform. Talks to the FastAPI backend in `../api.py`.

## Setup

```bash
npm install
cp .env.example .env   # adjust VITE_API_BASE_URL if the API isn't on localhost:8000
npm run dev
```

The dev server runs on `http://localhost:5173`, which is already allow-listed
in the backend's CORS config.

## Scripts

- `npm run dev` — start the Vite dev server
- `npm run build` — type-check and build for production into `dist/`
- `npm run lint` — lint the source
- `npm run preview` — preview the production build locally

## Structure

- `src/api.ts` — typed fetch client for every `/api/*` endpoint
- `src/types.ts` — request/response types mirroring `api.py`
- `src/components/` — `DatasetLoader`, `SummaryPanel`, `SearchPanel`,
  `ExperimentsPanel` (experiment list + guide/standard-plots/auto-analyze
  detail view)
- `src/App.tsx` — tabbed dashboard shell (Summary / Search / Experiments)
