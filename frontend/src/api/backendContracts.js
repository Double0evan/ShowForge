export const backendContracts = {
  sourceOfTruth: {
    inventory: "inventory_items stores item state, publication state, and media linkage.",
    claims: "claims is the active ownership ledger. Trade swaps update claims.user_id, not inventory rows.",
    binManager: "auction_log.id is only a row id. auction_log.position is the visual auction number.",
    users: "discord users are preferred, but pending/guest users are valid until merge/link resolution.",
  },
  requiredReadOnlyEndpoints: [
    "GET /api/inventory",
    "GET /api/claims",
    "GET /api/users",
    "GET /api/binshow/state",
    "GET /ui/binshow/log",
    "GET /ui/binshow/preview?item_code=N###",
    "GET /ui/members/search?q=...",
    "GET /ui/console/context",
  ],
};

export const liveCapabilities = {
  inventory: {
    list: true,
    publish: true,
    remove: true,
    assign: true,
    upload: true,
    editDetails: false,
  },
  claims: {
    list: true,
    removeRefund: true,
    setAuctionNumber: true,
    mockStatusOnly: false,
  },
  binManager: {
    listAuctionLog: true,
    listPendingSales: true,
    listWatcherState: true,
    fuzzyMatch: true,
    assignAuctionRow: true,
    deleteAuctionRow: true,
    clearAuctionLog: true,
    manualReviewStatus: false,
  },
  users: {
    list: true,
    adjustCredits: true,
    addGuest: true,
    merge: false,
  },
};
