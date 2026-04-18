# Phase Plan

## Phase 1 (Core: claims + vouchers + inventory)
1. Repo skeleton (backend/frontend/core/discord/db/docs)
2. Show folder + per-show DB creation/open/end (past shows read-only, optional unlock)
3. DB schema + indexes
4. Inventory service (count-based generate N001..N###, add/remove items)
5. Discord members sync -> users_cache (updates during show, verified from roles)
6. Pending identities (whatnot name) + immediate auto-link on nickname/verified updates
7. Voucher ledger UI + award/remove (reasons + winner slot), FIFO spending
8. Reaction handler (first reaction wins, requires role + balance >= 1, DM on fail)
9. Claims spreadsheet (reassign w/ refund+re-spend, removal w/ restore + refund prompt)
10. Dashboard summary (total inventory, remaining, users w/ unspent vouchers high->low)
11. Auth (single password + remember device)
12. Exports (claims/inventory/vouchers)

## Phase 2 (Uploads + watermark pipeline)
- Create show folder + template placement
- Auto-number RAW images (alphabetical), refuse if already numbered, reset prompt
- Watermark overlay from template
- Manual upload buttons; private uploads batch <=10/message
- Publish catalog 1 image/message (reaction-friendly)

## Phase 3 (Polish + distribution)
- Removed claims moved to audit channel w/ optional reason
- Role sync ladder Picks: 0..6, 6+; sync roles button
- Lightweight activity feed
- GitHub Releases auto-update tooling
