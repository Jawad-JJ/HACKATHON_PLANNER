// PlanForge dashboard. Shows ONLY what the backend saved: no sample data, no invented numbers.
// Live: served by `python serve.py` (same pipeline as main.py). Hosted (Vercel): connect to a
// laptop backend URL, or open an exported outputs/session.json file (read-only viewer).
"use strict";
let S = null, API = "", TAB = "overview";
const $ = (q) => document.querySelector(q);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const rs = (v) => v === null || v === undefined ? "-" : "Rs " + Number(v).toLocaleString("en-US");
const src = (s) => s ? `<span class="src" title="source fact">${esc(s)}</span>` : "";
const pill = (t, cls) => `<span class="pill ${esc(cls || t)}">${esc(t)}</span>`;
const store = { get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
                set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } } };

async function boot() {
  for (const base of ["", store.get("pf_backend") || null].filter((x) => x !== null)) {
    try {
      const r = await fetch(base + "/api/state", { cache: "no-store" });
      if (r.ok) { API = base; S = await r.json(); break; }
    } catch { /* try next */ }
  }
  if (!S) {
    try {
      const r = await fetch("/api/run", { cache: "no-store" });
      const h = r.ok ? await r.json() : null;
      if (h && "configured" in h) {
        let sess = null;
        try { sess = JSON.parse(store.get("pf_session") || "null"); } catch { sess = null; }
        S = { mode: "cloud", model: h.model, configured: h.configured, problem: h.problem, session: sess };
        if (!sess) TAB = "update";
      }
    } catch { /* no cloud function: viewer mode */ }
  }
  if (!S) S = { mode: "viewer", session: null, totals: null };
  render();
}

function setStatus() {
  const sess = S.session, plan = sess && sess.plan;
  const runs = (sess && sess.runs) || [];
  const last = runs[runs.length - 1];
  $("#status").innerHTML = S.mode === "cloud" && !sess ? `cloud backend · model ${esc(S.model || "-")} · upload a message pack to start`
    : S.mode === "viewer" && !sess ? "viewer mode - connect a backend or open a session file"
    : `${S.mode === "live" ? "live backend" + (API ? " " + esc(API) : "") : S.mode === "cloud" ? "cloud backend" : "viewer (read-only)"} · model ${esc(S.model || (sess && sess.calls && sess.calls[0] && sess.calls[0].model) || "-")}`
      + (last ? ` · run ${last.run_id} ${esc(last.mode)} ${last.seconds ?? "?"} s` : "")
      + (plan ? ` · ${plan.valid ? "plan VALID" : "plan NOT valid"}` : "");
}

function render() {
  setStatus();
  if ((!S.session || !S.session.plan) && S.mode === "cloud" && !["update", "exports"].includes(TAB)) TAB = "update";
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === TAB));
  const sess = S.session;
  const needData = !["update", "exports"].includes(TAB);
  if ((!sess || !sess.plan) && S.mode === "cloud" && needData) TAB = "update";
  if (!sess || !sess.plan) {
    $("#view").innerHTML = needData && S.mode !== "cloud" ? connectCard("No plan yet. Run a pack with python main.py <file>, or connect/open one below.") : VIEWS[TAB](sess);
    wire();
    return wireConnect();
  }
  $("#view").innerHTML = VIEWS[TAB](sess);
  wire(); wireConnect();
}

function connectCard(msg) {
  return `<div class="card"><h3>Data source</h3><p class="mute">${esc(msg)}</p>
  <div class="row"><input type="url" id="burl" placeholder="http://127.0.0.1:8000" value="${esc(store.get("pf_backend") || "")}">
  <button class="btn" id="bconnect">Connect backend</button></div>
  <p class="mute">or open an exported <code>outputs/session.json</code>: <input type="file" id="bfile" accept=".json"></p></div>`;
}
function wireConnect() {
  const b = $("#bconnect"); if (b) b.onclick = async () => { store.set("pf_backend", $("#burl").value.replace(/\/$/, "")); S = null; await boot(); };
  const f = $("#bfile"); if (f) f.onchange = async () => {
    try { const sess = JSON.parse(await f.files[0].text()); S = { mode: "viewer", session: sess }; render(); }
    catch (e) { alert("Not a session.json file: " + e.message); }
  };
}

const VIEWS = {
  overview(s) {
    const p = s.plan, b = p.budget, j = p.judging, last = s.runs[s.runs.length - 1];
    const tot = (S.totals) || sumTokens(s.calls);
    const rej = s.messages.filter((m) => ["rejected", "partly rejected"].includes(m.status)).length;
    return `<div class="banner ${p.valid ? "ok" : "bad"}">${p.valid ? "Plan is valid - all six checks pass" : "Plan is NOT valid - see checks below"} (version ${p.version})</div>
    <div class="grid">
      ${card("People on site", p.people.on_site, `${p.people.students} students + ${p.people.staff ?? 0} staff + ${p.people.judges ?? "-"} judges`)}
      ${card("Venue", p.venue.chosen ? esc(p.venue.chosen.name) : "-", p.venue.chosen ? `seats ${p.venue.chosen.capacity} · ${rs(p.venue.chosen.cost)}` : "")}
      ${card("Budget", rs(b.total), `cap ${rs(b.cap)} · ${rs(b.remaining)} left`)}
      ${card("Judging", `${j.judges_used ?? "-"} judges`, `${j.teams ?? "-"} teams · ${j.rounds ?? "-"} rounds · ${j.judging_minutes ?? "-"} min`)}
      ${card("Schedule", `${p.schedule.total_minutes ?? "-"} min`, p.schedule.start ? `starts ${esc(p.schedule.start)}` : "relative times")}
      ${card("Tokens (session)", (tot.total || 0).toLocaleString(), `${tot.calls} model call(s) · as reported`)}
      ${card("Rejected messages", rej, `${s.messages.length} messages read`)}
      ${card("Last run", last ? esc(last.mode) : "-", last ? `${last.calls.length} call(s) · predicted ${esc(last.prediction.tags.join(", "))} · ${last.prediction_matched ? "matched" : "check"}` : "")}
    </div>
    <div class="card"><h3>Six checks</h3><table>${p.checks.map((c) => `<tr><td>${pill(c.pass ? "PASS" : "FAIL")}</td><td><b>${esc(c.check)}</b></td><td>${esc(c.detail)}</td></tr>`).join("")}</table></div>
    ${p.risks && p.risks.length ? `<div class="card"><h3>Risks</h3>${p.risks.map((r) => `<div>${esc(r.text)} ${src(r.src)}</div>`).join("")}</div>` : ""}`;
  },

  plan(s) {
    const p = s.plan, v = p.venue, f = p.food, j = p.judging, sc = p.schedule, b = p.budget;
    const tl = (sc.slots || []).map((x) => `<div class="t-${esc(x.type)}" style="flex:${x.end - x.start}" title="${esc(x.name)} ${x.start}-${x.end} min">${esc(x.type === "build" ? "Build" : x.type === "judging" ? "Judging" : x.name)}</div>`).join("");
    const byJ = {}; (j.assignment || []).forEach((a) => (byJ[a.judge] = byJ[a.judge] || []).push(`T${a.team} (r${a.round})`));
    return `<div class="card"><h3>Venue</h3>${v.chosen ? `<p><b>${esc(v.chosen.name)}</b> seats ${v.chosen.capacity} for ${v.people_on_site} people · ${rs(v.chosen.cost)} ${src(v.chosen.src)}</p>` : "<p>-</p>"}
      ${v.required_features.length ? `<p class="mute">Must have: ${v.required_features.map(esc).join(", ")}</p>` : ""}
      <table><tr><th>Other option</th><th>Why not</th></tr>${v.alternatives.map((a) => `<tr><td>${esc(a.name)}</td><td>${esc(a.why_not || "fits, but costs more")}</td></tr>`).join("")}</table></div>
    <div class="card"><h3>Schedule</h3><div class="timeline">${tl}</div>
      <table><tr><th>Time</th><th>Activity</th><th>Source</th></tr>${(sc.slots || []).map((x) => `<tr><td>${esc(x.clock || `+${x.start}-${x.end} min`)}</td><td>${esc(x.name)}</td><td>${src(x.src)}</td></tr>`).join("")}</table></div>
    <div class="card"><h3>Food</h3>${f.chosen ? `<p><b>${f.quantity} x ${esc(f.chosen.name)}</b> @ ${rs(f.chosen.price_per_head)} = <b>${rs(f.cost)}</b> ${src(f.chosen.src)}</p><p class="mute">${esc(f.rule)}</p>` : "<p>-</p>"}
      <table><tr><th>Other menu</th><th>Detail</th></tr>${f.alternatives.map((a) => `<tr><td>${esc(a.name)}</td><td>${esc(a.why_not || `${rs(a.price_per_head)}/head, would cost ${rs(a.would_cost)}`)}</td></tr>`).join("")}</table></div>
    <div class="card"><h3>Judging</h3><p>${j.teams} teams · ${j.judges_used} of ${j.judges_available} judges · ${j.rounds} rounds x ${j.minutes_per_team} min · max ${j.max_load} teams per judge (limit ${j.max_teams_per_judge})</p>
      <div class="judges">${Object.keys(byJ).map((k) => `<div><b>Judge ${k}</b><br>${byJ[k].join(", ")}</div>`).join("")}</div></div>
    <div class="card"><h3>Budget</h3><table><tr><th>Item</th><th class="num">Amount</th><th class="hide-sm">Source</th></tr>
      ${b.lines.map((l) => `<tr><td>${esc(l.item)}</td><td class="num">${rs(l.amount)}</td><td class="hide-sm">${src(l.src)}</td></tr>`).join("")}
      <tr><td><b>Total</b></td><td class="num"><b>${rs(b.total)}</b></td><td></td></tr>
      <tr><td>Cap</td><td class="num">${rs(b.cap)}</td><td class="hide-sm">${src(b.cap_src)}</td></tr>
      <tr><td>Remaining</td><td class="num">${rs(b.remaining)}</td><td></td></tr></table>
      ${b.not_included.map((o) => `<p class="mute">Not included: ${esc(o.item)} ${rs(o.amount)} - not approved; ${esc(o.note)} ${src(o.src)}</p>`).join("")}</div>
    ${p.requirements.length ? `<div class="card"><h3>Rules from messages</h3><table>${p.requirements.map((r) => `<tr><td>${pill(r.state)}</td><td>${esc(r.rule)}</td><td>${r.actual ?? ""}</td><td>${src(r.src)}</td></tr>`).join("")}</table></div>` : ""}`;
  },

  messages(s) {
    return s.messages.map((m) => {
      const facts = s.facts.filter((f) => f.msg === m.id);
      return `<div class="card"><div class="row"><b>${esc(m.id)}</b> ${pill(m.status.split(" ")[0] === "partly" ? "partly" : m.status, m.status.split(" ")[0])}
        <span>${esc(m.sender)} · ${esc(m.role)} · ${esc(m.date_raw || "no date")}</span></div>
        <div class="quote">${esc(m.text || "(text not mapped)")}</div>
        ${facts.length ? `<table>${facts.map((f) => `<tr><td>${src(f.id)}</td><td>${esc(f.kind)}</td><td>${esc(factValue(f))}</td><td>${pill(f.state === "active" ? "accepted" : f.state, f.state === "active" ? "accepted" : f.state === "superseded" ? "outdated" : f.state)}</td><td class="mute">${esc(f.reason || "")}</td></tr>`).join("")}</table>` : ""}</div>`;
    }).join("") || "<p>No messages.</p>";
  },

  rejected(s) {
    const bad = s.messages.filter((m) => m.status !== "accepted");
    return `<div class="card"><h3>Rejected, outdated and ignored messages</h3><p class="mute">Each one shows the exact original text and the reason the plan did not use it.</p></div>` +
      (bad.map((m) => `<div class="card"><div class="row">${pill(m.status, m.status.split(" ")[0])} <b>${esc(m.id)}</b> ${esc(m.sender)} · ${esc(m.date_raw || "no date")}</div>
        <div class="quote">${esc(m.text)}</div><ul>${(m.reasons.length ? m.reasons : ["no planning facts in this message"]).map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>`).join("") || "<p>Nothing rejected.</p>");
  },

  trace(s) {
    const tot = sumTokens(s.calls);
    return s.runs.map((r) => `<div class="card"><h3>Run ${r.run_id} · ${esc(r.mode)} · ${esc(r.input.split(/[\\/]/).pop())}</h3>
      <p>Prediction (saved ${esc(r.predicted_at)}, before any call): ${r.prediction.tags.map((t) => pill(t, "tag")).join(" ")} · actual: ${(r.actual_tags || []).map((t) => pill(t, "tag")).join(" ")} · ${pill(r.prediction_matched ? "matched" : "mismatch", r.prediction_matched ? "ok" : "warn")}</p>
      ${s.calls.filter((c) => c.run_id === r.run_id).map(callBox).join("")}
      ${r.decisions.length ? `<table><tr><th>Verdict</th><th>Msg</th><th>Fact</th><th>Reason</th></tr>${r.decisions.map((d) => `<tr><td>${pill(d.verdict)}</td><td>${esc(d.message)}</td><td>${esc(d.kind || "")}</td><td>${esc(d.reason)}</td></tr>`).join("")}</table>` : ""}
      ${r.error ? `<p>${pill("error")} ${esc(r.error)} - previous plan kept</p>` : ""}</div>`).join("") +
      `<div class="card"><b>Total tokens (session):</b> input ${tot.input.toLocaleString()} + output ${tot.output.toLocaleString()} = <b>${tot.total.toLocaleString()}</b> over ${tot.calls} call(s) <span class="mute">- sums of provider-reported counts</span></div>`;
  },

  update(s) {
    if (S.mode === "cloud") {
      return `<div class="card"><h3>Upload messages</h3>
      <p class="mute">Choose the message pack <b>.txt</b> first, then each new message as it arrives (or paste it). Every file goes through the same pipeline as <code>python main.py &lt;file&gt;</code>: one model call to read it, everything else checked in code. Your plan is kept in this browser.</p>
      ${S.configured ? "" : `<p>${pill("error")} Server model not configured: ${esc(S.problem || "")}</p>`}
      <div class="row"><input type="file" id="files" accept=".txt,text/plain" multiple></div>
      <p class="mute" style="margin:10px 0 4px">or paste one message:</p>
      <textarea id="msg" placeholder="Paste the new message exactly as received"></textarea>
      <div class="row" style="margin-top:10px"><button class="btn" id="send">Run</button>
      <button class="btn sec" id="reset">Start a new plan</button>
      <span id="sendinfo" class="mute">Prediction for every run: only the reading area makes a model call (1 call).</span></div></div>
      <div id="result"></div>`;
    }
    const live = S.mode === "live";
    return `<div class="card"><h3>Process a new message</h3>
      <p class="mute">Runs the same pipeline as <code>python main.py &lt;file&gt;</code>: the text is saved as a file, read by the model once, then checked in code.</p>
      <textarea id="msg" placeholder="Paste the new message exactly as received" ${live ? "" : "disabled"}></textarea>
      <div class="row" style="margin-top:10px"><button class="btn" id="send" ${live ? "" : "disabled"}>Run update</button>
      <span id="sendinfo" class="mute">${live ? "Prediction for this run: only the reading area makes a model call." : "Connect a live backend to process messages."}</span></div></div>
      ${live ? "" : connectCard("This page is not connected to a backend.")}
      <div id="result"></div>`;
  },

  exports(s) {
    const files = ["submission.txt", "latest_plan.txt", "full_trace.txt", "latest_plan.json", "full_trace.json", "rejections.json", "updates.json", "session.json"];
    if (S.mode === "cloud") {
      return `<div class="card"><h3>Exports</h3><p class="mute">Files for the submission form, built from the plan in this browser.</p>
        <div class="row"><button class="btn" id="dlsub" ${s ? "" : "disabled"}>Download submission.txt</button>
        <button class="btn sec" id="dl" ${s ? "" : "disabled"}>Download session.json</button></div></div>`;
    }
    return `<div class="card"><h3>Exports</h3>${S.mode === "live" ? `<ul>${files.map((f) => `<li><a href="${esc(API)}/api/export/${f}">${f}</a></li>`).join("")}</ul>` : "<p class='mute'>File downloads need the live backend.</p>"}
      ${s ? `<button class="btn sec" id="dl">Download the session shown here (JSON)</button>` : ""}</div>`;
  },
};

function card(t, big, sub) { return `<div class="card"><h3>${esc(t)}</h3><div class="big">${big ?? "-"}</div><div class="mute">${sub || ""}</div></div>`; }
function factValue(f) {
  const skip = new Set(["kind", "id", "msg", "order", "date_iso", "date_raw", "run_id", "key", "state", "reason", "quote", "status", "info_only"]);
  return Object.entries(f).filter(([k, v]) => !skip.has(k) && v !== null && v !== "" && !(Array.isArray(v) && !v.length)).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`).join(" · ") + (f.status && f.status !== "confirmed" ? ` (${f.status})` : "");
}
function sumTokens(calls) {
  const t = { input: 0, output: 0, total: 0, calls: 0 };
  (calls || []).forEach((c) => { t.calls++; t.input += c.input_tokens || 0; t.output += c.output_tokens || 0; t.total += c.total_tokens ?? ((c.input_tokens || 0) + (c.output_tokens || 0)); });
  return t;
}
function callBox(c) {
  const tk = (v) => v === null || v === undefined ? "unreported" : v.toLocaleString();
  return `<details><summary>#${c.number} ${pill(c.tag, "tag")} ${esc(c.model)} · ${pill(c.status)} · tokens in ${tk(c.input_tokens)} / out ${tk(c.output_tokens)} / total ${tk(c.total_tokens)} · ${c.seconds}s</summary>
    <div class="mute" style="padding:0 12px">Input (exact):</div><pre>${esc(c.request.map((m) => `[${m.role}]\n${m.content}`).join("\n\n"))}</pre>
    <div class="mute" style="padding:0 12px">Output (exact):</div><pre>${esc(c.status === "ok" ? c.response : "ERROR: " + c.error)}</pre></details>`;
}

function wire() {
  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => { TAB = b.dataset.tab; render(); $("#view").focus(); }));
  const send = $("#send");
  if (send && S.mode === "cloud") {
    send.onclick = async () => {
      const files = Array.from(($("#files") && $("#files").files) || []);
      const items = await Promise.all(files.map(async (f) => ({ name: f.name, text: await f.text() })));
      if ($("#msg").value.trim()) items.push({ name: "pasted.txt", text: $("#msg").value });
      if (!items.length) { $("#sendinfo").textContent = "Choose a .txt file or paste a message first."; return; }
      send.disabled = true;
      const out = [];
      for (const it of items) {
        $("#sendinfo").textContent = `Running ${it.name} (model read + checks)...`;
        const before = S.session && S.session.plan;
        try {
          const r = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: it.text, filename: it.name, session: S.session }) });
          const data = await r.json();
          if (!r.ok) throw new Error(data.error || r.statusText);
          S.session = data.session; S.submission = data.submission;
          store.set("pf_session", JSON.stringify(data.session)); store.set("pf_submission", data.submission);
          const after = data.session.plan, run = data.run;
          out.push(`<div class="card"><h3>${esc(it.name)}: run ${run.run_id} (${esc(run.mode)})</h3>
            <p>${data.ok ? "" : pill("error") + " " + esc(data.error)} Plan ${after && after.valid ? pill("VALID", "ok") : pill("NOT valid", "error")} · ${run.calls.length} call(s) · predicted ${esc(run.prediction.tags.join(", "))} · actual ${esc((run.actual_tags || []).join(", "))} · ${run.seconds} s</p>
            <table><tr><th>Verdict</th><th>Reason</th></tr>${run.decisions.filter((d) => d.verdict !== "accepted").map((d) => `<tr><td>${pill(d.verdict)}</td><td>${esc(d.reason)}</td></tr>`).join("") || "<tr><td colspan=2>all facts accepted</td></tr>"}</table>
            ${before && after ? `<p>Budget ${rs(before.budget.total)} → <b>${rs(after.budget.total)}</b> · people ${before.people.on_site} → <b>${after.people.on_site}</b></p>` : ""}</div>`);
        } catch (e) { out.push(`<div class="card">${pill("error")} ${esc(it.name)}: ${esc(e.message)}</div>`); }
      }
      TAB = "update"; render();
      $("#result").innerHTML = out.join("");
      $("#sendinfo").textContent = "Done. See the Overview, Plan, Rejected and Trace tabs.";
    };
  } else if (send) send.onclick = async () => {
    const text = $("#msg").value; if (!text.trim()) return;
    send.disabled = true; $("#sendinfo").textContent = "Running (model read + checks)...";
    const before = S.session && S.session.plan;
    try {
      const r = await fetch(API + "/api/message", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || r.statusText);
      S = data; const after = S.session.plan, run = data.run;
      TAB = "update"; render();
      $("#result").innerHTML = `<div class="card"><h3>Result: run ${run.run_id} (${esc(run.mode)})</h3>
        <p>${data.ok ? "" : pill("error") + " " + esc(data.error)} Plan ${after.valid ? pill("VALID", "ok") : pill("NOT valid", "error")} · calls ${run.calls.length} · predicted ${esc(run.prediction.tags.join(", "))} · actual ${esc((run.actual_tags || []).join(", "))}</p>
        <table><tr><th>Verdict</th><th>Reason</th></tr>${run.decisions.map((d) => `<tr><td>${pill(d.verdict)}</td><td>${esc(d.reason)}</td></tr>`).join("")}</table>
        ${before ? `<p>Budget ${rs(before.budget.total)} → <b>${rs(after.budget.total)}</b> · people ${before.people.on_site} → <b>${after.people.on_site}</b> · venue ${esc(before.venue.chosen && before.venue.chosen.name)} → <b>${esc(after.venue.chosen && after.venue.chosen.name)}</b></p>` : ""}</div>`;
    } catch (e) { $("#sendinfo").textContent = "Failed: " + e.message; send.disabled = false; }
  };
  const rst = $("#reset");
  if (rst) rst.onclick = () => { if (!confirm("Clear the plan in this browser and start a new one?")) return;
    S.session = null; store.set("pf_session", "null"); store.set("pf_submission", ""); render(); };
  const dls = $("#dlsub");
  if (dls) dls.onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([S.submission || store.get("pf_submission") || ""], { type: "text/plain" })); a.download = "submission.txt"; a.click(); };
  const dl = $("#dl");
  if (dl) dl.onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(S.session, null, 1)], { type: "application/json" })); a.download = "session.json"; a.click(); };
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
boot();
