// Tiny API client. Base URL + API key are stored in localStorage so the console
// can point at any server on the LAN.

export function getBase() {
  return localStorage.getItem("ps_base") || "";
}
export function setBase(v) {
  localStorage.setItem("ps_base", v.replace(/\/$/, ""));
}
export function getKey() {
  return localStorage.getItem("ps_key") || "";
}
export function setKey(v) {
  localStorage.setItem("ps_key", v);
}

function headers(json) {
  const h = {};
  const k = getKey();
  if (k) h["X-API-Key"] = k;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(getBase() + path, {
    method,
    headers: headers(!!body),
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = text;
  }
  if (!res.ok) {
    throw new Error(typeof data === "object" ? data.detail || JSON.stringify(data) : data);
  }
  return data;
}

// Screenshot as a data URL (base64), for the live-screen panel.
export async function screenshot(deviceId) {
  const d = await api(`/devices/${deviceId}/screenshot?format=base64`);
  return { url: `data:image/png;base64,${d.image_base64}`, width: d.width, height: d.height };
}
