export default function TopBar({ onOpenCommandPalette, showToast }) {
  return (
    <header className="topbar">
      <button
        className="global-search command-search-trigger"
        type="button"
        onClick={onOpenCommandPalette}
      >
        <span>Search cards, users, claims...</span>
        <kbd>Ctrl K</kbd>
      </button>

      <div className="topbar-actions">
        <button
          className="top-icon-btn"
          type="button"
          title="Command menu"
          onClick={onOpenCommandPalette}
        >
          ⌘
        </button>

        <button
          className="top-icon-btn"
          type="button"
          title="Notifications"
          onClick={() => showToast?.("Notifications are mocked for now.")}
        >
          ◔
        </button>

        <button className="top-avatar" type="button" title="Account">
          E
        </button>
      </div>
    </header>
  );
}
