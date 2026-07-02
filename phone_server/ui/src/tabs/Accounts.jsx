import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const PLATFORMS = ["facebook", "instagram", "linkedin", "x", "tiktok", "youtube"];
const KINDS = ["personal", "business", "creator", "page"];

export default function Accounts() {
  const [devices, setDevices] = useState([]);
  const [apps, setApps] = useState([]);
  const [form, setForm] = useState({ device_id: "", name: "", platform: "facebook", kind: "business", app: "", handle: "" });
  const [msg, setMsg] = useState("");

  async function load() {
    const d = await api("/registry/devices"); setDevices(d.devices);
    if (!form.device_id && d.devices[0]) setForm((f) => ({ ...f, device_id: d.devices[0].device_id }));
    setApps((await api("/apps")).apps.map((a) => a.app));
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  async function add() {
    try {
      const { device_id, ...body } = form;
      await api(`/registry/devices/${device_id}/accounts`, { method: "POST", body });
      setMsg(`added ${form.name}`); setForm((f) => ({ ...f, name: "", handle: "" })); load();
    } catch (e) { setMsg(String(e.message || e)); }
  }
  async function del(dev, id) { await api(`/registry/devices/${dev}/accounts/${id}`, { method: "DELETE" }); load(); }

  return (
    <div className="grid">
      <div className="col">
        <h3>Accounts per phone</h3>
        {devices.map((d) => (
          <div className="card" key={d.device_id}>
            <b>{d.label || d.device_id}</b> <span className="muted small">{d.device_id}</span>
            {d.accounts.length === 0 && <div className="muted small">no accounts</div>}
            {d.accounts.map((a) => (
              <div className="acctrow" key={a.id}>
                <span className={"badge " + a.platform}>{a.platform}</span>
                <span>{a.name}</span><span className="muted small">{a.kind}{a.app ? ` · ${a.app}` : ""}{a.handle ? ` · ${a.handle}` : ""}</span>
                <button className="ghost" onClick={() => del(d.device_id, a.id)}>✕</button>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="col narrow">
        <h3>Add account</h3>
        <label>Phone</label>
        <select value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })}>
          {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.label || d.device_id}</option>)}
        </select>
        <label>Name</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Acme Ltd / Kelvin Lee" />
        <label>Platform</label>
        <select value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>{PLATFORMS.map((p) => <option key={p}>{p}</option>)}</select>
        <label>Kind</label>
        <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select>
        <label>App (onboarded slug)</label>
        <input list="apps" value={form.app} onChange={(e) => setForm({ ...form, app: e.target.value })} placeholder="facebook" />
        <datalist id="apps">{apps.map((a) => <option key={a} value={a} />)}</datalist>
        <label>Handle</label>
        <input value={form.handle} onChange={(e) => setForm({ ...form, handle: e.target.value })} placeholder="@handle / page name" />
        <button className="primary" onClick={add} disabled={!form.device_id || !form.name}>Add account</button>
        {msg && <div className="note">{msg}</div>}
      </div>
    </div>
  );
}
