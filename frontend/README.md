# Frontend — Marketing Campaign Builder

A **React** single-page application that provides the user interface for creating, monitoring, and approving AI-generated marketing campaigns. Built with **Vite** for fast development and **React Router** for client-side navigation.

## Running the Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open **http://localhost:5173** in your browser. The backend API must be running on port 8000 (see the [backend README](../backend/README.md)).

### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start the Vite dev server with hot module replacement |
| `npm run build` | Create a production build in `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run ESLint across the project |

## Pages

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | `Dashboard` | Lists all existing campaigns with status |
| `/new` | `NewCampaign` | Form to create a new campaign brief (product, goal, budget, channels, timeline) |
| `/campaigns/:id` | `CampaignDetail` | Real-time view of the agent pipeline with live results |

## Key Components

| Component | Purpose |
|-----------|---------|
| `PipelineProgress` | Visual progress bar showing which agent is currently active |
| `StrategySection` | Displays the generated campaign strategy |
| `ClarificationSection` | Presents follow-up questions from the Strategy Agent and collects user answers |
| `ContentSection` | Shows generated content pieces with per-piece approval controls |
| `ChannelPlanSection` | Displays channel recommendations and budget allocation |
| `AnalyticsSection` | Shows KPIs, tracking tools, and measurement framework |
| `ReviewSection` | Presents QA scores, issues, and suggestions |
| `EventLog` | Live feed of WebSocket events from the backend |
| `ThemeToggle` | Light/dark mode switcher |

## Hooks

| Hook | Purpose |
|------|---------|
| `useWebSocket` | Manages a WebSocket connection to `/ws/campaigns/{id}` for real-time pipeline events |
| `useTheme` | Persists and toggles the light/dark colour theme |

## API Integration

All backend communication is handled through `src/api.js`, which provides functions for:

- Creating campaigns
- Fetching campaign lists and details
- Submitting clarification answers
- Submitting content approval decisions

The WebSocket hook provides real-time event streaming so the UI updates as each agent completes its work.

## Project Structure

```
frontend/
├── public/               # Static assets
├── src/
│   ├── api.js            # Backend API client
│   ├── App.jsx           # Root component with routing
│   ├── main.jsx          # React entry point
│   ├── index.css         # Global styles
│   ├── components/       # Reusable UI components
│   │   ├── PipelineProgress.jsx
│   │   ├── StrategySection.jsx
│   │   ├── ClarificationSection.jsx
│   │   ├── ContentSection.jsx
│   │   ├── ChannelPlanSection.jsx
│   │   ├── AnalyticsSection.jsx
│   │   ├── ReviewSection.jsx
│   │   ├── EventLog.jsx
│   │   └── ThemeToggle.jsx
│   ├── hooks/            # Custom React hooks
│   │   ├── useWebSocket.js
│   │   └── useTheme.js
│   └── pages/            # Route-level page components
│       ├── Dashboard.jsx
│       ├── NewCampaign.jsx
│       └── CampaignDetail.jsx
├── index.html            # HTML entry point
├── vite.config.js        # Vite configuration
├── eslint.config.js      # ESLint configuration
├── nginx.conf            # Nginx config for container deployment
├── package.json
├── Containerfile          # Container build definition
└── Dockerfile             # Docker build definition
```

## Tech Stack

- **React 19** with functional components and hooks
- **React Router 7** for client-side routing
- **Vite 7** for development and bundling
- **ESLint 9** for code quality
