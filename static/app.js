const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const gate = document.querySelector("#gate");
const yard = document.querySelector("#yard");
const altar = document.querySelector("#altar");
const wait = document.querySelector("#wait");
const ofrenda = document.querySelector("#ofrenda");
const gateError = document.querySelector("#gate-error");
const statusLine = document.querySelector("#status");
const stones = document.querySelector("#stones");
const wave = document.querySelector("#wave");
const player = document.querySelector("#player");
const chartHost = document.querySelector("#chart");

const NO_EULOGY = "There is no eulogy for work that is still being touched, so neither voice can speak.";

let lastEulogy = "";
let lastChart = null;
let drawnSize = "";
let stageTimer = 0;
let elevenReady = false;

function pretty(iso) {
  if (!iso) return "";
  const [year, month, day] = iso.split("-").map(Number);
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

function showError(message) {
  gateError.textContent = message || "";
}

function detailText(detail) {
  if (!detail) return "The ritual stopped.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (typeof item === "string" ? item : item?.msg || ""))
      .filter(Boolean);
    return parts.join(" ") || "The ritual stopped.";
  }
  if (typeof detail === "object" && detail.msg) return detail.msg;
  return "The ritual stopped.";
}

async function readJson(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(detailText(body.detail));
  }
  return body;
}

function setWave(on) {
  wave.classList.toggle("on", on);
  window.haunt?.duck(on);
}

function lightCandles(count) {
  for (let index = 0; index < 3; index += 1) {
    document.querySelector(`#candle-${index}`).classList.toggle("lit", index < count);
  }
}

function beginWait() {
  const lines = [
    "Gathering what was left behind.",
    "Finding the week the work went quiet.",
    "Asking TabPFN what the silence would have held.",
    "Listening for Gemma, on this machine.",
  ];
  let step = 0;
  gate.hidden = true;
  yard.hidden = true;
  altar.hidden = false;
  wait.hidden = false;
  ofrenda.hidden = true;
  lightCandles(1);
  statusLine.textContent = lines[0];
  window.clearInterval(stageTimer);
  stageTimer = window.setInterval(() => {
    step = Math.min(step + 1, lines.length - 1);
    lightCandles(step + 1);
    statusLine.textContent = lines[step];
  }, 2200);
}

function endWait() {
  window.clearInterval(stageTimer);
  lightCandles(3);
  statusLine.textContent = "";
}

async function ritual(payload) {
  showError("");
  beginWait();
  try {
    const data = await readJson(await fetch("/api/ritual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
    endWait();
    renderAltar(data);
  } catch (error) {
    endWait();
    altar.hidden = true;
    gate.hidden = false;
    showError(error.message);
  }
}

function fact(term, value) {
  const wrap = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = value;
  wrap.append(dt, dd);
  return wrap;
}

function stopVoices() {
  window.speechSynthesis?.cancel();
  player.pause();
  setWave(false);
}

function renderAltar(data) {
  stopVoices();
  wait.hidden = true;
  ofrenda.hidden = false;
  const project = data.project;
  const death = data.death;
  document.querySelector("#source-line").textContent = project.source === "sample"
    ? "A fictional life, kept in this project"
    : project.source === "csv"
      ? "A record from this computer"
      : "A public GitHub repository";
  document.querySelector("#epitaph-name").textContent = project.name;
  document.querySelector("#epitaph-desc").textContent = project.description;

  const facts = document.querySelector("#facts");
  facts.replaceChildren(
    fact("Opened", pretty(death.born)),
    fact("Last touched", pretty(death.died)),
    fact("Quiet for", death.alive ? "still breathing" : `${death.silence_days} days`),
    fact("Commits", String(death.total_commits)),
  );

  const caption = document.querySelector("#chart-caption");
  if (death.alive) {
    const busy = data.series.filter((row) => row.actual > 0).length;
    const empty = data.series.length - busy;
    caption.textContent = empty
      ? `This repository was touched recently, so there is no forecast of a silence. ${death.total_commits} commits fall in ${busy} week${busy === 1 ? "" : "s"}. The other ${empty} week${empty === 1 ? " is" : "s are"} empty.`
      : "This repository was touched recently. The altar is for work that has gone quiet.";
  } else if (data.forecast) {
    caption.textContent = `${data.forecast.engine} on ${data.forecast.device} expected ${data.forecast.expected_on_death_week} commits in the week the work stopped, and ${data.forecast.ghost_commits} across the silence. ${data.forecast.detail}`;
  } else {
    caption.textContent = data.forecast_error || "The forecast candle is unlit.";
  }
  document.querySelector("#legend-ghost").hidden = !data.forecast;

  lastChart = { series: data.series, lifeWeeks: death.weeks_alive, alive: death.alive };
  drawChart(lastChart.series, lastChart.lifeWeeks, lastChart.alive, true);

  const quote = document.querySelector("#eulogy");
  const note = document.querySelector("#eulogy-note");
  const empty = document.querySelector("#eulogy-empty");
  if (!data.eulogy) {
    quote.textContent = "";
    quote.hidden = true;
    empty.hidden = false;
    note.textContent = "";
    lastEulogy = "";
  } else {
    empty.hidden = true;
    quote.hidden = false;
    quote.textContent = data.eulogy.text;
    quote.scrollTop = 0;
    lastEulogy = data.eulogy.text;
    const who = data.eulogy.speaker === "gemma"
      ? `Spoken by ${data.eulogy.model}, locally.`
      : "Spoken from the record on this machine.";
    note.textContent = [who, data.eulogy.note, project.history_note].filter(Boolean).join(" ");
  }
  document.querySelector("#speak-local").disabled = !lastEulogy;
  document.querySelector("#speak-eleven").hidden = !elevenReady;
  document.querySelector("#speak-eleven").disabled = !lastEulogy;
  player.hidden = true;
  document.querySelector("#voice-note").textContent = lastEulogy ? "" : NO_EULOGY;
}

/* ---------- the chart: one column a week, the forecast as a green ghost line ---------- */

const PAD_L = 34;
const PAD_R = 12;
const PAD_T = 16;
const PAD_B = 26;

function svgNode(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function drawChart(series, lifeWeeks, alive, animate) {
  chartHost.replaceChildren();
  if (!series.length) return;
  const width = Math.max(320, chartHost.clientWidth);
  const height = Math.max(140, chartHost.clientHeight);
  drawnSize = `${width}x${height}`;
  const axisY = height - PAD_B;
  const life = alive ? series : series.slice(0, lifeWeeks);
  const silence = alive ? [] : series.slice(lifeWeeks);
  const split = silence.length > Math.max(life.length, 1);
  const values = series.flatMap((row) => [row.actual, row.ghost].filter((value) => value !== null && value !== undefined));
  const peak = Math.max(1, ...values);

  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}` });
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Weekly commits. Each column is one week.");
  if (!animate) svg.classList.add("chart-still");

  const defs = svgNode("defs");
  const gradient = svgNode("linearGradient", { id: "barfill", x1: "0", y1: "0", x2: "0", y2: "1" });
  gradient.append(
    svgNode("stop", { offset: "0", "stop-color": "#ffd166" }),
    svgNode("stop", { offset: "1", "stop-color": "#ff5a12" }),
  );
  defs.append(gradient);
  svg.append(defs);

  const yAt = (value) => axisY - (value / peak) * (axisY - PAD_T);
  const inner = width - PAD_L - PAD_R;

  [0.5, 1].forEach((fraction) => {
    const value = peak * fraction;
    const y = yAt(value);
    svg.append(svgNode("line", { x1: PAD_L, x2: width - PAD_R, y1: y, y2: y, class: "grid-line" }));
    const text = svgNode("text", { x: PAD_L - 8, y: y + 4, "text-anchor": "end", class: "chart-label" });
    text.textContent = String(Math.round(value * 10) / 10);
    svg.append(text);
  });
  svg.append(svgNode("line", { x1: PAD_L, x2: width - PAD_R, y1: axisY, y2: axisY, class: "axis-line" }));

  const markDeath = (x) => {
    svg.append(svgNode("line", { x1: x, x2: x, y1: PAD_T, y2: axisY, class: "death-line" }));
    const label = svgNode("text", { x: x + 6, y: PAD_T + 10, class: "chart-label" });
    label.textContent = "the silence";
    svg.append(label);
  };

  if (!split) {
    const xAt = (index) => slotCenter(PAD_L, inner, series.length, index);
    drawBars(svg, series, PAD_L, inner, yAt, axisY);
    drawGhostLine(svg, series, xAt, yAt);
    if (!alive && lifeWeeks > 0 && lifeWeeks < series.length) {
      markDeath(PAD_L + (inner * lifeWeeks) / series.length);
    }
    labelWeeks(svg, series, xAt, axisY);
  } else {
    const lifeWidth = inner * 0.7;
    const gap = 16;
    const silenceWidth = inner - lifeWidth - gap;
    const buckets = bucket(silence, 28);
    const siloOrigin = PAD_L + lifeWidth + gap;
    drawBars(svg, life, PAD_L, lifeWidth, yAt, axisY);
    drawBars(svg, buckets, siloOrigin, silenceWidth, yAt, axisY);
    drawGhostLine(svg, buckets, (index) => slotCenter(siloOrigin, silenceWidth, buckets.length, index), yAt);
    markDeath(PAD_L + lifeWidth + gap / 2);
    labelWeeks(svg, life, (index) => slotCenter(PAD_L, lifeWidth, life.length, index), axisY);
  }
  chartHost.append(svg);
}

function slotCenter(origin, span, count, index) {
  const slot = span / Math.max(count, 1);
  return origin + index * slot + slot / 2;
}

function drawBars(svg, rows, origin, span, yAt, axisY) {
  const slot = span / Math.max(rows.length, 1);
  const barW = Math.min(26, Math.max(3, slot * 0.6));
  const step = Math.min(0.04, 0.9 / Math.max(rows.length, 1));
  rows.forEach((row, index) => {
    if (!row.actual) return;
    const x = origin + index * slot + (slot - barW) / 2;
    const y = yAt(row.actual);
    const bar = svgNode("rect", {
      x,
      y,
      width: barW,
      height: Math.max(axisY - y, 1),
      rx: Math.min(4, barW / 2),
      fill: "url(#barfill)",
      class: "bar",
    });
    bar.style.setProperty("--delay", `${(index * step).toFixed(2)}s`);
    svg.append(bar);
  });
}

function drawGhostLine(svg, rows, xAt, yAt) {
  const points = rows
    .map((row, index) => (row.ghost === null || row.ghost === undefined) ? null : `${xAt(index)},${yAt(row.ghost)}`)
    .filter(Boolean);
  if (!points.length) return;
  svg.append(svgNode("polyline", { points: points.join(" "), pathLength: "1", class: "ghost-line" }));
}

function labelWeeks(svg, rows, xAt, axisY) {
  if (!rows.length || !rows[0].week) return;
  const indexes = rows.length <= 6 ? rows.map((_, index) => index) : [0, Math.floor(rows.length / 2), rows.length - 1];
  indexes.forEach((index) => {
    const node = svgNode("text", {
      x: xAt(index),
      y: axisY + 17,
      "text-anchor": index === 0 && rows.length > 6 ? "start" : index === rows.length - 1 && rows.length > 6 ? "end" : "middle",
      class: "chart-label",
    });
    node.textContent = shortWeek(rows[index].week);
    svg.append(node);
  });
}

function shortWeek(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return `${day} ${MONTHS[month - 1].slice(0, 3)} ${String(year).slice(2)}`;
}

function bucket(rows, count) {
  if (rows.length <= count) return rows;
  const size = rows.length / count;
  const grouped = [];
  for (let index = 0; index < count; index += 1) {
    const start = Math.floor(index * size);
    const end = Math.max(start + 1, Math.floor((index + 1) * size));
    const slice = rows.slice(start, end);
    const actual = slice.reduce((sum, row) => sum + row.actual, 0) / slice.length;
    const ghosts = slice.map((row) => row.ghost).filter((value) => value !== null && value !== undefined);
    const ghost = ghosts.length ? ghosts.reduce((sum, value) => sum + value, 0) / ghosts.length : null;
    grouped.push({ actual, ghost, week: slice[0].week });
  }
  return grouped;
}

let resizeFrame = 0;
new ResizeObserver(() => {
  if (!lastChart || ofrenda.hidden) return;
  const size = `${Math.max(320, chartHost.clientWidth)}x${Math.max(140, chartHost.clientHeight)}`;
  if (size === drawnSize) return;
  window.cancelAnimationFrame(resizeFrame);
  resizeFrame = window.requestAnimationFrame(() => {
    drawChart(lastChart.series, lastChart.lifeWeeks, lastChart.alive, false);
  });
}).observe(chartHost);

/* ---------- the gate ---------- */

document.querySelector("#light-sample").addEventListener("click", () => {
  ritual({ sample: true });
});

document.querySelector("#user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  const username = document.querySelector("#username").value.trim();
  try {
    const data = await readJson(await fetch("/api/graveyard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    }));
    stones.replaceChildren();
    const quiet = data.repos.filter((repo) => repo.silence_days >= 120);
    document.querySelector("#yard-title").textContent = `Repositories under ${data.username}`;
    if (!data.repos.length) {
      document.querySelector("#yard-note").textContent = "GitHub shows no public repositories for this name. Private ones stay closed, and the login has to match the username in the profile URL.";
    } else if (!quiet.length) {
      document.querySelector("#yard-note").textContent = "None of these have been still for 120 days. They are listed anyway. Open one and the altar will say if it is still being touched.";
    } else {
      document.querySelector("#yard-note").textContent = "The longest silences come first. A repository pushed more recently can still be opened.";
    }
    data.repos.forEach((repo, index) => {
      const item = document.createElement("li");
      item.style.setProperty("--i", Math.min(index, 16));
      const button = document.createElement("button");
      button.type = "button";
      const main = document.createElement("span");
      main.className = "stone-main";
      const title = document.createElement("strong");
      title.textContent = repo.full_name;
      const meta = document.createElement("span");
      meta.className = "meta";
      const language = repo.language || "no language listed";
      const kind = repo.fork ? " · fork" : "";
      meta.textContent = `${language} · last push ${pretty(repo.pushed_on)}${kind}`;
      main.append(title, meta);
      const isQuiet = repo.silence_days >= 120;
      const pill = document.createElement("em");
      pill.className = isQuiet ? "pill quiet" : "pill";
      pill.textContent = isQuiet ? `quiet ${repo.silence_days} days` : `pushed ${repo.silence_days} days ago`;
      button.append(main, pill);
      button.addEventListener("click", () => ritual({ repo: repo.full_name }));
      item.append(button);
      stones.append(item);
    });
    gate.hidden = true;
    yard.hidden = false;
  } catch (error) {
    showError(error.message);
  }
});

document.querySelector("#yard-back").addEventListener("click", () => {
  yard.hidden = true;
  gate.hidden = false;
});

document.querySelector("#csv-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = document.querySelector("#csv-file").files[0];
  if (!file) {
    showError("Choose a CSV first.");
    return;
  }
  ritual({
    csv: await file.text(),
    name: document.querySelector("#life-name").value.trim() || "untitled-life",
  });
});

/* ---------- voices ---------- */

document.querySelector("#speak-local").addEventListener("click", () => {
  const note = document.querySelector("#voice-note");
  if (!lastEulogy) {
    note.textContent = NO_EULOGY;
    return;
  }
  if (!window.speechSynthesis) {
    note.textContent = "This browser has no local voice.";
    return;
  }
  const utterance = new SpeechSynthesisUtterance(lastEulogy);
  utterance.rate = 0.82;
  utterance.pitch = 0.72;
  utterance.onstart = () => setWave(true);
  utterance.onend = () => setWave(false);
  utterance.onerror = () => setWave(false);
  player.pause();
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
  note.textContent = "Spoken by this browser. The words did not leave the machine.";
});

document.querySelector("#speak-eleven").addEventListener("click", async () => {
  const note = document.querySelector("#voice-note");
  if (!lastEulogy) {
    note.textContent = NO_EULOGY;
    return;
  }
  note.textContent = "Sending the eulogy to ElevenLabs.";
  try {
    const data = await readJson(await fetch("/api/voice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: lastEulogy }),
    }));
    window.speechSynthesis?.cancel();
    player.src = `data:audio/mpeg;base64,${data.audio_base64}`;
    player.hidden = false;
    player.play();
    note.textContent = "That recording was made by ElevenLabs. The text of the eulogy left this machine to do it.";
  } catch (error) {
    note.textContent = error.message;
  }
});

player.addEventListener("play", () => setWave(true));
player.addEventListener("pause", () => setWave(false));
player.addEventListener("ended", () => setWave(false));

document.querySelector("#again").addEventListener("click", () => {
  stopVoices();
  altar.hidden = true;
  gate.hidden = false;
  ofrenda.hidden = true;
});

/* ---------- the night sky and the engines ---------- */

(function scatterStars() {
  const host = document.querySelector("#stars");
  for (let index = 0; index < 90; index += 1) {
    const star = document.createElement("span");
    const size = Math.random() < 0.15 ? 3 : Math.random() < 0.5 ? 2 : 1.5;
    star.style.left = `${Math.random() * 100}%`;
    star.style.top = `${Math.random() * 62}%`;
    star.style.width = `${size}px`;
    star.style.height = `${size}px`;
    star.style.setProperty("--t", `${2.5 + Math.random() * 4}s`);
    star.style.setProperty("--delay", `${-Math.random() * 6}s`);
    host.append(star);
  }
})();

function setEngine(name, on, hint) {
  const chip = document.querySelector(`[data-engine="${name}"]`);
  if (!chip) return;
  chip.classList.toggle("on", Boolean(on));
  chip.title = hint;
}

fetch("/api/health")
  .then((response) => response.json())
  .then((health) => {
    elevenReady = Boolean(health.elevenlabs);
    document.querySelector("#speak-eleven").hidden = !elevenReady;
    const tabpfn = health.tabpfn || {};
    setEngine("tabpfn", tabpfn.installed, tabpfn.installed ? `TabPFN ${tabpfn.version} is installed` : "TabPFN is not installed");
    const gemma = health.ollama?.gemma;
    setEngine("gemma", gemma, gemma ? `${gemma} through Ollama` : "Ollama has no Gemma model yet");
    setEngine("browserbase", health.browserbase, health.browserbase ? "Browserbase reads the public repo page" : "No Browserbase key");
    setEngine("elevenlabs", health.elevenlabs, health.elevenlabs ? "ElevenLabs key found, used only on request" : "No ElevenLabs key");
  })
  .catch(() => {});
