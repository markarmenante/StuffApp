# Shared connections and pathways

This public repository intentionally contains only a reference, not a private
account or credential inventory.

- Canonical local registry: `../boardroom/CONNECTORS.md` in the sibling checkout.
- Canonical Mac location: `~/GitHub/boardroom/CONNECTORS.md`.
- Authorized remote access: [Boardroom connection registry](https://github.com/markarmenante/boardroom/blob/main/CONNECTORS.md).

Before integration work, read the canonical registry's shared discovery/reuse
contract. Inspect existing adapters and the specifically documented credential
location before requesting credentials or creating a provider app. An existing
app may need authorization on a new machine without needing a replacement.

Reuse is limited to approved accounts, owners, scopes and runtimes. Do not copy
secrets into documentation, source, browser code or chat; do not combine tenants'
credentials, stores or private data. A registry reference grants no runtime access.

Update the canonical entry in the same task whenever a pathway, adapter,
endpoint, consumer, schedule or credential location changes, and commit/push
that update alongside the app change. Record verification date and environment.
If the canonical registry is inaccessible, report that limitation instead of
creating a duplicate integration or publishing a local copy of private details.
