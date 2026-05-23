import Foundation

actor StuffLocalStore {
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private let rootURL: URL
    private let filesURL: URL

    init(fileManager: FileManager = .default) throws {
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        decoder = JSONDecoder()

        let appSupport = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        rootURL = appSupport.appendingPathComponent(
            StuffConfig.localFolderName,
            isDirectory: true
        )
        filesURL = rootURL.appendingPathComponent(
            StuffConfig.filesFolderName,
            isDirectory: true
        )
        try fileManager.createDirectory(at: rootURL, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: filesURL, withIntermediateDirectories: true)
    }

    var localFilesURL: URL {
        filesURL
    }

    func saveSnapshot(_ snapshot: StuffMobileSnapshot) throws {
        try write(snapshot, to: "snapshot.json")
        try write(snapshot.maxUpdatedAt, to: "last-sync.json")
    }

    func saveChanges(_ changes: StuffMobileChanges) throws {
        try write(changes, to: "last-changes.json")
        try write(changes.maxUpdatedAt, to: "last-sync.json")
    }

    func loadSnapshot() -> StuffMobileSnapshot? {
        try? read("snapshot.json")
    }

    func loadLastChanges() -> StuffMobileChanges? {
        try? read("last-changes.json")
    }

    func lastSyncTime() -> String? {
        guard let value: String = try? read("last-sync.json") else {
            return nil
        }
        return value
    }

    func localURL(for file: StuffFile) -> URL {
        filesURL.appendingPathComponent(file.filename)
    }

    func hasFile(_ file: StuffFile) -> Bool {
        FileManager.default.fileExists(atPath: localURL(for: file).path)
    }

    func saveDownloadedFile(tempURL: URL, for file: StuffFile) throws {
        let destination = localURL(for: file)
        if FileManager.default.fileExists(atPath: destination.path) {
            try FileManager.default.removeItem(at: destination)
        }
        try FileManager.default.moveItem(at: tempURL, to: destination)
    }

    func removeLocalFile(named filename: String) {
        let destination = filesURL.appendingPathComponent(filename)
        try? FileManager.default.removeItem(at: destination)
    }

    private func write<T: Encodable>(_ value: T, to filename: String) throws {
        let data = try encoder.encode(value)
        try data.write(to: rootURL.appendingPathComponent(filename), options: .atomic)
    }

    private func read<T: Decodable>(_ filename: String) throws -> T {
        let data = try Data(contentsOf: rootURL.appendingPathComponent(filename))
        return try decoder.decode(T.self, from: data)
    }
}
