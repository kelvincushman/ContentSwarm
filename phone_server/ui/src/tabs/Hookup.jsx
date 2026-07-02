import React, { useEffect, useState } from "react";
import { api, getBase, getKey } from "../api.js";

const FORMATS = [
  ["system_prompt", "System Prompt", "Paste into OpenClaw / Hermes / Claude Code / any LLM"],
  ["tools", "Tools (OpenAI)", "OpenAI function-calling schema"],
  ["tools_anthropic", "Tools (Anthropic)", "Anthropic tool schema"],
  ["mcp", "MCP config", "For MCP-capable agents (via mcp-openapi-proxy)"],
  ["rest_cheatsheet", "REST cheatsheet", "curl examples"],
];

export default function Hookup() {
  const [kit, setKit] = useState(null);
  const [skills, setSkills] = useState(null);
  const [fmt, setFmt] = useState("system_prompt");
  const [redact, setRedact] = useState(false);
  const [copied, setCopied] = useState(false);
  const [preview, setPreview] = useState(null);

  async function load() {
    setKit(await api(`/integration?redact=${redact}`));
    try { setSkills(await api(`/integration/skills?redact=${redact}`)); } catch {}
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [redact]);

  function text() {
    if (!kit) return "";
    const v = kit[fmt];
    return typeof v === "string" ? v : JSON.stringify(v, null, 2);
  }
  async function copy() { await navigator.clipboard.writeText(text()); setCopied(true); setTimeout(() => setCopied(false), 1200); }

  async function downloadSkills() {
    const res = await fetch(`${getBase()}/integration/skills.zip?redact=${redact}`, { headers: { "X-API-Key": getKey() } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "phone-skills.zip"; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="col">
      <h3>Agent hookup kit <span className="muted small">— generated live from your phones, apps & accounts</span></h3>
      <p className="muted">Give this to any agent so it can drive the phones. Paste the System Prompt, register the Tools, wire the MCP config — or install Skills.</p>
      <div className="row">
        {FORMATS.map(([id, label]) => <button key={id} className={fmt === id ? "chip active" : "chip"} onClick={() => setFmt(id)}>{label}</button>)}
        <label className="chk"><input type="checkbox" checked={redact} onChange={(e) => setRedact(e.target.checked)} /> hide API key</label>
        <button className="primary" onClick={copy}>{copied ? "✓ copied" : "Copy"}</button>
      </div>
      <div className="muted small">{FORMATS.find((f) => f[0] === fmt)?.[2]}</div>
      {!redact && kit?.server?.auth_required && <div className="warn">⚠ Contains your API key — treat as a secret.</div>}
      <pre className="code">{text()}</pre>

      <h3>Skills <span className="muted small">— drop-in agent skills (alternative to MCP)</span></h3>
      <p className="muted">Each skill's <b>description</b> tells the agent <i>when</i> to use it, so it self-invokes. Unzip into the agent's skills directory (Claude Code / Hermes / OpenClaw).</p>
      <div className="row">
        <button className="primary" onClick={downloadSkills}>⬇ Download skills .zip</button>
        <span className="muted small">{skills ? `${skills.count} skill(s)` : ""}</span>
      </div>
      {skills && (
        <div className="cards">
          {skills.skills.map((s) => (
            <div className="card" key={s.name}>
              <b>{s.name}</b> <span className="muted small">{s.description}</span>
              <button className="ghost" style={{ float: "right" }} onClick={() => setPreview(skills.files.find((f) => f.path.startsWith(s.name + "/") && f.path.endsWith("SKILL.md"))?.content || "(no SKILL.md)")}>preview</button>
            </div>
          ))}
        </div>
      )}
      {preview && <pre className="code">{preview}</pre>}
    </div>
  );
}
