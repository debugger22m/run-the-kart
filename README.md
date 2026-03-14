# Run The Kart 🛻

Autonomous fleet management for food trucks, powered by Claude AI agents.

## Architecture

```
                    ┌─────────────────────┐
                    │  OrchestratorAgent  │
                    │  (coordinates flow) │
                    └────────┬────────────┘
                             │
               ┌─────────────┴─────────────┐
               ▼                           ▼
   ┌───────────────────┐       ┌───────────────────────┐
   │    EventAgent     │       │    SchedulerAgent     │
   │  Finds local      │──────▶│  Assigns carts to     │
   │  events via LLM   │       │  events via LLM       │
   └───────────────────┘       └───────────────────────┘
           │                            │
   ┌───────┴───────┐           ┌────────┴────────┐
   │  event_tools  │           │   maps_tools    │
   │  (mock/real)  │           │  (mock/real)    │
   └───────────────┘           └─────────────────┘
```

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `Cart` | `src/models/cart.py` | A single food truck — has status, location, and assignment |
| `Fleet` | `src/models/fleet.py` | Manages a collection of `Cart` objects |
| `Schedule` | `src/models/schedule.py` | A cart-to-event assignment with timing and revenue data |
| `Event` | `src/models/schedule.py` | An event the fleet can serve (embedded in `Schedule`) |
| `EventAgent` | `src/agents/event_agent.py` | Discovers and ranks nearby events using Claude |
| `SchedulerAgent` | `src/agents/scheduler_agent.py` | Assigns carts to events using Claude |
| `OrchestratorAgent` | `src/agents/orchestrator.py` | Top-level coordinator of the two agents |

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Open .env and set your ANTHROPIC_API_KEY
```

## Running

### API Server

```bash
source .venv/bin/activate
python3 main.py server
# Server starts at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### CLI (single cycle)

```bash
source .venv/bin/activate
python3 main.py run --lat 37.7749 --lng -122.4194 --radius 10
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/fleet` | Fleet overview and status breakdown |
| `GET` | `/api/v1/fleet/carts` | List all carts |
| `POST` | `/api/v1/fleet/carts` | Add a cart to the fleet |
| `DELETE` | `/api/v1/fleet/carts/{id}` | Remove a cart |
| `GET` | `/api/v1/schedules` | List active schedules |
| `POST` | `/api/v1/schedules/complete` | Mark a schedule as completed |
| `POST` | `/api/v1/orchestrate` | **Trigger a full AI orchestration cycle** |

### Example: trigger orchestration

```bash
curl -X POST http://localhost:8000/api/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"latitude": 37.7749, "longitude": -122.4194, "radius_km": 10, "hours_ahead": 12}'
```

## Swapping Mocks for Real APIs

The mock tool handlers are clearly separated from their schemas:

- **Events**: Edit `src/tools/event_tools.py` — replace `_search_local_events`, `_get_event_details`, `_estimate_foot_traffic` with real Eventbrite / Ticketmaster API calls.
- **Maps / Routing**: Edit `src/tools/maps_tools.py` — replace handlers with Google Maps Directions / Distance Matrix API calls.

The agent and orchestrator code does not need to change.

## Project Structure

```
run-the-kart/
├── main.py                      # CLI entry point
├── requirements.txt
├── .env.example
├── src/
│   ├── agents/
│   │   ├── base.py              # Shared agentic loop (tool-use handling)
│   │   ├── orchestrator.py      # Top-level coordinator
│   │   ├── event_agent.py       # Event discovery agent
│   │   └── scheduler_agent.py   # Cart scheduling agent
│   ├── models/
│   │   ├── cart.py              # Cart + CartStatus + Coordinates
│   │   ├── fleet.py             # Fleet (manages Cart collection)
│   │   └── schedule.py          # Schedule + Event + ScheduleStatus
│   ├── tools/
│   │   ├── event_tools.py       # Claude tool schemas + mock handlers
│   │   └── maps_tools.py        # Claude tool schemas + mock handlers
│   └── api/
│       ├── app.py               # FastAPI app factory
│       ├── state.py             # Shared app state (fleet + orchestrator)
│       └── routes.py            # All REST endpoints
```
