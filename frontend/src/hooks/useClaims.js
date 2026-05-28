import { useCallback, useEffect, useMemo, useState } from "react";
import { showforgeApi } from "../api/showforgeApi";

const DEFAULT_PAGE_SIZE = 20;

export function useClaims({ showToast } = {}) {
  const [claims, setClaims]         = useState([]);
  const [loading, setLoading]       = useState(true);
  const [selectedIds, setSelected]  = useState([]);
  const [search, setSearchRaw]      = useState("");
  const [sourceFilter, setSourceRaw] = useState("All");
  const [ratingFilter, setRatingRaw] = useState("All");
  const [sortKey, setSortKey]       = useState("createdAt");
  const [sortDirection, setSortDir] = useState("desc");
  const [page, setPage]             = useState(1);
  const [pageSize, setPageSizeRaw]  = useState(DEFAULT_PAGE_SIZE);

  const loadClaims = useCallback(async () => {
    setLoading(true);
    try {
      const next = await showforgeApi.listClaims();
      setClaims(next);
    } catch (e) {
      showToast?.(`Failed to load claims: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadClaims(); }, [loadClaims]);

  // ── Filtering ─────────────────────────────────────────────────────────────

  const filteredClaims = useMemo(() => {
    const q = search.toLowerCase().trim();

    const visible = claims.filter((c) => {
      const matchesSearch =
        !q ||
        [c.itemCode, c.owner, c.source, c.auctionNumber]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(q));

      const matchesSource = sourceFilter === "All" || c.source === sourceFilter;
      const matchesRating = ratingFilter === "All" || c.rating === ratingFilter;

      return matchesSearch && matchesSource && matchesRating;
    });

    return [...visible].sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const r = String(av).localeCompare(String(bv), undefined, { numeric: true });
      return sortDirection === "asc" ? r : -r;
    });
  }, [claims, search, sourceFilter, ratingFilter, sortKey, sortDirection]);

  const filterOptions = useMemo(() => {
    const unique = (vals) =>
      ["All", ...Array.from(new Set(vals.filter(Boolean))).sort()].map((v) => ({
        value: v, label: v,
      }));
    return {
      sources: unique(claims.map((c) => c.source)),
      ratings: unique(claims.map((c) => c.rating)),
    };
  }, [claims]);

  const activeFilterCount = [search.trim(), sourceFilter, ratingFilter]
    .filter((v) => v && v !== "All").length;

  // ── Pagination ────────────────────────────────────────────────────────────

  const totalPages = Math.max(1, Math.ceil(filteredClaims.length / pageSize));
  const safePage   = Math.min(page, totalPages);

  useEffect(() => {
    if (page !== safePage) setPage(safePage);
  }, [page, safePage]);

  const pagedClaims = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return filteredClaims.slice(start, start + pageSize);
  }, [filteredClaims, pageSize, safePage]);

  // ── Selection ─────────────────────────────────────────────────────────────

  const allVisibleSelected =
    pagedClaims.length > 0 &&
    pagedClaims.every((c) => selectedIds.includes(c.id));

  function toggleRow(id) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  function toggleAllVisible() {
    if (allVisibleSelected) {
      setSelected((prev) => prev.filter((id) => !pagedClaims.some((c) => c.id === id)));
      return;
    }
    setSelected((prev) => {
      const next = new Set(prev);
      pagedClaims.forEach((c) => next.add(c.id));
      return Array.from(next);
    });
  }

  function clearSelection() { setSelected([]); }

  // ── Sort / filter setters ─────────────────────────────────────────────────

  function resetPage() { setPage(1); }
  function setSearch(v)       { setSearchRaw(v);   resetPage(); }
  function setSourceFilter(v) { setSourceRaw(v);   resetPage(); }
  function setRatingFilter(v) { setRatingRaw(v);   resetPage(); }
  function setPageSize(v)     { setPageSizeRaw(Number(v)); resetPage(); }

  function clearFilters() {
    setSearchRaw("");
    setSourceRaw("All");
    setRatingRaw("All");
    resetPage();
  }

  function changeSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  // ── Mutations ─────────────────────────────────────────────────────────────

  async function removeClaim(itemCode, refund = true) {
    try {
      await showforgeApi.removeClaim(itemCode, refund);
      showToast?.(`${itemCode} removed${refund ? " + refunded" : ""}.`);
      await loadClaims();
      setSelected((prev) => {
        const removed = claims.find((c) => c.itemCode === itemCode);
        return removed ? prev.filter((id) => id !== removed.id) : prev;
      });
    } catch (e) {
      showToast?.(`Remove failed: ${e.message}`);
    }
  }

  async function bulkRemoveRefund(ids) {
    const itemCodes = ids
      .map((id) => claims.find((c) => c.id === id)?.itemCode)
      .filter(Boolean);

    let succeeded = 0;
    for (const code of itemCodes) {
      try {
        await showforgeApi.removeClaim(code, true);
        succeeded++;
      } catch {
        // continue
      }
    }
    showToast?.(`${succeeded} claim(s) removed and refunded.`);
    await loadClaims();
    clearSelection();
  }

  async function setAuctionNumber(itemCode, auctionNumber) {
    try {
      await showforgeApi.setClaimAuctionNumber(itemCode, auctionNumber);
      showToast?.(`Auction # updated for ${itemCode}.`);
      await loadClaims();
    } catch (e) {
      showToast?.(`Failed to update auction #: ${e.message}`);
    }
  }

  async function postSummary(rating) {
    try {
      await showforgeApi.postClaimSummary(rating);
      showToast?.(`${rating.toUpperCase()} summary posted to Discord.`);
    } catch (e) {
      showToast?.(`Summary failed: ${e.message}`);
    }
  }

  // ── Stats ─────────────────────────────────────────────────────────────────

  const pulseStats = useMemo(() => ({
    total:   claims.length,
    active:  claims.filter((c) => c.status === "Active").length,
    bin:     claims.filter((c) => c.sourceKey === "bin").length,
    direct:  claims.filter((c) => c.sourceKey === "staff").length,
    discord: claims.filter((c) => c.sourceKey === "button" || c.sourceKey === "reaction").length,
  }), [claims]);

  return {
    claims,
    filteredClaims,
    pagedClaims,
    loading,
    pulseStats,
    // filters
    search,       setSearch,
    sourceFilter, setSourceFilter,
    ratingFilter, setRatingFilter,
    filterOptions,
    activeFilterCount,
    clearFilters,
    // sort
    sortKey, sortDirection, changeSort,
    // selection
    selectedIds,
    allVisibleSelected,
    toggleRow,
    toggleAllVisible,
    clearSelection,
    // pagination
    page: safePage,
    pageSize,
    setPage,
    setPageSize,
    totalPages,
    // actions
    removeClaim,
    bulkRemoveRefund,
    setAuctionNumber,
    postSummary,
    reload: loadClaims,
  };
}
