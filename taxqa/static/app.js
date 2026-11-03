const form = document.getElementById("ask");
const input = document.getElementById("question");
const submit = document.getElementById("submit");
const thread = document.getElementById("thread");
const intro = document.getElementById("intro");
const newChat = document.getElementById("new-chat");

const STATUS_TEXT = {
  answered: "Answered from the Act",
  partial: "Partly answered",
  refused: "Not answered",
  error: "Something went wrong",
};
const COMPONENT_NAMES = {
  verified: "Citations verified", retrieval: "Match to the question",
  agreement: "Found by more than one search", completeness: "Question fully covered",
};

// Builds an element; text is always set as textContent so nothing from the server is parsed as HTML.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child !== null && child !== undefined) node.append(child);
  return node;
}

function pages(item) {
  return item.page_start === item.page_end ? `p. ${item.page_start}` : `pp. ${item.page_start}-${item.page_end}`;
}

function pdfLink(item, text) {
  return el("a", { href: `/act.pdf#page=${item.page_start}`, target: "_blank", rel: "noopener", text });
}

// Keep the newest text in view, unless the reader has scrolled up to look at something.
function follow(update) {
  const atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 120;
  update();
  if (atBottom) window.scrollTo(0, document.body.scrollHeight);
}

/* ---------- One question and its answer ---------- */

class Turn {
  constructor(question) {
    this.verdict = el("span", { class: "verdict working", text: "Working" });
    this.head = el("div", { class: "answer-head" }, this.verdict);
    this.progress = el("p", { class: "progress", text: "Searching the Act" });
    this.body = el("div", {}, this.progress);
    this.panel = el("div", { class: "answer" }, this.head, this.body);
    this.node = el("article", { class: "turn" }, el("div", { class: "question", text: question }), this.panel);
    this.points = null;
    this.gap = null;
  }

  retrieved(event) {
    const shown = event.sections.slice(0, 6).join(", ");
    const more = event.sections.length > 6 ? ` and ${event.sections.length - 6} more` : "";
    this.progress.textContent = event.extracts
      ? `Found ${event.extracts} extracts in ${shown}${more}. Drafting the answer`
      : "Nothing in the Act matched";
  }

  // Text of the answer while the model writes it. It is shown as a draft until the citations are checked.
  draft(event) {
    if (!this.points) {
      this.verdict.textContent = "Draft, citations being checked";
      this.progress.textContent = "Drafting the answer";
      this.points = el("ol", { class: "points draft" });
      this.body.append(this.points);
    }
    if (event.field === "statement") {
      while (this.points.children.length <= event.claim) this.points.append(el("li", {}, el("p")));
      this.points.children[event.claim].firstChild.textContent += event.text;
    } else {
      if (!this.gap) {
        this.gap = el("p");
        this.body.append(el("div", { class: "notice gap" }, el("strong", { text: "Not covered by the text found" }), this.gap));
      }
      this.gap.textContent += event.text;
    }
  }

  restart() {
    this.points = null;
    this.gap = null;
    this.progress.textContent = "Asking the model again";
    this.body.replaceChildren(this.progress);
  }

  fail(message) {
    this.verdict.className = "verdict error";
    this.verdict.textContent = STATUS_TEXT.error;
    this.body.replaceChildren(el("p", { class: "message error-text", text: message }));
  }

  done(data) {
    this.verdict.className = `verdict ${data.status}`;
    this.verdict.textContent = STATUS_TEXT[data.status] || data.status;
    const confidence = renderConfidence(data.confidence);
    if (confidence) this.head.append(confidence);
    this.body.replaceChildren(...renderAnswer(data));
  }
}

/* ---------- The verified answer ---------- */

function renderConfidence(confidence) {
  if (!confidence) return null;
  const rows = Object.entries(confidence.components).map(([key, value]) =>
    el("tr", {}, el("td", { text: COMPONENT_NAMES[key] || key }), el("td", { text: `${Math.round(value * 100)}%` })));
  const label = confidence.label[0].toUpperCase() + confidence.label.slice(1);
  return el("details", { class: "confidence" },
    el("summary", {}, "Confidence: ", el("strong", { class: confidence.label, text: label }),
      ` (${Math.round(confidence.score * 100)}%)`),
    el("table", {}, el("tbody", {}, ...rows)),
    el("p", { text: "Computed from the evidence after the answer is checked, not reported by the model." }));
}

function renderPoint(claim) {
  const cite = el("div", { class: "cite" });
  claim.citations.forEach((c, i) => {
    if (i) cite.append(el("span", { class: "sep", text: "|" }));
    cite.append(pdfLink(c, c.ref), ` (${pages(c)})`);
  });
  const item = el("li", { class: claim.verified ? "" : "unverified" }, el("p", { text: claim.statement }), cite);
  if (claim.quote) item.append(el("blockquote", { class: "quote", text: claim.quote }));
  if (!claim.verified) item.append(el("p", { class: "flag", text: `Not verified: ${claim.problem}. Check the Act before relying on this point.` }));
  return item;
}

// One row per verified point: what it says and where the Act says it, as in an advisory note.
function renderReferences(claims) {
  const rows = claims.filter((c) => c.verified).map((claim, i) => {
    const refs = el("td");
    for (const c of claim.citations) {
      refs.append(el("div", {}, pdfLink(c, c.ref), el("span", { class: "doc", text: ` ${c.document}, PDF ${pages(c)}` })));
    }
    return el("tr", {}, el("td", { text: String(i + 1) }), el("td", { text: claim.statement }), refs);
  });
  if (!rows.length) return [];
  return [el("div", { class: "section-title", text: "Statutory references" }),
    el("table", { class: "refs" },
      el("thead", {}, el("tr", {}, el("th", { text: "#" }), el("th", { text: "Point" }), el("th", { text: "Provision" }))),
      el("tbody", {}, ...rows))];
}

function renderSource(source) {
  const summary = el("summary", {}, el("strong", { text: source.ref }), " ",
    el("span", { class: "heading", text: source.heading }), " ", pdfLink(source, pages(source)));
  const node = el("details", { class: "source" }, summary, el("p", { text: source.text }));
  if (source.amended_by.length) node.append(el("p", { class: "amended", text: `Amended: ${source.amended_by.join("; ")}` }));
  return node;
}

function renderAnswer(data) {
  const parts = [];
  if (data.confidence && data.confidence.label === "low") {
    parts.push(el("div", { class: "notice warn", text: "Low confidence: the cited text only partly supports this answer. Read the cited provisions before relying on it." }));
  }
  if (data.message) parts.push(el("p", { class: "message", text: data.message }));
  if (data.status !== "refused" && data.claims.length) {
    parts.push(el("ol", { class: "points" }, ...data.claims.map(renderPoint)));
  }
  if (data.not_covered) {
    parts.push(el("div", { class: "notice gap" }, el("strong", { text: "Not covered by the text found" }), el("p", { text: data.not_covered })));
  }
  parts.push(...renderReferences(data.claims));
  if (data.sources.length) {
    parts.push(el("div", { class: "section-title", text: "Text of the cited provisions" }), ...data.sources.map(renderSource));
  }
  parts.push(el("p", { class: "meta", text:
    `${data.document}, ${data.edition}. ${data.extracts_considered} extracts considered. ` +
    `Model: ${data.model || "n/a"}. Search ${data.timing_ms.retrieval} ms, answer ${(data.timing_ms.llm / 1000).toFixed(1)} s.` }));
  return parts;
}

/* ---------- Asking ---------- */

async function ask(question) {
  submit.disabled = true;
  intro.hidden = true;
  newChat.hidden = false;
  const turn = new Turn(question);
  follow(() => thread.append(turn.node));
  window.scrollTo(0, document.body.scrollHeight);

  try {
    const res = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail = Array.isArray(data.detail) ? "Please enter a question of 3 to 1000 characters." : data.detail;
      turn.fail(detail || `Request failed (${res.status}).`);
      return;
    }
    // Newline-delimited JSON: one event per line, possibly split across network chunks.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (!line) continue;
        const event = JSON.parse(line);
        follow(() => {
          if (event.type === "retrieved") turn.retrieved(event);
          else if (event.type === "draft") turn.draft(event);
          else if (event.type === "restart") turn.restart();
          else if (event.type === "done") { turn.done(event.answer); finished = true; }
          else if (event.type === "error") { turn.fail(event.message); finished = true; }
        });
      }
    }
    if (!finished) turn.fail("The connection closed before the answer was complete. Please try again.");
  } catch {
    turn.fail("Could not reach the server. Check your connection and try again.");
  } finally {
    submit.disabled = false;
    input.focus();
  }
}

function grow() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight + 2, 180)}px`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question || submit.disabled) return;
  input.value = "";
  grow();
  ask(question);
});

input.addEventListener("input", grow);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

for (const button of document.querySelectorAll(".sample")) {
  button.addEventListener("click", () => {
    if (submit.disabled) return;
    ask(button.textContent);
  });
}

newChat.addEventListener("click", () => {
  if (submit.disabled) return;
  for (const turn of thread.querySelectorAll(".turn")) turn.remove();
  intro.hidden = false;
  newChat.hidden = true;
  input.focus();
});

fetch("/api/info")
  .then((res) => res.json())
  .then((info) => {
    document.getElementById("edition").textContent = `${info.document}, ${info.edition.replace(/^As /, "as ")}`;
  })
  .catch(() => {});
