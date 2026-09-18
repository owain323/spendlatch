/* SpendPilot web experience — simulated Alexa+ interaction model.
 * Voice-first (progressive enhancement), evidence-chain cards, decision ledger,
 * cross-session memory. Keyboard is the primary path. */

const chatEl = document.getElementById("chat");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const micBtn = document.getElementById("mic");
const newSessionBtn = document.getElementById("new-session");
const ledgerToggle = document.getElementById("ledger-toggle");
const ledgerPanel = document.getElementById("ledger-panel");
const ledgerBody = document.getElementById("ledger-body");
const statsEl = document.getElementById("stats");

const SESSION_KEY = "spendpilot.session";
let sessionId = localStorage.getItem(SESSION_KEY) || null;

function money(v) {
  return "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function evidenceHTML(items) {
  if (!items || !items.length) return "";
  return `<div class="evidence">${items.map(e =>
    `<div><b>${esc(e.signal)}</b> — ${esc(e.value)}<br><span class="src">${esc(e.source)}</span></div>`
  ).join("")}</div>`;
}

function cardHTML(card) {
  switch (card.type) {
    case "anomaly":
      return `<div class="card">
        <span class="badge ${card.severity}">${card.severity}</span>
        <span class="badge ${card.confidence}">confidence: ${card.confidence}</span>
        <h3>${esc(card.title)}</h3>
        ${evidenceHTML(card.evidence)}
        ${card.action_ids && card.action_ids.length
          ? `<p class="meta" style="margin-top:8px">Proof available — ask me to "prove the saving".</p>` : ""}
      </div>`;
    case "kept":
      return `<div class="card">
        <span class="badge keep">judgment · keep</span>
        <span class="badge ${card.confidence}">confidence: ${card.confidence}</span>
        <h3>${esc(card.title)}</h3>
        ${evidenceHTML(card.evidence)}
        <p class="note">${esc(card.judgment)}</p>
      </div>`;
    case "saving":
      return `<div class="card">
        <span class="badge conf">confidence · ${card.confidence}</span>
        <h3>${esc(card.title)}</h3>
        <div class="saving-flow">
          <span class="before">${money(card.monthly_before)}/mo</span>
          <span class="arrow">→</span>
          <span class="after">${money(card.monthly_after)}/mo</span>
        </div>
        <p class="meta">Expected saving: <strong>${card.expected_saving_pct}%</strong>
          (${money(card.annual_saving)}/yr)</p>
        <ul>${card.proof_steps.map(s => `<li>${esc(s)}</li>`).join("")}</ul>
        <p class="meta">Risk: ${esc(card.risk)}</p>
        <p class="note">${esc(card.estimate_basis)}</p>
        ${card.proposal_id
          ? `<p class="note action-hint">On the table as <b>${esc(card.proposal_id)}</b> —
             reply <b>"approve"</b> and I will issue a signed, single-use mandate.</p>` : ""}
      </div>`;
    case "mandate":
      return `<div class="card mandate">
        <span class="badge ok">signed mandate</span>
        <h3>${esc(card.mandate_id)} · ${esc(card.scope.operation)}</h3>
        <ul>
          <li>Scope: ${esc(card.scope.provider)} only — hard cap ${money(card.scope.max_monthly_before)}/mo</li>
          <li>Single use · expires ${esc(card.expires_at.replace("T", " ").slice(0, 19))} UTC</li>
          <li>Approver: ${esc(card.approver)}</li>
        </ul>
        <p class="meta mono">sig ${esc(card.signature.slice(0, 20))}...</p>
        <p class="note">HMAC-SHA256 mandate — a local stand-in for AP2 verifiable credentials.
          Reply <b>"execute"</b> and the adapter runs; without this, nothing moves.</p>
      </div>`;
    case "receipt":
      return `<div class="card receipt">
        <span class="badge ok">executed · receipt</span>
        <span class="badge conf">simulated adapter</span>
        <h3>${esc(card.operation)}</h3>
        <div class="saving-flow">
          <span class="before">${money(card.monthly_before)}/mo</span>
          <span class="arrow">→</span>
          <span class="after">${money(card.monthly_after)}/mo</span>
        </div>
        <ul>${card.changes.map(s => `<li>${esc(s)}</li>`).join("")}</ul>
        <p class="meta">Adapter: ${esc(card.adapter)} · mandate ${esc(card.mandate_id)} ·
          approved by ${esc(card.approver)}</p>
        <p class="note">Rollback: ${esc(card.rollback)}</p>
      </div>`;
    case "mandates": {
      const rows = card.mandates.map(m =>
        `<li><b>${esc(m.mandate_id)}</b> ${esc(m.scope.operation)} —
           <span class="badge ${m.status === "issued" ? "ok" : "conf"}">${esc(m.status)}</span>
           <span class="meta">cap ${money(m.scope.max_monthly_before)}/mo · sig ${esc(m.signature_short)}</span></li>`).join("");
      const props = card.proposals.map(p =>
        `<li><b>${esc(p.proposal_id)}</b> ${esc(p.title)} —
           <span class="badge conf">${esc(p.status)}</span></li>`).join("");
      const receipts = card.receipts.map(r =>
        `<li><b>${esc(r.operation)}</b> via ${esc(r.adapter)} — saved ${money(r.monthly_saving)}/mo
           <span class="meta">(simulated · ${esc(r.executed_at.replace("T", " ").slice(0, 19))} UTC)</span></li>`).join("");
      return `<div class="card">
        <span class="badge conf">action accountability</span>
        <h3>Proposals · mandates · receipts</h3>
        ${props ? `<p class="meta">Proposals</p><ul>${props}</ul>` : ""}
        ${rows ? `<p class="meta">Mandates</p><ul>${rows}</ul>` : ""}
        ${receipts ? `<p class="meta">Receipts</p><ul>${receipts}</ul>` : ""}
        ${!props && !rows && !receipts ? `<p class="note">Nothing yet — the loop is prove → approve → execute → receipt.</p>` : ""}
      </div>`;
    }
    case "budget": {
      const pct = Math.min(card.used_pct || 0, 100);
      return `<div class="card">
        <span class="badge ${card.status}">budget · ${card.status}</span>
        <h3>${esc(card.category)}</h3>
        <p class="amount">${money(card.spent)} / ${money(card.monthly_limit)}</p>
        <div class="bar ${card.status}"><span style="width:${pct}%"></span></div>
        <p class="meta">${card.used_pct}% used this month</p>
      </div>`;
    }
    case "overview": {
      const max = Math.max(...card.providers.map(p => p.amount));
      return `<div class="card">
        <span class="badge conf">${card.month}</span>
        <h3>Total spend</h3>
        <p class="amount">${money(card.total)}</p>
        <p class="meta">${card.delta_pct > 0 ? "+" : ""}${card.delta_pct}% vs ${card.prev_month}</p>
        <div class="spark">${card.providers.slice(0, 8).map(p =>
          `<span style="height:${Math.max(8, p.amount / max * 100)}%" title="${esc(p.name)} ${money(p.amount)}"></span>`).join("")}
        </div>
        <ul>${card.providers.slice(0, 6).map(p =>
          `<li>${esc(p.name)} — ${money(p.amount)}${p.delta_pct ? ` (${p.delta_pct > 0 ? "+" : ""}${p.delta_pct}%)` : ""}</li>`).join("")}
        </ul>
      </div>`;
    }
    case "unit":
      return `<div class="card">
        <span class="badge conf">unit economics</span>
        <h3>Cost per 1K tasks</h3>
        <ul>${card.providers.map(r => {
          const last = r.points[r.points.length - 1];
          const drift = r.drift && r.drift.mom_pct !== null ? `${r.drift.mom_pct > 0 ? "+" : ""}${r.drift.mom_pct}% MoM` : "n/a";
          return `<li>${esc(r.provider)} — ${money(last.cost_per_1k_tasks)} /1K tasks (${drift})${r.canary ? ' <span class="badge over">canary</span>' : ""}</li>`;
        }).join("")}</ul>
        <p class="note">Total spend is the smoke alarm; cost per task is the canary.</p>
      </div>`;
    case "subscriptions":
      return `<div class="card">
        <span class="badge conf">recurring</span>
        <h3>Subscriptions</h3>
        <ul>${card.items.map(s =>
          `<li>${esc(s.name)} — ${money(s.monthly)}/mo${s.flag === "zombie" ? ' — <span class="badge warn">unused ' + s.last_used_days + "d</span>" : ""}</li>`).join("")}
        </ul>
      </div>`;
    case "ledger":
      return `<div class="card">
        <span class="badge conf">accountability</span>
        <h3>Decision ledger</h3>
        <ul>${card.entries.map(e =>
          `<li><b>${esc(e.kind)}</b> ${esc(e.subject)} — ${esc(e.reason)}</li>`).join("")}
        </ul>
        <p class="note">Challenge any entry: "challenge #3" — your overrule becomes my context.</p>
      </div>`;
    default:
      return "";
  }
}

function addCards(cards) {
  if (!cards || !cards.length) return;
  const row = document.createElement("div");
  row.className = "carousel";
  row.innerHTML = cards.map(cardHTML).join("");
  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function renderStats(stats) {
  if (!stats) return;
  statsEl.hidden = false;
  document.getElementById("stat-total").textContent = money(stats.total);
  document.getElementById("stat-month").textContent = "this month (" + stats.month + ")";
  document.getElementById("stat-delta").textContent = (stats.delta_pct > 0 ? "+" : "") + stats.delta_pct + "%";
  document.getElementById("stat-anomalies").textContent = stats.anomalies;
  document.getElementById("stat-saving").textContent = money(stats.saving_potential);
}

async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function send(text) {
  if (!text.trim()) return;
  addMessage("user", text);
  inputEl.value = "";
  const data = await post("/api/chat", { message: text, session_id: sessionId });
  sessionId = data.session_id;
  localStorage.setItem(SESSION_KEY, sessionId);
  addMessage("agent", data.reply);
  addCards(data.cards);
  if (!ledgerPanel.hidden) loadLedger();
}

async function loadLedger() {
  const res = await fetch("/api/ledger");
  const data = await res.json();
  ledgerBody.innerHTML = data.entries.map(e =>
    `<div class="ledger-entry">
       <span class="kind ${esc(e.kind)}">${esc(e.kind)} #${e.seq}</span>
       <span class="why"><b>${esc(e.subject)}</b> — ${esc(e.reason)}</span>
     </div>`).join("") || '<p class="why">No decisions recorded yet.</p>';
}

ledgerToggle.addEventListener("click", () => {
  ledgerPanel.hidden = !ledgerPanel.hidden;
  ledgerToggle.classList.toggle("active", !ledgerPanel.hidden);
  if (!ledgerPanel.hidden) loadLedger();
});

async function boot() {
  const url = "/api/opening" + (sessionId ? `?session_id=${sessionId}` : "");
  const res = await fetch(url);
  const data = await res.json();
  sessionId = data.session_id;
  localStorage.setItem(SESSION_KEY, sessionId);
  renderStats(data.stats);
  addMessage("agent", data.reply);  // the agent speaks first — it does not wait to be asked
  addCards(data.cards);
}

sendBtn.addEventListener("click", () => send(inputEl.value));
inputEl.addEventListener("keydown", (e) => { if (e.key === "Enter") send(inputEl.value); });

document.querySelectorAll(".chip").forEach(chip =>
  chip.addEventListener("click", () => send(chip.dataset.say)));

newSessionBtn.addEventListener("click", () => {
  localStorage.removeItem(SESSION_KEY);
  sessionId = null;
  chatEl.innerHTML = "";
  statsEl.hidden = true;
  boot();
});

/* Voice input: progressive enhancement only. Keyboard is the primary path. */
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recog = new SpeechRecognition();
  recog.lang = "en-US";
  micBtn.addEventListener("click", () => {
    micBtn.classList.add("listening");
    recog.start();
  });
  recog.onresult = (e) => {
    const text = e.results[0][0].transcript;
    micBtn.classList.remove("listening");
    send(text);
  };
  recog.onerror = () => micBtn.classList.remove("listening");
  recog.onend = () => micBtn.classList.remove("listening");
} else {
  micBtn.style.display = "none";  // graceful degradation
}

boot();
