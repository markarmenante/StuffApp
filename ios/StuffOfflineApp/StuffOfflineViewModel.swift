import Foundation
import SwiftUI

@MainActor
final class StuffOfflineViewModel: ObservableObject {
    @Published private(set) var categories: [String: StuffCategory] = [:]
    @Published private(set) var records: [String: [StuffRecord]] = [:]
    @Published var selectedCategory: String = "watches"
    @Published var statusText: String = "Not synced yet"
    @Published var isSyncing = false
    @Published var errorMessage: String?
    @Published private(set) var lastSyncedAt: Date?

    private let store: StuffLocalStore
    private let client: StuffSyncClient
    private let lastSyncedAtKey = "stuff.lastSyncedAt"

    init() {
        do {
            let store = try StuffLocalStore()
            self.store = store
            self.client = StuffSyncClient(store: store)
            self.lastSyncedAt = UserDefaults.standard.object(forKey: lastSyncedAtKey) as? Date
            Task { await loadLocalCache() }
        } catch {
            fatalError("Could not create Stuff local store: \(error)")
        }
    }

    var orderedCategories: [(String, StuffCategory)] {
        let preferredOrder = [
            "watches", "coins", "properties", "credit_cards", "persons",
            "cameras", "lenses", "pens", "art", "vehicles", "recordings",
            "audio", "rifles", "items"
        ]
        let rank = Dictionary(uniqueKeysWithValues: preferredOrder.enumerated().map { ($0.element, $0.offset) })
        return categories
            .map { ($0.key, $0.value) }
            .sorted {
                let left = rank[$0.0] ?? Int.max
                let right = rank[$1.0] ?? Int.max
                if left == right {
                    return $0.1.name < $1.1.name
                }
                return left < right
            }
    }

    var selectedRecords: [StuffRecord] {
        records[selectedCategory] ?? []
    }

    var lastSyncedText: String {
        guard let lastSyncedAt else {
            return "Never synced"
        }
        return "Last synced \(lastSyncedAt.formatted(date: .abbreviated, time: .shortened))"
    }

    func localURL(for file: StuffFile) async -> URL? {
        await store.hasFile(file) ? await store.localURL(for: file) : nil
    }

    func detailURL(for record: StuffRecord) -> URL {
        StuffConfig.serverURL
            .appendingPathComponent(record.category)
            .appendingPathComponent(record.id)
    }

    func title(for record: StuffRecord) -> String {
        guard let category = categories[record.category] else {
            return record.id
        }
        let primary = record.data[category.labelField]?.displayString ?? ""
        let secondary = record.data[category.sublabelField]?.displayString ?? ""
        return [primary, secondary].filter { !$0.isEmpty }.joined(separator: " ")
    }

    func subtitle(for record: StuffRecord) -> String {
        let keys = ["status", "property", "property_name", "owner", "date", "purchase_date", "vendor"]
        let parts = keys.compactMap { key -> String? in
            let value = record.data[key]?.displayString.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return value.isEmpty ? nil : value
        }
        return parts.prefix(3).joined(separator: " · ")
    }

    func coverFile(for record: StuffRecord) -> StuffFile? {
        guard let imageField = categories[record.category]?.imageField else {
            return record.files.first { $0.isImage }
        }
        return record.files.first { $0.field == imageField } ?? record.files.first { $0.isImage }
    }

    func loadLocalCache() async {
        if let snapshot = await store.loadSnapshot() {
            apply(snapshot)
            statusText = "Offline cache loaded"
        }
        if let changes = await store.loadLastChanges() {
            apply(changes)
        }
    }

    func sync() async {
        guard !isSyncing else { return }
        isSyncing = true
        errorMessage = nil
        statusText = "Syncing"
        do {
            await StuffCookieBridge.syncWebCookiesToURLSession()
            let summary = try await client.pullChanges { [weak self] message in
                Task { @MainActor in self?.statusText = message }
            }
            await loadLocalCache()
            markSyncedNow()
            statusText = "Synced · \(summary.fileText)"
        } catch {
            errorMessage = error.localizedDescription
            statusText = "Sync failed"
        }
        isSyncing = false
    }

    private func markSyncedNow() {
        let now = Date()
        lastSyncedAt = now
        UserDefaults.standard.set(now, forKey: lastSyncedAtKey)
    }

    private func apply(_ snapshot: StuffMobileSnapshot) {
        categories = snapshot.categories
        records = snapshot.records.mapValues(sortRecords)
        if !categories.keys.contains(selectedCategory),
           let first = orderedCategories.first?.0 {
            selectedCategory = first
        }
    }

    private func apply(_ changes: StuffMobileChanges) {
        var merged = records
        for tombstone in changes.recordTombstones {
            merged[tombstone.category] = (merged[tombstone.category] ?? [])
                .filter { $0.id != tombstone.recordID }
        }
        for (category, changedRows) in changes.records {
            var byID = Dictionary(uniqueKeysWithValues: (merged[category] ?? []).map { ($0.id, $0) })
            for row in changedRows {
                byID[row.id] = row
            }
            merged[category] = sortRecords(Array(byID.values))
        }
        records = merged
    }

    private func sortRecords(_ rows: [StuffRecord]) -> [StuffRecord] {
        rows.sorted { lhs, rhs in
            let left = lhs.updatedAt ?? ""
            let right = rhs.updatedAt ?? ""
            if left == right {
                return title(for: lhs) < title(for: rhs)
            }
            return left > right
        }
    }
}
