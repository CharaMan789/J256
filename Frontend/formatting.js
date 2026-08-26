// ---------- formatting.js ----------
// Shared rich-text-lite system used by every compose flow (articles,
// discussions, announcements, replies) and every place a post body is
// displayed. Bodies are stored as plain text with a small markdown-ish
// syntax — never raw HTML — so the same string works everywhere: feed
// cards, article detail, the magazine PDF, moderation previews.
//
// Syntax:
//   **bold**
//   *italic*   or   _italic_
//   `code`
//   [font=Georgia]text[/font]      (wraps a run of text in a font choice)
//   $inline latex$
//   $$block latex$$
//
// FORMAT_FONTS is the fixed list offered in the font picker — keep this
// in sync with the <select> built in buildFormatToolbar().
const FORMAT_FONTS = [
  { label: "Default", value: "" },
  { label: "Serif", value: "Source Serif 4, serif" },
  { label: "Display Serif", value: "Fraunces, serif" },
  { label: "Sans", value: "Inter, sans-serif" },
  { label: "Mono", value: "IBM Plex Mono, monospace" },
];

// ---------- toolbar: inserting markup into a textarea at the cursor ----------

function insertAroundSelection(textarea, before, after) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const value = textarea.value;
  const selected = value.slice(start, end);
  const newValue = value.slice(0, start) + before + selected + after + value.slice(end);
  textarea.value = newValue;
  // Keep the wrapped text selected so hitting the same button again
  // (or typing over it) behaves the way people expect from a word processor.
  textarea.selectionStart = start + before.length;
  textarea.selectionEnd = start + before.length + selected.length;
  textarea.focus();
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertAtCursor(textarea, text, cursorOffset) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const value = textarea.value;
  textarea.value = value.slice(0, start) + text + value.slice(end);
  const pos = start + (cursorOffset != null ? cursorOffset : text.length);
  textarea.selectionStart = textarea.selectionEnd = pos;
  textarea.focus();
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

function applyBold(textarea) { insertAroundSelection(textarea, "**", "**"); }
function applyItalic(textarea) { insertAroundSelection(textarea, "*", "*"); }
function applyInlineCode(textarea) { insertAroundSelection(textarea, "`", "`"); }

function applyFont(textarea, fontValue) {
  if (!fontValue) return;
  insertAroundSelection(textarea, `[font=${fontValue}]`, "[/font]");
}

function applyInlineLatex(textarea) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  if (start === end) {
    insertAtCursor(textarea, "$x^2$", 1); // lands cursor right after the opening $
  } else {
    insertAroundSelection(textarea, "$", "$");
  }
}

function applyBlockLatex(textarea) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  if (start === end) {
    insertAtCursor(textarea, "\n$$\n\\frac{a}{b}\n$$\n", 4);
  } else {
    insertAroundSelection(textarea, "\n$$\n", "\n$$\n");
  }
}

// Builds the toolbar HTML. `idPrefix` namespaces element ids so the same
// toolbar can appear more than once on a page (e.g. article editor vs a
// reply box) without id collisions.
function buildFormatToolbar(idPrefix) {
  const fontOptions = FORMAT_FONTS.map(f => `<option value="${f.value}">${f.label}</option>`).join("");
  return `
    <div class="format-toolbar" id="${idPrefix}FormatToolbar">
      <button type="button" class="toolbar-btn" data-action="bold" title="Bold"><strong>B</strong></button>
      <button type="button" class="toolbar-btn" data-action="italic" title="Italic"><em>I</em></button>
      <button type="button" class="toolbar-btn" data-action="code" title="Inline code">&lt;/&gt;</button>
      <span class="format-toolbar-divider"></span>
      <select class="format-font-select" id="${idPrefix}FontSelect" title="Font for selected text">
        ${fontOptions}
      </select>
      <span class="format-toolbar-divider"></span>
      <button type="button" class="toolbar-btn" data-action="latex-inline" title="Inline LaTeX ($x^2$)">${ICONS.latex}<span class="toolbar-btn-label">Σ</span></button>
      <button type="button" class="toolbar-btn" data-action="latex-block" title="Block LaTeX ($$...$$)">${ICONS.latex}<span class="toolbar-btn-label">∑</span></button>
    </div>
  `;
}

// Wires a toolbar built by buildFormatToolbar() to a specific textarea.
// Call this right after inserting the toolbar + textarea into the DOM.
function wireFormatToolbar(idPrefix, textarea) {
  const toolbar = document.getElementById(`${idPrefix}FormatToolbar`);
  if (!toolbar || !textarea) return;
  toolbar.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.action;
      if (action === "bold") applyBold(textarea);
      else if (action === "italic") applyItalic(textarea);
      else if (action === "code") applyInlineCode(textarea);
      else if (action === "latex-inline") applyInlineLatex(textarea);
      else if (action === "latex-block") applyBlockLatex(textarea);
    });
  });
  const fontSelect = document.getElementById(`${idPrefix}FontSelect`);
  if (fontSelect) {
    fontSelect.addEventListener("change", () => {
      applyFont(textarea, fontSelect.value);
      fontSelect.selectedIndex = 0;
    });
  }
}

// ---------- rendering: turning stored plain text into safe HTML ----------

// Renders a post/reply body for display. Always escapes first, so the
// input is never trusted as HTML — formatting syntax is matched and
// replaced with real tags only after escaping, and LaTeX is handed to
// KaTeX (also given already-escaped source, so it never re-parses markup).
function renderFormattedBody(rawText) {
  if (!rawText) return "";
  let html = escapeHtml(rawText);

  // Block LaTeX first ($$...$$), so a lone $ inside it isn't later
  // mistaken for the start of an inline span.
  html = html.replace(/\$\$([\s\S]+?)\$\$/g, (match, expr) => renderLatex(expr, true));

  // Inline LaTeX ($...$), skipping the block delimiter itself. Requires the
  // expression to not start/end with whitespace — the same convention
  // Pandoc/Obsidian use — so ordinary prose mentioning two dollar amounts
  // ("$5 and $10") isn't misread as a formula.
  html = html.replace(/\$(\S[^\n$]*?\S|\S)\$/g, (match, expr) => renderLatex(expr, false));

  // Font span: [font=Value]text[/font]
  html = html.replace(/\[font=([^\]\n]+)\]([\s\S]+?)\[\/font\]/g, (match, font, inner) => {
    return `<span style="font-family:${font.replace(/"/g, "")}">${inner}</span>`;
  });

  // Bold before italic so **x** doesn't get eaten by the single-* rule first.
  html = html.replace(/\*\*([^\n*]+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(?:\*([^\n*]+?)\*)|(?:_([^\n_]+?)_)/g, (m, a, b) => `<em>${a || b}</em>`);
  html = html.replace(/`([^\n`]+?)`/g, "<code>$1</code>");

  return html;
}

// Renders a truncated, formatting-stripped preview — used for draft rows,
// moderation queue snippets, and anywhere raw ** / $ / [font=] syntax
// would just look like clutter rather than being rendered.
function plainPreview(rawText, maxLen) {
  if (!rawText) return "";
  let text = rawText
    .replace(/\$\$([\s\S]+?)\$\$/g, "$1")
    .replace(/\$(\S[^\n$]*?\S|\S)\$/g, "$1")
    .replace(/\[font=[^\]\n]+\]([\s\S]+?)\[\/font\]/g, "$1")
    .replace(/\*\*([^\n*]+?)\*\*/g, "$1")
    .replace(/(?:\*([^\n*]+?)\*)|(?:_([^\n_]+?)_)/g, (m, a, b) => a || b)
    .replace(/`([^\n`]+?)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  if (maxLen && text.length > maxLen) text = text.slice(0, maxLen);
  return text;
}

// KaTeX is loaded from a CDN (see index.html) without `defer` removed, so
// on a slow connection a view can render before it's ready. If it hasn't
// loaded yet or fails on malformed input, fall back to showing the raw
// expression rather than breaking the whole render — and re-render the
// current view once KaTeX does finish loading, so the fallback text is
// only ever seen briefly.
function renderLatex(expr, displayMode) {
  if (typeof katex === "undefined") {
    return `<span class="latex-fallback" data-latex-expr="${escapeHtml(expr)}" data-latex-display="${!!displayMode}">${expr}</span>`;
  }
  try {
    return katex.renderToString(expr, { throwOnError: false, displayMode: !!displayMode });
  } catch (e) {
    return `<span class="latex-fallback">${expr}</span>`;
  }
}

document.addEventListener("katex-ready", () => {
  document.querySelectorAll(".latex-fallback[data-latex-expr]").forEach(el => {
    try {
      const expr = el.getAttribute("data-latex-expr");
      const displayMode = el.getAttribute("data-latex-display") === "true";
      el.outerHTML = katex.renderToString(expr, { throwOnError: false, displayMode });
    } catch (e) {
      // leave the fallback text in place
    }
  });
});