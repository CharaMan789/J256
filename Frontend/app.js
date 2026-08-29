const API = ""; // same origin — backend serves this frontend directly
const ALLOWED_DOMAIN = "iisertvm.ac.in";

const appEl = document.getElementById("app");
const authArea = document.getElementById("authArea");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const mobileMenuBtn = document.getElementById("mobileMenuBtn");
const sidebarScrim = document.getElementById("sidebarScrim");
const navItems = document.querySelectorAll(".nav-item");

let currentUser = null;
let currentView = "home";

// ---------- helpers ----------

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Something went wrong");
  }
  return res.status === 204 ? null : res.json();
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const diffMs = Date.now() - new Date(dateStr + "Z").getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const ICONS = {
  image: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="2" y="3" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.4"/><circle cx="6.5" cy="7" r="1.3" stroke="currentColor" stroke-width="1.2"/><path d="M3 13l4-4 3 3 2.5-2.5L15 13" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`,
  video: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="2" y="4.5" width="9.5" height="9" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M11.5 7.5L16 5v8l-4.5-2.5" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>`,
  file: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M6 2h4.5L14 5.5V15a1 1 0 01-1 1H6a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M10.5 2v3.5H14" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>`,
  audio: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M6.5 12V4.5l7-1.8v7.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="4.8" cy="12" r="1.8" stroke="currentColor" stroke-width="1.4"/><circle cx="11.8" cy="10.2" r="1.8" stroke="currentColor" stroke-width="1.4"/></svg>`,
  pdf: `<svg width="26" height="26" viewBox="0 0 26 26" fill="none"><path d="M6 2.5h9l5 5V22a1.3 1.3 0 01-1.3 1.3H6A1.3 1.3 0 014.7 22V3.8A1.3 1.3 0 016 2.5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M15 2.5V8h5" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><text x="13" y="17.5" font-family="IBM Plex Mono, monospace" font-size="5.5" font-weight="600" text-anchor="middle" fill="currentColor">PDF</text></svg>`,
  latex: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M3 13.5L7.5 4.5M7.5 4.5L12 13.5M4.7 10h5.6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M12.5 6.5h3M14 6.5v6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  x: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><line x1="3" y1="3" x2="13" y2="13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><line x1="13" y1="3" x2="3" y2="13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  plus: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><line x1="8" y1="2.5" x2="8" y2="13.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="2.5" y1="8" x2="13.5" y2="8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
  newspaper: `<svg width="20" height="20" viewBox="0 0 18 18" fill="none"><rect x="2.5" y="3" width="13" height="12" rx="1" stroke="currentColor" stroke-width="1.4"/><line x1="5" y1="6" x2="10.5" y2="6" stroke="currentColor" stroke-width="1.2"/><line x1="5" y1="8.3" x2="10.5" y2="8.3" stroke="currentColor" stroke-width="1.2"/></svg>`,
  poll: `<svg width="16" height="16" viewBox="0 0 18 18" fill="none"><rect x="3" y="10" width="3" height="5" rx="0.5" stroke="currentColor" stroke-width="1.3"/><rect x="7.5" y="6" width="3" height="9" rx="0.5" stroke="currentColor" stroke-width="1.3"/><rect x="12" y="3" width="3" height="12" rx="0.5" stroke="currentColor" stroke-width="1.3"/></svg>`,
  discussion: `<svg width="16" height="16" viewBox="0 0 18 18" fill="none"><path d="M3 4.5h12a1 1 0 011 1v6a1 1 0 01-1 1H8l-3.5 3v-3H3a1 1 0 01-1-1v-6a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`,
  announcement: `<svg width="16" height="16" viewBox="0 0 18 18" fill="none"><path d="M2.5 7v4h2.5l4 3V4l-4 3H2.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M11.5 6.5a3 3 0 010 5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M13.5 4.5a6 6 0 010 9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  reply: `<svg width="15" height="15" viewBox="0 0 18 18" fill="none"><path d="M15 9a5.5 5.5 0 01-5.5 5.5H6l-3 2.5v-3.2A5.5 5.5 0 013.5 3.5h6A5.5 5.5 0 0115 9z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`,
  thumbsUp: `<svg width="14" height="14" viewBox="0 0 18 18" fill="none"><path d="M7 8l3-5.5a1.6 1.6 0 013 1v4h3a1.5 1.5 0 011.4 2.1l-2 5A1.5 1.5 0 0113.9 15.5H7V8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M7 8v7.5H4.5a1 1 0 01-1-1V9a1 1 0 011-1H7z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`,
  thumbsDown: `<svg width="14" height="14" viewBox="0 0 18 18" fill="none"><path d="M11 10l-3 5.5a1.6 1.6 0 01-3-1v-4h-3a1.5 1.5 0 01-1.4-2.1l2-5A1.5 1.5 0 014.1 2.5H11V10z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M11 10V2.5h2.5a1 1 0 011 1V9a1 1 0 01-1 1H11z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`,
  bell: `<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M5 7.5a4 4 0 018 0v3l1.3 2.2H3.7L5 10.5v-3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M7.3 14.8a1.7 1.7 0 003.4 0" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  incognito: `<svg width="20" height="20" viewBox="0 0 18 18" fill="none"><path d="M2.5 11.5c0-3 2.9-6 6.5-6s6.5 3 6.5 6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="5.3" cy="12.3" r="1.9" stroke="currentColor" stroke-width="1.3"/><circle cx="12.7" cy="12.3" r="1.9" stroke="currentColor" stroke-width="1.3"/><path d="M7.2 12.3h3.6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>`,
  shield: `<svg width="20" height="20" viewBox="0 0 18 18" fill="none"><path d="M9 2.2l5.5 2v4.3c0 3.5-2.3 6.3-5.5 7.3-3.2-1-5.5-3.8-5.5-7.3V4.2L9 2.2z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M6.3 9l1.9 1.9L11.7 7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
};

// ---------- theme ----------

const themeToggle = document.getElementById("themeToggle");
const themeToggleIcon = document.getElementById("themeToggleIcon");
const themeToggleLabel = document.getElementById("themeToggleLabel");

const SUN_ICON = `<svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3.2" stroke="currentColor" stroke-width="1.3"/><path d="M8 1.5v1.4M8 13.1v1.4M2.4 8h1.4M12.2 8h1.4M3.9 3.9l1 1M11.1 11.1l1 1M3.9 12.1l1-1M11.1 4.9l1-1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>`;
const MOON_ICON = `<svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M13.5 9.3A5.6 5.6 0 0 1 6.7 2.5a5.7 5.7 0 1 0 6.8 6.8z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>`;

function applyThemeUI(theme) {
  const isDark = theme === "dark";
  themeToggleIcon.innerHTML = isDark ? MOON_ICON : SUN_ICON;
  themeToggleLabel.textContent = isDark ? "Dark mode" : "Light mode";
}

applyThemeUI(document.documentElement.getAttribute("data-theme") || "light");

themeToggle.addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("j_theme", next);
  applyThemeUI(next);
});

// ---------- sidebar ----------

const isMobileWidth = () => window.matchMedia("(max-width: 720px)").matches;

// On mobile "collapsed" means "off-screen" (see CSS), so the sidebar
// should start collapsed there — a phone opening the site for the first
// time shouldn't have the menu covering the whole screen. On desktop it
// stays collapsed only if the person collapsed it themselves last time;
// that preference is saved separately so switching screen sizes doesn't
// carry one mode's saved state into the other and strand the toggle.
const savedDesktopCollapsed = localStorage.getItem("j_sidebar_collapsed") === "1";
if (isMobileWidth() || savedDesktopCollapsed) {
  sidebar.classList.add("collapsed");
}

function toggleSidebar() {
  sidebar.classList.toggle("collapsed");
  if (!isMobileWidth()) {
    localStorage.setItem("j_sidebar_collapsed", sidebar.classList.contains("collapsed") ? "1" : "0");
  }
}

sidebarToggle.addEventListener("click", toggleSidebar);
if (mobileMenuBtn) mobileMenuBtn.addEventListener("click", toggleSidebar);
if (sidebarScrim) sidebarScrim.addEventListener("click", toggleSidebar);

navItems.forEach(item => {
  item.addEventListener("click", () => {
    goTo(item.dataset.view);
    // On mobile, picking a section should close the overlay menu instead
    // of leaving it covering the new page.
    if (isMobileWidth() && !sidebar.classList.contains("collapsed")) {
      sidebar.classList.add("collapsed");
    }
  });
});

function setActiveNav(view) {
  navItems.forEach(item => item.classList.toggle("active", item.dataset.view === view));
}

function goTo(view) {
  currentView = view;
  setActiveNav(view);
  render();
}

// ---------- auth ----------

async function loadCurrentUser() {
  currentUser = await fetchJSON(`${API}/auth/me`).catch(() => null);
  renderAuthArea();
  if (currentView === "account") render();
  maybeShowOnboarding();
}

function renderAuthArea() {
  document.getElementById("reportedNavItem").hidden = !(currentUser && currentUser.is_moderator);
  document.getElementById("notifBellBtn").hidden = !currentUser;
  if (currentUser) {
    loadUnreadCount();
    startNotifPolling();
  } else {
    stopNotifPolling();
  }
  if (currentUser) {
    const avatar = currentUser.picture
      ? `<img src="${currentUser.picture}" alt="">`
      : `<div class="avatar-fallback">${escapeHtml(currentUser.name[0] || "?")}</div>`;
    authArea.innerHTML = `
      <div class="user-chip" id="userChip" role="button" tabindex="0">
        ${avatar}
        <div class="user-chip-text">
          <span class="user-chip-name">${escapeHtml(currentUser.name)}</span>
          <button class="user-chip-out" id="logoutLink">sign out</button>
        </div>
      </div>
      ${currentUser.is_moderator ? `<span class="mod-t-value" id="modTValue">T: …</span>` : ""}
    `;
    document.getElementById("logoutLink").addEventListener("click", (e) => {
      e.stopPropagation();
      window.location.href = `${API}/auth/logout`;
    });
    document.getElementById("userChip").addEventListener("click", () => goToAccount());
    document.getElementById("userChip").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        goToAccount();
      }
    });
    if (currentUser.is_moderator) loadModTValue();
  } else {
    authArea.innerHTML = `
      <div class="auth-signed-out">
        <button class="signin-btn" id="signinBtn">Sign in with Google</button>
      </div>
    `;
    document.getElementById("signinBtn").addEventListener("click", () => {
      window.location.href = `${API}/auth/login`;
    });
  }
}

// "T value" — total registered users, same denominator ban polls use for
// turnout (see moderation.py K_RATIO/TURNOUT_RATIO). Moderator-only.
async function loadModTValue() {
  try {
    const { total_users } = await fetchJSON(`${API}/moderation/user-count`);
    const el = document.getElementById("modTValue");
    if (el) el.textContent = `T: ${total_users}`;
  } catch (e) {
    // Silent — this is a small sidebar badge, not worth an error banner.
  }
}

function checkLoginError() {
  const params = new URLSearchParams(window.location.search);
  const error = params.get("error");
  if (!error) return;
  let msg = "Something went wrong signing in.";
  if (error === "login_failed") msg = "Sign-in didn't go through. Try again.";
  if (error === "iiser_domain_mismatch") msg = `Sign in with your @${ALLOWED_DOMAIN} Google account.`;
  const banner = document.createElement("div");
  banner.className = "error-msg";
  banner.style.cssText = "text-align:center; padding:12px; background:var(--red-pale); color:var(--red); margin: 12px 32px 0; border-radius:10px; font-weight:500;";
  banner.textContent = msg;
  document.body.insertBefore(banner, document.querySelector(".shell"));
}

function requireLogin() {
  if (!currentUser) {
    window.location.href = `${API}/auth/login`;
    return false;
  }
  return true;
}

// ---------- notifications ----------
// See notifications.py for why: a notification only ever says "someone
// replied to one of your discussions/comments" — no title, no preview,
// no link to the specific post. Nothing here fetches or renders anything
// beyond that generic text, by design.

let notifPollTimer = null;

async function loadUnreadCount() {
  if (!currentUser) return;
  try {
    const { count } = await fetchJSON(`${API}/notifications/unread-count`);
    const badge = document.getElementById("notifBadge");
    if (count > 0) {
      badge.textContent = count > 9 ? "9+" : String(count);
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
  } catch (e) {
    // Silent — a failed poll shouldn't interrupt anything else.
  }
}

function startNotifPolling() {
  if (notifPollTimer) return;
  notifPollTimer = setInterval(loadUnreadCount, 45000);
}

function stopNotifPolling() {
  if (notifPollTimer) {
    clearInterval(notifPollTimer);
    notifPollTimer = null;
  }
}

async function openNotifPanel() {
  const panel = document.getElementById("notifPanel");
  panel.hidden = false;
  const list = document.getElementById("notifPanelList");
  list.innerHTML = `<p class="empty-state">Loading…</p>`;
  try {
    const items = await fetchJSON(`${API}/notifications`);
    list.innerHTML = items.length === 0
      ? `<p class="empty-state">No notifications yet.</p>`
      : items.map(n => `
          <div class="notif-item ${n.is_read ? "" : "notif-item-unread"}">
            <p>${escapeHtml(n.text)}</p>
            <span class="notif-item-time">${timeAgo(n.created_at)}</span>
          </div>
        `).join("");
    // Opening the panel is what "seeing" your notifications means here —
    // there's nothing further to click into per item, so mark-all-read
    // happens right away rather than needing a separate button.
    await fetchJSON(`${API}/notifications/read-all`, { method: "POST" });
    document.getElementById("notifBadge").hidden = true;
  } catch (e) {
    list.innerHTML = `<p class="empty-state">Couldn't load notifications.</p>`;
  }
}

function closeNotifPanel() {
  document.getElementById("notifPanel").hidden = true;
}

function wireNotifBell() {
  const bellBtn = document.getElementById("notifBellBtn");
  const panel = document.getElementById("notifPanel");
  bellBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (panel.hidden) openNotifPanel();
    else closeNotifPanel();
  });
  document.addEventListener("click", (e) => {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== bellBtn) closeNotifPanel();
  });
}

// ---------- router ----------

function render() {
  if (currentView === "home") renderHome();
  else if (currentView === "explore") renderExplore();
  else if (currentView === "explore-detail") renderExploreDetail();
  else if (currentView === "explore-compose") renderExploreCompose();
  else if (currentView === "magazine") renderMagazine();
  else if (currentView === "article-detail") renderArticleDetail(articleDetailId);
  else if (currentView === "drafts") renderDrafts();
  else if (currentView === "reported") renderReported();
  else if (currentView === "ban-polls") renderBanPolls();
  else if (currentView === "account") renderAccount();
}

function goToAccount() {
  if (!requireLogin()) return;
  currentView = "account";
  render();
}

function renderAccount() {
  appEl.innerHTML = `
    <div class="page-wrap">
      <div class="page-header">
        <p class="page-eyebrow">Account</p>
        <h1 class="page-title">My account</h1>
      </div>
      <div class="account-section">
        <p class="account-label">Signed in as</p>
        <p class="account-value">${escapeHtml(currentUser.email)}</p>
      </div>
      <button class="signin-btn" id="accountSignOutBtn" style="width:auto; padding:11px 22px; margin-top:24px;">Sign out</button>
    </div>
  `;
  document.getElementById("accountSignOutBtn").addEventListener("click", () => {
    window.location.href = `${API}/auth/logout`;
  });
}

// ---------- home / dashboard ----------

function renderHome() {
  appEl.innerHTML = `
    <div class="page-wrap">
      <div class="page-header">
        <p class="page-eyebrow">Dashboard</p>
        <h1 class="page-title">Welcome to J256</h1>
        <p class="page-subtitle">Pick a section to get started.</p>
      </div>
      <div class="dashboard-grid">
        <div class="dashboard-card" id="goExploreCard">
          <div class="dashboard-card-icon">${ICONS.discussion}</div>
          <h3 class="dashboard-card-title">Explore</h3>
          <p class="dashboard-card-desc">Polls, discussions, and announcements from campus.</p>
        </div>
        <div class="dashboard-card" id="goMagazineCard">
          <div class="dashboard-card-icon">${ICONS.newspaper}</div>
          <h3 class="dashboard-card-title">E-Magazine <span class="nav-badge">Soon</span></h3>
          <p class="dashboard-card-desc">Under development — check back soon.</p>
        </div>
      </div>
    </div>
  `;
  document.getElementById("goExploreCard").addEventListener("click", () => goTo("explore"));
  document.getElementById("goMagazineCard").addEventListener("click", () => goTo("magazine"));
}

// ---------- explore ----------

let explorePosts = [];
let explorePage = 1;
let exploreTotalPages = 1;
let exploreDetailId = null;
let exploreComposeType = null; // 'poll' | 'discussion' | 'announcement'
let exploreComposeFiles = [];
let articleDetailId = null;

function openArticleDetail(id) {
  articleDetailId = id;
  currentView = "article-detail";
  setActiveNav("magazine");
  render();
}

function goToExploreFeed() {
  currentView = "explore";
  setActiveNav("explore");
  render();
}

function openExploreDetail(id) {
  exploreDetailId = id;
  currentView = "explore-detail";
  setActiveNav("explore");
  render();
}

function openExploreCompose(type) {
  if (!requireLogin()) return;
  exploreComposeType = type;
  exploreComposeFiles = [];
  currentView = "explore-compose";
  setActiveNav("explore");
  render();
}

async function renderExplore(page) {
  if (page) explorePage = page;
  appEl.innerHTML = `<div class="page-wrap"><p class="empty-state">Loading Explore…</p></div>`;
  try {
    const data = await fetchJSON(`${API}/explore?page=${explorePage}`);
    explorePosts = data.posts;
    explorePage = data.page;
    exploreTotalPages = data.total_pages;
    appEl.innerHTML = `
      <div class="page-wrap">
        <div class="explore-header-row">
          <div class="page-header" style="margin-bottom:0;">
            <p class="page-eyebrow">Explore</p>
            <h1 class="page-title">What's happening</h1>
            <p class="page-subtitle" style="margin-bottom:0;">Polls, discussions, and announcements from campus.</p>
          </div>
          <div class="post-type-menu-wrap">
            <button class="new-article-cta" id="explorePostBtn" aria-haspopup="true">${ICONS.plus} Post</button>
            <div class="post-type-menu" id="postTypeMenu">
              <button type="button" data-type="poll">${ICONS.poll} Poll</button>
              <button type="button" data-type="discussion">${ICONS.discussion} Discussion</button>
              <button type="button" data-type="announcement">${ICONS.announcement} Announcement</button>
            </div>
          </div>
        </div>
        <div class="explore-feed" id="exploreFeed">
          ${explorePosts.length === 0
            ? `<div class="empty-state">Nothing here yet. Be the first to post.</div>`
            : explorePosts.map(explorePostCard).join("")}
        </div>
        ${explorePager()}
      </div>
    `;
    wireExploreFeed();
  } catch (e) {
    appEl.innerHTML = `<div class="page-wrap"><p class="empty-state">Couldn't load Explore.<br>${escapeHtml(e.message)}</p></div>`;
  }
}

// Old-forum-style pager: numbered page links + Prev/Next, shown at the
// bottom of the feed once you've scrolled past the last post on the
// page — no infinite scroll, no auto-loading more content.
function explorePager() {
  if (exploreTotalPages <= 1) return "";
  const pages = [];
  for (let i = 1; i <= exploreTotalPages; i++) {
    pages.push(`
      <button type="button" class="pager-page ${i === explorePage ? "pager-page-active" : ""}"
        data-page="${i}" ${i === explorePage ? "disabled" : ""}>${i}</button>
    `);
  }
  return `
    <div class="explore-pager">
      <button type="button" class="pager-nav" data-page="${explorePage - 1}" ${explorePage <= 1 ? "disabled" : ""}>&laquo; Prev</button>
      <div class="pager-pages">${pages.join("")}</div>
      <button type="button" class="pager-nav" data-page="${explorePage + 1}" ${explorePage >= exploreTotalPages ? "disabled" : ""}>Next &raquo;</button>
    </div>
  `;
}

function wireExploreFeed() {
  const postBtn = document.getElementById("explorePostBtn");
  const menu = document.getElementById("postTypeMenu");
  const wrap = postBtn ? postBtn.closest(".post-type-menu-wrap") : null;
  if (postBtn && menu && wrap) {
    // Desktop: CSS handles open/close on hover. This click handler is a
    // fallback for touch devices (no hover) and keyboard use.
    postBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      wrap.classList.toggle("menu-open");
    });
    document.addEventListener("click", () => wrap.classList.remove("menu-open"));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") wrap.classList.remove("menu-open");
    });
    menu.querySelectorAll("button[data-type]").forEach(btn => {
      btn.addEventListener("click", () => {
        wrap.classList.remove("menu-open");
        openExploreCompose(btn.dataset.type);
      });
    });
  }

  document.querySelectorAll(".poll-option").forEach(el => {
    el.addEventListener("click", () => voteOnPoll(el.dataset.postId, el.dataset.optionId));
  });
  document.querySelectorAll(".post-card-clickable").forEach(card => {
    card.addEventListener("click", () => openExploreDetail(card.dataset.id));
  });
  document.querySelectorAll(".pager-page, .pager-nav").forEach(btn => {
    btn.addEventListener("click", () => {
      const n = parseInt(btn.dataset.page, 10);
      if (!n || n < 1) return;
      renderExplore(n);
      appEl.scrollIntoView({ behavior: "instant", block: "start" });
    });
  });
  wireReportButtons();
  wireReactionButtons();
}

function postTypeBadge(type) {
  const map = { poll: "Poll", discussion: "Discussion", announcement: "Announcement", article: "Article" };
  return `<span class="post-type-badge post-type-badge-${type}">${map[type]}</span>`;
}

function postCardMeta(p) {
  const showOp = p.type === "discussion" && p.is_op;
  return `${escapeHtml(p.author)}${p.is_anonymous ? " (anon)" : ""}${opBadgeHtml(showOp)} · ${timeAgo(p.created_at)}`;
}

function opBadgeHtml(isOp) {
  return isOp ? ` <span class="op-badge">OP</span>` : "";
}

function attachmentsRow(atts) {
  if (!atts || atts.length === 0) return "";
  return `<div class="post-card-attachments">${atts.map(a => {
    if (a.kind === "video") return `<video src="${API}${a.url}" controls></video>`;
    if (a.kind === "audio") return `<audio src="${API}${a.url}" controls></audio>`;
    if (a.kind === "file") return `<div class="doc-attachment-file">${ICONS.file} <a href="${API}${a.url}" target="_blank">${escapeHtml(a.original_name)}</a></div>`;
    return `<img src="${API}${a.url}" alt="">`;
  }).join("")}</div>`;
}

function explorePostCard(p) {
  if (p.type === "poll") return pollCard(p);
  if (p.type === "discussion") return discussionCard(p);
  return announcementCard(p);
}

function pollCard(p) {
  const total = p.total_votes;
  const options = p.options.map(o => {
    const pct = total > 0 ? Math.round((o.vote_count / total) * 100) : 0;
    return `
      <div class="poll-option ${o.is_mine ? "poll-option-mine" : ""}" data-post-id="${p.id}" data-option-id="${o.id}">
        <div class="poll-option-fill" style="width:${pct}%"></div>
        <span class="poll-option-label">${escapeHtml(o.text)}</span>
        <span class="poll-option-pct">${total > 0 ? pct + "%" : ""}</span>
      </div>
    `;
  }).join("");
  return `
    <div class="post-card" data-type="poll" data-id="${p.id}">
      <div class="post-card-meta">${postTypeBadge("poll")} ${postCardMeta(p)}</div>
      <h3 class="post-card-title">${escapeHtml(p.title)}</h3>
      <div class="poll-options">${options}</div>
      <div class="poll-total-votes">${total} vote${total === 1 ? "" : "s"}</div>
      <div class="post-card-footer">${reactionButtonsHtml("explore", p)}${reportButtonHtml("explore", p.id)}</div>
    </div>
  `;
}

function discussionCard(p) {
  return `
    <div class="post-card post-card-clickable" data-type="discussion" data-id="${p.id}">
      <div class="post-card-meta">${postTypeBadge("discussion")} ${postCardMeta(p)}</div>
      <h3 class="post-card-title">${escapeHtml(p.title)}</h3>
      <p class="post-card-body">${renderFormattedBody(p.body)}</p>
      ${attachmentsRow(p.attachments)}
      <div class="post-card-actions">${ICONS.reply} ${p.reply_count} repl${p.reply_count === 1 ? "y" : "ies"}</div>
      <div class="post-card-footer">${reactionButtonsHtml("explore", p)}${reportButtonHtml("explore", p.id)}</div>
    </div>
  `;
}

function announcementCard(p) {
  return `
    <div class="post-card" data-type="announcement" data-id="${p.id}">
      <div class="post-card-meta">${postTypeBadge("announcement")} ${postCardMeta(p)}</div>
      <h3 class="post-card-title">${escapeHtml(p.title)}</h3>
      <p class="post-card-body">${renderFormattedBody(p.body)}</p>
      ${attachmentsRow(p.attachments)}
      <div class="post-card-footer">${reactionButtonsHtml("explore", p)}${reportButtonHtml("explore", p.id)}</div>
    </div>
  `;
}

// E-Magazine article, shown in the feed exactly like an Explore post —
// full text, photos/videos inline — rather than only being reachable
// through the compiled PDF. Clicking it opens the same article detail
// page the "Download the PDF" flow always had, just now actually linked to.
function articleCard(a) {
  return `
    <div class="post-card post-card-clickable" data-type="article" data-id="${a.id}">
      <div class="post-card-meta">${postTypeBadge("article")} ${escapeHtml(a.author)}${a.is_anonymous ? " (anon)" : ""} · ${timeAgo(a.published_at)}</div>
      <h3 class="post-card-title">${escapeHtml(a.title)}</h3>
      <p class="post-card-body">${renderFormattedBody(a.body)}</p>
      ${attachmentsRow(a.attachments)}
      <div class="post-card-footer">${reactionButtonsHtml("article", a)}${reportButtonHtml("article", a.id)}</div>
    </div>
  `;
}

async function voteOnPoll(postId, optionId) {
  if (!requireLogin()) return;
  try {
    const result = await fetchJSON(`${API}/explore/${postId}/vote`, {
      method: "POST",
      body: new URLSearchParams({ option_id: optionId }),
    });
    const idx = explorePosts.findIndex(p => String(p.id) === String(postId));
    if (idx === -1) return;
    explorePosts[idx] = { ...explorePosts[idx], ...result };
    const card = document.querySelector(`.post-card[data-id="${postId}"][data-type="poll"]`);
    if (card) {
      card.outerHTML = pollCard(explorePosts[idx]);
      const newCard = document.querySelector(`.post-card[data-id="${postId}"][data-type="poll"]`);
      newCard.querySelectorAll(".poll-option").forEach(el => {
        el.addEventListener("click", () => voteOnPoll(el.dataset.postId, el.dataset.optionId));
      });
    }
  } catch (e) {
    alert(e.message);
  }
}

// ---------- explore: discussion detail + replies ----------

async function renderExploreDetail() {
  appEl.innerHTML = `<div class="page-wrap"><p class="empty-state">Loading…</p></div>`;
  try {
    const p = await fetchJSON(`${API}/explore/${exploreDetailId}`);
    appEl.innerHTML = `
      <div class="page-wrap">
        <button class="back-link" id="backToExplore">← Back to Explore</button>
        <div class="post-card-meta">${postTypeBadge("discussion")} ${postCardMeta(p)}</div>
        <h1 class="article-detail-title" style="font-size:28px;">${escapeHtml(p.title)}</h1>
        <div class="article-detail-body" style="font-size:16px;">${renderFormattedBody(p.body)}</div>
        ${attachmentsRow(p.attachments)}
        <div class="post-card-footer">${reactionButtonsHtml("explore", p)}<div class="post-card-actions-right">${reportButtonHtml("explore", p.id)}${deleteButtonHtml(p)}</div></div>
          <h3 class="reply-heading">${p.replies.length} repl${p.replies.length === 1 ? "y" : "ies"}</h3>
          <div class="reply-list" id="replyList">
            ${p.replies.length === 0
              ? `<p class="empty-state" style="padding:20px 0;">No replies yet.</p>`
              : p.replies.map(r => replyItem(r, 0)).join("")}
          </div>

          <div class="reply-composer">
            ${buildFormatToolbar("reply")}
            <textarea class="reply-input" id="replyInput" placeholder="Write a reply… **bold**, *italic*, $x^2$" rows="2"></textarea>
            <div class="format-live-preview format-live-preview-compact" id="replyLivePreview"></div>
            <input type="file" id="replyImageInput" accept="image/*" style="display:none">
            <input type="file" id="replyVideoInput" accept="video/*" style="display:none">
            <input type="file" id="replyAudioInput" accept="audio/*" style="display:none">
            <input type="file" id="replyFileInput" style="display:none">
            <div class="reply-composer-row">
              <div class="reply-attach-buttons">
                <button type="button" class="toolbar-btn toolbar-btn-labeled" id="replyAttachImageBtn" title="Add photo">${ICONS.image}<span>Photo</span></button>
                <button type="button" class="toolbar-btn toolbar-btn-labeled" id="replyAttachVideoBtn" title="Add video">${ICONS.video}<span>Video</span></button>
                <button type="button" class="toolbar-btn toolbar-btn-labeled" id="replyAttachAudioBtn" title="Add audio">${ICONS.audio}<span>Audio</span></button>
                <button type="button" class="toolbar-btn toolbar-btn-labeled" id="replyAttachFileBtn" title="Add file">${ICONS.file}<span>File</span></button>
              </div>
              <div class="anon-toggle">
                <label class="switch">
                  <input type="checkbox" id="replyAnonCheckbox">
                  <span class="switch-track"></span>
                </label>
                <span>Anonymous</span>
              </div>
              <button class="submit-btn" id="sendReplyBtn">Reply</button>
            </div>
            <div class="reply-preview" id="replyPreview"></div>
          </div>
        </div>
      </div>
    `;
    document.getElementById("backToExplore").addEventListener("click", goToExploreFeed);
    wireReplyComposer(p);
    wireReportButtons();
    wireDeleteButtons();
    wireReactionButtons();
  } catch (e) {
    appEl.innerHTML = `<div class="page-wrap"><p class="empty-state">Couldn't load this post.<br>${escapeHtml(e.message)}</p></div>`;
  }
}

function replyItem(r, depth) {
  depth = depth || 0;
  const children = (r.children || []).map(c => replyItem(c, depth + 1)).join("");
  return `
    <div class="reply-item" data-reply-id="${r.id}" style="${depth > 0 ? `margin-left:${Math.min(depth, 4) * 22}px;` : ""}">
      <div class="post-card-meta">${escapeHtml(r.author)}${r.is_anonymous ? " (anon)" : ""}${opBadgeHtml(r.is_op)} · ${timeAgo(r.created_at)}</div>
      <p class="reply-body">${renderFormattedBody(r.body)}</p>
      ${attachmentsRow(r.attachments)}
      <div class="post-card-footer">
        ${reactionButtonsHtml("explore_reply", r)}
        <button class="reply-to-reply-btn" data-reply-id="${r.id}" data-reply-author="${escapeHtml(r.author)}">Reply</button>
      </div>
    </div>
    ${children}
  `;
}

function wireReplyComposer(post) {
  let stagedFile = null;
  let replyingToId = null;
  const imageInput = document.getElementById("replyImageInput");
  const videoInput = document.getElementById("replyVideoInput");
  const audioInput = document.getElementById("replyAudioInput");
  const fileInput = document.getElementById("replyFileInput");
  const replyInputEl = document.getElementById("replyInput");
  wireFormatToolbar("reply", replyInputEl);
  replyInputEl.addEventListener("input", (e) => updateLivePreview("replyLivePreview", e.target.value));

  function setReplyingTo(replyId, authorName) {
    replyingToId = replyId;
    let indicator = document.getElementById("replyingToIndicator");
    if (!indicator) {
      indicator = document.createElement("div");
      indicator.id = "replyingToIndicator";
      indicator.className = "replying-to-indicator";
      replyInputEl.parentElement.insertBefore(indicator, replyInputEl);
    }
    if (replyId) {
      indicator.innerHTML = `Replying to ${escapeHtml(authorName)} <button type="button" id="cancelReplyTo">${ICONS.x}</button>`;
      indicator.hidden = false;
      document.getElementById("cancelReplyTo").addEventListener("click", () => setReplyingTo(null, null));
      replyInputEl.focus();
    } else {
      indicator.hidden = true;
    }
  }

  // Delegated so it keeps working after renderExploreDetail() re-renders
  // the reply list (e.g. right after posting a reply).
  document.addEventListener("click", function replyToReplyHandler(e) {
    if (!document.body.contains(document.getElementById("sendReplyBtn"))) {
      document.removeEventListener("click", replyToReplyHandler);
      return;
    }
    const btn = e.target.closest(".reply-to-reply-btn");
    if (!btn) return;
    if (!requireLogin()) return;
    setReplyingTo(btn.dataset.replyId, btn.dataset.replyAuthor);
  });

  document.getElementById("replyAttachImageBtn").addEventListener("click", () => {
    if (!requireLogin()) return;
    imageInput.click();
  });
  document.getElementById("replyAttachVideoBtn").addEventListener("click", () => {
    if (!requireLogin()) return;
    videoInput.click();
  });
  document.getElementById("replyAttachAudioBtn").addEventListener("click", () => {
    if (!requireLogin()) return;
    audioInput.click();
  });
  document.getElementById("replyAttachFileBtn").addEventListener("click", () => {
    if (!requireLogin()) return;
    fileInput.click();
  });

  function stageFile(input) {
    stagedFile = input.files[0] || null;
    const preview = document.getElementById("replyPreview");
    if (!stagedFile) {
      preview.innerHTML = "";
      return;
    }
    preview.innerHTML = `
      <div class="reply-preview-chip">
        ${escapeHtml(stagedFile.name)}
        <button type="button" id="clearReplyFile">${ICONS.x}</button>
      </div>
    `;
    document.getElementById("clearReplyFile").addEventListener("click", () => {
      stagedFile = null;
      imageInput.value = "";
      videoInput.value = "";
      audioInput.value = "";
      fileInput.value = "";
      preview.innerHTML = "";
    });
  }

  imageInput.addEventListener("change", () => stageFile(imageInput));
  videoInput.addEventListener("change", () => stageFile(videoInput));
  audioInput.addEventListener("change", () => stageFile(audioInput));
  fileInput.addEventListener("change", () => stageFile(fileInput));

  document.getElementById("sendReplyBtn").addEventListener("click", async () => {
    if (!requireLogin()) return;
    const body = document.getElementById("replyInput").value.trim();
    if (!body) return;
    const btn = document.getElementById("sendReplyBtn");
    btn.disabled = true;
    try {
      const formData = new FormData();
      formData.set("body", body);
      formData.set("is_anonymous", document.getElementById("replyAnonCheckbox").checked ? "true" : "false");
      if (replyingToId) formData.set("parent_reply_id", replyingToId);
      if (stagedFile) formData.set("file", stagedFile);
      await fetchJSON(`${API}/explore/${post.id}/replies`, { method: "POST", body: formData });
      renderExploreDetail();
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });
}

// ---------- explore: compose (poll / discussion / announcement) ----------

function pollOptionInputRow() {
  return `
    <div class="option-row">
      <input type="text" class="option-input" placeholder="Option" maxlength="80">
      <button type="button" class="option-remove" title="Remove">${ICONS.x}</button>
    </div>
  `;
}

function updateOptionRemoveButtons() {
  const container = document.getElementById("pollOptionInputs");
  const disable = container.children.length <= 2;
  container.querySelectorAll(".option-remove").forEach(btn => { btn.disabled = disable; });
}

function wireOptionRemove(btn) {
  btn.addEventListener("click", () => {
    const container = document.getElementById("pollOptionInputs");
    if (container.children.length <= 2) return;
    btn.closest(".option-row").remove();
    updateOptionRemoveButtons();
  });
}

function wirePollOptionInputs() {
  document.querySelectorAll(".option-remove").forEach(wireOptionRemove);
  updateOptionRemoveButtons();
}

function addPollOptionInput() {
  const container = document.getElementById("pollOptionInputs");
  container.insertAdjacentHTML("beforeend", pollOptionInputRow());
  wireOptionRemove(container.lastElementChild.querySelector(".option-remove"));
  updateOptionRemoveButtons();
}

function stageComposeFiles(fileList) {
  exploreComposeFiles = exploreComposeFiles.concat(Array.from(fileList));
  renderComposeAttachmentsPreview();
}

function renderComposeAttachmentsPreview() {
  const container = document.getElementById("composeAttachmentsPreview");
  if (!container) return;
  container.innerHTML = exploreComposeFiles.map((f, i) => {
    const url = URL.createObjectURL(f);
    const isVideo = f.type.startsWith("video/");
    const isAudio = f.type.startsWith("audio/");
    const isImage = f.type.startsWith("image/");
    const inner = isVideo
      ? `<video src="${url}" controls></video>`
      : isAudio
      ? `<audio src="${url}" controls></audio>`
      : isImage
      ? `<img src="${url}" alt="">`
      : `<div class="doc-attachment-file">${ICONS.file} ${escapeHtml(f.name)}</div>`;
    return `
      <div class="doc-attachment" data-idx="${i}">
        ${inner}
        <button class="doc-attachment-remove" data-idx="${i}" title="Remove">${ICONS.x}</button>
      </div>
    `;
  }).join("");
  container.querySelectorAll(".doc-attachment-remove").forEach(btn => {
    btn.addEventListener("click", () => {
      exploreComposeFiles.splice(Number(btn.dataset.idx), 1);
      renderComposeAttachmentsPreview();
    });
  });
}

function renderExploreCompose() {
  const type = exploreComposeType;
  const titleMap = { poll: "New Poll", discussion: "New Discussion", announcement: "New Announcement" };

  let bodyHtml;
  if (type === "poll") {
    bodyHtml = `
      <textarea class="doc-title-input" id="pollQuestion" rows="1" placeholder="Ask a question" maxlength="200"></textarea>
      <div class="poll-option-inputs" id="pollOptionInputs">
        ${pollOptionInputRow()}${pollOptionInputRow()}
      </div>
      <button type="button" class="add-option-btn" id="addOptionBtn">${ICONS.plus} Add option</button>
    `;
  } else {
    bodyHtml = `
      <textarea class="doc-title-input" id="titleInput" rows="1" placeholder="Title" maxlength="140"></textarea>
      ${buildFormatToolbar("explore")}
      <textarea class="doc-body-input" id="bodyInput" placeholder="${type === "announcement" ? "What's the announcement?" : "What's on your mind?"} Use **bold**, *italic*, \`code\`, and $x^2$ for LaTeX."></textarea>
      <div class="format-live-preview" id="exploreLivePreview"></div>
      <div class="doc-attachments" id="composeAttachmentsPreview"></div>
    `;
  }

  appEl.innerHTML = `
    <div class="compose-page">
      <div class="compose-topbar">
        <button class="compose-cancel" id="composeCancel">${ICONS.x} Cancel</button>
        <div class="compose-toolbar">
          ${type !== "poll" ? `
            <button type="button" class="toolbar-btn toolbar-btn-labeled" id="attachImageBtn" title="Add photo">${ICONS.image}<span>Photo</span></button>
            <button type="button" class="toolbar-btn toolbar-btn-labeled" id="attachVideoBtn" title="Add video">${ICONS.video}<span>Video</span></button>
            <button type="button" class="toolbar-btn toolbar-btn-labeled" id="attachAudioBtn" title="Add audio">${ICONS.audio}<span>Audio</span></button>
            <button type="button" class="toolbar-btn toolbar-btn-labeled" id="attachFileBtn" title="Add file">${ICONS.file}<span>File</span></button>
          ` : ""}
        </div>
        <span class="compose-status" id="composeStatus"></span>
      </div>

      ${type !== "poll" ? `
        <input type="file" id="mediaImageInput" accept="image/*" multiple style="display:none">
        <input type="file" id="mediaVideoInput" accept="video/*" multiple style="display:none">
        <input type="file" id="mediaAudioInput" accept="audio/*" multiple style="display:none">
        <input type="file" id="mediaFileInput" multiple style="display:none">
      ` : ""}

      <div class="doc-page-wrap">
        <div class="doc-page">
          <p class="page-eyebrow">${titleMap[type]}</p>
          ${bodyHtml}
          <div class="doc-anon-row">
            <div class="anon-toggle">
              <label class="switch">
                <input type="checkbox" id="anonCheckbox">
                <span class="switch-track"></span>
              </label>
              <span>Anonymous</span>
            </div>
          </div>
        </div>
      </div>

      <div class="compose-bottom-bar">
        <span></span>
        <span class="error-msg" id="composeError"></span>
        <button class="submit-btn" id="postBtn">Post</button>
      </div>
    </div>
  `;

  document.getElementById("composeCancel").addEventListener("click", cancelExploreCompose);

  if (type === "poll") {
    autoGrow(document.getElementById("pollQuestion"));
    document.getElementById("pollQuestion").addEventListener("input", (e) => autoGrow(e.target));
    wirePollOptionInputs();
    document.getElementById("addOptionBtn").addEventListener("click", addPollOptionInput);
    document.getElementById("postBtn").addEventListener("click", submitPoll);
  } else {
    autoGrow(document.getElementById("titleInput"));
    autoGrow(document.getElementById("bodyInput"));
    const bodyInputEl = document.getElementById("bodyInput");
    wireFormatToolbar("explore", bodyInputEl);
    document.getElementById("titleInput").addEventListener("input", (e) => autoGrow(e.target));
    document.getElementById("bodyInput").addEventListener("input", (e) => {
      autoGrow(e.target);
      updateLivePreview("exploreLivePreview", e.target.value);
    });
    document.getElementById("attachImageBtn").addEventListener("click", () => document.getElementById("mediaImageInput").click());
    document.getElementById("attachVideoBtn").addEventListener("click", () => document.getElementById("mediaVideoInput").click());
    document.getElementById("attachAudioBtn").addEventListener("click", () => document.getElementById("mediaAudioInput").click());
    document.getElementById("attachFileBtn").addEventListener("click", () => document.getElementById("mediaFileInput").click());
    document.getElementById("mediaImageInput").addEventListener("change", (e) => stageComposeFiles(e.target.files));
    document.getElementById("mediaVideoInput").addEventListener("change", (e) => stageComposeFiles(e.target.files));
    document.getElementById("mediaAudioInput").addEventListener("change", (e) => stageComposeFiles(e.target.files));
    document.getElementById("mediaFileInput").addEventListener("change", (e) => stageComposeFiles(e.target.files));
    renderComposeAttachmentsPreview();
    document.getElementById("postBtn").addEventListener("click", () => submitDiscussionOrAnnouncement(type));
  }
}

async function submitPoll() {
  const errEl = document.getElementById("composeError");
  const btn = document.getElementById("postBtn");
  errEl.textContent = "";
  const question = document.getElementById("pollQuestion").value.trim();
  const options = Array.from(document.querySelectorAll(".option-input"))
    .map(i => i.value.trim())
    .filter(Boolean);
  if (!question) { errEl.textContent = "Give the poll a question."; return; }
  if (options.length < 2) { errEl.textContent = "Add at least 2 options."; return; }
  btn.disabled = true;
  btn.textContent = "Posting…";
  try {
    const formData = new FormData();
    formData.set("question", question);
    options.forEach(o => formData.append("options", o));
    formData.set("is_anonymous", document.getElementById("anonCheckbox").checked ? "true" : "false");
    await fetchJSON(`${API}/explore/polls`, { method: "POST", body: formData });
    exploreComposeFiles = [];
    goToExploreFeed();
  } catch (e) {
    errEl.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Post";
  }
}

async function submitDiscussionOrAnnouncement(type) {
  const errEl = document.getElementById("composeError");
  const btn = document.getElementById("postBtn");
  errEl.textContent = "";
  const title = document.getElementById("titleInput").value.trim();
  const body = document.getElementById("bodyInput").value.trim();
  if (!title || !body) { errEl.textContent = "Give it a title and some content."; return; }
  btn.disabled = true;
  btn.textContent = "Posting…";
  try {
    const formData = new FormData();
    formData.set("title", title);
    formData.set("body", body);
    formData.set("is_anonymous", document.getElementById("anonCheckbox").checked ? "true" : "false");
    exploreComposeFiles.forEach(f => formData.append("files", f));
    const endpoint = type === "discussion" ? "discussions" : "announcements";
    await fetchJSON(`${API}/explore/${endpoint}`, { method: "POST", body: formData });
    exploreComposeFiles = [];
    goToExploreFeed();
  } catch (e) {
    errEl.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Post";
  }
}

function cancelExploreCompose() {
  const hasContent = exploreComposeFiles.length > 0
    || (document.getElementById("titleInput") && document.getElementById("titleInput").value.trim())
    || (document.getElementById("bodyInput") && document.getElementById("bodyInput").value.trim())
    || (document.getElementById("pollQuestion") && document.getElementById("pollQuestion").value.trim());
  if (hasContent && !confirm("Discard this post?")) return;
  exploreComposeFiles = [];
  goToExploreFeed();
}

// ---------- magazine ----------
// Temporarily closed to the public while this feature is under
// development. Deliberately short-circuits before any network call or
// compose/detail flow — nobody can reach an article, submit one, or
// trigger the PDF from here while this is in place, regardless of how
// they got to this view (nav click, the Home dashboard card, or a
// stale link/bookmark to ?view=magazine).
async function renderMagazine() {
  appEl.innerHTML = `
    <div class="page-wrap">
      <div class="page-header">
        <p class="page-eyebrow">E-Magazine</p>
        <h1 class="page-title">The Newspaper</h1>
      </div>
      <div class="empty-state" style="padding:48px 24px; text-align:center;">
        <p style="font-size:16px; font-weight:600; margin-bottom:6px;">This feature is currently under development.</p>
        <p style="color:var(--muted);">The E-Magazine is being rebuilt — check back soon.</p>
      </div>
    </div>
  `;
}

function wireMagazineFeed() {
  document.querySelectorAll("#magazineFeed .post-card-clickable").forEach(card => {
    card.addEventListener("click", () => openArticleDetail(card.dataset.id));
  });
  wireReportButtons();
  wireReactionButtons();
}

async function renderArticleDetail(id) {
  appEl.innerHTML = `<div class="page-wrap"><p class="empty-state">Loading…</p></div>`;
  try {
    const a = await fetchJSON(`${API}/posts/${id}`);
    const media = a.attachments.map(att => {
      if (att.kind === "image") return `<img src="${API}${att.url}" alt="">`;
      if (att.kind === "video") return `<video src="${API}${att.url}" controls></video>`;
      if (att.kind === "audio") return `<audio src="${API}${att.url}" controls></audio>`;
      return `<div class="doc-attachment-file">${ICONS.file} <a href="${API}${att.url}" target="_blank">${escapeHtml(att.original_name)}</a></div>`;
    }).join("");
    appEl.innerHTML = `
      <div class="page-wrap">
        <button class="back-link" id="backToMagazine">← Back to the newspaper</button>
        <div class="article-detail-meta">${escapeHtml(a.author)}${a.is_anonymous ? " (anon)" : ""} · ${timeAgo(a.published_at)}</div>
        <h1 class="article-detail-title">${escapeHtml(a.title)}</h1>
        ${media ? `<div class="article-detail-attachments">${media}</div>` : ""}
        <div class="article-detail-body">${renderFormattedBody(a.body)}</div>
        <div class="post-card-footer">${reactionButtonsHtml("article", a)}${reportButtonHtml("article", a.id)}</div>
      </div>
    `;
    document.getElementById("backToMagazine").addEventListener("click", () => goTo("magazine"));
    wireReportButtons();
    wireReactionButtons();
  } catch (e) {
    appEl.innerHTML = `<div class="page-wrap"><p class="empty-state">Couldn't load that article.<br>${escapeHtml(e.message)}</p></div>`;
  }
}

// ---------- saved drafts ----------

function draftRow(d) {
  const title = d.title.trim() || "Untitled";
  return `
    <div class="draft-row" data-id="${d.id}">
      <div class="draft-row-main">
        <h3 class="draft-title ${d.title.trim() ? "" : "untitled"}">${escapeHtml(title)}</h3>
        <p class="draft-snippet">${escapeHtml(plainPreview(d.body, 120)) || "No content yet."}</p>
      </div>
      <div style="display:flex; align-items:center; gap:16px; flex-shrink:0;">
        <span class="draft-meta">edited ${timeAgo(d.updated_at)}</span>
        <button class="draft-delete" data-id="${d.id}">delete</button>
      </div>
    </div>
  `;
}

async function renderDrafts() {
  // Saved Drafts holds E-Magazine article drafts specifically — closed
  // down alongside the rest of that feature (see renderMagazine above)
  // rather than left as a working side-door into the compose editor.
  appEl.innerHTML = `
    <div class="page-wrap">
      <div class="page-header">
        <p class="page-eyebrow">E-Magazine</p>
        <h1 class="page-title">Saved Drafts</h1>
      </div>
      <div class="empty-state" style="padding:48px 24px; text-align:center;">
        <p style="font-size:16px; font-weight:600; margin-bottom:6px;">This feature is currently under development.</p>
        <p style="color:var(--muted);">The E-Magazine is being rebuilt — check back soon.</p>
      </div>
    </div>
  `;
}

// ---------- compose (document-style editor, E-Magazine articles) ----------

let composeDraft = null; // full draft object currently open
let composeDirty = false;
let composeReturnView = "magazine";

async function startNewArticle() {
  if (!requireLogin()) return;
  try {
    const draft = await fetchJSON(`${API}/posts/drafts`, { method: "POST" });
    openCompose(draft.id);
  } catch (e) {
    alert(e.message);
  }
}

async function openCompose(id) {
  if (!requireLogin()) return;
  composeReturnView = currentView === "drafts" ? "drafts" : "magazine";
  try {
    composeDraft = await fetchJSON(`${API}/posts/${id}`);
    composeDirty = false;
    renderCompose();
  } catch (e) {
    alert(e.message);
  }
}

function renderCompose() {
  const d = composeDraft;
  appEl.innerHTML = `
    <div class="compose-page">
      <div class="compose-topbar">
        <button class="compose-cancel" id="composeCancel">${ICONS.x} Cancel</button>
        <div class="compose-toolbar">
          <button class="toolbar-btn toolbar-btn-labeled" id="attachImageBtn" title="Add image">${ICONS.image}<span>Photo</span></button>
          <button class="toolbar-btn toolbar-btn-labeled" id="attachVideoBtn" title="Add video">${ICONS.video}<span>Video</span></button>
          <button class="toolbar-btn toolbar-btn-labeled" id="attachAudioBtn" title="Add audio">${ICONS.audio}<span>Audio</span></button>
          <button class="toolbar-btn toolbar-btn-labeled" id="attachFileBtn" title="Add file">${ICONS.file}<span>File</span></button>
        </div>
        <span class="compose-status" id="composeStatus">${d.status === "draft" ? "Draft" : ""}</span>
      </div>

      <input type="file" id="imageInput" accept="image/*" style="display:none">
      <input type="file" id="videoInput" accept="video/*" style="display:none">
      <input type="file" id="audioInput" accept="audio/*" style="display:none">
      <input type="file" id="fileInput" style="display:none">

      <div class="doc-page-wrap">
        <div class="doc-page">
          <textarea class="doc-title-input" id="titleInput" rows="1" placeholder="Article title" maxlength="140">${escapeHtml(d.title)}</textarea>
          ${buildFormatToolbar("article")}
          <textarea class="doc-body-input" id="bodyInput" placeholder="Start writing... Use **bold**, *italic*, code with backticks, and $x^2$ for LaTeX.">${escapeHtml(d.body)}</textarea>
          <div class="format-live-preview" id="articleLivePreview"></div>

          <div class="doc-attachments" id="attachmentsList"></div>

          <div class="doc-anon-row">
            <div class="anon-toggle">
              <label class="switch">
                <input type="checkbox" id="anonCheckbox" ${d.is_anonymous ? "checked" : ""}>
                <span class="switch-track"></span>
              </label>
              <span>Anonymous</span>
            </div>
          </div>
        </div>
      </div>

      <div class="compose-bottom-bar">
        <button class="save-draft-btn" id="saveDraftBtn">Save Draft</button>
        <span class="error-msg" id="composeError"></span>
        <button class="submit-btn" id="submitBtn">Submit</button>
      </div>
    </div>
  `;

  renderAttachmentsList();
  autoGrow(document.getElementById("titleInput"));
  autoGrow(document.getElementById("bodyInput"));

  const bodyInputEl = document.getElementById("bodyInput");
  wireFormatToolbar("article", bodyInputEl);
  updateLivePreview("articleLivePreview", bodyInputEl.value);

  document.getElementById("composeCancel").addEventListener("click", cancelCompose);
  document.getElementById("titleInput").addEventListener("input", (e) => { composeDirty = true; autoGrow(e.target); markUnsaved(); });
  document.getElementById("bodyInput").addEventListener("input", (e) => {
    composeDirty = true;
    autoGrow(e.target);
    markUnsaved();
    updateLivePreview("articleLivePreview", e.target.value);
  });
  document.getElementById("anonCheckbox").addEventListener("change", (e) => {
    composeDirty = true;
    markUnsaved();
  });

  document.getElementById("attachImageBtn").addEventListener("click", () => document.getElementById("imageInput").click());
  document.getElementById("attachVideoBtn").addEventListener("click", () => document.getElementById("videoInput").click());
  document.getElementById("attachAudioBtn").addEventListener("click", () => document.getElementById("audioInput").click());
  document.getElementById("attachFileBtn").addEventListener("click", () => document.getElementById("fileInput").click());
  document.getElementById("imageInput").addEventListener("change", (e) => uploadAttachment(e.target.files[0], "image"));
  document.getElementById("videoInput").addEventListener("change", (e) => uploadAttachment(e.target.files[0], "video"));
  document.getElementById("audioInput").addEventListener("change", (e) => uploadAttachment(e.target.files[0], "audio"));
  document.getElementById("fileInput").addEventListener("change", (e) => uploadAttachment(e.target.files[0], "file"));

  document.getElementById("saveDraftBtn").addEventListener("click", () => saveDraft(true));
  document.getElementById("submitBtn").addEventListener("click", submitArticle);
}

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

// Renders a live "how this will actually look" preview under a compose
// textarea, using the same renderFormattedBody() function the real feed
// and article views use — so what you see while typing matches what
// everyone else will see.
function updateLivePreview(elementId, rawText) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (!rawText || !rawText.trim()) {
    el.innerHTML = "";
    el.classList.remove("has-content");
    return;
  }
  el.classList.add("has-content");
  el.innerHTML = renderFormattedBody(rawText);
}

function markUnsaved() {
  const status = document.getElementById("composeStatus");
  if (status) status.textContent = "Unsaved changes";
}

function renderAttachmentsList() {
  const container = document.getElementById("attachmentsList");
  if (!container) return;
  container.innerHTML = composeDraft.attachments.map(att => {
    let inner;
    if (att.kind === "image") inner = `<img src="${API}${att.url}" alt="">`;
    else if (att.kind === "video") inner = `<video src="${API}${att.url}" controls></video>`;
    else if (att.kind === "audio") inner = `<audio src="${API}${att.url}" controls></audio>`;
    else inner = `<div class="doc-attachment-file">${ICONS.file} ${escapeHtml(att.original_name)}</div>`;
    return `
      <div class="doc-attachment" data-id="${att.id}">
        ${inner}
        <button class="doc-attachment-remove" data-id="${att.id}" title="Remove">${ICONS.x}</button>
      </div>
    `;
  }).join("");
  container.querySelectorAll(".doc-attachment-remove").forEach(btn => {
    btn.addEventListener("click", () => removeAttachment(btn.dataset.id));
  });
}

async function uploadAttachment(file, kind) {
  if (!file) return;
  const status = document.getElementById("composeStatus");
  if (status) status.textContent = "Uploading…";
  try {
    const formData = new FormData();
    formData.set("kind", kind);
    formData.set("file", file);
    const att = await fetchJSON(`${API}/posts/${composeDraft.id}/attachments`, { method: "POST", body: formData });
    composeDraft.attachments.push(att);
    renderAttachmentsList();
    if (status) status.textContent = "Unsaved changes";
  } catch (e) {
    alert(e.message);
    if (status) status.textContent = "";
  }
}

async function removeAttachment(attachmentId) {
  try {
    await fetchJSON(`${API}/attachments/${attachmentId}`, { method: "DELETE" });
    composeDraft.attachments = composeDraft.attachments.filter(a => String(a.id) !== String(attachmentId));
    renderAttachmentsList();
  } catch (e) {
    alert(e.message);
  }
}

async function saveDraft(showStatus) {
  const title = document.getElementById("titleInput").value;
  const body = document.getElementById("bodyInput").value;
  const isAnon = document.getElementById("anonCheckbox").checked;
  const saveDraftBtn = document.getElementById("saveDraftBtn");
  const status = document.getElementById("composeStatus");
  saveDraftBtn.disabled = true;
  if (showStatus && status) status.textContent = "Saving…";
  try {
    const formData = new FormData();
    formData.set("title", title);
    formData.set("body", body);
    formData.set("is_anonymous", isAnon ? "true" : "false");
    const updated = await fetchJSON(`${API}/posts/${composeDraft.id}`, { method: "PUT", body: formData });
    composeDraft = updated;
    composeDirty = false;
    if (status) status.textContent = "Saved just now";
  } catch (e) {
    if (status) status.textContent = "";
    alert(e.message);
  } finally {
    saveDraftBtn.disabled = false;
  }
}

async function submitArticle() {
  const errEl = document.getElementById("composeError");
  const submitBtn = document.getElementById("submitBtn");
  errEl.textContent = "";
  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting…";
  try {
    // Save whatever's currently typed first, so submit always reflects the latest text.
    const title = document.getElementById("titleInput").value;
    const body = document.getElementById("bodyInput").value;
    const isAnon = document.getElementById("anonCheckbox").checked;
    const formData = new FormData();
    formData.set("title", title);
    formData.set("body", body);
    formData.set("is_anonymous", isAnon ? "true" : "false");
    await fetchJSON(`${API}/posts/${composeDraft.id}`, { method: "PUT", body: formData });
    await fetchJSON(`${API}/posts/${composeDraft.id}/submit`, { method: "POST" });
    composeDirty = false;
    goTo("magazine");
  } catch (e) {
    errEl.textContent = e.message;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Submit";
  }
}

function cancelCompose() {
  if (composeDirty && !confirm("Discard unsaved changes? Anything not saved as a draft will be lost.")) {
    return;
  }
  composeDraft = null;
  goTo(composeReturnView);
}


// ---------- reported posts (moderators only) ----------

async function renderReported() {
  if (!currentUser || !currentUser.is_moderator) {
    appEl.innerHTML = `<div class="page-wrap"><p class="empty-state">Moderators only.</p></div>`;
    return;
  }
  appEl.innerHTML = `
    <div class="page-wrap">
      <div class="page-header">
        <p class="page-eyebrow">Backstage</p>
        <h1 class="page-title">Reported Posts</h1>
      </div>
      <div id="reportedContent"><p class="empty-state">Loading…</p></div>
    </div>
  `;
  const container = document.getElementById("reportedContent");
  try {
    const reports = await fetchJSON(`${API}/moderation/reported`);
    if (reports.length === 0) {
      container.innerHTML = `<div class="empty-state">No reported posts.</div>`;
      return;
    }
    container.innerHTML = reports.map(reportedItem).join("");
    reports.forEach(r => wireReportedItem(r));
  } catch (e) {
    container.innerHTML = `<p class="empty-state">Couldn't load reports.<br>${escapeHtml(e.message)}</p>`;
  }
}

function reportedItem(r) {
  const canBanPoll = r.post_exists && r.post_is_anonymous;
  return `
    <div class="mod-item" data-report-id="${r.id}" data-post-kind="${r.post_kind}" data-post-id="${r.post_id}">
      <div class="mod-item-meta">${escapeHtml(r.post_type)} · reported by ${escapeHtml(r.reported_by_name)} · ${timeAgo(r.created_at)}</div>
      <h3 class="mod-item-title">${escapeHtml(r.post_title || "(untitled)")}</h3>
      <p class="mod-item-body">${escapeHtml(plainPreview(r.post_body || "", 300))}</p>
      <div class="mod-actions-row">
        <button class="mod-btn mod-btn-dismiss" data-action="cancel">Cancel report</button>
        <button class="mod-btn mod-btn-remove" data-action="warn">Warn</button>
        ${canBanPoll ? `<button class="mod-btn mod-btn-ban" data-action="ban-poll">Start Ban Poll</button>` : ""}
      </div>
      <div class="mod-warn-box" id="warnBox-${r.id}" hidden>
        <textarea class="mod-warn-reason" id="warnReason-${r.id}" placeholder="Reason for the warning — this gets emailed to the author"></textarea>
        <div class="mod-warn-actions">
          <button class="mod-btn mod-btn-dismiss" data-action="warn-cancel">Cancel</button>
          <button class="mod-btn mod-btn-remove" data-action="warn-send">Send warning</button>
        </div>
      </div>
      ${canBanPoll ? `
      <div class="mod-warn-box" id="banPollBox-${r.id}" hidden>
        <textarea class="mod-warn-reason" id="banPollReason-${r.id}" placeholder="Why should this post go to a ban poll? Cite the rule or reason — everyone will see this"></textarea>
        <div class="mod-warn-actions">
          <button class="mod-btn mod-btn-dismiss" data-action="ban-poll-cancel">Cancel</button>
          <button class="mod-btn mod-btn-ban" data-action="ban-poll-start">Start poll</button>
        </div>
      </div>` : ""}
    </div>
  `;
}

function wireReportedItem(r) {
  const item = document.querySelector(`.mod-item[data-report-id="${r.id}"]`);
  if (!item) return;
  const warnBox = document.getElementById(`warnBox-${r.id}`);

  item.querySelector('[data-action="cancel"]').addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      await fetchJSON(`${API}/moderation/reports/${r.id}/cancel`, { method: "POST" });
      renderReported();
    } catch (err) {
      alert(err.message);
      e.target.disabled = false;
    }
  });

  item.querySelector('[data-action="warn"]').addEventListener("click", () => {
    warnBox.hidden = false;
  });
  item.querySelector('[data-action="warn-cancel"]').addEventListener("click", () => {
    warnBox.hidden = true;
  });
  item.querySelector('[data-action="warn-send"]').addEventListener("click", async (e) => {
    const reason = document.getElementById(`warnReason-${r.id}`).value.trim();
    if (!reason) { alert("Write a reason before sending."); return; }
    e.target.disabled = true;
    try {
      await fetchJSON(`${API}/moderation/reports/${r.id}/warn`, {
        method: "POST",
        body: new URLSearchParams({ reason }),
      });
      renderReported();
    } catch (err) {
      alert(err.message);
      e.target.disabled = false;
    }
  });

  const banBtn = item.querySelector('[data-action="ban-poll"]');
  if (banBtn) {
    const banBox = document.getElementById(`banPollBox-${r.id}`);
    banBtn.addEventListener("click", () => { banBox.hidden = false; });
    item.querySelector('[data-action="ban-poll-cancel"]').addEventListener("click", () => {
      banBox.hidden = true;
    });
    item.querySelector('[data-action="ban-poll-start"]').addEventListener("click", async (e) => {
      const reason = document.getElementById(`banPollReason-${r.id}`).value.trim();
      if (!reason) { alert("Write a reason before starting the poll."); return; }
      if (!confirm("Start a public Ban Poll on this post? This cannot be undone.")) return;
      e.target.disabled = true;
      try {
        await fetchJSON(`${API}/moderation/ban-polls`, {
          method: "POST",
          body: new URLSearchParams({ post_kind: r.post_kind, post_id: r.post_id, reason }),
        });
        alert("Ban Poll started. Find it under Ban Polls.");
        renderReported();
      } catch (err) {
        alert(err.message);
        e.target.disabled = false;
      }
    });
  }
}

// ---------- ban polls (public: view + vote; moderators: start) ----------

async function renderBanPolls() {
  appEl.innerHTML = `
    <div class="page-wrap">
      <div class="page-header">
        <p class="page-eyebrow">Community</p>
        <h1 class="page-title">Ban Polls</h1>
        <p class="page-subtitle">Public votes on de-anonymizing the author of a reported anonymous post.</p>
      </div>
      <div id="banPollsContent"><p class="empty-state">Loading…</p></div>
    </div>
  `;
  const container = document.getElementById("banPollsContent");
  try {
    const polls = await fetchJSON(`${API}/moderation/ban-polls`);
    if (polls.length === 0) {
      container.innerHTML = `<div class="empty-state">No ban polls yet.</div>`;
      return;
    }
    container.innerHTML = polls.map(banPollItem).join("");
    polls.forEach(p => wireBanPollItem(p));
  } catch (e) {
    container.innerHTML = `<p class="empty-state">Couldn't load ban polls.<br>${escapeHtml(e.message)}</p>`;
  }
}

function banPollItem(p) {
  const total = p.yes_votes + p.no_votes;
  const yesPct = total > 0 ? Math.round((p.yes_votes / total) * 100) : 0;
  const turnoutPct = p.total_users > 0 ? Math.round((total / p.total_users) * 100) : 0;

  let resultLine = "";
  if (p.status === "resolved") {
    resultLine = `<div class="ban-poll-announcement">The Ban Poll No. ${p.id} resulted in de-anonymization of ${escapeHtml(p.revealed_name)}.</div>`;
  }

  let voteRow = "";
  if (p.status === "open") {
    if (p.my_vote) {
      voteRow = `<p class="ban-poll-voted-note">You voted <strong>${p.my_vote}</strong>. You cannot change your vote once you vote.</p>`;
    } else {
      voteRow = `
        <p class="ban-poll-voted-note">You cannot change your vote once you vote.</p>
        <div class="ban-poll-vote-row">
          <button class="mod-btn mod-btn-approve" data-action="vote-yes">Yes</button>
          <button class="mod-btn mod-btn-dismiss" data-action="vote-no">No</button>
        </div>
      `;
    }
  }

  let revealRow = "";
  if (p.status === "open" && currentUser && currentUser.is_moderator) {
    revealRow = `
      <div class="ban-poll-reveal-row">
        <button class="mod-btn mod-btn-ban" data-action="reveal" ${p.conditions_met ? "" : "disabled"}>Reveal identity</button>
        <span class="ban-poll-conditions-note">${p.conditions_met ? "Conditions met — reveal is available." : "Conditions not yet met."}</span>
      </div>
    `;
  }

  return `
    <div class="mod-item ban-poll-item" data-poll-id="${p.id}">
      <div class="mod-item-meta">Ban Poll No. ${p.id} · ${escapeHtml(p.post_type)} · ${p.status === "resolved" ? "resolved " + timeAgo(p.resolved_at) : "open · " + timeAgo(p.created_at)}</div>
      <h3 class="mod-item-title">${escapeHtml(p.post_title || "(untitled)")}</h3>
      <p class="mod-item-body">${escapeHtml(plainPreview(p.post_body || "", 300))}</p>
      <p class="ban-poll-reason"><strong>Moderator's reason:</strong> ${escapeHtml(p.reason)}</p>
      <div class="ban-poll-tally">
        <div class="ban-poll-bar"><div class="ban-poll-bar-fill" style="width:${yesPct}%"></div></div>
        <span>${p.yes_votes} Yes · ${p.no_votes} No · ${turnoutPct}% turnout</span>
      </div>
      ${voteRow}
      ${revealRow}
      ${resultLine}
    </div>
  `;
}

function wireBanPollItem(p) {
  const item = document.querySelector(`.ban-poll-item[data-poll-id="${p.id}"]`);
  if (!item) return;
  const yesBtn = item.querySelector('[data-action="vote-yes"]');
  const noBtn = item.querySelector('[data-action="vote-no"]');

  if (yesBtn && noBtn) {
    const castVote = async (vote) => {
      if (!requireLogin()) return;
      if (!confirm(`Vote "${vote}" on Ban Poll No. ${p.id}? You cannot change your vote once you vote.`)) return;
      yesBtn.disabled = true;
      noBtn.disabled = true;
      try {
        await fetchJSON(`${API}/moderation/ban-polls/${p.id}/vote`, {
          method: "POST",
          body: new URLSearchParams({ vote }),
        });
        renderBanPolls();
      } catch (err) {
        alert(err.message);
        yesBtn.disabled = false;
        noBtn.disabled = false;
      }
    };
    yesBtn.addEventListener("click", () => castVote("yes"));
    noBtn.addEventListener("click", () => castVote("no"));
  }

  const revealBtn = item.querySelector('[data-action="reveal"]');
  if (revealBtn) {
    revealBtn.addEventListener("click", async () => {
      if (!confirm(`Reveal the identity behind Ban Poll No. ${p.id}? This is permanent and public.`)) return;
      revealBtn.disabled = true;
      try {
        await fetchJSON(`${API}/moderation/ban-polls/${p.id}/reveal`, { method: "POST" });
        renderBanPolls();
      } catch (err) {
        alert(err.message);
        revealBtn.disabled = false;
      }
    });
  }
}

// ---------- reporting a post (any signed-in user) ----------

async function reportPost(postKind, postId, btn) {
  if (!requireLogin()) return;
  if (!confirm("Report this post to moderators?")) return;
  btn.disabled = true;
  try {
    await fetchJSON(`${API}/reports`, {
      method: "POST",
      body: new URLSearchParams({ post_kind: postKind, post_id: postId }),
    });
    btn.textContent = "Reported";
  } catch (err) {
    alert(err.message);
    btn.disabled = false;
  }
}

function reportButtonHtml(postKind, postId) {
  return `<button class="report-btn" data-report-kind="${postKind}" data-report-id="${postId}">Report</button>`;
}

function wireReportButtons(root) {
  (root || document).querySelectorAll(".report-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      reportPost(btn.dataset.reportKind, btn.dataset.reportId, btn);
    });
  });
}

// Delete is only ever shown when the backend says is_mine — which the
// backend deliberately sets to false for anonymous posts (see explore.py
// delete_explore_post), so an anonymous author never sees this button and
// the "anonymous posts are permanent" rule holds without extra checks here.
function deleteButtonHtml(post) {
  if (!post.is_mine) return "";
  return `<button class="delete-post-btn" data-delete-id="${post.id}">Delete</button>`;
}

function wireDeleteButtons(root) {
  (root || document).querySelectorAll(".delete-post-btn").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this post? This can't be undone.")) return;
      btn.disabled = true;
      try {
        await fetchJSON(`${API}/explore/${btn.dataset.deleteId}`, { method: "DELETE" });
        goToExploreFeed();
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    });
  });
}

// ---------- reactions (thumbs up / down) ----------
// postKind: "article" (newspaper) or "explore" (poll/discussion/announcement).
// Buttons are shown on every post regardless of who's viewing — including
// to the author of an anonymous post — since hiding them just for the
// author would itself leak "this is your post" the same way the delete
// button intentionally avoids doing. Self-reacting is rejected by the
// backend with a plain error instead.
function reactionButtonsHtml(postKind, post) {
  const mine = post.my_reaction;
  return `
    <div class="reaction-buttons" data-reaction-kind="${postKind}" data-reaction-id="${post.id}">
      <button type="button" class="reaction-btn reaction-btn-like ${mine === "like" ? "reaction-btn-active" : ""}" data-reaction="like" title="Like">
        ${ICONS.thumbsUp}<span>${post.like_count}</span>
      </button>
      <button type="button" class="reaction-btn reaction-btn-dislike ${mine === "dislike" ? "reaction-btn-active" : ""}" data-reaction="dislike" title="Dislike">
        ${ICONS.thumbsDown}<span>${post.dislike_count}</span>
      </button>
    </div>
  `;
}

async function handleReactionClick(btn) {
  if (!requireLogin()) return;
  const wrap = btn.closest(".reaction-buttons");
  const postKind = wrap.dataset.reactionKind;
  const postId = wrap.dataset.reactionId;
  const reaction = btn.dataset.reaction;
  try {
    const endpoint = postKind === "article"
      ? `${API}/posts/${postId}/react`
      : postKind === "explore_reply"
      ? `${API}/explore/replies/${postId}/react`
      : `${API}/explore/${postId}/react`;
    const result = await fetchJSON(endpoint, {
      method: "POST",
      body: new URLSearchParams({ reaction }),
    });
    // The same post's buttons can appear twice at once (e.g. feed card +
    // detail view isn't simultaneous here, but keep this robust) — update
    // every matching instance on the page.
    document.querySelectorAll(
      `.reaction-buttons[data-reaction-kind="${postKind}"][data-reaction-id="${postId}"]`
    ).forEach(w => {
      w.outerHTML = reactionButtonsHtml(postKind, {
        id: postId,
        like_count: result.like_count,
        dislike_count: result.dislike_count,
        my_reaction: result.my_reaction,
      });
    });
    wireReactionButtons();
  } catch (e) {
    alert(e.message);
  }
}

function wireReactionButtons(root) {
  (root || document).querySelectorAll(".reaction-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleReactionClick(btn);
    });
  });
}

// ---------- onboarding ----------
// First-run welcome flow: shown once per account, right after sign-in,
// before the person can use anything else. Blocks the whole site (no
// close button, no click-through on the backdrop) until they explicitly
// accept — enforced server-side via users.onboarded_at, not just a
// frontend flag, so it can't be skipped by clearing localStorage.

const ONBOARDING_FEATURES = [
  {
    icon: ICONS.incognito,
    title: "Anonymity, done right",
    desc: "Post anonymously with a fresh, random name generated just for that post. Not even you can prove after the fact which anonymous post was yours.",
  },
  {
    icon: ICONS.discussion,
    title: "Explore",
    desc: "Start polls, spark discussions, and share announcements with the rest of campus.",
  },
  {
    icon: ICONS.newspaper,
    title: "E-Magazine",
    desc: "Submit articles and read what's been published — compiled into a downloadable campus newspaper.",
  },
  {
    icon: ICONS.thumbsUp,
    title: "Reactions",
    desc: "A simple like or dislike on every post and reply. No leaderboards, no karma — just honest signal.",
  },
  {
    icon: ICONS.shield,
    title: "Community-moderated",
    desc: "Reports go to real moderators, and a transparent, community-voted process exists for serious cases of anonymity abuse.",
  },
  {
    icon: ICONS.incognito,
    title: "Private by default, even from yourself",
    desc: "Notifications only ever say \"someone replied\" — never who, what, or where. Even your own activity trail can't be used to connect you back to something you posted anonymously.",
  },
];

function onboardingWelcomeStep() {
  return `
    <div class="onboarding-step onboarding-step-welcome">
      <div class="onboarding-wordmark">J256</div>
      <h1 class="onboarding-title">Welcome to J256</h1>
      <p class="onboarding-lead">
        An independent, student-built platform for the IISER Thiruvananthapuram
        campus — polls, discussions, announcements, and an e-magazine, all in one place.
      </p>
      <p class="onboarding-sub">
        Here's what makes this space work, and what's asked of everyone who uses it.
        Takes a minute.
      </p>
    </div>
  `;
}

function onboardingFeaturesStep() {
  const features = ONBOARDING_FEATURES.map(f => `
    <div class="onboarding-feature">
      <div class="onboarding-feature-icon">${f.icon}</div>
      <div class="onboarding-feature-text">
        <h4>${escapeHtml(f.title)}</h4>
        <p>${escapeHtml(f.desc)}</p>
      </div>
    </div>
  `).join("");

  return `
    <div class="onboarding-step">
      <p class="onboarding-eyebrow">Step 2 of 4</p>
      <h2 class="onboarding-heading">Things you need to know</h2>
      <div class="onboarding-features">${features}</div>

      <h3 class="onboarding-subheading">The philosophy</h3>
      <div class="onboarding-philosophy">
        <p>If everyone were free to speak what makes them curious, what bothers them,
        what inspires them — to say their mind and their heart without always having to
        attach a name to it — a campus gets better at seeing itself. Speaking plainly
        here is a way of finding pieces of yourself in other people.</p>
        <p>That's what anonymity is for on J256: a tool for honesty, not a shield for
        cruelty. The platform is built to protect the first and push back against the
        second.</p>
      </div>
    </div>
  `;
}

const ONBOARDING_GUIDELINES = [
  "Be respectful. Disagreement is welcome; harassment, hate speech, and personal attacks are not.",
  "Don't try to unmask anyone. Attempting to identify an anonymous poster outside the official Ban Poll process is a serious violation.",
  "No doxxing. Never share someone else's personal information without their consent.",
  "Stay honest. Don't impersonate others or knowingly spread false information.",
  "Report, don't retaliate. If something crosses the line, report it — moderators are here to help.",
  "This complements, not replaces, IISER TVM's code of conduct. J256 operates alongside institutional policy, not instead of it.",
];

function onboardingGuidelinesStep() {
  const items = ONBOARDING_GUIDELINES.map((g, i) => `
    <li><span class="onboarding-guideline-num">${i + 1}</span><span>${escapeHtml(g)}</span></li>
  `).join("");

  return `
    <div class="onboarding-step">
      <p class="onboarding-eyebrow">Step 3 of 4</p>
      <h2 class="onboarding-heading">Community Guidelines</h2>
      <p class="onboarding-sub" style="margin-bottom:20px;">Please read through before continuing.</p>
      <ol class="onboarding-guidelines">${items}</ol>
    </div>
  `;
}

const ONBOARDING_GUIDELINES_2 = [
  "Harm to any real person, idea, belief, or an intention to harm said categories will be taken seriously.",
  "Anything illegal is strictly illegal.",
  "Distressing or taboo content is not encouraged, unless shared from an autobiographical perspective — even then, it is generally discouraged.",
  "Spread of hate against any party (a person, a group of people, an idea, anything) is prohibited.",
  "Attempts to influence others ideologically, personally, or by any other means are prohibited.",
];

function onboardingGuidelinesStep2() {
  const items = ONBOARDING_GUIDELINES_2.map((g, i) => `
    <li><span class="onboarding-guideline-num">${i + 1}</span><span>${escapeHtml(g)}</span></li>
  `).join("");

  return `
    <div class="onboarding-step">
      <p class="onboarding-eyebrow">Step 4 of 4</p>
      <h2 class="onboarding-heading">A few more guidelines</h2>
      <p class="onboarding-sub" style="margin-bottom:20px;">Please read through before continuing.</p>
      <ol class="onboarding-guidelines">${items}</ol>

      <label class="onboarding-agree-row">
        <input type="checkbox" id="onboardingAgreeCheckbox">
        <span>I choose to accept the rules.</span>
      </label>
    </div>
  `;
}

const ONBOARDING_STEPS = [onboardingWelcomeStep, onboardingFeaturesStep, onboardingGuidelinesStep, onboardingGuidelinesStep2];
let onboardingStepIndex = 0;

function maybeShowOnboarding() {
  if (!currentUser || currentUser.onboarded) {
    removeOnboardingOverlay();
    return;
  }
  onboardingStepIndex = 0;
  renderOnboardingOverlay();
}

function removeOnboardingOverlay() {
  const el = document.getElementById("onboardingOverlay");
  if (el) el.remove();
  document.body.classList.remove("onboarding-lock");
  const shell = document.querySelector(".shell");
  if (shell) shell.inert = false;
}

function renderOnboardingOverlay() {
  let overlay = document.getElementById("onboardingOverlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "onboardingOverlay";
    overlay.className = "onboarding-overlay";
    document.body.appendChild(overlay);
  }
  document.body.classList.add("onboarding-lock");
  // inert (not just visual covering) so Tab/screen-reader navigation
  // can't reach the sidebar or page content hiding underneath — this is
  // meant to actually gate the site, not just look like it does.
  const shell = document.querySelector(".shell");
  if (shell) shell.inert = true;

  const isFirst = onboardingStepIndex === 0;
  const isLast = onboardingStepIndex === ONBOARDING_STEPS.length - 1;

  overlay.innerHTML = `
    <div class="onboarding-card">
      <div class="onboarding-dots">
        ${ONBOARDING_STEPS.map((_, i) => `<span class="onboarding-dot ${i === onboardingStepIndex ? "onboarding-dot-active" : ""}"></span>`).join("")}
      </div>
      <div class="onboarding-body">${ONBOARDING_STEPS[onboardingStepIndex]()}</div>
      <div class="onboarding-footer">
        <button type="button" class="onboarding-btn onboarding-btn-ghost" id="onboardingPrevBtn" ${isFirst ? "disabled" : ""}>
          ${isFirst ? "" : "← Previous"}
        </button>
        <button type="button" class="onboarding-btn onboarding-btn-primary" id="onboardingNextBtn" ${isLast ? "disabled" : ""}>
          ${isLast ? "I choose to accept the rules" : "Next →"}
        </button>
      </div>
    </div>
  `;

  document.getElementById("onboardingPrevBtn").addEventListener("click", () => {
    if (onboardingStepIndex > 0) {
      onboardingStepIndex--;
      renderOnboardingOverlay();
    }
  });

  document.getElementById("onboardingNextBtn").addEventListener("click", async () => {
    if (!isLast) {
      onboardingStepIndex++;
      renderOnboardingOverlay();
      return;
    }
    await acceptOnboarding();
  });

  if (isLast) {
    const checkbox = document.getElementById("onboardingAgreeCheckbox");
    const nextBtn = document.getElementById("onboardingNextBtn");
    checkbox.addEventListener("change", () => {
      nextBtn.disabled = !checkbox.checked;
    });
  }
}

async function acceptOnboarding() {
  const nextBtn = document.getElementById("onboardingNextBtn");
  nextBtn.disabled = true;
  nextBtn.textContent = "Just a moment…";
  try {
    currentUser = await fetchJSON(`${API}/auth/onboarding/accept`, { method: "POST" });
    removeOnboardingOverlay();
  } catch (e) {
    alert(e.message);
    nextBtn.disabled = false;
    nextBtn.textContent = "I choose to accept the rules";
  }
}

// ---------- boot ----------

if (new URLSearchParams(window.location.search).get("view") === "account") {
  currentView = "account";
}
checkLoginError();
wireNotifBell();
loadCurrentUser();
setActiveNav(currentView);
render();
window.history.replaceState({}, "", window.location.pathname);