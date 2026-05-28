# ShowForge React Frontend Handoff

## Current rule
React is the staff/admin management tool. Discord is the user/customer-facing layer for now.

## Backend reality
The backend already exists and should not be reinvented:
- FastAPI backend
- discord.py bot
- SQLite per-show DBs
- existing Jinja HTML control panel being replaced
- working inventory publishing, claim assignment, bin manager, trade system, user linking, voucher ledger, media tracking, and watermark upload pipeline

## Frontend architecture direction
UI should adapt to existing workflows:
UI → hooks → showforgeApi/domain API layer → mock now / FastAPI later.

## Important workflow split
Inventory intake/upload/publish feeds into Bin Manager/Claim Queue. Claims is the finalized ownership ledger only.

## Current API architecture prep
This update adds:
- `apiClient.js`
- `endpoints.js`
- `config.js`
- `mappers.js`
- `liveShowforgeApi.js`
- `activityLog.js`
- updated `showforgeApi.js`
- `useActivityFeed`
- `useOperation`

Mock mode remains default through `VITE_SHOWFORGE_API_MODE=mock`.
Future live mode can be enabled with `VITE_SHOWFORGE_API_MODE=live` once matching backend JSON endpoints exist.

## Next likely work
1. Add JSON endpoints to FastAPI for Claims and Users.
2. Wire Inventory `/api/inventory` first.
3. Add Bin Manager live polling or websocket/SSE.
4. Replace mock upload queue with `/ui/upload` calls.
5. Add event stream from backend/bot to RightDock.
