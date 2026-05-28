export const endpoints = {
  // Active show info
  show: {
    active: "/shows/active",
    mode: "/shows/mode",
    new: "/ui/show/new",
    end: "/ui/show/end",
    resetClaims: "/ui/show/reset_claims",
  },

  // Inventory — real routes in ui.py + main.py
  inventory: {
    list: "/api/inventory",          // GET  — returns { ok, items: [...] }
    poll: "/ui/inventory/poll",      // GET  — lightweight status-only poll
    publish: "/ui/publish",          // POST — FormData: item_code
    publishAll: "/ui/publish_all",   // POST — no body
    republish: "/ui/republish",      // POST — FormData: item_code
    remove: "/ui/inventory/remove",  // POST — FormData: item_code
    assign: "/ui/inventory/assign",  // POST — FormData: item_code, display_name
    upload: "/ui/inbox/upload",      // POST — FormData: rating, files[]
  },

  // Claims
  claims: {
    list: "/api/claims",              // GET  — returns { ok, claims: [...] }
    remove: "/ui/claims/remove",      // POST — FormData: item_code, refund
    setAuction: "/ui/claims/set_auction", // POST — FormData: item_code, auction_number
    summary: "/ui/claims/summary",    // POST — FormData: rating
  },

  // Bin show manager
  binManager: {
    state: "/api/binshow/state",        // GET  — returns { ok, rows, pending_sales, watcher }
    log: "/ui/binshow/log",             // GET  — returns { ok, rows }
    fuzzy: "/ui/binshow/fuzzy",         // GET  — ?whatnot_name=...
    preview: "/ui/binshow/preview",     // GET  — ?item_code=N###
    submit: "/ui/binshow/submit",       // POST — FormData: auction_number, whatnot_name, discord_name, discord_id
    logAssign: (auctionId) => `/ui/binshow/log/${auctionId}/assign`, // POST — FormData
    logDelete: (auctionId) => `/ui/binshow/log/${auctionId}`,        // DELETE
    logInsert: "/ui/binshow/log/insert", // Insert Line
    logClear: "/ui/binshow/log/clear",  // POST
    reviews: "/bin/reviews",            // GET  — unresolved low-confidence matches
    reviewReassign: (id) => `/bin/reviews/${id}/reassign`,   // POST — ?discord_display_name=
    reviewKeepGuest: (id) => `/bin/reviews/${id}/keep_guest`, // POST
  },

  // Users
  users: {
    list: "/api/users",              // GET  — returns { ok, users: [...] }
    adjust: "/ui/users/adjust",      // POST — FormData: user_id, delta, note
    awardBulk: "/ui/users/award_bulk", // POST — FormData: user_ids (csv), amount, note
    membersSearch: "/ui/members/search", // GET — ?q=
    consoleContext: "/ui/console/context", // GET
    consoleRun: "/ui/console/run",   // POST — FormData: command
  },

  // Watcher (file watcher, not OCR watcher)
  watcher: {
    log: "/ui/watcher/log",    // GET
    start: "/ui/watcher/start", // POST
    stop: "/ui/watcher/stop",   // POST
    clear: "/ui/watcher/clear", // POST
  },

  // Trade admin (proxied through backend to bot)
  trade: {
    lock: "/trade/lock",
    unlock: "/trade/unlock",
    refreshAll: "/trade/refresh_all",
    closeChannels: "/trade/close_channels",
    report: "/trade/report",
  },

  // Vouchers (direct backend)
  vouchers: {
    balance: "/vouchers/balance",  // GET — ?user_id=
    ledger: "/vouchers/ledger",    // GET — ?user_id= (optional)
    award: "/vouchers/award",      // POST
    adjust: "/vouchers/adjust",    // POST
  },

  // Bin queue (direct backend)
  binQueue: {
    peek: "/bin/peek",
    queue: "/bin/queue",
    history: "/bin/history",
    clear: "/bin/clear",
    delete: (rowId) => `/bin/queue/${rowId}`,
    inject: "/bin/inject",
    reassign: "/bin/reassign",
  },

  // Native pickers (server-side tkinter dialogs)
  pick: {
    folder: "/ui/pick/folder",
    file: "/ui/pick/file",
  },

  // Settings
  settings: {
    save: "/ui/settings/save",
  },

  // Health
  health: "/health",
};
