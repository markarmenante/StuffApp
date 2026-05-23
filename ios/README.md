# Stuff iOS Native App

The web app remains the source of truth. The iOS app should keep a local
read-through cache so the collection remains usable when connectivity is poor:

1. Download `/api/mobile/snapshot` after sign-in.
2. Store records locally on the device.
3. Download every file listed in the snapshot into the app sandbox.
4. Poll `/api/mobile/changes?since=<last-sync-time>` when online.
5. Replay queued edits to the existing web APIs, then pull changes again.

This avoids a second source of truth. The iPhone has its own copy for browsing,
but the canonical record still lives in the Flask app and the server-side
StuffFiles upload store.

## API

- `GET /api/mobile/snapshot`
  Full JSON snapshot of visible categories, records, and referenced files.

- `GET /api/mobile/changes?since=<ISO timestamp>`
  Incremental record updates, file manifest updates, record tombstones, and
  file tombstones since the previous sync.

The API honors the same Cloudflare/user/category/row permissions as the web UI.

## Native Client Shape

Open `Stuff.xcodeproj` in Xcode and run the `Stuff` scheme on the iPhone or
iPhone simulator.

The Swift files in `StuffOfflineApp/` implement the native app:

- `StuffConfig.swift`
  Server URL and local folder names.

- `StuffSyncModels.swift`
  Codable payloads matching the Flask mobile API.

- `StuffLocalStore.swift`
  App-support storage for snapshots, incremental updates, and files.

- `StuffSyncClient.swift`
  Snapshot/change fetches and local file downloads.

- `ContentView.swift`
  SwiftUI offline browsing UI for categories, records, details, and local files.

- `StuffWebView.swift`
  Embedded live web app for workflows that should keep using the server UI.

- `StuffCookieBridge.swift`
  Copies the Cloudflare/web cookies from the web view into URLSession before
  sync so the native API calls inherit the signed-in session.

Edits are intentionally online-only for now: tap **Edit Live**, make the change
in the server app, then close it. The native app syncs afterward and refreshes
the local cache. Offline mode is for access and review, which keeps the web app
as the only source of truth.
