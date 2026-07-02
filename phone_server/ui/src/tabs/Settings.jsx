import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Settings() {
  const [cfg, setCfg] = useState(null);
  const [hosts, setHosts] = useState([]);
  const [msg, setMsg] = useState("");
  const [newHost, setNewHost] = useState({ name: "", base_url: "", api_key: "EMPTY", kind: "openai-compatible" });

  async function load() {
    const c = await api("/config"); setCfg(c);
    try { setHosts((await api("/config/models")).hosts); } catch {}
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  async function save(patch) { const r = await api("/config", { method: "PUT", body: patch }); setCfg({ ...cfg, editable: r.editable }); setMsg("saved"); }
  async function addHost() {
    const model_hosts = [...(cfg.editable.model_hosts || []), newHost];
    await save({ model_hosts }); setNewHost({ name: "", base_url: "", api_key: "EMPTY", kind: "openai-compatible" }); load();
  }
  async function rmHost(name) {
    await save({ model_hosts: cfg.editable.model_hosts.filter((h) => h.name !== name) }); load();
  }

  if (!cfg) return <div className="muted">loading…</div>;
  const e = cfg.editable, s = cfg.static;
  const allModels = hosts.flatMap((h) => h.models.map((m) => ({ base: h.base_url, model: m, name: h.name })));

  return (
    <div className="grid">
      <div className="col narrow">
        <h3>Default agent model</h3>
        <select value={(e.default_model_base_url || "") + "|" + (e.default_model_name || "")}
          onChange={(ev) => { const [base, model] = ev.target.value.split("|"); save({ default_model_base_url: base, default_model_name: model }); }}>
          <option value={(e.default_model_base_url || "") + "|" + (e.default_model_name || "")}>{e.default_model_name || "current"}</option>
          {allModels.map((m, i) => <option key={i} value={m.base + "|" + m.model}>{m.model} · {m.name}</option>)}
        </select>
        <label>Default language</label>
        <select value={e.default_lang || "en"} onChange={(ev) => save({ default_lang: ev.target.value })}><option>en</option><option>cn</option></select>
        <label>Live-stream FPS</label>
        <input type="number" step="0.5" defaultValue={e.stream_fps} onBlur={(ev) => save({ stream_fps: parseFloat(ev.target.value) })} />
        <label>Public URL (advertised in hookup kit)</label>
        <input defaultValue={e.public_url || ""} onBlur={(ev) => save({ public_url: ev.target.value })} placeholder="http://192.168.55.124:8770" />
        {msg && <div className="note">{msg}</div>}
      </div>

      <div className="col">
        <h3>Model hosts <span className="muted small">(OpenAI-compatible / Ollama)</span></h3>
        <table className="tbl">
          <thead><tr><th>Name</th><th>Base URL</th><th>Reachable</th><th>#models</th><th></th></tr></thead>
          <tbody>
            {hosts.map((h) => (
              <tr key={h.name}><td>{h.name}</td><td className="mono small">{h.base_url}</td>
                <td><span className={"dot " + (h.reachable ? "on" : "off")} /></td><td>{h.models.length}</td>
                <td><button className="ghost" onClick={() => rmHost(h.name)}>✕</button></td></tr>
            ))}
          </tbody>
        </table>
        <div className="row">
          <input placeholder="name" value={newHost.name} onChange={(ev) => setNewHost({ ...newHost, name: ev.target.value })} style={{ width: 100 }} />
          <input placeholder="http://host:11434/v1" value={newHost.base_url} onChange={(ev) => setNewHost({ ...newHost, base_url: ev.target.value })} />
          <input placeholder="api key" value={newHost.api_key} onChange={(ev) => setNewHost({ ...newHost, api_key: ev.target.value })} style={{ width: 90 }} />
          <button className="primary" onClick={addHost} disabled={!newHost.name || !newHost.base_url}>Add host</button>
        </div>

        <h3>Server (read-only)</h3>
        <div className="card mono small">
          <div>host: {s.host}:{s.port}</div>
          <div>auth required: {String(s.auth_required)}</div>
          <div>profiles dir: {s.profiles_dir}</div>
          <div>registry: {s.registry_path}</div>
        </div>
      </div>
    </div>
  );
}
