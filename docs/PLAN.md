# DTF Club Hub: Implementation Plan

**Goal:** a single website for the DTF Club fantasy football league that members add to their phone's home screen (a PWA, no App Store). It ties together 8 independently maintained tools, plus a few static pages. It largely replaces the Google Site (https://sites.google.com/view/thedtfclub). Slack stays the chat and notification channel.

**Audience for this doc:** the implementing session. Read all of it before starting. Do one phase at a time, and stop at every **🛑 USER** checkpoint.

---

## 0. Context and ground rules

### 0.1 The 8 tools today

All repos are public under `namkurd`. All are static GitHub Pages sites built from Python scripts and scheduled GitHub Actions, with no build step and no framework. All of them are served from the **same origin**, `https://namkurd.github.io/<Repo>/`.

| # | Tool (display name) | Repo | Page(s) served | Pages source | Data / jobs | Notes |
|---|---|---|---|---|---|---|
| 1 | **Rumble Central** (live Rumbles standings) | `SleeperLiveRumbles` | `/SleeperLiveRumbles/rumbles.html` (`index.html` redirects) | main / root | `update.yml` (nightly + Tue), `wp_record.yml` and `live_qb_capture.yml` (every 30 min on game days). Needs secret `YOUTUBE_API` | Has its own `manifest.webmanifest` (scope `./`) and a no-op `sw.js`. 650 KB single HTML file. Replay deep links: `rumbles.html?wp=<week>.<rid>.<oppRid>&season=<yyyy>`. Uses localStorage key `rumbles.embed*` (embed mode for the Google Site). Committed `__pycache__/` |
| 2 | **Lifetime Win/Loss** | `sleepersheet` | `/sleepersheet/` | main / root | `update.yml` Tue early morning | Also contains a **legacy copy** of `rumbles.html` and `build_rumbles.py` |
| 3 | **Trade Network** | `SleeperTradeNodes` | `/SleeperTradeNodes/` | main / root | `update.yml` hourly. Needs secret `PARSE_API_KEY` | Legacy `rumbles.html` copy. Shares `par.py` logic with FAB |
| 4 | **FAB Management** (waiver wire) | `FAB-Management` | `/FAB-Management/` (+ `lineup.html`) | main / root | `update.yml` hourly, commits only on change | `data.json` is **1.7 MB** |
| 5 | **Record Book** | `Recordbook` | `/Recordbook/` | main / root | `update.yml` Tue | `engine/load.py` reads **raw.githubusercontent.com `main`** files from `SleeperLiveRumbles` and `sleepersheet` (hard data dependency). 77 hardcoded absolute links to Rumble Central replays. Browser edit mode commits through the GitHub API using a PAT stored in localStorage key `rb-token`. Filters live in the URL |
| 6 | **Head-to-Head** (career matrix) | `Sleeper-Head-to-Head` | `/Sleeper-Head-to-Head/` | main / root | `update.yml` Tue | Legacy `rumbles.html` and `build_rumbles.py`. README says these pages are **iframe-embedded in the Google Site** |
| 7 | **Auction Archive** | `SleeperAuction` | `/SleeperAuction/` (from `site/`) | **GitHub Actions** artifact | `update.yml` every 6 h with a heartbeat commit | Page lives in `site/index.html`. Already uses `location.hash` routes. Dark-only theme. Committed xlsx backup and `__pycache__` |
| 8 | **Rulebook** | `Rulebook-` (trailing hyphen) | `/Rulebook-/` | main / root (assumed; verify) | **No workflow.** `python3 tools/build.py` is run by hand. Slack-sync procedure in `tools/SYNC_SUGGESTIONS.md` | Current rules were imported from the Google Site (`tools/current.txt`). Proposal history 2019–2026 is in `tools/rules.txt` |

Other repos seen in the account: `rumble-central` (private), `general-rumbles`, and `league-page` (an old 2022 fork). They are **out of scope** unless the user says otherwise.

Facts that matter:
- **Current league ID** `1389416556617801728` (2026) is hardcoded as a fallback in `FAB-Management/update_waivers.py`, `Sleeper-Head-to-Head/build_matrix.py` and `SleeperLiveRumbles/build_rumbles.py`. Most scripts walk `previous_league_id` back from there.
- **Themes are already similar.** Dark bg `#0f1115` and light bg `#f5f6f9` (Rumbles, Rulebook), accent `#f0914a` (Rumbles), IBM Plex Sans in Trade Network and FAB, and most tools support `prefers-color-scheme`. Auction is dark-only. H2H has no CSS tokens.
- **Slack:** workspace `dtf-club`, suggestions channel `#league-suggestions` (`CCG47441Z`).
- This session's network policy **blocks `sites.google.com` and `namkurd.github.io`**. Nothing about the live sites has been verified from inside the session.

### 0.2 Core architectural decision: the hub is the GitHub *user site*

Create a new repo named exactly **`namkurd.github.io`**. GitHub serves it at the **root**, `https://namkurd.github.io/`, while every tool keeps serving at `/<Repo>/` on the same origin.

This one choice solves most of the hard problems:

1. **Seamless "app" navigation.** The PWA manifest gets `scope: "/"`, so every tool page is inside the installed app's scope. Moving from the hub to `/Recordbook/` and back stays inside the standalone window. There are no iframes, and no Safari sheets popping up.
2. **One service worker** at `/sw.js` with scope `/` can give offline fallback for every tool.
3. **Shared localStorage.** The "Which manager are you?" choice made once in the hub is readable by every tool.
4. **No CORS.** The hub's Home screen can `fetch('/Recordbook/data/…')` directly.
5. **Tools stay independent.** Each repo still deploys itself. The hub never builds or copies tool code.

Do **not** merge the repos into a monorepo, and do **not** use iframes for tools.

The fallback, used only if the user refuses the user-site repo, is a project repo such as `/dtf/`. Its service worker could not cover the tools, and out-of-scope navigation gets worse on iOS.

### 0.3 Integration ladder (how "update individually, feed the whole" works)

Each tool sits at some level. Tools can be at different levels, and **updating a tool never requires a hub change** unless its URL changes.

| Level | What the tool does | What it gets |
|---|---|---|
| **L0 Listed** | Nothing. It has an entry in the hub's `tools.json` | Shows in nav and menus. External links such as the Sleeper app or a Google Sheet are allowed |
| **L1 Shelled** | Adds one line to its HTML: `<script src="/shell/nav.js" defer></script>` | Global nav bar, shared install manifest, theme color, analytics. If the script fails, the tool still works |
| **L2 Fed** | Its workflow also writes a small `summary.json` (§3.3) | Cards on the hub Home screen and the manager pages |
| **L3 Native** | Uses `/shell/tokens.css`, reads the `dtf.me` manager, and builds cross-links with `DTF.link()` | Looks and behaves like one app |

### 0.4 Rules for the implementing session

- **Branching:** develop on `claude/fantasy-football-unified-app-7d6kpi` in every repo. **Pages serves `main`**, so nothing is live until the user merges. Open one PR per repo per phase, but only when the user asks for PRs. Never push to `main`.
- **Hub repo:** ✅ `namkurd/namkurd.github.io` exists. Attach it with `add_repo` (`access: "push"`). This plan lives in it at `docs/PLAN.md`, next to the icons in `shell/icons/`.
- **No build step, no framework, no npm runtime dependencies.** Use vanilla HTML, CSS and JS, and web components where useful. This matches every existing tool. Only pinned, vendored files are allowed, and only if truly needed.
- **Don't break data contracts.** `Recordbook/engine/load.py` reads files from `SleeperLiveRumbles` and `sleepersheet` on `main`. Don't rename, move or reshape those files. Before touching any `*.json` another repo reads, grep all 8 repos for its filename.
- **Never delete a URL that has been shared.** Old Google Site embeds and Slack links point at the existing pages. Replace retired pages with redirect stubs (copy the `SleeperLiveRumbles/index.html` pattern: `meta refresh` + `location.replace` that keeps `search` and `hash`).
- **Add a `.nojekyll`** file to the hub and to any repo that lacks one. Jekyll ignores files that start with `_`, and it slows deploys.
- **Namespace everything shared.** localStorage keys get the `dtf.` prefix. Global JS goes under `window.DTF`. The nav bar CSS lives inside **Shadow DOM** so it can't clash with tool CSS.
- **Mobile first:** test at 390×844 (iPhone) and at 1280×800. Chromium and Playwright are preinstalled; see §7.
- Don't commit secrets. Keep commits small, with clear messages.

---

## 1. 🛑 Decisions needed from the user before Phase 1

Ask these in one `AskUserQuestion` call, recommendations first:

1. **Domain.** Keep `namkurd.github.io` (free, recommended to start), or buy a custom domain such as `dtfclub.com` (about $12/yr)? Changing the domain later changes the origin, which wipes home-screen installs, saved preferences and the Record Book token, so decide **before** announcing the site to the league. Every `*.github.io` project page automatically moves under a custom domain set on the user site.
2. ~~**Hub repo.**~~ ✅ Done: created by the user.
3. **Rename `Rulebook-` to `Rulebook`?** Recommended now, before launch. GitHub does **not** redirect Pages URLs after a rename. The hub registry absorbs the change.
4. **Branding.** ✅ Logo decided: the **Rumble Central split-flap orange "R"**. It is already rebuilt as a vector and committed (see §2.1). Brand colors from the logo: bg `#0f1115`, card `#1f2430`, orange `#ff8a3d`; use `#ff8a3d` as the hub accent. Still to confirm: the app name on the home screen (default "DTF Club", short name "DTF").
5. **Google Site inventory.** This session cannot reach `sites.google.com`. Ask the user to either allow it in the environment's network settings or paste the list of pages and what is on each. You need this for Phase 3.
6. **Navigation grouping.** Confirm the default in §2.2.
7. **Optional services:** a Slack incoming webhook (yes/no) and privacy-friendly analytics through GoatCounter (yes/no).

---

## 2. Phase 1: Hub shell, install and global nav (MVP)

**Outcome:** members can install "DTF Club" to their home screen, open it, and move between all 8 tools with a persistent nav bar, never leaving the app.

### 2.1 Hub repo layout (`namkurd.github.io`)

```
/index.html               Home (Phase 2 fills in the cards; Phase 1 = tool grid)
/manifest.webmanifest
/sw.js                    service worker, scope "/"
/.nojekyll
/404.html                 friendly not-found page with nav
/tools.json               the registry (single source of truth for tool URLs)
/league.json              current season config (Phase 2)
/managers.json            canonical manager list (Phase 2)
/shell/nav.js             <dtf-nav> web component + DTF helpers (keep under 12 KB)
/shell/tokens.css         optional shared design tokens (L3)
/shell/icons/             ✅ ALREADY COMMITTED: logo.svg (512 master), favicon.svg (transparent crop),
                          icon-192.png, icon-512.png, maskable-512.png, apple-touch-icon-180.png, favicon-32.png
/tools/icons/             mklogo.py + render.js regenerate the icons (see header comments). Don't hand-edit the PNGs
/pages/                   static pages (Phase 3)
/install/index.html       "How to add to your home screen" (iPhone + Android, with screenshots)
/README.md                how to add a tool or page, and the contracts in §3
```

### 2.2 Navigation model

On phones there is a **bottom tab bar** with 5 tabs. On desktop (≥ 900 px) the same items sit in a top bar.

| Tab | Contains |
|---|---|
| **Home** | Hub home (cards, this week, freshness) |
| **Live** | Rumble Central |
| **History** | Record Book · Head-to-Head · Lifetime Win/Loss |
| **Moves** | Trade Network · FAB Management · Auction Archive |
| **League** | Rulebook · static pages (dues, payouts, key dates, champions, members) · Slack link |

- Tapping a tab with one tool opens that tool. A tab with several tools opens a small **section sheet** (a slide-up list) that is rendered by `nav.js`, so it works on every tool page.
- The **current tool** is highlighted. `nav.js` figures this out by matching `location.pathname` against `tools.json` paths.
- A **back button** (‹) appears in the top-left mini header whenever `history.length > 1` and you are not on Home. **iOS standalone mode has no browser back button**, so this is required.
- A **refresh button** goes in the mini header, because there is no pull-to-refresh in iOS standalone. `nav.js` also fires a `dtf:refresh` event when the app comes back to the foreground after more than 10 minutes (`visibilitychange`). Tools may listen for it; if none does, the default is `location.reload()`.
- External links (Sleeper app, Slack, Google Sheets) open with `target="_blank"`.

### 2.3 `tools.json` (registry contract)

```json
{
  "schema": 1,
  "tools": [
    {
      "id": "rumbles",
      "name": "Rumble Central",
      "short": "Rumbles",
      "tab": "live",
      "path": "/SleeperLiveRumbles/rumbles.html",
      "repo": "namkurd/SleeperLiveRumbles",
      "icon": "bolt",
      "description": "Live Rumbles standings and matchups",
      "summary": "/SleeperLiveRumbles/summary.json",
      "links": {
        "replay": "/SleeperLiveRumbles/rumbles.html?season={season}&wp={week}.{rid}.{opp}"
      }
    }
  ],
  "pages": [
    { "id": "dues", "name": "Dues & Payouts", "tab": "league", "path": "/pages/dues.html" }
  ],
  "external": [
    { "id": "slack", "name": "Slack", "tab": "league", "url": "https://dtf-club.slack.com/" },
    { "id": "sleeper", "name": "Sleeper", "tab": "league", "url": "https://sleeper.com/leagues/1389416556617801728" }
  ]
}
```

Fill in all 8 tools from §0.1. `links` holds deep-link templates, filled in by `DTF.link(id, linkName, params)`. Add templates only for parameters a tool actually supports today: Rumbles `wp`/`season`, Record Book's URL filters (read its code for the parameter names), Auction's hash routes (read `site/index.html`), and sleepersheet's hash. **Renaming a repo then means editing one line here.**

### 2.4 `shell/nav.js` responsibilities

1. Define the custom element `<dtf-nav>` (Shadow DOM, self-contained CSS) and append it to `document.body` automatically. Tools only add the script tag.
2. Fetch `/tools.json`: `cache: "no-cache"`, memoized in `sessionStorage` for the session. Ship a tiny inline fallback list so the nav still renders if the fetch fails.
3. Inject into `<head>` whatever is missing: `<link rel="manifest" href="/manifest.webmanifest">`, `apple-touch-icon`, `theme-color`, `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style=black-translucent`, and `mobile-web-app-capable`. Note: **iOS reads the manifest and touch icon only from the page where "Add to Home Screen" was tapped.** That is why every tool page must carry them, via this injection.
4. **Layout safety.** Add `padding-bottom: calc(56px + env(safe-area-inset-bottom))` to `body` on mobile so the bar never covers tool content. Check `viewport-fit=cover`. Hide the nav when `?embed=1` is present or when Rumbles' existing embed mode is on (`rumbles.embed*` localStorage), so iframe embeds in the old Google Site stay clean.
5. Register `/sw.js` if it is not registered yet (`navigator.serviceWorker.register('/sw.js', {scope: '/'})`).
6. **One-time cleanup:** unregister any service worker whose scope is `/SleeperLiveRumbles/` (Rumble Central's no-op worker would otherwise shadow the root one for that path).
7. Expose `window.DTF = { tools, link(id, name, params), me(), setMe(id), onRefresh(fn) }`.
8. Analytics, only if the user approved GoatCounter: one async script, loaded here, which covers every tool at once.
9. Performance budget: under 12 KB unminified, no dependencies, `defer`, no layout shift. Reserve the bar height with CSS before the registry loads.

### 2.5 Manifest and service worker

`manifest.webmanifest`:
- `name` "DTF Club", `short_name` "DTF"
- `start_url` "/?source=pwa", `scope` "/", `display` "standalone"
- `background_color` and `theme_color` `#0f1115` (the logo background, so the iOS/Android splash screen blends in)
- icons: 192, 512, and a maskable 512, as **real PNG files** (not data URIs)
- `shortcuts` for Rumbles, Record Book and Rulebook (Android long-press)

`sw.js` strategy. Keep it simple and **never let users get stuck on stale data**:
- **Precache** only the shell: `/`, `/shell/nav.js`, `/shell/tokens.css`, icons, `/tools.json`, `/404.html`, and an `/offline.html`. Cache name `dtf-shell-v<N>`. Bump `N` on every shell change, delete old caches on `activate`, and call `skipWaiting()` + `clients.claim()`.
- **Same-origin HTML navigations:** network-first with a 4 s timeout. Fall back to the cached copy of that page, then `/offline.html`. Store successful responses in `dtf-pages`, capped at about 30 entries.
- **Same-origin `.json`:** network-first (`cache: "no-cache"` so ETags revalidate cheaply). Fall back to cache when offline. Cap at about 60 entries. **Exclude files over 1 MB** from caching (FAB `data.json`).
- **Cross-origin** (Sleeper API, fonts, YouTube, nflverse): do not intercept. Rumble Central's live scores must always hit the network.
- Never cache non-GET requests or `api.github.com` (Record Book edit mode).

### 2.6 Wire every tool to L1

In each of the 8 repos, add `<script src="/shell/nav.js" defer></script>` before `</body>` on every user-facing page:
- `SleeperLiveRumbles/rumbles.html`
- `sleepersheet/index.html`
- `SleeperTradeNodes/index.html`
- `FAB-Management/index.html` and `lineup.html`
- `Recordbook/index.html`
- `Sleeper-Head-to-Head/index.html`
- `SleeperAuction/site/index.html`
- `Rulebook-/index.html` **and** check `tools/build.py`, so the line survives into the regenerated `dist/` output. If `dist/` is not served, leave it alone.

Also:
- Remove `SleeperLiveRumbles/manifest.webmanifest` and `sw.js`, and their `<link>`/`register` lines. Leave `sw.js` as a self-unregistering stub for one season:
  `self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',()=>self.registration.unregister());`
- Check whether any tool has a fixed bottom bar or a `position:fixed` footer that collides with the nav. Rumble Central's EPA button sits "bottom of the page on phones". Fix it per tool with a `body.dtf-has-nav` class that `nav.js` sets.
- If a script that regenerates HTML (`build_*.py`) writes the page, the script tag must go into the **template inside the script**, or the next Action run removes it. Check every `build_*.py` and `update_*.py` for HTML writes.

### 2.7 Acceptance criteria (Phase 1)

- [ ] On a local mirror (§7), every tool page shows the nav. The active tab is correct. The back and refresh buttons work. No tool content is hidden behind the bar at 390×844.
- [ ] Lighthouse PWA/installability passes on `/` (or Chromium DevTools shows "installable").
- [ ] Offline (Playwright `context.setOffline(true)`): previously visited pages load from cache, and unvisited pages show `/offline.html`.
- [ ] `?embed=1` hides the nav.
- [ ] No console errors added on any tool page.
- [ ] `/install/` page written for iPhone (Safari → Share → Add to Home Screen; **must be Safari** on iOS) and Android (Chrome menu → Install app).
- [ ] 🛑 USER merges the hub and the 8 tool PRs, then verifies on their own phone.

---

## 3. Phase 2: Home screen and data feeds (L2)

**Outcome:** the Home screen is the place to check each week, with something useful from every tool on one screen. It loads fast on cell service.

### 3.1 `league.json` (hub)

```json
{ "schema": 1, "name": "DTF Club", "season": 2026, "league_id": "1389416556617801728",
  "slack": "https://dtf-club.slack.com/", "key_dates": [ { "label": "Trade deadline", "date": "2026-11-18" } ] }
```

This is the **single place** to change at season rollover. Tools *may* read it: JS with `fetch('/league.json')`, Python from `https://namkurd.github.io/league.json` or raw.githubusercontent. Migrating the existing hardcoded fallbacks is optional and goes in Phase 5. Get `key_dates` from the user and the Rulebook.

### 3.2 `managers.json` (hub)

This is the canonical identity list, and it fixes name mismatches across tools:
```json
{ "schema": 1, "managers": [
  { "id": "ben", "name": "Ben", "aliases": ["Ben D", "namkurd"], "sleeper_user_ids": ["…"], "active": true, "since": 2012 }
] }
```
Build it from Sleeper (`/v1/league/<id>/users` across the `previous_league_id` chain) plus the name lists already in the repos (sleepersheet history from 2013, Auction from 2012, `history_baseline.tsv`, Record Book holders). 🛑 USER reviews it, because nicknames and former members need a human.

### 3.3 `summary.json` (contract every tool can publish)

This is how tools feed the hub. It keeps the hub generic, with **no tool-specific code in the hub**:
```json
{
  "schema": 1,
  "tool": "recordbook",
  "generatedAt": "2026-11-04T14:39:04Z",
  "season": 2026, "week": 9,
  "headline": "2 records fell this week",
  "items": [
    { "title": "Most points in a week", "subtitle": "Ben · 212.4 (prev 208.1)",
      "href": "/Recordbook/?id=most-points-week", "ts": "2026-11-03", "managers": ["ben"], "tag": "new" }
  ]
}
```
Rules:
- Under 10 KB, at most about 8 items, already sorted.
- `href` is root-relative.
- `managers` use `managers.json` ids. Map them in the tool's Python using `managers.json`.

Add it to each tool's existing Python job and workflow `git add` list. Suggested items per tool:

| Tool | summary.json items |
|---|---|
| Rumble Central | Current standings top 5 and your position, this week's live or final Rumbles by team |
| Record Book | Records broken or tied in the last 14 days (from `changelog.jsonl`) |
| Trade Network | Last 5 trades with value delta |
| FAB Management | This week's best pickups, season leader |
| Head-to-Head | Biggest rivalry streaks or notable this-week matchups |
| Lifetime Win/Loss | All-time top 3, current season top 3 |
| Auction Archive | Offseason only: last draft's best and worst value; in season: nothing or one "draft recap" link |
| Rulebook | Count and list of PENDING proposals (needs a tiny build step; the Rulebook has no workflow, so add one that runs `tools/build.py` on push) |

### 3.4 Home screen layout (hub `index.html`)

From top to bottom:
1. **Greeting and "you"**: "Week 9 · You're 3rd in Rumbles". This uses `dtf.me`. On first visit, show a one-tap "Which manager are you?" picker (stored as `localStorage['dtf.me']`; changeable on the League tab).
2. **This week**: matchup cards from Rumble Central's summary. During games, show a "Live" pill linking to Rumble Central.
3. **Feed**: cards from every `summary.json`, sorted by `ts`. Each card shows the tool name and the age ("updated 2 h ago"). Items involving `dtf.me` come first.
4. **Key dates** from `league.json`.
5. **Quick links grid** of all tools.

Behavior:
- Fetch all summaries in parallel with `Promise.allSettled`. If one tool fails, its card says "unavailable" and the rest still render.
- Mark any summary older than 3 days in season (`generatedAt`) as **stale** (grey). This is how broken Actions get noticed.
- Render cached data first, then refresh in place. Show a skeleton, never a spinner. Target first paint under 1 s on 4G.

### 3.5 Acceptance criteria (Phase 2)

- [ ] Home works with 0 to 8 summaries present.
- [ ] Each existing tool workflow still passes. Run each repo's tests: `SleeperLiveRumbles/test/`, `sleepersheet/test/`, and others where present.
- [ ] Each summary is under 10 KB and validates against the shape above. Put a tiny validator in the hub: `/tools/validate_summary.py`.
- [ ] The manager picker persists and the highlight works across tools.

---

## 4. Phase 3: Static pages and Google Site replacement

**Outcome:** everything worth keeping from the Google Site lives in the hub. The Google Site becomes a single "We moved" link.

1. **Inventory** (needs §1 item 5): list every Google Site page. Mark each one **Replace by tool** (for example, rules → Rulebook, which already imported them; history → Record Book and Lifetime Win/Loss), **Static page**, or **Drop**.
2. **Static pages** live in `/pages/*.html` and use a shared page template: plain HTML with the nav script and `tokens.css`, written so the user can edit them in the GitHub web editor. Likely pages, to be confirmed against the inventory:
   - **Dues & Payouts.** Cross-link Rulebook MN rules.
   - **Key Dates / Calendar.** Rendered from `league.json`.
   - **Champions & Sacko wall.** Prefer generating it from sleepersheet or Record Book data rather than hand-maintaining it.
   - **Members.** Generated from `managers.json`.
   - **About / League history.**
   - **Install the app** (`/install/`, done in Phase 1).
3. Add every page to `tools.json → pages` so it appears under the League tab.
4. **Transition:**
   - Ask the user to edit the Google Site: a banner and a button to the hub, and the embedded iframes swapped for links.
   - Keep the legacy embeds working until the user confirms they are gone. That is why the nav honors `?embed=1` and Rumbles' embed mode.
5. Write a **"Welcome to the new site" Slack post** (draft only, for the user to send) with the install instructions link.

---

## 5. Phase 4: Cross-linking and cleanup

### 5.1 Cross-links (use `DTF.link()` or root-relative URLs, never `https://namkurd.github.io/...`)

| From | To | How |
|---|---|---|
| Record Book replay links (77) | Rumble Central | Change the absolute URLs to root-relative in `data/records.json` and the engine, so a custom domain works |
| Record Book auction records | Auction Archive player or draft view | **The user believes this exists, but no such link was found in the current code.** Confirm with the user, then add it using Auction's hash routes |
| Head-to-Head matrix cell (a game) | Rumble Central replay | `rumbles.html?season=&wp=week.rid.opp` |
| Lifetime Win/Loss manager row | Head-to-Head for that manager; Record Book filtered by holder | Read each tool for the parameter names. Add a manager parameter to H2H if it lacks one |
| Trade Network player | Auction Archive price history | Auction hash route |
| FAB pickup | Trade Network (if later traded) | Player id |
| Rulebook rules by category | TR → FAB / Trade Network, DR → Auction, PL → Rumble Central, SA → Record Book | Small "See it in action →" link per category |
| Every tool | Hub manager page (Phase 5) | `/manager/?id=` |

### 5.2 Cleanup (each in its own commit, reviewed by the user)

- **Retire the legacy Rumbles copies** in `sleepersheet`, `SleeperTradeNodes` and `Sleeper-Head-to-Head`. Replace each `rumbles.html` with a redirect stub to `/SleeperLiveRumbles/rumbles.html`, keeping the query string. 🛑 USER confirms before you remove the matching `build_rumbles.py` steps from those workflows.
  - Before removing anything, grep all repos to confirm nothing reads their `rumbles_history.json`.
  - Note that `Sleeper-Head-to-Head`'s workflow updates both the matrix and Rumbles; keep the matrix part.
- Remove committed `__pycache__/` (SleeperLiveRumbles, SleeperAuction) and add a `.gitignore`.
- **Rename `Rulebook-` → `Rulebook`** if approved. Update `tools.json` and leave nothing else pointing at the old path.
- Add a **"Consumers" section** to each README listing which other repos or the hub read its files (Record Book → SleeperLiveRumbles and sleepersheet; hub → every `summary.json`).

---

## 6. Phase 5: Nice-to-haves (do only when asked)

- **Manager profile page** `/manager/?id=ben`: aggregates each tool's `summary.json` items for that manager, plus deep links into every tool filtered to them. It's the strongest "one app" feature.
- **Health check workflow** in the hub (daily):
  - Read every `summary.json` `generatedAt`, plus each repo's latest workflow run through the public GitHub API with `GITHUB_TOKEN`.
  - On stale data or failed runs, post to Slack via the `SLACK_WEBHOOK_URL` secret and write `/status.json`, which feeds a small status page.
- **Scheduled workflows get disabled after 60 days without repo activity.** In the offseason, FAB (commits only on change), Record Book, H2H and sleepersheet are at risk. Auction already has a heartbeat commit. Either copy that pattern or have the hub health check alert on it.
- **Slack announcements** from tool workflows (record broken, trade completed, weekly Rumbles recap) through the same webhook.
- **Rulebook Slack sync as a scheduled Claude Routine**, running `tools/SYNC_SUGGESTIONS.md` weekly.
- **Shared Python** (`par.py` is duplicated in Trade Network and FAB; there are several league-chain walkers): extract later into a `dtf-core` package installed in workflows with `pip install git+https://github.com/namkurd/dtf-core`. Only do this when one of them needs changing anyway.
- **Repo bloat:** FAB's 1.7 MB `data.json` is recommitted hourly whenever it changes. Consider the Auction pattern: Pages deploy through `actions/deploy-pages` artifacts, so generated data isn't committed.
- Push notifications (iOS 16.4+ installed PWAs only) need a push server. **Not recommended**; Slack already does this job.
- Migrate the hardcoded league-ID fallbacks to read `league.json`.

---

## 7. Local development and testing

Mirror the production origin layout locally so root-relative paths (`/shell/nav.js`, `/Recordbook/`) behave exactly as on GitHub Pages:

```bash
mkdir -p ~/site && cd ~/site
ln -s /home/user/namkurd.github.io/* .          # hub at root (adjust to where the hub is cloned)
ln -s /home/user/SleeperLiveRumbles SleeperLiveRumbles
ln -s /home/user/sleepersheet sleepersheet
ln -s /home/user/SleeperTradeNodes SleeperTradeNodes
ln -s /home/user/FAB-Management FAB-Management
ln -s /home/user/Recordbook Recordbook
ln -s /home/user/Sleeper-Head-to-Head Sleeper-Head-to-Head
ln -s /home/user/SleeperAuction/site SleeperAuction   # Auction serves site/
ln -s /home/user/Rulebook- Rulebook-                   # or wherever it's cloned
python3 -m http.server 8080
```

Notes:
- Service workers need `localhost` or HTTPS. `localhost` works.
- Write a Playwright smoke test in the hub at `tests/smoke.js`. It's not deployed and doesn't need to be ignored, but keep it out of the precache. For each tool path, at 390×844 and 1280×800, it should:
  - load the page and assert `dtf-nav` exists with the correct active tab
  - check for no console errors that weren't there before, and no horizontal scroll
  - check that the bottom 70 px of content is not obscured
  - take a screenshot to `tests/screens/`
- The Sleeper API (`api.sleeper.app`) may be blocked by the session network. Pages should degrade gracefully, which is a useful test in itself. Do not mock it into tool code.
- Run each tool repo's existing tests after changing it.

---

## 8. Pitfalls checklist (read before each phase)

1. **Stale caches.** Use network-first for HTML and JSON, and version the shell cache. Never cache-first data.
2. **Build scripts regenerating HTML** remove the nav script tag. Edit the template in the Python, not just the output.
3. **Data contracts across repos.** Record Book reads SleeperLiveRumbles and sleepersheet on `main`. Grep before renaming or reshaping anything.
4. **Shared origin means shared localStorage.** Use the `dtf.` prefix for new keys. The Record Book GitHub token (`rb-token`) can be read by every page on the origin. That's acceptable because only the user's own code runs there, but: no third-party scripts besides pinned ones, and the user's PAT should be **fine-grained, limited to the Recordbook repo's contents**. Mention this to the user.
5. **iOS standalone quirks.** Install only works through Safari. There is no back button and no pull-to-refresh. Safe-area insets apply. iOS evicts storage for apps unused for weeks. The touch icon and manifest must be on the page where the user taps Add to Home Screen.
6. **Repo renames break Pages URLs** with no redirect. Route every link through `tools.json` or keep redirect stubs.
7. **GitHub Pages caching** is `max-age=600`. Use `cache: "no-cache"` or `?_=` busting for data. Expect up to 10 minutes of delay on HTML after a deploy.
8. **Big payloads.** Rumble Central is 650 KB and FAB data is 1.7 MB. The Home screen must read only `summary.json`. Lazy-load everything else.
9. **Fixed-position collisions** between tool UI and the bottom nav.
10. **Iframes** (Google Site embeds) must keep working until the user retires them. Honor embed mode.
11. **Silent workflow failures** and 60-day schedule disabling. Show freshness, and add a health check later.
12. **Scope creep.** Don't restyle tools in Phases 1 and 2. L3 theming is opt-in and per tool, later.

---

## 9. Suggested order of work and sizing

| Step | Repos touched | Size |
|---|---|---|
| §1 decisions, user creates and attaches hub repo | – | user |
| Phase 1: hub shell, manifest, SW, nav, install page | hub | M |
| Phase 1: add nav script to 8 tools, remove Rumbles manifest/SW, fix collisions | all 8 | S each |
| 🛑 user merges and tests on phone, then shares with 1–2 league members for feedback | | |
| Phase 2: league.json, managers.json (user review), Home screen | hub | M |
| Phase 2: summary.json per tool (start with Rumbles, Record Book, Trade Network) | 3, then the rest | S each |
| Phase 3: Google Site inventory, static pages, transition, Slack welcome draft | hub | M |
| Phase 4: cross-links and cleanup | several | S each |
| Phase 5: on request | | |

**Definition of done for the overall project:** a league member installs "DTF Club" from Safari. They see this week's Rumbles and the latest records, trades and waivers on Home. They reach any of the 8 tools and the static pages within two taps, and never leave the app. The Google Site points here. The user can update any tool repo without touching the hub, and adds a new tool by appending one entry to `tools.json` plus one script tag.
