import React, { useEffect, useRef, useState } from "react";
import { screenshot, api } from "../api.js";

// Detect a (near) all-black frame by sampling the decoded image on a canvas.
function isBlack(img) {
  try {
    const c = document.createElement("canvas");
    c.width = 24; c.height = 48;
    const ctx = c.getContext("2d");
    ctx.drawImage(img, 0, 0, 24, 48);
    const d = ctx.getImageData(0, 0, 24, 48).data;
    let max = 0;
    for (let i = 0; i < d.length; i += 4) max = Math.max(max, d[i], d[i + 1], d[i + 2]);
    return max < 8;
  } catch { return false; }
}

// Live phone screen. Polls a screenshot and reports normalized 0-1000 click
// coordinates via onPoint(nx, ny). `hint` labels what a click will do.
export default function LiveScreen({ deviceId, onPoint, hint = "click to tap", fps = 0.8 }) {
  const [src, setSrc] = useState(null);
  const [err, setErr] = useState(null);
  const [paused, setPaused] = useState(false);
  const [blank, setBlank] = useState(false);
  const imgRef = useRef(null);

  async function wake() {
    try { const r = await api(`/devices/${deviceId}/wake`, { method: "POST" }); setErr(r.locked ? "screen woken — but phone is LOCKED, unlock it (PIN) on the device" : null); }
    catch (e) { setErr(String(e.message || e)); }
  }

  useEffect(() => {
    if (!deviceId || paused) return;
    let alive = true;
    const tick = async () => {
      try {
        const shot = await screenshot(deviceId);
        if (alive) { setSrc(shot.url); setErr(null); }
      } catch (e) {
        if (alive) setErr(String(e.message || e));
      }
    };
    tick();
    const id = setInterval(tick, Math.max(400, 1000 / fps));
    return () => { alive = false; clearInterval(id); };
  }, [deviceId, paused, fps]);

  function click(e) {
    if (!onPoint || !imgRef.current) return;
    const r = imgRef.current.getBoundingClientRect();
    const nx = Math.round(((e.clientX - r.left) / r.width) * 1000);
    const ny = Math.round(((e.clientY - r.top) / r.height) * 1000);
    onPoint(nx, ny);
  }

  if (!deviceId) return <div className="screen empty">select a device</div>;
  return (
    <div className="livescreen">
      <div className="livescreen-bar">
        <span className="muted">{hint}</span>
        <span>
          <button className="ghost" onClick={wake}>⏻ wake</button>
          <button className="ghost" onClick={() => setPaused((p) => !p)}>{paused ? "▶ resume" : "⏸ pause"}</button>
        </span>
      </div>
      {err && <div className="err">{err}</div>}
      {blank && !err && <div className="warn">Screen is black — the phone is asleep or on a secure lock screen (screenshots are blocked). Click <b>wake</b> and unlock the phone (PIN) on the device.</div>}
      {src ? (
        <img ref={imgRef} src={src} className="screen" onClick={click} alt="phone screen"
          onLoad={(e) => setBlank(isBlack(e.target))} />
      ) : (
        <div className="screen empty">loading…</div>
      )}
    </div>
  );
}
