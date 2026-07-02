import React, { useEffect, useState } from "react";
import { api, getBase, setBase, getKey, setKey } from "./api.js";
import Devices from "./tabs/Devices.jsx";
import Onboard from "./tabs/Onboard.jsx";
import Accounts from "./tabs/Accounts.jsx";
import Settings from "./tabs/Settings.jsx";
import Hookup from "./tabs/Hookup.jsx";

const TABS = [
  ["devices", "Devices"],
  ["onboard", "Onboard App"],
  ["accounts", "Accounts"],
  ["settings", "Settings"],
  ["hookup", "Agent Hookup"],
];

export default function App() {
  const [tab, setTab] = useState("devices");
  const [base, setBaseState] = useState(getBase());
  const [key, setKeyState] = useState(getKey());
  const [health, setHealth] = useState(null);

  // default base to same origin the console is served from
  useEffect(() => {
    if (!getBase()) {
      const origin = window.location.origin;
      setBase(origin); setBaseState(origin);
    }
  }, []);

  async function connect() {
    setBase(base); setKey(key);
    try { setHealth(await api("/health")); }
    catch (e) { setHealth({ error: String(e.message || e) }); }
  }
  useEffect(() => { connect(); /* eslint-disable-next-line */ }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">📱 Phone Server Console</div>
        <div className="conn">
          <input value={base} onChange={(e) => setBaseState(e.target.value)} placeholder="http://host:8770" style={{ width: 200 }} />
          <input value={key} onChange={(e) => setKeyState(e.target.value)} placeholder="API key" type="password" style={{ width: 130 }} />
          <button onClick={connect}>Connect</button>
          <span className={"pill " + (health?.ok ? "ok" : "bad")}>
            {health?.ok ? `v${health.version}` : health?.error ? "error" : "…"}
          </span>
        </div>
      </header>

      <nav className="tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "tab active" : "tab"} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>

      <main className="content">
        {tab === "devices" && <Devices />}
        {tab === "onboard" && <Onboard />}
        {tab === "accounts" && <Accounts />}
        {tab === "settings" && <Settings />}
        {tab === "hookup" && <Hookup />}
      </main>
    </div>
  );
}
