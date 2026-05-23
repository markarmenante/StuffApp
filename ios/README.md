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

The starter Swift files in `StuffOfflineApp/` implement the sync layer:

- `StuffConfig.swift`
  Server URL and local folder names.

- `StuffSyncModels.swift`
  Codable payloads matching the Flask mobile API.

- `StuffLocalStore.swift`
  App-support storage for snapshots, incremental updates, and files.

- `StuffSyncClient.swift`
  Snapshot/change fetches and local file downloads.

Next step is an Xcode project with a SwiftUI UI over `StuffLocalStore`, plus a
small online web view fallback for workflows that are not worth re-building on
iPhone yet.
