import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const FORMATS = [
  ["system_prompt", "System Prompt", "Paste into OpenClaw / Hermes / Claude Code / any LLM"],
  ["tools", "Tools (OpenAI)", "OpenAI function-calling schema"],
  ["tools_anthropic", "Tools (Anthropic)", "Anthropic tool schema"],
  ["mcp", "MCP config", "For MCP-capable agents (via mcp-openapi-proxy)"],
  ["rest_cheatsheet", "REST cheatsheet", "curl examples"],
];

export default function Hookup() {
  const [kit, setKit] = useState(null);
  const [fmt, setFmt] = useState("system_prompt");
  const [redact, setRedact] = useState(false);
  const [copied, setCopied] = useState(false);

  async function load() { setKit(await api(`/integration?redact=${redact}`)); }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [redact]);

  function text() {
    if (!kit) return "";
    const v = kit[fmt];
    return typeof v === "string" ? v : JSON.stringify(v, null, 2);
  }
  async function copy() { await navigator.clipboard.writeText(text()); setCopied(true); setTimeout(() => setCopied(false), 1200); }

  return (
    <div className="col">
      <h3>Agent hookup kit <span className="muted small">— generated live from your phones, apps & accounts</span></h3>
      <p className="muted">Give this to any agent so it can drive the phones. Paste the System Prompt, register the Tools, or wire the MCP config.</p>
      <div className="row">
        {FORMATS.map(([id, label]) => <button key={id} className={fmt === id ? "chip active" : "chip"} onClick={() => setFmt(id)}>{label}</button>)}
        <label className="chk"><input type="checkbox" checked={redact} onChange={(e) => setRedact(e.target.checked)} /> hide API key</label>
        <button onClick={copy}>{copied ? "✓ copied" : "Copy"}</button>
      </div>
      <div className="muted small">{FORMATS.find((f) => f[0] === fmt)?.[2]}</div>
      {!redact && kit?.server?.auth_required && <div className="warn">⚠ Contains your API key — treat as a secret.</div>}
      <pre className="code">{text()}</pre>
    </div>
  );
}
