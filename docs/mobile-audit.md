# PDA App (apps/mobile): Stage A Audit and Improvement Plan

Date: 2026-11-10. Scope: `apps/mobile` only. Nothing in the app was changed during this audit.

Status legend for findings: **Confirmed** means verified by reading the code (and where noted, by running a tool).
**Potential** means a plausible risk that needs measurement or a device test before acting on it.

---

## 1. Baseline

| Check | Command | Result |
|---|---|---|
| Typecheck | `npx tsc --noEmit` | Pass (exit 0) |
| Lint | `npx eslint src` | Pass (exit 0) |
| Dependency health | `npx expo-doctor` | 20/20 checks passed |
| Unit tests | none | No test runner is set up in `apps/mobile` |
| Browser E2E | `apps/backend/tests/e2e/test_pda.py` (Playwright, against `expo export --platform web`) | Not run in this audit; it needs the backend stack. CI runs it (`.github/workflows/ci.yml`) |

### Stack (from `package.json` / `app.json`)

- Expo SDK **58** (`expo ~58.0.23`), React Native **0.88.1**, React **19.3**, TypeScript **6.0** in strict mode, npm (package-lock).
- Routing: **expo-router 58** with a single `Stack` (`src/app/_layout.tsx`), typed routes on.
- State: **zustand 5**. `session`, `queue` and `settings` are persisted to AsyncStorage. `masterData` is persisted to a file through `lib/largeStore.ts`. `tasks` is in memory only.
- Storage: AsyncStorage (small JSON, offline read caches), `expo-file-system` `File` API (master data, photo base64). **There is no SQLite**, even though PLAN §4.2 mentions "SQLite/MMKV".
- Native modules used: expo-haptics, expo-image-picker, expo-image-manipulator, expo-crypto, expo-constants, expo-file-system.
- Already installed as expo-router dependencies, but not declared in `package.json`: `react-native-reanimated 4.7`, `react-native-gesture-handler 3.4`, `expo-glass-effect 58`. To use any of them directly, add it with `npx expo install` first.
- Not present: icon library, custom fonts, blur, secure storage, list virtualization library.
- Android config: package `com.wms.pda`, portrait only, `userInterfaceStyle: "light"`, `usesCleartextTraffic: true`, predictive back disabled. No `android/` folder (CNG). No EAS config (`eas.json` absent), so no device build pipeline exists yet (PLAN: "device builds pending an Android environment").
- Scanning model: **keyboard wedge** (HID/DataWedge) into a focused `TextInput`. There is no vendor SDK, by design (PLAN §4.2).

---

## 2. Architecture overview

```
src/app/            screens (expo-router)          src/stores/            zustand
  _layout.tsx  ── sync loop (20 s) + task poll ──▶   queue.ts    offline submit queue, idempotent replay
  index.tsx     home menu + master data              session.ts  serverUrl, token, username
  login.tsx                                          masterData.ts  compact master data → Map indexes
  receive.tsx   PO → location → items → submit       tasks.ts    new pick/count polling + haptic
  putaway.tsx ┐                                      settings.ts "each scan counts 1"
  move.tsx    ┴▶ components/TransferScreen.tsx
  count.tsx     count → location → item → qty     src/lib/
  pick.tsx      guided: bin → item → qty → post      api.ts       fetch wrapper, error kinds, 15 s timeout
  queue.tsx     pending / held / failed / done       inbound.ts   read endpoints with offline cache fallback
                                                     largeStore.ts file storage (web: chunked AsyncStorage)
src/components/  ui.tsx (Button, Card, Field, Row,   photos.ts    camera → resize → base64 file
                 Banner, EachScanToggle, colors)     types.ts     API DTOs
                 ScanInput, PhotoCapture, SyncIndicator
```

**Write path.** A screen calls `useQueue.submit()`, which adds an op and runs `sync()`. Ops replay strictly in order.
Document ops carry `client_request_id`, so replays never create duplicate documents, and photos carry `Idempotency-Key`.
Business rejections go to *failed*. Network and server errors stay *pending*. A 401 pauses the queue and sets `needsLogin`.
Ops are bound to the user who created them, so a shared PDA never posts one person's work under another's name.

**Read path.** `lib/inbound.ts` `withCache()` fetches fresh data, falls back to the last cached copy only on a network
error, and tells the screen it is showing cached data.

This core is well designed. The queue's idempotency, ordering, per-user binding and photo handling are careful and
documented. The improvement work below must keep it as is. Most of the problems are in presentation, screen state
and a few edge cases in the network layer, not in the architecture.

### Feature inventory (all must be preserved)

| Feature | Screen | API |
|---|---|---|
| Sign in (server URL, username, password) | login | `POST /auth/login` (form) |
| Master data download / offline barcode lookup | home | `GET /mobile/master-data?format=compact` |
| Receive against PO, batch/expiry, continuous scan, photos | receive | `GET /purchase-orders`, `POST /grns`, `/grns/{id}/post`, `/cancel`, `/documents/{id}/attachments` |
| Putaway (dock → BIN) / Move (→ BIN/DOCK), batch choice | putaway, move | `GET /stock/balances`, `POST /putaways`, `/moves` (+ post/cancel) |
| Cycle count by location, blind count support, continuous scan, photos | count | `GET /cycle-counts`, `POST /cycle-counts/{id}/counts`, attachments |
| Guided picking, skip line, short pick, post | pick | `GET /picks`, `POST /picks/{id}/lines/{line}/confirm`, `/picks/{id}/post` |
| Offline queue: pending / held for other user / failed (retry, delete) / recent | queue | — |
| New-work alerts (polling, haptic, home badge) | home | `GET /picks?status=OPEN`, `GET /cycle-counts?status=COUNTING` |
| Sync status in every header | all | — |

---

## 3. Findings

**No P0 was confirmed.** I found no way to lose data, corrupt stock, or break the app in normal use. Several P1 items
can strand queued work or lose unsubmitted scans, so they come first.

### P1: reliability, data handling, usability

| # | Finding | Status | Where |
|---|---|---|---|
| P1-1 | **Response body has no timeout.** The 15 s abort timer is cleared once headers arrive (`finally`), then `await response.text()` runs unbounded. If a Wi-Fi drop stalls a response mid-body, the request never settles. `sync()` then stays "running" for good, every later `sync()` returns that same promise, and the queue stops until the app restarts. | Confirmed (code) | [api.ts:65-81](../apps/mobile/src/lib/api.ts#L65-L81) |
| P1-2 | **Offline read caches are not scoped to user or server.** Keys such as `cache.count.<id>` and `cache.po.<DOCNO>` are shared by everyone who signs in on the device, and sign-out does not clear them. Example: a user with the view permission opens a count (book quantities cached), then a blind-count user opens it offline and sees the book quantities. This defeats the blind-count control. A server URL change also serves another server's cached POs by doc no. | Confirmed (code) | [inbound.ts:12-25](../apps/mobile/src/lib/inbound.ts#L12-L25), [session.ts:27](../apps/mobile/src/stores/session.ts#L27) |
| P1-3 | **Unsubmitted work is lost without warning.** Receive entries, transfer entries and count/pick screen state are plain `useState`. Android back, the header back arrow, "Change purchase order" or "Change source location" discard 20 scanned lines with no confirmation. | Confirmed (code) | [receive.tsx:48-55](../apps/mobile/src/app/receive.tsx#L48-L55), [TransferScreen.tsx:232-241](../apps/mobile/src/components/TransferScreen.tsx#L232-L241) |
| P1-4 | **Orphaned photo files.** Photos taken on Receive are deleted only by `reset()`. Leaving the screen any other way (back, or unmount) leaves the base64 files in the document directory for good. Each file is about 200-400 KB. | Confirmed (code) | [receive.tsx:48-50](../apps/mobile/src/app/receive.tsx#L48-L50) |
| P1-5 | **Feedback can be off-screen.** `Banner` is the first child of the `ScrollView`. Once the operator scrolls down (long PO, pick line list), a "Wrong bin" or "Rejected" message appears above the visible area. Only success has a haptic (`selectionAsync` on +1); wrong-scan errors have no haptic, so the operator gets no feedback at all. | Confirmed (code) | all screens; [pick.tsx:81-99](../apps/mobile/src/app/pick.tsx#L81-L99) |
| P1-6 | **Text contrast fails WCAG AA** (computed): warning `#d48806` is 2.87:1 on white and 2.39:1 on its banner tint. Success `#389e0d` is 3.46:1 and 2.84:1. Primary `#1677ff` with white button text is 4.10:1. AA needs 4.5:1. This matters more on PDA screens in bright light. | Confirmed (computed) | [ui.tsx:16-26](../apps/mobile/src/components/ui.tsx#L16-L26) |
| P1-7 | **Session lasts 60 minutes with no refresh.** `access_token_expire_minutes = 60` and there is no refresh token, so every shift has repeated mid-task sign-ins. Queued work is kept, but read screens only show the raw 401 text and do not send the user to sign in. | Confirmed (code); the fix needs a backend decision | `apps/backend/app/core/config.py:18`, [api.ts:83](../apps/mobile/src/lib/api.ts#L83) |
| P1-8 | **Token is stored in plain AsyncStorage.** It sits inside the app sandbox, but `allowBackup` is not disabled, and the token is a 60-minute bearer credential. `expo-secure-store` (Android Keystore) is the standard choice. | Confirmed: plaintext. Potential: exploitability | [session.ts:29](../apps/mobile/src/stores/session.ts#L29) |
| P1-9 | **Cleartext HTTP is enabled globally** (`usesCleartextTraffic: true`). Passwords and tokens cross warehouse Wi-Fi in clear. Turning this off would break current on-prem installs, so the fix is a decision plus HTTPS deployment guidance, not a silent change. | Confirmed (config) | `app.json` |

### P2: maintainability, UX, smaller correctness gaps

| # | Finding | Status | Where |
|---|---|---|---|
| P2-1 | No design tokens beyond a 9-color object. About 40 inline `fontSize`/style literals and `"#fff"` hard-coded in four files. No dark mode (`userInterfaceStyle: "light"`, `StatusBar style="dark"`). | Confirmed | ui.tsx, all screens |
| P2-2 | Inline "Delete"/"Remove" are bare `Text` in a `Pressable`: about 20 px tall, below the 48 dp target and hard to hit with gloves. | Confirmed | receive.tsx:244, TransferScreen.tsx:217, PhotoCapture.tsx:27 |
| P2-3 | Screen-reader labels are missing: `ScanInput`/`Field` labels are separate `Text` nodes, not tied to the inputs, and the keyboard toggle has no label. Font scaling has not been checked (fixed 12-13 px hints). | Confirmed | ScanInput.tsx, ui.tsx |
| P2-4 | Login can double-submit: `onSubmitEditing={login}` on the password field ignores `loading`, so pressing Enter twice sends two logins. Enter with empty fields also submits. | Confirmed | [login.tsx:67](../apps/mobile/src/app/login.tsx#L67) |
| P2-5 | Quantity checks differ between screens: Receive/Transfer use `parseQty` (4 decimals), while Count/Pick use `Number()` (any decimals, accepts `1e3`). | Confirmed | count.tsx:135, pick.tsx:103 |
| P2-6 | Master data is not tied to a server. If the server URL changes, a failed refresh is swallowed after sign-in ([login.tsx:35-38](../apps/mobile/src/app/login.tsx#L35-L38)) and barcodes resolve against the old server's items. | Confirmed (code) | masterData.ts |
| P2-7 | Pick/Count "done on this device" markers (`local`, `queued`) are lost when the screen is left. When the user reopens a cached pick offline, lines already confirmed show as "To pick" again. Replay is idempotent, so this is not a data problem, but operators may re-pick. | Confirmed (code) | pick.tsx:26, count.tsx:42 |
| P2-8 | Lists are rendered with `.map()` inside `ScrollView` (PO lines, pick lines, queue). That is fine at tens of rows. It may stutter on a 300-line PO on a low-end PDA. | Potential: measure | receive.tsx:225, pick.tsx:214 |
| P2-9 | Master data is parsed with `JSON.parse` and decoded on the JS thread during startup, behind the hydration spinner. With tens of thousands of items this may add seconds to cold start on a PDA-class CPU. | Potential: measure on device | masterData.ts:111-124 |
| P2-10 | No unit tests. The logic most worth testing (queue replay rules, `parseQty`/`parseDate`, master-data decode/lookup order) is pure and easy to test. | Confirmed | — |
| P2-11 | Count/Pick selection lists are full-width buttons that show only `doc_no · remark`. There is no date, line count or pull-to-refresh, and there is no empty-state action. | Confirmed | count.tsx:174-191, pick.tsx:152-163 |

### P3: polish

- P3-1: `SyncIndicator` shows a green "Online" before any request has been made (`online === null`). It should show "–" or "Checking" until the first result.
- P3-2: Entry keys use `Date.now()`. A collision is unlikely but possible with very fast continuous scanning. Use a counter or `randomUUID`.
- P3-3: Home uses `useSession()` and Queue uses `useQueue()` without selectors, so they re-render on any store change. The cost is negligible at this size; fix it only while touching those files.
- P3-4: The ①②③ step numbers live inside label strings, so there is no persistent "where am I in this flow" indicator.

### Checked and found fine

- No `console.*` calls in `src`, and no secrets in source. The server URL is user-entered, and the password is never stored.
- Timers and `AppState` listeners in `_layout.tsx` are cleaned up. The `ScanInput` focus guard is cleared on deactivate and blur.
- Queue concurrency: there is a single in-flight `sync()`, and submits added during a sync are picked up. The task poller has the same single-flight guard.
- Idempotency on every write path, including lost-response cases (409 handling for create and pick post).
- Large data is kept out of AsyncStorage, which is limited on Android: master data and photos go to files.

---

## 4. UI/UX assessment and redesign specification

### 4.1 Who uses this and what that implies

Warehouse operators on rugged Android PDAs (about 5-6" screens, keyboard-wedge scanner, often gloves, bright or cold
environments, mid- to low-end CPUs/GPUs). They repeat the same 3-4 step flow hundreds of times a shift, usually while
looking at the goods rather than the screen. Design priorities, in order:

1. **Scan feedback you can feel and see from arm's length**: haptic and color/position, never a message off-screen.
2. **Where am I in the flow**: a persistent step indicator.
3. **The primary action is always reachable**: a fixed bottom bar, not the end of a scroll.
4. **Large tabular numbers** for quantities, codes and bins.
5. **No accidental loss of work.**
6. Visual polish, last.

### 4.2 Visual direction (recommendation)

- **Solid, layered surfaces, with no Liquid Glass on the main screens.** Blur on Android is expensive and patchy:
  `expo-glass-effect` renders only on iOS 26 and falls back to a plain view elsewhere, and translucent surfaces lose
  readability under warehouse lighting. "Glass" will mean at most one subtle translucent sticky action bar, with an
  opaque fallback. I recommend leaving it out completely.
- **Light / Dark / System theme, persisted** (setting on Home). Dark is useful for night shifts and cold stores. Use
  layered dark surfaces like the web console, not pure black.
- **Same brand as the web console**: indigo accent `#4f46e5` / `#6d6ff5` and the neutral scales from
  `apps/web/src/theme/index.ts`, with status colors tuned to ≥ 4.5:1 for text.
- **System font (Roboto on Android)** with a fixed scale and `fontVariant: ["tabular-nums"]` for quantities. A variable
  web font adds APK size and gains nothing on PDA screens. Bin and SKU codes are shown large and semibold, not
  monospace (narrower, easier to read).
- **Motion**: short (150-200 ms) presence animations for the feedback toast and the quantity panel, through the
  already-present Reanimated, with reduced motion respected. No animation on list rows or on the scan path.

### 4.3 Per-screen specification

Every screen keeps its current data sources, store calls, API payloads, validation rules and `testID`s.

**Home** (`index.tsx`)
- *Now*: six identical full-width blue buttons, then master-data and user cards. Warnings are stacked banners.
- *Problems*: everything has the same visual weight. New-work badges are appended to button text. Sign-out is a large red button.
- *Proposed*: a header strip with user, server host and sync state. A 2-column **task tile grid** (icon, label, count
  badge: "3 new", queue count) for Receive / Put away / Move / Count / Pick, with Queue as a full-width tile. Alerts
  (session expired, no master data) become one prioritized notice with its action button inline ("Sign in", "Update now").
  Master data shows as a compact row with a refresh icon button. A small Settings section holds theme and "Each scan counts 1".
- *States*: no master data, so the tiles are disabled and the notice offers "Update now". Updating shows a progress spinner in the row.

**Login**
- *Proposed*: app mark and title. Server URL is collapsed into a "Server" row (tap to edit) once set. Username and
  password with a show/hide toggle. Enter and the button share one guarded submit (P2-4). Errors are shown inline under the form.

**Receive / Put away / Move / Count** (shared skeleton)
- *Now*: one long scroll. Step labels are inside the input labels, the banner is at the top, and Submit is at the bottom.
- *Proposed layout*:
  - **Context bar** (fixed top): document/location chips (`PO-0012 · IN-01`), tap to change, with a confirm dialog if
    there are unsubmitted lines (P1-3).
  - **Step indicator**: `Order › Location › Items`, with the current step highlighted.
  - **Scan field**: large, with a clear active/inactive state. The keyboard toggle becomes an icon button with a label.
  - **Feedback toast**: fixed just under the scan field, colored by kind and paired with a haptic (success: light;
    error: `notificationAsync(Error)`). It stays until the next scan, so it is never scrolled away (P1-5).
  - **Quantity panel**: a card that opens inline with the item name, an "Open 12 EA" stat and a large numeric field.
  - **Lines list**: compact rows with SKU and name on the left and tabular `3 / 12 EA` with a status pill on the right.
    Delete becomes a 48 dp icon button (P2-2).
  - **Fixed bottom action bar**: the primary action ("Submit receipt · 4 lines") is always visible. Secondary actions go in an overflow.
- *States*: loading PO/balances shows skeleton rows. An offline cached read shows a persistent "Cached 10:42" pill in
  the context bar instead of a one-off banner. A rejected submit shows an error toast and keeps the entries. A queued
  submit shows a warning toast "Saved on this device".

**Pick**
- *Proposed*: the target bin as a hero (about 34 sp, semibold), item and quantity under it, and a progress bar `5 / 12`.
  Wrong bin/item gives a red flash on the hero and an error haptic. The line list is collapsed behind "All lines". Skip
  stays a secondary action. Finish is in the bottom bar.

**Count / Pick selection lists**
- *Proposed*: list rows with doc no., remark, created date and a chevron. Pull-to-refresh replaces the Refresh button
  (the E2E test waits for the text "Refresh", see §6). The empty state explains where the work comes from.

**Queue**
- *Proposed*: sections (Pending · Waiting for another user · Failed · Recently completed) with counts in the section
  headers. Failed rows show the error in a tinted block. Retry/Delete become paired buttons, and Delete asks for
  confirmation, because it discards work. "Sync now" goes in the header or bottom bar.

---

## 5. Design system to build (Stage C)

All of it goes in `src/theme/` and `src/components/`, extending the existing `ui.tsx` exports (`Button`, `Card`, `Field`,
`Row`, `Banner`) rather than duplicating them, so the change to screens stays small.

- **Tokens**: `palette.light/dark` (bg, surface, surfaceRaised, border, text, textSecondary, textMuted, primary,
  onPrimary, success/warning/danger/info, each with a text-safe and a tint variant), `space` (4/8/12/16/24/32),
  `radius` (6/10/14), `type` (display 34, title 20, heading 17, body 16, label 14, caption 13; quantities with
  tabular nums), `size` (touch 48, input 52, scan input 60), `motion` (fast 150, base 200).
- **Theme**: a `useTheme()` hook that reads a `settings.theme` preference (`system | light | dark`) plus `useColorScheme()`.
  `app.json` changes to `userInterfaceStyle: "automatic"`, and StatusBar follows the theme.
- **Components** (new ones only where at least two screens use them): `Screen` (safe area, fixed toast slot, bottom
  action bar), `StepIndicator`, `ContextBar`, `Toast` (replaces the in-scroll banner for scan feedback), `ListRow`,
  `StatusPill`, `IconButton`, `EmptyState`, `ConfirmDialog` (via `Alert.alert` on native and a modal on web, because
  E2E runs in a browser).
- **Icons**: one icon set added with `npx expo install` (decision D3).

---

## 6. Contracts that must not change

- **API**: every path, method, payload and `client_request_id` / `Idempotency-Key` rule listed in §2.
- **Queue semantics**: ordering, per-user binding, failed/pending classification, photo lifecycle.
- **E2E selectors** (`apps/backend/tests/e2e/test_pda.py`): testIDs `server-url, username, password, login,
  menu-receive, menu-pick, menu-count, scan-po, scan-location, scan-item, qty, confirm-entry, submit-receive,
  confirm-count, each-scan, take-photo, photo-note, photo-thumb, sync-indicator, retry-op, held-for-others, failed-ops`,
  plus the scanned inputs `scan-*`.
- **E2E text** that the tests match on: "Received, document no.", "Saved on this device", "Sign out",
  "New work: 1 pick list", "1 new" inside `menu-pick`, "Refresh" on the pick screen, "`<title>` → GRN…" under recent,
  "`<SKU>` +1, now 3", "Recorded `<SKU>` = 4", "Pending" inside `sync-indicator`, "`<doc_no>` · `<remark>`" on the count
  list, "× 2" and "Into `<loc>`" in queue details. Any wording change goes into the same commit as the matching test update.
- Navigation: tests call `page.go_back()` from a screen to reach Home, so the Home → screen stack must stay.

---

## 7. Implementation plan

Each row is one reviewable commit. Testing for every row: `tsc` + `eslint` + `expo-doctor`, and `test_pda.py` where flows are touched.

| ID | Pri | Change | Files | Depends | Risk | Status |
|---|---|---|---|---|---|---|
| **B1** | P1 | Abort covers the whole request incl. body read; settle `sync()` on any throw | lib/api.ts | — | Low | Pending |
| **B2** | P1 | Scope read caches by server and user (key prefix); clear on sign-out and on user/server change | lib/inbound.ts, stores/session.ts | — | Low | Pending |
| **B3** | P1 | Confirm before discarding unsubmitted lines (back, change PO/location); remove photos on unmount | receive.tsx, TransferScreen.tsx, count.tsx | C (ConfirmDialog) or `Alert` | Med | Done (2026-11-10) |
| **B4** | P1 | Error haptic on rejected scans | all scan screens | — | Low | Done (2026-11-10) |
| **B5** | P2 | Guarded login submit; shared quantity validation (`parseQty` with a zero-allowed variant for count/pick) | login.tsx, inbound.ts, count.tsx, pick.tsx | — | Low | Partly: login guard done; shared qty validation pending |
| **C1** | P1/P2 | Theme tokens, light/dark palettes with AA contrast, `useTheme`, theme setting, `app.json` automatic | src/theme/*, ui.tsx, settings.ts, app.json, _layout.tsx | — | Med | Done (2026-11-10) |
| **C2** | P2 | New shared components (§5); restyle existing `ui.tsx` components to tokens, same exports | components/* | C1 | Med | Done (2026-11-10) |
| **D1** | P1 | Scan screen skeleton: context bar, step indicator, fixed feedback toast, bottom action bar | Receive first, then Transfer, Count | C2 | Med | Done (2026-11-10) |
| **D2** | P2 | Pick hero layout and progress | pick.tsx | C2 | Med | Done (2026-11-10) |
| **D3** | P2 | Home tile grid, settings section; Login polish | index.tsx, login.tsx | C2 | Low | Done (2026-11-10) |
| **D4** | P2 | Selection lists with pull-to-refresh and empty states; Queue sections and delete confirm | count.tsx, pick.tsx, queue.tsx | C2 | Low | Done (2026-11-10) |
| **E1** | P2 | Measure cold start and master-data hydrate on a real PDA; optimize only if > 1 s | masterData.ts | device | Low | Blocked (device) |
| **E2** | P2 | Virtualize long line lists (FlatList) if measured jank | receive.tsx, pick.tsx | device | Low | Blocked (device) |
| **E3** | P2 | Persist pick/count "done on this device" markers per document | pick.tsx, count.tsx | — | Low | Pending |
| **F1** | P1 | Token in `expo-secure-store` with web fallback; `allowBackup: false` | session.ts, app.json | D2 decision | Med | Pending (decision) |
| **F2** | P1 | On 401 in read screens: route to Login, then return; keep screen state | lib/api.ts, screens | — | Med | Pending |
| **F3** | P1 | Session length: longer token or refresh-token flow | backend + mobile | D1 decision | Med | Pending (decision) |
| **F4** | P1 | HTTPS deployment guide; keep cleartext as an explicit opt-in | docs/deployment.md, app.json | D4 decision | Low | Pending (decision) |
| **G1** | P2 | `jest-expo` unit tests: queue replay classification, parsers, master-data decode and lookup order | new tests | — | Low | Pending |
| **G2** | — | Full `test_pda.py` run plus manual checklist on a device (keyboard, back, dark mode, font scale) | — | all | — | Pending |

Order: **B → C → D → F → E → G**. G1 can run alongside B so that the queue logic has tests before anything near it changes.

---

## 8. Decisions needed before Stage B/C

- **D1: Session length.** Option (a) raises the token lifetime for PDA sign-ins, e.g. one shift. Option (b) adds a
  refresh token, which is a backend change. Option (c) keeps 60 minutes. This decides F3.
- **D2: Secure token storage.** Add `expo-secure-store`? It is a native module, so it needs a dev or EAS build, not Expo Go.
- **D3: New dependencies for UI.** One icon set, and Reanimated declared directly. Both are SDK-matched through `npx expo install`.
- **D4: Cleartext HTTP.** Keep it on by default for on-prem LAN installs, or require HTTPS?
- **D5: Visual direction.** Confirm "solid surfaces, light/dark/system, web-console indigo, no glass" (§4.2). Also
  decide whether you want HTML mockups of Home, Receive and Pick in light and dark before any screen code is written.
