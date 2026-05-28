import Button from "./Button";

export default function FilterBar({
  search,
  onSearchChange,
  searchPlaceholder = "Search…",
  filters = [],
  activeFilterCount = 0,
  onClear,
}) {
  return (
    <div className="filter-bar">
      <div className="filter-search">
        <span>⌕</span>
        <input
          value={search}
          placeholder={searchPlaceholder}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>

      <div className="filter-controls">
        {filters.map((filter) => (
          <label className="filter-field" key={filter.key}>
            <span>{filter.label}</span>
            <select
              value={filter.value}
              onChange={(event) => filter.onChange(event.target.value)}
            >
              {filter.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>

      <Button onClick={onClear} disabled={activeFilterCount === 0}>
        Clear{activeFilterCount ? ` (${activeFilterCount})` : ""}
      </Button>
    </div>
  );
}
