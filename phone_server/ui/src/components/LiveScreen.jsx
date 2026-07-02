import React, { useEffect, useRef, useState } from "react";
import { screenshot } from "../api.js";

// Live phone screen. Polls a screenshot and reports normalized 0-1000 click
// coordinates via onPoint(nx, ny). `hint` labels what a click will do.
export default function LiveScreen({ deviceId, onPoint, hint = "click to tap", fps = 0.8 }) {
  const [src, setSrc] = useState(null);
  const [err, setErr] = useState(null);
  const [paused, setPaused] = useState(false);
  const imgRef = useRef(null);

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
        <button className="ghost" onClick={() => setPaused((p) => !p)}>{paused ? "▶ resume" : "⏸ pause"}</button>
      </div>
      {err && <div className="err">{err}</div>}
      {src ? (
        <img ref={imgRef} src={src} className="screen" onClick={click} alt="phone screen" />
      ) : (
        <div className="screen empty">loading…</div>
      )}
    </div>
  );
}
