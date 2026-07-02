import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import LiveScreen from "../components/LiveScreen.jsx";

export default function Devices() {
  const [devices, setDevices] = useState([]);
  const [hosts, setHosts] = useState([]);
  const [sel, setSel] = useState(null);
  const [addr, setAddr] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    try {
      const d = await api("/registry/devices");
      setDevices(d.devices);
      if (!sel && d.devices[0]) setSel(d.devices[0].device_id);
    } catch (e) { setMsg(String(e.message || e)); }
  }
  async function loadModels() {
    try { setHosts((await api("/config/models")).hosts); } catch {}
  }
  useEffect(() => { load(); loadModels(); /* eslint-disable-next-line */ }, []);

  async function save(dev, patch) {
    await api(`/registry/devices/${dev}`, { method: "PUT", body: patch });
    load();
  }
  async function savePin(dev, pin) {
    await api(`/registry/devices/${dev}/pin`, { method: "PUT", body: { pin } });
    load();
  }
  async function connectWifi() {
    setMsg("connecting…");
    try { const r = await api("/devices/connect", { method: "POST", body: { address: addr } }); setMsg(r.message); load(); }
    catch (e) { setMsg(String(e.message || e)); }
  }
  async function enableTcpip(dev) {
    try { const r = await api(`/devices/${dev}/tcpip`, { method: "POST" }); setMsg(`WiFi addr: ${r.wifi_address || "n/a"}`); }
    catch (e) { setMsg(String(e.message || e)); }
  }
  async function tap(nx, ny) {
    if (!sel) return;
    try { await api(`/devices/${sel}/tap`, { method: "POST", body: { x: nx, y: ny, normalized: true } }); }
    catch (e) { setMsg(String(e.message || e)); }
  }

  const allModels = hosts.flatMap((h) => h.models.map((m) => ({ label: `${m}  ·  ${h.name}`, base: h.base_url, model: m })));

  return (
    <div className="grid">
      <div className="col">
        <h3>Phones</h3>
        <div className="row">
          <input placeholder="192.168.x.x:5555" value={addr} onChange={(e) => setAddr(e.target.value)} />
          <button onClick={connectWifi}>Connect WiFi</button>
        </div>
        {msg && <div className="muted small">{msg}</div>}
        <table className="tbl">
          <thead><tr><th></th><th>Device</th><th>Label</th><th>Agent model</th><th>PIN</th><th></th></tr></thead>
          <tbody>
            {devices.map((d) => (
              <tr key={d.device_id} className={sel === d.device_id ? "selrow" : ""} onClick={() => setSel(d.device_id)}>
                <td><span className={"dot " + (d.connected ? "on" : "off")} /></td>
                <td className="mono">{d.device_id}<div className="muted small">{d.model || d.status}</div></td>
                <td><input defaultValue={d.label} onBlur={(e) => save(d.device_id, { label: e.target.value })} placeholder="add label" /></td>
                <td>
                  <select value={d.agent_model.base_url + "|" + d.agent_model.model_name}
                    onChange={(e) => { const [base, model] = e.target.value.split("|"); save(d.device_id, { model_base_url: base, model_name: model }); }}>
                    <option value={d.agent_model.base_url + "|" + d.agent_model.model_name}>{d.agent_model.model_name}</option>
                    {allModels.map((m, i) => <option key={i} value={m.base + "|" + m.model}>{m.label}</option>)}
                  </select>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <input type="password" style={{ width: 70 }} placeholder={d.has_pin ? "•••• set" : "set PIN"}
                    onBlur={(e) => { if (e.target.value) { savePin(d.device_id, e.target.value); e.target.value = ""; } }} />
                  {d.has_pin && <span className="muted small" title="auto-unlock enabled"> 🔓</span>}
                </td>
                <td><button className="ghost" onClick={(e) => { e.stopPropagation(); enableTcpip(d.device_id); }}>→WiFi</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="col narrow">
        <h3>Live screen {sel && <span className="muted small">({sel})</span>}</h3>
        <LiveScreen deviceId={sel} onPoint={tap} hint="click to tap" />
      </div>
    </div>
  );
}
