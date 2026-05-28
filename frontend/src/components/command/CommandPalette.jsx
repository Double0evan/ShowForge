import "./commandPalette.css";
import { useEffect, useMemo, useRef, useState } from "react";

const COMMANDS = [
  {
    id: "inventory",
    icon: "▣",
    label: "Open Inventory",
    hint: "Upload, publish, assign, and inspect show inventory",
    page: "Inventory",
    group: "Navigation",
  },
  {
    id: "claims",
    icon: "⇅",
    label: "Open Claims",
    hint: "View finalized ownership records",
    page: "Claims",
    group: "Navigation",
  },
  {
    id: "bin-manager",
    icon: "◎",
    label: "Open Bin Manager",
    hint: "Manage auction queue and assignment workflow",
    page: "Bin Manager",
    group: "Navigation",
  },
  {
    id: "users",
    icon: "◌",
    label: "Open Users",
    hint: "Review Discord, pending, and guest users",
    page: "Users",
    group: "Navigation",
  },
  {
    id: "database",
    icon: "▤",
    label: "Open Database",
    hint: "Inspect backend data structures",
    page: "Database",
    group: "Navigation",
  },
  {
    id: "upload",
    icon: "⇧",
    label: "Stage Uploads",
    hint: "Jump to inventory upload workflow",
    page: "Inventory",
    workspace: "Inventory Ops",
    group: "Inventory",
  },
  {
    id: "publish",
    icon: "↑",
    label: "Publish Inventory",
    hint: "Use inventory actions to publish selected cards",
    page: "Inventory",
    workspace: "Inventory Ops",
    group: "Inventory",
    toast: "Use Inventory actions to publish selected items.",
  },
  {
    id: "summary",
    icon: "☰",
    label: "Prepare Claims Summary",
    hint: "Generate the show claims summary later through backend wiring",
    page: "Claims",
    group: "Claims",
    toast: "Claims summary is mocked until backend wiring.",
  },
  {
    id: "lock-trades",
    icon: "⌁",
    label: "Lock Trades",
    hint: "Trade lock will call the backend once wired",
    page: "Bin Manager",
    group: "Show Control",
    toast: "Trade lock action is backend-deferred.",
  },
  {
  id: "console",
  icon: "▶",
  label: "Open Console",
  hint: "Run commands and monitor live logs",
  page: "Console",
  group: "Navigation",
},
{
  id: "settings",
  icon: "⚙",
  label: "Open Settings",
  hint: "Environment config, channel IDs, file paths",
  page: "Settings",
  group: "Navigation",
},
{
  id: "history",
  icon: "◫",
  label: "Open History",
  hint: "Browse and download past show data",
  page: "History",
  group: "Navigation",
},
{
  id: "award",
  icon: "+",
  label: "Award Credits",
  hint: "Go to Users to bulk award credits",
  page: "Users",
  group: "Show Control",
},
{
  id: "new-show",
  icon: "◇",
  label: "New Show",
  hint: "Create a new show via Console",
  page: "Console",
  group: "Show Control",
},
{
  id: "end-show",
  icon: "◈",
  label: "End Show",
  hint: "End the active show via Console",
  page: "Console",
  group: "Show Control",
},
];

function normalize(value) {
  return String(value || "").toLowerCase();
}

export default function CommandPalette({
  open,
  onClose,
  activePage,
  setActivePage,
  setActiveWorkspace,
  showToast,
}) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);

  const filteredCommands = useMemo(() => {
    const q = normalize(query.trim());

    if (!q) return COMMANDS;

    return COMMANDS.filter((command) =>
      [command.label, command.hint, command.group, command.page]
        .some((value) => normalize(value).includes(q))
    );
  }, [query]);

  useEffect(() => {
    if (!open) return;

    setQuery("");
    setSelectedIndex(0);

    const focusTimer = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 30);

    return () => window.clearTimeout(focusTimer);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelectedIndex((current) =>
          Math.min(current + 1, filteredCommands.length - 1)
        );
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelectedIndex((current) => Math.max(current - 1, 0));
        return;
      }

      if (event.key === "Enter") {
        event.preventDefault();
        const command = filteredCommands[selectedIndex];
        if (command) runCommand(command);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, filteredCommands, selectedIndex]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  function runCommand(command) {
    if (command.page) setActivePage(command.page);
    if (command.workspace) setActiveWorkspace?.(command.workspace);

    showToast?.(command.toast || command.label);
    onClose();
  }

  if (!open) return null;

  const groupedCommands = filteredCommands.reduce((groups, command) => {
    const group = command.group || "Commands";
    groups[group] = groups[group] || [];
    groups[group].push(command);
    return groups;
  }, {});

  let visibleIndex = -1;

  return (
    <div className="command-backdrop" onMouseDown={onClose}>
      <section
        className="command-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="command-input-wrap">
          <span className="command-input-icon">⌘</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Search commands, pages, actions...`}
          />
          <kbd>Esc</kbd>
        </div>

        <div className="command-results">
          {filteredCommands.length === 0 && (
            <div className="command-empty">
              <strong>No commands found</strong>
              <span>Try searching for inventory, claims, users, or bin manager.</span>
            </div>
          )}

          {Object.entries(groupedCommands).map(([group, commands]) => (
            <div className="command-group-block" key={group}>
              <div className="command-group-label">{group}</div>

              {commands.map((command) => {
                visibleIndex += 1;
                const isActive = visibleIndex === selectedIndex;

                return (
                  <button
                    key={command.id}
                    type="button"
                    className={`command-row ${isActive ? "is-active" : ""}`}
                    onMouseEnter={() => setSelectedIndex(visibleIndex)}
                    onClick={() => runCommand(command)}
                  >
                    <span className="command-row-icon">{command.icon}</span>

                    <span className="command-row-copy">
                      <strong>{command.label}</strong>
                      <small>{command.hint}</small>
                    </span>

                    <span className="command-row-page">{command.page || activePage}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <footer className="command-help">
          <span>↑↓ Navigate</span>
          <span>Enter Select</span>
          <span>Ctrl K Open</span>
        </footer>
      </section>
    </div>
  );
}
