import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import LiveScreen from "../components/LiveScreen.jsx";

const ACTIONS = ["open_app", "tap_element", "type", "swipe_dir", "wait", "wait_for", "assert_screen", "back", "home"];

function slugify(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "el";
}

export default function Onboard() {
  const [devices, setDevices] = useState([]);
  const [device, setDevice] = useState("");
  const [packages, setPackages] = useState([]);
  const [pkg, setPkg] = useState("");
  const [app, setApp] = useState("");
  const [session, setSession] = useState(null);
  const [draft, setDraft] = useState(null);
  const [mode, setMode] = useState("tap"); // tap | label
  const [msg, setMsg] = useState("");
  // flow builder (manual)
  const [flowName, setFlowName] = useState("");
  const [flowParams, setFlowParams] = useState("");
  const [steps, setSteps] = useState([]);
  // auto train (recording)
  const [recording, setRecording] = useState(false);
  const [recFlow, setRecFlow] = useState("");
  const [autoScreens, setAutoScreens] = useState(true);
  const [recParams, setRecParams] = useState([]);
  const [recCount, setRecCount] = useState(0);
  const [lastActivity, setLastActivity] = useState(null);

  useEffect(() => { api("/registry/devices").then((d) => { setDevices(d.devices); if (d.devices[0]) setDevice(d.devices[0].device_id); }); }, []);
  useEffect(() => { if (device) api(`/devices/${device}/packages`).then((d) => setPackages(d.packages)).catch(() => {}); }, [device]);

  async function refreshDraft(sid) { setDraft(await api(`/onboard/${sid || session}/draft`)); }

  async function start() {
    setMsg("starting…");
    try {
      const r = await api("/onboard/start", { method: "POST", body: { app: app || pkg.split(".").pop(), package: pkg, device_id: device } });
      setSession(r.session_id); setApp(r.app); await refreshDraft(r.session_id);
      setMsg(`session ${r.session_id} — launch the app on the phone, then capture`);
    } catch (e) { setMsg(String(e.message || e)); }
  }
  async function openApp() { try { await api(`/apps/${app}/devices/${device}/open`, { method: "POST" }); } catch { /* not saved yet */ await api(`/devices/${device}/launch`, { method: "POST", body: { app } }).catch(() => {}); } }
  async function capture() { const c = await api(`/onboard/${session}/capture`, { method: "POST" }); setMsg(`captured ${c.node_count} nodes · screen: ${c.detected_screen || "unknown"}`); }

  // --- Auto Train: recording -------------------------------------------

  function toggleRecord() {
    if (!recording) {
      if (!session) { setMsg("start a session first"); return; }
      if (!recFlow) { setMsg("enter a flow name to record into"); return; }
      setRecording(true); setRecParams([]); setRecCount(0); setLastActivity(null);
      setMsg(`● recording to "${recFlow}" — tap the screen, or use the quick actions below`);
    } else {
      setRecording(false);
      setMsg(`■ stopped recording "${recFlow}" — review it under Learned, or Save the app profile`);
    }
  }

  async function pushRecordedStep(step) {
    await api(`/onboard/${session}/record`, { method: "POST", body: { flow: recFlow, step } });
    setRecCount((c) => c + 1);
    refreshDraft();
  }

  async function maybeRecordScreenChange() {
    if (!autoScreens) return;
    try {
      const info = await api(`/devices/${device}/current_app`);
      if (info.activity && info.activity !== lastActivity) {
        setLastActivity(info.activity);
        const screenName = slugify(info.activity.split("/").pop() || info.activity);
        const d = await api(`/onboard/${session}/draft`);
        if (!d.screens[screenName]) {
          await api(`/onboard/${session}/screen`, { method: "POST", body: { name: screenName } });
        }
        await api(`/onboard/${session}/record`, { method: "POST", body: { flow: recFlow, step: { action: "assert_screen", screen: screenName, timeout: 6, optional: true } } });
        setRecCount((c) => c + 1);
      }
    } catch { /* best-effort — never block recording on this */ }
    refreshDraft();
  }

  async function recordTap(nx, ny) {
    await api(`/devices/${device}/tap`, { method: "POST", body: { x: nx, y: ny, normalized: true } });
    let name = `el_${recCount + 1}`;
    try {
      const sug = await api(`/onboard/${session}/suggest`, { method: "POST", body: { x: nx, y: ny, normalized: true } });
      const label = sug?.node?.text || sug?.node?.content_desc;
      if (label) name = slugify(label);
    } catch { /* fall back to el_N */ }
    await api(`/onboard/${session}/element`, { method: "POST", body: { name, from_x: nx, from_y: ny, normalized: true } });
    await pushRecordedStep({ action: "tap_element", element: name });
    setMsg(`● recorded: tap_element "${name}"`);
    await maybeRecordScreenChange();
  }

  async function recordBack() {
    await api(`/devices/${device}/back`, { method: "POST" });
    await pushRecordedStep({ action: "back" });
    setMsg("● recorded: back");
    await maybeRecordScreenChange();
  }
  async function recordHome() {
    await api(`/devices/${device}/home`, { method: "POST" });
    await pushRecordedStep({ action: "home" });
    setMsg("● recorded: home");
  }
  async function recordWaitStep() {
    await pushRecordedStep({ action: "wait", seconds: 1 });
    setMsg("● recorded: wait 1s");
  }
  async function recordType() {
    const text = prompt("Text to type now:");
    if (!text) return;
    const asParam = confirm(`Save as a reusable parameter {{text}}?\nOK = parameter (recommended)\nCancel = literal text "${text}"`);
    await api(`/devices/${device}/type`, { method: "POST", body: { text, clear: true } });
    const stepText = asParam ? "{{text}}" : text;
    await pushRecordedStep({ action: "type", text: stepText });
    if (asParam && !recParams.includes("text")) {
      const params = [...recParams, "text"];
      setRecParams(params);
      const d = await api(`/onboard/${session}/draft`);
      const existingSteps = d.flows[recFlow]?.steps || [];
      await api(`/onboard/${session}/flow`, { method: "POST", body: { flow: { name: recFlow, params, steps: existingSteps } } });
    }
    setMsg(`● recorded: type "${stepText}"`);
    refreshDraft();
  }

  // --- manual click handling (Tap / Label element modes) -----------------

  async function onPoint(nx, ny) {
    if (!session) { setMsg("start a session first"); return; }
    if (recording) { await recordTap(nx, ny); return; }
    if (mode === "tap") {
      await api(`/devices/${device}/tap`, { method: "POST", body: { x: nx, y: ny, normalized: true } });
      setMsg(`✓ tapped (${nx}, ${ny}) — watch the phone / wait for the next screenshot refresh`);
      return;
    }
    const name = prompt("Element name (e.g. compose_button):");
    if (!name) return;
    await api(`/onboard/${session}/element`, { method: "POST", body: { name, from_x: nx, from_y: ny, normalized: true } });
    setMsg(`element '${name}' saved`); refreshDraft();
  }
  async function addScreen() {
    const name = prompt("Screen name (e.g. home):"); if (!name) return;
    await api(`/onboard/${session}/screen`, { method: "POST", body: { name } });
    setMsg(`screen '${name}' saved`); refreshDraft();
  }
  function addStep() { setSteps([...steps, { action: "tap_element", element: "" }]); }
  function upStep(i, patch) { setSteps(steps.map((s, j) => (j === i ? { ...s, ...patch } : s))); }
  function rmStep(i) { setSteps(steps.filter((_, j) => j !== i)); }
  async function saveFlow() {
    const params = flowParams.split(",").map((s) => s.trim()).filter(Boolean);
    const flow = { name: flowName, params, steps: steps.map(cleanStep) };
    await api(`/onboard/${session}/flow`, { method: "POST", body: { flow } });
    setMsg(`flow '${flowName}' saved`); setSteps([]); setFlowName(""); setFlowParams(""); refreshDraft();
  }
  async function saveProfile() { const r = await api(`/onboard/${session}/save`, { method: "POST" }); setMsg(`saved → ${r.saved}`); }

  const elementNames = draft ? Object.keys(draft.elements) : [];
  const recStepCount = draft?.flows?.[recFlow]?.steps?.length || 0;

  return (
    <div className="grid">
      <div className="col narrow">
        <h3>1 · Target</h3>
        <label>Phone</label>
        <select value={device} onChange={(e) => setDevice(e.target.value)}>
          {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.label || d.device_id}</option>)}
        </select>
        <label>App package</label>
        <input list="pkgs" value={pkg} onChange={(e) => setPkg(e.target.value)} placeholder="com.twitter.android" />
        <datalist id="pkgs">{packages.map((p) => <option key={p} value={p} />)}</datalist>
        <label>App slug</label>
        <input value={app} onChange={(e) => setApp(e.target.value)} placeholder="twitter" />
        <div className="row">
          <button className="primary" onClick={start} disabled={!device || !pkg}>Start session</button>
          <button className="ghost" onClick={openApp} disabled={!session}>Open app</button>
          <button className="ghost" onClick={capture} disabled={!session}>Capture</button>
        </div>
        {session && <div className="muted small">session {session}</div>}
        {msg && <div className="note">{msg}</div>}

        <h3>Auto Train <span className={"rec-toggle" + (recording ? " on" : "")}>{recording ? `● recording (${recStepCount} steps)` : "off"}</span></h3>
        <p className="muted small">Toggle recording, then just use the phone below — every tap becomes a robust step automatically (selectors derived for you, no manual labeling).</p>
        <div className="row">
          <input placeholder="flow to record (post_tweet)" value={recFlow} onChange={(e) => setRecFlow(e.target.value)} disabled={recording} style={{ flex: 1, minWidth: 140 }} />
          <button className={recording ? "" : "primary"} onClick={toggleRecord} disabled={!session || (!recording && !recFlow)}>
            {recording ? "⏹ Stop" : "⏺ Record"}
          </button>
        </div>
        {recording && (
          <>
            <div className="row">
              <button className="ghost" onClick={recordBack}>⌫ Back</button>
              <button className="ghost" onClick={recordHome}>⌂ Home</button>
              <button className="ghost" onClick={recordWaitStep}>⏱ Wait 1s</button>
              <button className="ghost" onClick={recordType}>⌨ Type text…</button>
            </div>
            <label className="chk"><input type="checkbox" checked={autoScreens} onChange={(e) => setAutoScreens(e.target.checked)} /> auto-detect &amp; assert screens on navigation</label>
          </>
        )}

        <h3>Screen ·
          <span className="modeswitch">
            <button className={mode === "tap" ? "chip active" : "chip"} onClick={() => setMode("tap")} disabled={recording}>Tap</button>
            <button className={mode === "label" ? "chip active" : "chip"} onClick={() => setMode("label")} disabled={recording}>Label element</button>
          </span>
        </h3>
        <LiveScreen deviceId={device} onPoint={onPoint}
          hint={recording ? "🔴 recording — click to tap & capture a step" : mode === "tap" ? "click to tap & navigate" : "click a control to name it"}
          markerVariant={recording ? "rec-marker" : "click-marker"}
          disabled={!session} disabledReason={!session ? "Click \"Start session\" above first — the screen isn't clickable until then" : ""} />
      </div>

      <div className="col">
        <h3>2 · Learned <button className="ghost" onClick={addScreen} disabled={!session}>+ name current screen</button></h3>
        {draft ? (
          <div className="cards">
            <div className="card"><b>Elements</b> {elementNames.length ? elementNames.map((n) => <span key={n} className="tag">{n}</span>) : <i className="muted">none yet — record or label an element</i>}</div>
            <div className="card"><b>Screens</b> {Object.keys(draft.screens).length ? Object.keys(draft.screens).map((n) => <span key={n} className="tag">{n}</span>) : <i className="muted">none yet</i>}</div>
            <div className="card"><b>Flows</b> {Object.keys(draft.flows).length ? Object.entries(draft.flows).map(([n, f]) => <span key={n} className="tag">{n} ({f.steps?.length || 0})</span>) : <i className="muted">none yet</i>}</div>
          </div>
        ) : <div className="muted">start a session to begin</div>}

        <h3>3 · Build a flow manually</h3>
        <div className="row">
          <input placeholder="flow name (post_tweet)" value={flowName} onChange={(e) => setFlowName(e.target.value)} />
          <input placeholder="params comma-sep (text)" value={flowParams} onChange={(e) => setFlowParams(e.target.value)} />
        </div>
        {steps.map((s, i) => (
          <div className="steprow" key={i}>
            <select value={s.action} onChange={(e) => upStep(i, { action: e.target.value })}>
              {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            {["tap_element", "wait_for"].includes(s.action) && (
              <select value={s.element || ""} onChange={(e) => upStep(i, { element: e.target.value })}>
                <option value="">element…</option>{elementNames.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            )}
            {s.action === "type" && <input placeholder="text or {{param}}" value={s.text || ""} onChange={(e) => upStep(i, { text: e.target.value })} />}
            {s.action === "swipe_dir" && <select value={s.direction || "up"} onChange={(e) => upStep(i, { direction: e.target.value })}>{["up", "down", "left", "right"].map((d) => <option key={d}>{d}</option>)}</select>}
            {s.action === "assert_screen" && <select value={s.screen || ""} onChange={(e) => upStep(i, { screen: e.target.value })}><option value="">screen…</option>{draft && Object.keys(draft.screens).map((n) => <option key={n} value={n}>{n}</option>)}</select>}
            {["wait", "wait_for"].includes(s.action) && <input type="number" placeholder="sec" style={{ width: 60 }} value={s.seconds || ""} onChange={(e) => upStep(i, { seconds: parseFloat(e.target.value) })} />}
            <button className="ghost" onClick={() => rmStep(i)}>✕</button>
          </div>
        ))}
        <div className="row">
          <button className="ghost" onClick={addStep} disabled={!session}>+ step</button>
          <button className="primary" onClick={saveFlow} disabled={!session || !flowName || !steps.length}>Save flow</button>
        </div>

        <h3>4 · Save</h3>
        <button className="primary" onClick={saveProfile} disabled={!session}>💾 Save app profile</button>
      </div>
    </div>
  );
}

function cleanStep(s) {
  const out = { action: s.action };
  for (const k of ["element", "text", "direction", "screen", "seconds"]) if (s[k] !== undefined && s[k] !== "") out[k] = s[k];
  return out;
}
