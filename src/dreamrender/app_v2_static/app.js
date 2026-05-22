const state = {
  data: null,
  drag: null,
};
const layoutKey = "dreamrender.app.bentoLayout.v2";

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[char]));

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.message || response.statusText);
  return data;
}

function showInlineMessage(selector, tone, title, detail) {
  const element = $(selector);
  element.hidden = false;
  element.className = `inline-message ${tone}`;
  element.innerHTML = `
    <strong>${esc(title)}</strong>
    ${detail ? `<span>${esc(detail)}</span>` : ""}
  `;
}

function loadLayout() {
  try {
    return JSON.parse(localStorage.getItem(layoutKey) || "{}");
  } catch {
    return {};
  }
}

function saveLayout() {
  const layout = {};
  document.querySelectorAll(".bento-grid").forEach(grid => {
    const gridName = grid.dataset.grid || "default";
    layout[gridName] = [...grid.querySelectorAll(".bento-card")].map(card => card.dataset.widget);
  });
  localStorage.setItem(layoutKey, JSON.stringify(layout));
}

function applySavedLayout() {
  const layout = loadLayout();
  document.querySelectorAll(".bento-grid").forEach(grid => {
    const gridName = grid.dataset.grid || "default";
    const cards = new Map([...grid.querySelectorAll(".bento-card")].map(card => [card.dataset.widget, card]));
    (layout[gridName] || []).forEach(widget => {
      const card = cards.get(widget);
      if (card) grid.appendChild(card);
    });
  });
}

function swapCards(first, second) {
  const marker = document.createElement("div");
  const parent = first.parentNode;
  parent.insertBefore(marker, first);
  second.parentNode.insertBefore(first, second);
  parent.insertBefore(second, marker);
  marker.remove();
  saveLayout();
}

function cardFromPoint(x, y) {
  const hidden = state.drag?.card;
  if (hidden) hidden.style.pointerEvents = "none";
  const target = document.elementFromPoint(x, y)?.closest(".bento-card");
  if (hidden) hidden.style.pointerEvents = "";
  return target;
}

function clearDropTarget() {
  document.querySelectorAll(".drop-target").forEach(card => card.classList.remove("drop-target"));
}

async function refresh() {
  const data = await fetch("/api/state").then(response => response.json());
  state.data = data;
  render(data);
}

function render(data) {
  const config = data.config || {};
  $("#toggle").textContent = data.worker_running ? "Stop DreamRender" : "Start DreamRender";
  $("#toggle").classList.toggle("stop", Boolean(data.worker_running));
  $("#dashboard").disabled = !data.worker_running;
  $("#dashboard").title = data.worker_running ? "Open the DreamRender dashboard" : "Start DreamRender before opening the dashboard";
  $("#worker-state").textContent = data.worker_running ? `Running as ${config.worker_id}` : "Stopped";
  $("#monitor-state").textContent = data.monitor_running ? `Running on port ${config.monitor_port}` : "Stopped";
  $("#app-status").textContent = data.status || "Ready";

  $("#share").value = config.share || "";
  $("#c4d").value = config.c4d || "";
  $("#worker-id").value = config.worker_id || "";
  $("#chunk-size").value = config.chunk_size || 5;
  $("#monitor-port").value = config.monitor_port || 8766;
  $("#keep-worker").checked = Boolean(config.keep_worker_running);

  renderHealth(data.health || []);
  renderQueue(data.queue || {});
  renderGpus(data.gpus || [], data.gpu_message);
  $("#log").value = (data.worker_log || []).join("\n");
}

function renderHealth(items) {
  $("#health").innerHTML = items.map(item => `
    <div class="health-item">
      <span class="health-dot ${item.ok ? "ok" : ""}"></span>
      <span class="health-label">${esc(item.label)}</span>
      <span class="health-detail">${esc(item.detail)}</span>
    </div>
  `).join("");
}

function renderQueue(queue) {
  const jobs = queue.jobs || [];
  const workers = queue.workers || [];
  const activeWorkers = workers.filter(worker => worker.state === "online").length;
  const current = jobs[0];
  if (!jobs.length) {
    $("#queue-summary").innerHTML = `
      <div><strong>${activeWorkers}</strong> worker(s) online</div>
      <div>No queued jobs.</div>
      <div>Submit from Cinema 4D with Extensions &gt; DreamRender Submit Render.</div>
      <div>Code ${esc(queue.code_signature || "")}</div>
    `;
    return;
  }
  const stats = current.stats || {};
  $("#queue-summary").innerHTML = `
    <div><strong>${activeWorkers}</strong> worker(s) online</div>
    <div><strong>${esc(current.name)}</strong></div>
    <div>${Number(current.progress || 0).toFixed(1)}% complete</div>
    <div>Average ${esc(stats.avg || "--")} - ETA ${esc(stats.eta || "--")}</div>
  `;
}

function renderGpus(gpus, message) {
  if (!gpus.length) {
    $("#gpus").innerHTML = `<p>${esc(message || "No GPU data available.")}</p>`;
    return;
  }
  $("#gpus").innerHTML = gpus.map(gpu => `
    <article class="gpu">
      <div class="gpu-head">
        <span>GPU ${esc(gpu.index)} - ${esc(gpu.name)}</span>
        <span>${esc(gpu.util)}% load - ${esc(gpu.memory_used)}/${esc(gpu.memory_total)} MB VRAM</span>
      </div>
      <div class="gpu-track"><div class="gpu-fill" style="width:${Math.max(1, Number(gpu.util || 0))}%"></div></div>
    </article>
  `).join("");
}

function readConfigForm() {
  return {
    share: $("#share").value,
    c4d: $("#c4d").value,
    worker_id: $("#worker-id").value,
    chunk_size: Number($("#chunk-size").value || 5),
    monitor_port: Number($("#monitor-port").value || 8766),
    keep_worker_running: $("#keep-worker").checked,
  };
}

async function saveConfig() {
  await post("/api/config", readConfigForm());
  await refresh();
}

document.addEventListener("click", async event => {
  const tab = event.target.closest(".tab");
  if (tab) {
    document.querySelectorAll(".tab").forEach(button => button.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.tab).classList.add("active");
  }
});

document.addEventListener("pointerdown", event => {
  const handle = event.target.closest(".drag-handle");
  if (!handle) return;
  const card = handle.closest(".bento-card");
  if (!card) return;
  event.preventDefault();
  handle.setPointerCapture(event.pointerId);
  state.drag = {
    card,
    handle,
    grid: card.parentElement,
    startX: event.clientX,
    startY: event.clientY,
    active: false,
  };
});

document.addEventListener("pointermove", event => {
  const drag = state.drag;
  if (!drag) return;
  const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
  if (!drag.active && distance > 4) {
    drag.active = true;
    drag.card.classList.add("dragging");
    document.body.classList.add("is-dragging-widget");
  }
  if (!drag.active) return;
  clearDropTarget();
  const target = cardFromPoint(event.clientX, event.clientY);
  if (target && target !== drag.card && target.parentElement === drag.grid) {
    target.classList.add("drop-target");
  }
});

document.addEventListener("pointerup", event => {
  const drag = state.drag;
  if (!drag) return;
  const target = cardFromPoint(event.clientX, event.clientY);
  if (drag.active && target && target !== drag.card && target.parentElement === drag.grid) {
    swapCards(drag.card, target);
  }
  drag.card.classList.remove("dragging");
  document.body.classList.remove("is-dragging-widget");
  clearDropTarget();
  state.drag = null;
});

document.addEventListener("pointercancel", () => {
  if (state.drag?.card) state.drag.card.classList.remove("dragging");
  document.body.classList.remove("is-dragging-widget");
  clearDropTarget();
  state.drag = null;
});

$("#toggle").addEventListener("click", async () => {
  await saveConfig();
  await post("/api/action", { action: state.data?.worker_running ? "stop" : "start" });
  await refresh();
});
$("#dashboard").addEventListener("click", () => post("/api/action", { action: "open_dashboard" }));
$("#save-config").addEventListener("click", saveConfig);
$("#repair").addEventListener("click", async () => {
  await post("/api/action", { action: "repair" });
  await refresh();
});
$("#open-queue").addEventListener("click", () => post("/api/action", { action: "open_queue" }));
$("#install-plugin").addEventListener("click", async () => {
  const button = $("#install-plugin");
  button.disabled = true;
  button.textContent = "Installing...";
  showInlineMessage("#plugin-result", "working", "Installing Cinema 4D plugin", "DreamRender is copying the submitter into your Cinema 4D preferences.");
  try {
    const result = await post("/api/action", { action: "install_plugin" });
    showInlineMessage("#plugin-result", "ok", "Cinema 4D plugin installed", result.message || "Restart Cinema 4D and open Extensions > DreamRender Submit Render.");
  } catch (error) {
    showInlineMessage("#plugin-result", "error", "Plugin install failed", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Install C4D Plugin";
  }
  await refresh();
});
$("#copy-log").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("#log").value);
});

applySavedLayout();
refresh();
setInterval(refresh, 2500);
