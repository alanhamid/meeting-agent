"use strict";
const $ = (s) => document.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const c of kids) e.append(c);
  return e;
};
let MID = null;
const tokenBox = $("#token");
try { tokenBox.value = sessionStorage.getItem("ma_token") || ""; } catch (_) {}
tokenBox.addEventListener("change", () => { try { sessionStorage.setItem("ma_token", tokenBox.value); } catch (_) {} });

async function api(path, method = "GET", body) {
  const h = { "Content-Type": "application/json" };
  if (tokenBox.value) h.Authorization = "Bearer " + tokenBox.value;
  const r = await fetch("/api" + path, { method, headers: h, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
  return data;
}

/* ---------- setup form ---------- */
function participantRow() {
  const sel = (name, opts, extra = "") => {
    const s = el("select", { name, ...(extra ? { required: "" } : {}) });
    for (const [v, t] of opts) s.append(el("option", { value: v }, t));
    return s;
  };
  const status = sel("nda_status", [["", "NDA signed? (choose)"], ["signed", "NDA signed"], ["not_signed", "NDA not signed"], ["pending", "NDA pending"]], "r");
  status.firstChild.disabled = true; status.value = "";
  const scope = sel("nda_scope", [["all", "Scope: all"], ["technical", "Scope: technical"], ["commercial", "Scope: commercial"]]);
  const row = el("div", { class: "prow" },
    el("input", { name: "name", placeholder: "Name", required: "" }),
    el("input", { name: "organisation", placeholder: "Organisation", required: "" }),
    el("input", { name: "role", placeholder: "Their role", required: "" }),
    status, scope,
    el("input", { name: "nda_date", type: "date", title: "NDA date" }),
    el("input", { name: "nda_reference", placeholder: "NDA doc reference" }),
    el("input", { name: "nda_expires", type: "date", title: "NDA expires (optional)" }),
    el("button", { type: "button", onclick: () => row.remove() }, "Remove"));
  return row;
}
$("#addp").addEventListener("click", () => $("#plist").append(participantRow()));
$("#plist").append(participantRow());

$("#mform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("#merr").textContent = "";
  const f = new FormData(ev.target);
  const participants = [...document.querySelectorAll(".prow")].map((r) => {
    const g = (n) => r.querySelector(`[name=${n}]`).value.trim();
    const p = { name: g("name"), organisation: g("organisation"), role: g("role"), nda_status: g("nda_status"), nda_scope: g("nda_scope") };
    for (const k of ["nda_date", "nda_reference", "nda_expires"]) if (g(k)) p[k] = g(k);
    return p;
  });
  const body = {
    title: f.get("title"), meeting_date: f.get("meeting_date"), platform: f.get("platform"),
    stakeholder: f.get("stakeholder"), goal: f.get("goal"),
    avoid_topics: String(f.get("avoid") || "").split(",").map((s) => s.trim()).filter(Boolean),
    participants,
  };
  try {
    const m = await api("/meetings", "POST", body);
    await api(`/meetings/${m.id}/start`, "POST");
    openMeeting(m.id);
  } catch (e) { $("#merr").textContent = "Cannot start: " + e.message; }
});

async function loadPast() {
  try {
    const ms = await api("/meetings");
    const box = $("#past"); box.replaceChildren();
    for (const m of ms) box.append(el("div", { class: "person" }, `${m.meeting_date} - ${m.title} (${m.status})`,
      m.status === "active" ? el("button", { onclick: () => openMeeting(m.id) }, "Resume") : ""));
  } catch (_) {}
}
loadPast();

/* ---------- live view ---------- */
async function openMeeting(id) {
  MID = id; $("#setup").hidden = true; $("#live").hidden = false; await refresh();
}
async function refresh() {
  const m = await api(`/meetings/${MID}`);
  $("#mtitle").textContent = `${m.title} - ${m.stakeholder.replaceAll("_", " ")}`;
  const b = $("#banner"); b.replaceChildren();
  for (const t of ["technical", "commercial"]) {
    const c = m.clearance[t];
    b.append(el("span", { class: "pill " + (c.cleared ? "ok" : "no") },
      c.cleared ? `${t}: NDA material cleared` : `${t}: PUBLIC ONLY (blocked by ${c.blocked_by.join(", ") || "no participants"})`));
  }
  const ppl = $("#people"); ppl.replaceChildren();
  for (const p of m.participants) {
    const sel = el("select", { onchange: (e) => setNda(p, e.target.value) },
      ...["signed", "not_signed", "pending"].map((v) => { const o = el("option", { value: v }, v.replace("_", " ")); if (v === p.nda_status) o.selected = true; return o; }));
    ppl.append(el("div", { class: "person" },
      el("span", {}, `${p.name} (${p.organisation}${p.joined_late ? ", joined late" : ""})`), sel));
  }
  const fl = await api(`/meetings/${MID}/followups`);
  const ul = $("#followups"); ul.replaceChildren();
  for (const f of fl) {
    const li = el("li", {}, `[${f.reason}] ${f.question}${f.who.length ? " - for " + f.who.join(", ") : ""} `);
    if (f.status === "open") li.append(el("button", { onclick: async () => { await api(`/meetings/${MID}/followups/${f.id}/done`, "POST"); refresh(); } }, "done"));
    else li.append(el("span", { class: "muted" }, "(done)"));
    ul.append(li);
  }
}
async function setNda(p, status) {
  let body = { nda_status: status };
  if (status === "signed") {
    const ref = prompt(`NDA document reference for ${p.name}:`); if (!ref) return refresh();
    const d = prompt("NDA signed date (YYYY-MM-DD):", new Date().toISOString().slice(0, 10)); if (!d) return refresh();
    const scope = prompt("Scope: all, technical or commercial", "all") || "all";
    body = { nda_status: status, nda_reference: ref, nda_date: d, nda_scope: scope };
  }
  try { await api(`/meetings/${MID}/participants/${p.id}/nda`, "PUT", body); } catch (e) { alert(e.message); }
  refresh();
}
$("#joinbtn").addEventListener("click", async () => {
  const name = $("#late").value.trim(); if (!name) return;
  await api(`/meetings/${MID}/participants`, "POST", { name }); $("#late").value = ""; refresh();
});
$("#endbtn").addEventListener("click", async () => { await api(`/meetings/${MID}/end`, "POST"); location.reload(); });

async function ask() {
  const q = $("#q").value.trim(); if (!q) return;
  const out = $("#answer"); out.replaceChildren(el("p", { class: "muted" }, "Thinking..."));
  try { render(await api(`/meetings/${MID}/ask`, "POST", { question: q })); }
  catch (e) { out.replaceChildren(el("p", { class: "err" }, e.message)); }
  refresh();
}
function render(r) {
  const out = $("#answer"); out.replaceChildren();
  for (const w of r.warnings) out.append(el("div", { class: "card wrn" }, "Careful: " + w.message));
  const main = el("div", { class: "card" }, el("div", { class: "say" }, r.say));
  main.append(el("div", { class: "muted" }, "Outcome: " + r.outcome.replace("_", " ")));
  for (const s of r.sources) main.append(el("span", { class: "chip", title: s.chunk_id }, `${s.title} - ${s.level}, ${s.confidence}`));
  out.append(main);
  for (const n of r.private_notes) out.append(el("div", { class: "card priv" }, el("strong", {}, "For you only (never say): "), `${n.title} - ${n.excerpt}`));
  if (r.withheld.length) {
    const box = el("div", { class: "card priv" }, el("strong", {}, "Withheld under NDA rules (for you only). "));
    for (const s of r.withheld) box.append(el("button", { onclick: () => releaseOnce(s) }, "Release once: " + s.title));
    out.append(box);
  }
}
async function releaseOnce(s) {
  const reason = prompt(`Why release "${s.title}" to this meeting? (logged)`); if (!reason) return;
  try { await api(`/meetings/${MID}/release`, "POST", { chunk_id: s.chunk_id, reason }); $("#answer").prepend(el("p", { class: "muted" }, "Released for the next answer. Ask again.")); }
  catch (e) { alert(e.message); }
}
$("#askbtn").addEventListener("click", ask);
$("#q").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });

/* ---------- push-to-talk (browser speech recognition; cloud STT is a later swap) ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const mic = $("#mic");
if (!SR) { mic.disabled = true; $("#micnote").textContent = "Voice needs Chrome or Edge. Typing works everywhere."; }
else {
  $("#micnote").textContent = "Mute the call before you hold the button, so the room does not hear your question.";
  let rec = null;
  const stop = () => { if (rec) { rec.stop(); } };
  mic.addEventListener("pointerdown", () => {
    rec = new SR(); rec.lang = "en-US"; rec.interimResults = false;
    rec.onresult = (e) => { $("#q").value = e.results[0][0].transcript; ask(); };
    rec.onerror = (e) => { $("#micnote").textContent = "Mic error: " + e.error; };
    rec.start(); mic.textContent = "Listening...";
  });
  for (const ev of ["pointerup", "pointerleave"]) mic.addEventListener(ev, () => { stop(); mic.textContent = "Hold to talk"; });
}
