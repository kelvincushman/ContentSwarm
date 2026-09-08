"use strict";
const $ = id => document.getElementById(id);
let csrf = "", phones = [], previewUrl = null, polling = false;
function say(text) { $("notice").textContent = text; }
function el(tag, text, cls) { const e = document.createElement(tag); if(text !== undefined) e.textContent=text; if(cls)e.className=cls; return e; }
function button(text, fn) { const b=el("button",text); b.type="button"; b.onclick=()=>guard(fn,b); return b; }
async function guard(fn, b) { if(b)b.disabled=true; try { await fn(); } catch(e) { say(e.message); } finally { if(b)b.disabled=false; } }
async function api(path, body, raw=false) {
  if(location.protocol!=="https:" && !["localhost","127.0.0.1","[::1]"].includes(location.hostname))throw Error("Open this console over HTTPS before signing in.");
  const r=await fetch(path.startsWith("/api/")?path:"/api/v1"+path,{method:body===undefined?"GET":"POST",credentials:"same-origin",headers:body===undefined?{}:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:body===undefined?undefined:JSON.stringify(body)});
  if(!r.ok){let data;try{data=await r.json();}catch{}throw Error(data?.error||`Request failed (${r.status})`);}
  return raw?r:await r.json();
}
function phonePath() { const name=$("phone").value; if(!name || !phones.some(p=>p.name===name&&p.connected))throw Error("Connect and select an authorized phone first."); return "/phones/"+encodeURIComponent(name); }
function confirmAction(title, text) { return new Promise(resolve=>{const d=$("confirm");$("confirm-title").textContent=title;$("confirm-body").textContent=text;d.returnValue="cancel";d.onclose=()=>resolve(d.returnValue==="yes");d.showModal();}); }
function empty(target, text) { $(target).replaceChildren(el("p",text,"empty")); }
async function refresh() {
  const [p,t,f,r]=await Promise.all([api("/phones"),api("/tasks"),api("/flows"),api("/reviews")]);
  const selected=$("phone").value; phones=p.phones; $("phone").replaceChildren();
  for(const ph of phones){const option=el("option",ph.name+(ph.connected?" · connected":" · offline"));option.value=ph.name;$("phone").append(option);}
  if(phones.some(p=>p.name===selected))$("phone").value=selected;
  $("connection").textContent=`${phones.filter(p=>p.connected).length} phone(s) connected`; phoneStatus();
  const tasks=Array.isArray(t.tasks)?t.tasks:Object.values(t.tasks||{});
  empty("task-list","No tasks yet. Start with a small navigation task.");
  if(tasks.length){$("task-list").replaceChildren();for(const task of tasks.slice().reverse().slice(0,20)){const card=el("article",undefined,"card");card.append(el("span",task.status||"pending","badge"),el("p",task.task||task.task_id||"Phone task"),el("pre",JSON.stringify(task.result||task.error||{},null,2)));$("task-list").append(card);}}
  empty("flow-list","No learned flows yet. Teach a bounded workflow from Tasks.");
  if(f.flows.length){$("flow-list").replaceChildren();for(const flow of f.flows){const card=el("article",undefined,"card");card.append(el("h2",flow.name),el("p",flow.task),el("span",`${flow.steps} steps · ${flow.app||"app unspecified"}`,"badge"),button("Inspect and replay",async()=>{const detail=await api("/flows/"+encodeURIComponent(flow.name));if(await confirmAction("Run this recorded workflow?",JSON.stringify(detail,null,2))){await api(phonePath()+"/replay",{flow_name:flow.name});say("Replay submitted. Check the task result and phone screen.");await refresh();}}));$("flow-list").append(card);}}
  renderReviews(r.reviews);
}
function phoneStatus(){const p=phones.find(p=>p.name===$("phone").value);$("phone-status").textContent=p?(p.connected?"Connected over ADB":"Offline. Reconnect and authorize USB debugging."):"No devices enrolled. Click Discover.";}
function renderReviews(items) {
  $("pending").textContent=items.filter(i=>i.status==="pending").length;
  empty("review-list","Your reply queue is clear. The agent adds Humanizer-reviewed drafts here with their source conversation.");
  if(!items.length)return;$("review-list").replaceChildren();
  for(const item of items){const card=el("article",undefined,"card");card.append(el("p",`${item.platform} · ${item.account} · ${item.status}`,"review-meta"),el("h2",`${item.author} said`),el("blockquote",item.original),el("h2","Your reply"),el("blockquote",item.reply,"reply"));const link=el("a","Open source conversation");link.href=item.source_url;link.target="_blank";link.rel="noopener noreferrer";card.append(link,el("p",`Humanizer ${item.humanizer_version}${item.edited_by_user?" · edited by you":""}`,"hint"));
    if(["pending","rejected"].includes(item.status)){const actions=el("div",undefined,"review-actions");const editor=el("textarea");editor.value=item.reply;editor.rows=5;editor.hidden=true;editor.setAttribute("aria-label","Rewrite your reply");const save=button("Save rewrite for review",async()=>{await api(`/reviews/${item.id}/edit`,{revision:item.revision,reply:editor.value});say("Rewrite saved. Review it before approving.");await refresh();});save.hidden=true;
      actions.append(button("👍 Approve",async()=>{if(await confirmAction(`Approve reply as ${item.account}?`,`${item.author}: ${item.original}\n\nYour reply:\n${item.reply}`)){await api(`/reviews/${item.id}/approve`,{revision:item.revision});say("Approved and waiting for the agent. This is not yet a delivery confirmation.");await refresh();}}),button("👎 Reject & rewrite",async()=>{if(item.status==="pending"){const updated=await api(`/reviews/${item.id}/reject`,{revision:item.revision});Object.assign(item,updated);}editor.hidden=false;save.hidden=false;editor.focus();}),button("Edit",async()=>{editor.hidden=false;save.hidden=false;editor.focus();}));card.append(actions,editor,save);}
    if(item.evidence)card.append(el("p",item.evidence,"hint"));$("review-list").append(card);
  }
}
async function capture(){const path=phonePath();const r=await api(path+"/screenshot",undefined,true);if(path!==phonePath())return;const blob=await r.blob();if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(blob);$("preview").src=previewUrl;$("preview").hidden=false;$("preview-empty").hidden=true;}
$("login-form").onsubmit=e=>{e.preventDefault();guard(async()=>{const r=await api("/api/console/login",{token:$("token").value});$("token").value="";csrf=r.csrf;await connected();});};
async function connected(){$("login").hidden=true;$("workspace").hidden=false;$("logout").hidden=false;await refresh();}
$("logout").onclick=()=>guard(async()=>{await api("/api/console/logout",{});location.reload();});
$("refresh").onclick=()=>guard(refresh,$("refresh"));
$("discover").onclick=()=>guard(async()=>{await api("/phones/discover",{});await refresh();},$("discover"));
$("phone").onchange=()=>{phoneStatus();$("preview").hidden=true;$("preview-empty").hidden=false;$("screen-tree").textContent="";};
$("capture").onclick=()=>guard(capture,$("capture"));
for(const [id,key] of [["home","HOME"],["back","BACK"]])$(id).onclick=()=>guard(async()=>{await api(phonePath()+"/action",{action:"key",key,confirm:true});await capture();},$(id));
$("launch").onclick=()=>guard(async()=>{await api(phonePath()+"/app",{app:$("app").value});await capture();say("Launch requested. Check the preview for login or setup prompts.");},$("launch"));
$("sense").onclick=()=>guard(async()=>{const r=await api(phonePath()+"/ui");$("screen-tree").textContent=r.elements.filter(e=>e.text||e.desc).map(e=>e.text||e.desc).join("\n");},$("sense"));
$("task-form").onsubmit=e=>{e.preventDefault();guard(async()=>{const path=phonePath(),mode=$("mode").value,task=$("task").value;if(mode==="learn"&&!$("flow-name").value.trim())throw Error("Give the workflow a name.");if(!await confirmAction("Start this phone task?",task+"\n\nThe vision agent will control the selected phone. Stop before external commitments unless separately approved."))return;await api(path+"/"+mode,{task,flow_name:$("flow-name").value});say("Task submitted.");await refresh();});};
document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{document.querySelectorAll("[data-tab]").forEach(n=>n.setAttribute("aria-selected",String(n===b)));document.querySelectorAll(".tab").forEach(t=>t.hidden=t.id!==b.dataset.tab);});
guard(async()=>{try{const r=await api("/api/console/session");csrf=r.csrf;await connected();}catch{}});
setInterval(async()=>{if(!csrf||document.hidden||polling)return;polling=true;try{const tasks=await api("/status");$("connection").textContent=`${tasks.phones?.connected||0} phone(s) connected`;}catch(e){say(e.message);}finally{polling=false;}},15000);
