# Shared connections and pathways

This public repository contains only a pointer to the private
[shared-services catalog](https://github.com/markarmenante/shared-services),
with its [discovery and reuse contract](https://github.com/markarmenante/shared-services/blob/main/docs/security-and-reuse.md).
The existing Boardroom connector reference also points there. Do not publish the
private catalog, its exports, account inventory, costs or credentials here.

Before integration work, use existing authorized access to read the catalog.
Inspect the owning adapter and documented protected storage location before
requesting credentials or creating a provider app. Missing local authorization
does not establish that an existing integration needs replacing.

Reuse is limited to approved accounts, owners, scopes and runtimes. Keep secret
values in their existing protected stores, out of source, documentation, browser
code and chat. Do not combine tenants' credentials, stores or private data.
A catalog reference grants no runtime access.

This documentation change does not migrate an app runtime, change deployment
ownership or introduce a new paid host. Update the private central catalog in
the same task when a connector, adapter, consumer, scope or protected storage
reference changes. Record verification date and environment there, and
commit/push the relevant documentation alongside the app change. If private
access is unavailable, report the limitation instead of copying private details
here or creating a duplicate integration.
