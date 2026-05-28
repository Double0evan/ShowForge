import { useEffect, useRef, useState } from "react";
import { apiClient } from "../../api/apiClient";
import { endpoints } from "../../api/endpoints";
import Panel from "../shared/Panel";
import Button from "../shared/Button";

const COMMANDS = [
  { cmd: "award",         args: "<name> <amount>",       desc: "Award credits to a user" },
  { cmd: "award_discord", args: "<discord_id> <amount>", desc: "Award by Discord ID" },
  { cmd: "add_guest",     args: "<name> [amount]",        desc: "Create a guest user" },
  { cmd: "balance",       args: "<name>",                 desc: "Check credit balance" },
  { cmd: "remove_claim",  args: "<code> [norefund]",      desc: "Remove a claim" },
  { cmd: "remove_item",   args: "<code>",                 desc: "Remove an inventory item" },
  { cmd: "publish",       args: "<code>",                 desc: "Publish item to catalog" },
  { cmd: "new_show",      args: "<YYYY-MM-DD> <name>",    desc: "Create a new show" },
  { cmd: "end_show",      args: "",                       desc: "End the active show" },
];

const QUICK_ACTIONS = [
  { label: "End Show",     cmd: "end_show",      icon: "◈", danger: true },
  { label: "+ Credit",     cmd: "award ",        icon: "+", danger: false },
  { label: "Balance",      cmd: "balance ",      icon: "◎", danger: false },
  { label: "Remove Claim", cmd: "remove_claim ", icon: "✕", danger: true },
  { label: "Guest User",   cmd: "add_guest ",    icon: "♙", danger: false },
  { label: "Publish",      cmd: "publish ",      icon: "↑", danger: false },
];

function CommandsView({ showToast }) {
  const [input, setInput]             = useState("");
  const [history, setHistory]         = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [suggIdx, setSuggIdx]         = useState(-1);
  const [cmdHistory, setCmdHistory]   = useState([]);
  const [histIdx, setHistIdx]         = useState(-1);
  const [context, setContext]         = useState({ users: [], codes: [] });
  const outputRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    apiClient.get(endpoints.users.consoleContext)
      .then((r) => setContext({ users: r.users || [], codes: r.codes || [] }))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [history]);

  useEffect(() => {
    const raw = input.trimStart();
    if (!raw) { setSuggestions([]); return; }
    const parts = raw.split(/\s+/);
    const verb  = parts[0].toLowerCase();
    if (parts.length === 1) {
      setSuggestions(COMMANDS.filter((c) => c.cmd.startsWith(verb))
        .map((c) => ({ label: `${c.cmd} ${c.args}`.trim(), value: c.cmd, desc: c.desc })));
    } else if (parts.length === 2) {
      const partial   = parts[1].toLowerCase();
      const needsUser = ["award", "add_guest", "balance"].includes(verb);
      const needsCode = ["remove_claim", "remove_item", "publish"].includes(verb);
      if (needsUser) {
        setSuggestions(context.users.filter((u) => u.toLowerCase().startsWith(partial)).slice(0, 6)
          .map((u) => ({ label: u, value: `${verb} ${u}`, desc: "" })));
      } else if (needsCode) {
        setSuggestions(context.codes.filter((c) => c.toLowerCase().startsWith(partial)).slice(0, 6)
          .map((c) => ({ label: c, value: `${verb} ${c}`, desc: "" })));
      } else { setSuggestions([]); }
    } else { setSuggestions([]); }
    setSuggIdx(-1);
  }, [input, context]);

  async function runCommand(cmd) {
    const trimmed = cmd.trim();
    if (!trimmed) return;
    setHistory((h) => [...h, { type: "cmd", text: trimmed }]);
    setCmdHistory((h) => [trimmed, ...h.slice(0, 49)]);
    setHistIdx(-1); setInput(""); setSuggestions([]);
    try {
      const fd = apiClient.toFormData({ command: trimmed });
      const r  = await apiClient.post(endpoints.users.consoleRun, fd);
      setHistory((h) => [...h, { type: r.ok ? "ok" : "err", text: r.message || r.error || (r.ok ? "Done." : "Error.") }]);
    } catch (e) {
      setHistory((h) => [...h, { type: "err", text: e.message }]);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "ArrowDown" && suggestions.length > 0) { e.preventDefault(); setSuggIdx((i) => Math.min(i + 1, suggestions.length - 1)); }
    else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (suggestions.length > 0) { setSuggIdx((i) => Math.max(i - 1, -1)); }
      else { const next = Math.min(histIdx + 1, cmdHistory.length - 1); setHistIdx(next); if (cmdHistory[next]) setInput(cmdHistory[next]); }
    } else if (e.key === "Tab" && suggestions.length > 0) {
      e.preventDefault();
      setInput(suggestions[suggIdx >= 0 ? suggIdx : 0].value + " "); setSuggestions([]);
    } else if (e.key === "Enter") {
      if (suggIdx >= 0 && suggestions[suggIdx]) { setInput(suggestions[suggIdx].value + " "); setSuggestions([]); setSuggIdx(-1); }
      else runCommand(input);
    } else if (e.key === "Escape") { setSuggestions([]); setSuggIdx(-1); }
  }

  return (
    <div className="console-workspace">
      <div className="workspace-header">
        <div><h1>Console</h1><p>Run commands. Tab to autocomplete, ↑ for history.</p></div>
        <div className="workspace-actions"><button className="console-clear-btn" onClick={() => setHistory([])}>Clear Output</button></div>
      </div>

      <div className="console-quick-row">
        {QUICK_ACTIONS.map((a) => (
          <button key={a.cmd} className={`console-quick-chip ${a.danger ? "danger" : ""}`}
            onClick={() => { setInput(a.cmd); inputRef.current?.focus(); if (!a.cmd.endsWith(" ")) runCommand(a.cmd); }}>
            <span>{a.icon}</span>{a.label}
          </button>
        ))}
      </div>

      <div className="console-layout">
        <div className="console-terminal-panel">
          <div className="console-output" ref={outputRef}>
            {history.length === 0 && (
              <div className="console-boot-msg">
                <span className="console-boot-line">ShowForge Console v3</span>
                <span className="console-boot-line dim">Tab to autocomplete · ↑↓ history · Enter to run</span>
              </div>
            )}
            {history.map((line, i) => (
              <div key={i} className={`console-line console-${line.type}`}>
                {line.type === "cmd" && <span className="console-prompt-inline">❯</span>}
                {line.type === "ok"  && <span className="console-status-ok">✓</span>}
                {line.type === "err" && <span className="console-status-err">✗</span>}
                <span>{line.text}</span>
              </div>
            ))}
          </div>
          <div className="console-input-area">
            {suggestions.length > 0 && (
              <div className="console-suggestions">
                {suggestions.map((s, i) => (
                  <div key={s.label} className={`console-suggestion ${i === suggIdx ? "active" : ""}`}
                    onMouseDown={(e) => { e.preventDefault(); setInput(s.value + " "); setSuggestions([]); inputRef.current?.focus(); }}>
                    <span className="sugg-cmd">{s.label}</span>
                    {s.desc && <span className="sugg-desc">{s.desc}</span>}
                  </div>
                ))}
              </div>
            )}
            <div className="console-input-row">
              <span className="console-prompt">❯</span>
              <input ref={inputRef} className="console-input" value={input}
                onChange={(e) => { setInput(e.target.value); setHistIdx(-1); }}
                onKeyDown={handleKeyDown} placeholder="award, balance, publish..."
                autoFocus autoComplete="off" spellCheck={false}
              />
            </div>
          </div>
        </div>

        <div className="console-right-col">
          <div className="console-ref-panel">
            <div className="console-ref-header">Commands</div>
            {COMMANDS.map((c) => (
              <div key={c.cmd} className="console-ref-row"
                onClick={() => { setInput(c.cmd + " "); inputRef.current?.focus(); }}>
                <span className="console-ref-cmd">{c.cmd}</span>
                {c.args && <span className="console-ref-args">{c.args}</span>}
                <span className="console-ref-desc">{c.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function LiveLogView() {
  const [logLines, setLogLines]   = useState([]);
  const [running, setRunning]     = useState(false);
  const logRef = useRef(null);

  useEffect(() => {
    async function poll() {
      try {
        const r = await apiClient.get(`${endpoints.watcher.log}?lines=200`);
        setLogLines(r.lines || []);
        setRunning(Boolean(r.alive));
      } catch { /* silent */ }
    }
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logLines]);

  return (
    <div className="console-workspace">
      <div className="workspace-header">
        <div>
          <h1>Live Log</h1>
          <p>Real-time watcher output. Refreshes every 3 seconds.</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className={`show-live-dot ${running ? "" : "off"}`} />
          <span style={{ fontSize: 12, color: "var(--muted)" }}>{running ? "Watcher running" : "Watcher stopped"}</span>
        </div>
      </div>
      <div className="console-terminal-panel" style={{ flex: 1, minHeight: 400 }}>
        <div className="console-output" ref={logRef}>
          {logLines.length === 0
            ? <div className="console-boot-line dim">No log output yet.</div>
            : logLines.map((line, i) => <div key={i} className="console-log-line">{line}</div>)
          }
        </div>
      </div>
    </div>
  );
}

export default function ConsoleWorkspace({ showToast, activeTab }) {
  if (activeTab === "Live Log") return <LiveLogView />;
  return <CommandsView showToast={showToast} />;
}
