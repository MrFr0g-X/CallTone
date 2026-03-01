# CallTone UI

React frontend for the CallTone QA system.

## Tech Stack

- React 18 + TypeScript
- Tailwind CSS + shadcn/ui
- Framer Motion (animations)
- TanStack Query (data fetching)
- Recharts (charts)
- Axios (API client)

## Setup

```bash
npm install
npm run dev
# http://localhost:8080
```

Requires the API running at `http://localhost:8000`. See the root README for full instructions.

## Pages

- **Landing** — `/`
- **Login** — `/login`
- **QA Dashboard** — `/qa/dashboard` (login as `qa@calltone.tech`)
- **Agent Dashboard** — `/agent/dashboard` (login as `agent@calltone.tech`)
- **Call Detail** — `/qa/call/:callId`
- **Admin** — `/admin` (login as `admin@calltone.tech`)
