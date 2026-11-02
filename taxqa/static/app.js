const form = document.getElementById("ask");
const input = document.getElementById("question");
const submit = document.getElementById("submit");
const statusBox = document.getElementById("status");
const result = document.getElementById("result");

const STATUS_TEXT = {
  answered: "Answered from the Act",
  partial: "Partly answered",
  refused: "Not answered",
  error: "Something went wrong",
};

// Builds an element; text is always set as textContent so nothing from the server is parsed as HTML.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

function pages(item) {
  return item.page_start === item.page_end ? `p. ${item.page_start}` : `pp. ${item.page_start}-${item.page_end}`;
}

function pdfLink(item, text) {
  return el("a", { href: `/act.pdf#page=${item.page_start}`, target: "_blank", rel: "noopener", text });
}

function showStatus(text, kind = "") {
  statusBox.hidden = false;
  statusBox.className = `status ${kind}`;
  statusBox.textContent = text;
}

function renderConfidence(confidence) {
  if (!confidence) return null;
  const names = { verified: "Citations verified", retrieval: "Match to the question",
                  agreement: "Found by more than one search", completeness: "Question fully covered" };
  const rows = Object.entries(confidence.components).map(([key, value]) =>
    el("li", { text: `${names[key] || key}: ${Math.round(value * 100)}%` }));
  return el("details", { class: `confidence ${confidence.label}` },
    el("summary", { text: `Confidence: ${confidence.label} (${Math.round(confidence.score * 100)}%)` }),
    el("ul", {}, ...rows),
    el("p", { class: "note", text: "Computed from the evidence, not reported by the model. See the README for the formula." }));
}

function renderClaim(claim) {
  const cites = el("span", { class: "cites" });
  for (const c of claim.citations) cites.append(pdfLink(c, `${c.ref}, ${pages(c)}`));
  const item = el("li", { class: claim.verified ? "claim" : "claim unverified" },
    el("p", { text: claim.statement }), cites);
  if (claim.quote) item.append(el("blockquote", { text: claim.quote }));
  if (!claim.verified) item.append(el("p", { class: "flag", text: `Not verified: ${claim.problem}. Check the Act before relying on this point.` }));
  return item;
}

function renderSource(source) {
  const head = el("summary", {}, el("strong", { text: source.ref }), ` ${source.heading} `,
    pdfLink(source, pages(source)));
  const body = el("details", { class: "source" }, head, el("p", { text: source.text }));
  if (source.amended_by.length) body.append(el("p", { class: "amended", text: `Amended: ${source.amended_by.join("; ")}` }));
  return body;
}

// One row per verified point: what it says and where the Act says it, as in a legal memo.
function renderReferences(data) {
  const rows = data.claims.filter((c) => c.verified).map((claim, i) => {
    const refs = el("td");
    for (const c of claim.citations) {
      refs.append(el("div", {}, pdfLink(c, `${c.ref}`), ` ${c.document}, PDF ${pages(c)}`));
    }
    return el("tr", {}, el("td", { text: String(i + 1) }), el("td", { text: claim.statement }), refs);
  });
  if (!rows.length) return null;
  return el("table", { class: "refs" },
    el("thead", {}, el("tr", {}, el("th", { text: "#" }), el("th", { text: "Answer statement" }), el("th", { text: "Statutory reference" }))),
    el("tbody", {}, ...rows));
}

function render(data) {
  result.replaceChildren();
  result.hidden = false;
  statusBox.hidden = true;

  const header = el("div", { class: `verdict ${data.status}` }, el("span", { text: STATUS_TEXT[data.status] || data.status }));
  result.append(header);
  const confidence = renderConfidence(data.confidence);
  if (confidence) result.append(confidence);
  if (data.confidence && data.confidence.label === "low") {
    result.append(el("p", { class: "flag", text: "Low confidence: the cited text only partly supports this answer. Read the cited provisions before relying on it." }));
  }
  if (data.message) result.append(el("p", { class: "message", text: data.message }));

  const verified = data.claims.filter((c) => c.verified);
  const shown = data.status === "refused" ? [] : data.claims;
  if (shown.length) result.append(el("ol", { class: "claims" }, ...shown.map(renderClaim)));
  if (data.status === "partial" && verified.length < data.claims.length) {
    result.append(el("p", { class: "note", text: "Points marked as not verified could not be matched word for word to the cited text." }));
  }
  if (data.not_covered) {
    result.append(el("div", { class: "gap" }, el("h3", { text: "Not covered by the text found" }), el("p", { text: data.not_covered })));
  }
  const references = renderReferences(data);
  if (references) result.append(el("h3", { text: "Statutory references" }), references);
  if (data.sources.length) {
    result.append(el("h3", { text: "Cited text" }), ...data.sources.map(renderSource));
  }
  result.append(el("p", { class: "meta", text:
    `${data.document}, ${data.edition}. ${data.extracts_considered} extracts considered. ` +
    `Model: ${data.model || "n/a"}. Search ${data.timing_ms.retrieval} ms, answer ${(data.timing_ms.llm / 1000).toFixed(1)} s.` }));
}

async function ask(question) {
  submit.disabled = true;
  result.hidden = true;
  showStatus("Searching the Act and checking the answer against it. This usually takes 10 to 20 seconds.", "busy");
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? "Please enter a question of 3 to 1000 characters." : data.detail;
      showStatus(detail || `Request failed (${res.status}).`, "error");
      return;
    }
    render(data);
  } catch {
    showStatus("Could not reach the server. Check your connection and try again.", "error");
  } finally {
    submit.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (question) ask(question);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) form.requestSubmit();
});

for (const button of document.querySelectorAll(".example")) {
  button.addEventListener("click", () => {
    input.value = button.textContent;
    form.requestSubmit();
  });
}

fetch("/api/info")
  .then((res) => res.json())
  .then((info) => {
    document.getElementById("edition").textContent =
      `Source: ${info.document}, ${info.edition} (official PDF, Income Tax Department).`;
  })
  .catch(() => {
    document.getElementById("edition").textContent = "";
  });
