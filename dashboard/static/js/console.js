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
  await refreshSocial();
}
function phoneStatus(){const p=phones.find(p=>p.name===$("phone").value);$("phone-status").textContent=p?(p.connected?"Connected over ADB":"Offline. Reconnect and authorize USB debugging."):"No devices enrolled. Click Discover.";}
function renderReviews(items) {
  $("pending").textContent=items.filter(i=>i.status==="pending").length;
  empty("review-list","Your reply queue is clear. The agent adds Humanizer-reviewed drafts here with their source conversation.");
  if(!items.length)return;$("review-list").replaceChildren();
  for(const item of items){const card=el("article",undefined,"card");card.append(el("p",`${item.platform} · ${item.account} · ${item.status}`,"review-meta"),el("h2",`${item.author} said`),el("blockquote",item.original),el("h2","Your reply"),el("blockquote",item.reply,"reply"));const link=el("a","Open source conversation");link.href=item.source_url;link.target="_blank";link.rel="noopener noreferrer";card.append(link,el("p",`Humanizer ${item.humanizer_version}${item.edited_by_user?" · edited by you":""}`,"hint"));
    if(["pending","rejected"].includes(item.status)){const actions=el("div",undefined,"review-actions");const editor=el("textarea");editor.value=item.reply;editor.rows=5;editor.hidden=true;editor.setAttribute("aria-label","Rewrite your reply");const save=button("Save rewrite for review",async()=>{await api(`/reviews/${item.id}/edit`,{revision:item.revision,reply:editor.value});say("Rewrite saved. Review it before approving.");await refresh();});save.hidden=true;
      actions.append(button("👍 Approve",async()=>{if(await confirmAction(`Approve reply as ${item.account}?`,`${item.author}: ${item.original}\n\nYour reply:\n${item.reply}`)){await api(`/reviews/${item.id}/approve`,{revision:item.revision});say("Approved and waiting for the agent. This is not yet a delivery confirmation.");await refresh();}}),button("👎 Reject & rewrite",async()=>{if(item.status==="pending"){const updated=await api(`/reviews/${item.id}/reject`,{revision:item.revision});Object.assign(item,updated);}editor.hidden=false;save.hidden=false;editor.focus();}),button("Edit",async()=>{editor.hidden=false;save.hidden=false;editor.focus();}));card.append(actions,editor,save);}
    if(["pending","rejected","approved"].includes(item.status)){
      const when=el("input");when.type="datetime-local";when.setAttribute("aria-label","Publish at");
      card.append(el("p",item.publish_at?`Publish after approval at: ${new Date(item.publish_at*1000).toLocaleString()}`:"Set a future time before approving, or approval makes this eligible immediately.","hint"),when,
        button("Set publish time",async()=>{if(!when.value)throw Error("Choose a date and time.");await api(`/reviews/${item.id}/schedule`,{revision:item.revision,at:new Date(when.value).toISOString()});await refresh();}));
      const edit=el("textarea");edit.value=item.reply;edit.setAttribute("aria-label","Revise approved text");
      card.append(edit,button("Change text & require approval again",async()=>{await api(`/reviews/${item.id}/edit`,{revision:item.revision,reply:edit.value});await refresh();}));
    }
    if(["pending","rejected","approved"].includes(item.status))card.append(button("Cancel draft",async()=>{if(await confirmAction("Cancel this draft?",item.reply)){await api(`/reviews/${item.id}/cancel`,{revision:item.revision});await refresh();}}));
    if(item.status==="executing"){const evidence=el("textarea");evidence.placeholder="After inspecting the phone, describe what happened.";evidence.setAttribute("aria-label","Recovery observations");card.append(evidence,button("Stop delivery and mark uncertain",async()=>{if(!evidence.value.trim())throw Error("Record what you observed first.");if(await confirmAction("Revoke this delivery lease?","This stops further actions and releases the phone. It will not retry the post.")){await api(`/reviews/${item.id}/recover`,{revision:item.revision,evidence:evidence.value});await refresh();}}));}
    if(item.evidence)card.append(el("p",item.evidence,"hint"));$("review-list").append(card);
  }
}
let accounts=[], editingSchedule=null;
function chosenAccount(){const id=$("social-account").value;if(!id)throw Error("Save or select an account first.");return id;}
async function refreshSocial(){
  const [a,s,j]=await Promise.all([api("/social/accounts"),api("/social/schedules"),api("/social/jobs")]);
  accounts=a.accounts;const selected=$("social-account").value;$("social-account").replaceChildren(new Option("New account",""));
  for(const account of accounts)$("social-account").append(new Option(`${account.name} · ${account.platform}`,account.id));
  if(accounts.some(a=>a.id===selected))$("social-account").value=selected;
  const assigned=new Set(Array.from($("account-phones").selectedOptions,o=>o.value));
  $("account-phones").replaceChildren();for(const phone of phones){const o=new Option(phone.name,phone.name);o.selected=assigned.has(phone.name);$("account-phones").append(o);}
  empty("schedule-list","No schedules yet.");if(s.schedules.length)$("schedule-list").replaceChildren();
  for(const schedule of s.schedules){const card=el("article",undefined,"card");const account=accounts.find(a=>a.id===schedule.account_id);card.append(el("h3",account?.name||schedule.account_id),el("p",schedule.prompt),el("p",`${schedule.enabled?"Active":"Paused / finished"} · ${schedule.next_at?new Date(schedule.next_at*1000).toLocaleString():"No next run"}`),el("pre",JSON.stringify(schedule.spec,null,2)),button("Edit / resume",async()=>{editingSchedule=schedule;$("social-account").value=schedule.account_id;fillAccount();$("social-prompt").value=schedule.prompt;$("draft-kind").value=schedule.kind||"post";for(const [key,id] of [["source_url","draft-url"],["author","draft-author"],["original","draft-original"]])$(id).value=schedule[key]||"";draftFields();$("schedule-kind").value=schedule.spec.kind;for(const key of ["time","timezone","minutes","weekday","day"]){const id={timezone:"schedule-zone"}[key]||`schedule-${key}`;if(schedule.spec[key]!==undefined)$(id).value=schedule.spec[key];}if(schedule.spec.at){const date=new Date(schedule.spec.at);date.setMinutes(date.getMinutes()-date.getTimezoneOffset());$("schedule-at").value=date.toISOString().slice(0,16);}$("schedule-save").textContent="Save schedule changes";$("social-prompt").focus();}),button("Pause",async()=>{await api(`/social/schedules/${schedule.id}/pause`,{revision:schedule.revision});await refreshSocial();}));$("schedule-list").append(card);}
  empty("social-jobs","No draft jobs yet.");if(j.jobs.length)$("social-jobs").replaceChildren();for(const job of j.jobs.slice(0,30))$("social-jobs").append(el("p",`${job.status} · ${job.prompt}${job.error?" · "+job.error:""}`));
}
function fillAccount(){const a=accounts.find(a=>a.id===$("social-account").value);for(const k of ["name","handle","soul"])$("account-"+k).value=a?.[k]||"";$("account-platform").value=a?.platform||"x";$("account-platform").disabled=!!a;$("account-handle").readOnly=!!a;$("indicator-id").value=a?.delivery_indicator?.id||"";$("indicator-text").value=a?.delivery_indicator?.text||"";$("indicator-compose").value=a?.delivery_indicator?.compose_id||"";$("indicator-posted").value=a?.delivery_indicator?.posted_id||"";for(const o of $("account-phones").options)o.selected=!!a?.phones.includes(o.value);empty("memory-list","Load this account's context to view its sources.");}
$("social-account").onchange=()=>{fillAccount();editingSchedule=null;$("schedule-save").textContent="Save";};
$("indicator-form").onsubmit=e=>{e.preventDefault();guard(async()=>{const a=accounts.find(a=>a.id===chosenAccount());const delivery_indicator=$("indicator-id").value?{id:$("indicator-id").value,text:$("indicator-text").value,compose_id:$("indicator-compose").value,posted_id:$("indicator-posted").value}:null;await api("/social/accounts",{...a,delivery_indicator});await refreshSocial();say("Account check saved. Test it on every assigned phone before enabling delivery.");});};
$("account-form").onsubmit=e=>{e.preventDefault();guard(async()=>{const old=accounts.find(a=>a.id===$("social-account").value);const data={name:$("account-name").value,platform:$("account-platform").value,handle:$("account-handle").value,soul:$("account-soul").value,phones:Array.from($("account-phones").selectedOptions,o=>o.value)};if(old)Object.assign(data,{id:old.id,revision:old.revision});const saved=await api("/social/accounts",data);await refreshSocial();$("social-account").value=saved.id;fillAccount();say("Account saved.");});};
async function loadMemory(){const data=await api(`/social/accounts/${chosenAccount()}/memory`);$("memory-list").replaceChildren();for(const m of data.memories){const card=el("article",undefined,"card");card.append(el("p",m.text),el("small",`${m.trusted?"Owner knowledge":"Observation"} · ${m.source}`));$("memory-list").append(card);}say(`${data.memories.length} memory items; ${data.reviews.length} recent drafts or replies${data.truncated?" (context capped)":""}.`);}
$("memory-refresh").onclick=()=>guard(loadMemory);
$("memory-form").onsubmit=e=>{e.preventDefault();guard(async()=>{await api(`/social/accounts/${chosenAccount()}/memory`,{text:$("memory-text").value,source:$("memory-source").value,thread:$("memory-thread").value});$("memory-text").value="";await loadMemory();});};
function draftFields(){const reply=$("draft-kind").value==="reply";$("draft-source").hidden=!reply;for(const id of ["draft-url","draft-author","draft-original"])$(id).required=reply;}
$("draft-kind").onchange=draftFields;
$("schedule-reset").onclick=()=>{editingSchedule=null;$("schedule-save").textContent="Save";};
$("schedule-form").onsubmit=e=>{e.preventDefault();guard(async()=>{const account_id=chosenAccount(),prompt=$("social-prompt").value,kind=$("schedule-kind").value;const target={kind:$("draft-kind").value};if(target.kind==="reply")Object.assign(target,{source_url:$("draft-url").value,author:$("draft-author").value,original:$("draft-original").value});if(kind==="now"){await api("/social/jobs",{account_id,prompt,...target});say("Draft queued for the next worker run.");}else{const spec={kind};if(kind==="once"){if(!$("schedule-at").value)throw Error("Choose a date.");spec.at=new Date($("schedule-at").value).toISOString();}else if(kind==="interval")spec.minutes=Number($("schedule-minutes").value);else Object.assign(spec,{time:$("schedule-time").value,timezone:$("schedule-zone").value,weekday:Number($("schedule-weekday").value),day:Number($("schedule-day").value)});const data={account_id,prompt,spec,...target};if(editingSchedule)Object.assign(data,{id:editingSchedule.id,revision:editingSchedule.revision});await api("/social/schedules",data);editingSchedule=null;$("schedule-save").textContent="Save";say("Schedule saved. Each new draft will need approval.");}await refreshSocial();});};
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
