import Foundation

actor StuffSyncClient {
    enum SyncError: Error {
        case badResponse(Int)
        case badResponseAt(String, Int)
        case invalidFileURL(String)
        case signInRequired
        case invalidJSON(String)
    }

    private let session: URLSession
    private let store: StuffLocalStore
    private let decoder = JSONDecoder()

    init(session: URLSession = .shared, store: StuffLocalStore) {
        self.session = session
        self.store = store
    }

    func bootstrap(progress: ((String) -> Void)? = nil) async throws {
        progress?("Downloading Stuff snapshot")
        let snapshot: StuffMobileSnapshot = try await getJSON("/api/mobile/snapshot")
        try await store.saveSnapshot(snapshot)
        try await downloadMissingFiles(snapshot.files, progress: progress)
    }

    func pullChanges(progress: ((String) -> Void)? = nil) async throws {
        guard let lastSync = await store.lastSyncTime() else {
            try await bootstrap(progress: progress)
            return
        }
        progress?("Checking Stuff changes")
        let encoded = lastSync.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? lastSync
        let changes: StuffMobileChanges = try await getJSON("/api/mobile/changes?since=\(encoded)")
        try await store.saveChanges(changes)
        try await downloadMissingFiles(changes.files, progress: progress)
        for tombstone in changes.fileTombstones {
            if let filename = tombstone.filename {
                await store.removeLocalFile(named: filename)
            }
        }
    }

    private func getJSON<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: path, relativeTo: StuffConfig.serverURL) else {
            throw SyncError.invalidFileURL(path)
        }
        let (data, response) = try await session.data(from: url)
        try validate(response)
        if let http = response as? HTTPURLResponse {
            let contentType = (http.value(forHTTPHeaderField: "Content-Type") ?? "").lowercased()
            if !contentType.contains("json") {
                throw SyncError.signInRequired
            }
        }
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw SyncError.invalidJSON(error.localizedDescription)
        }
    }

    private func downloadMissingFiles(
        _ files: [StuffFile],
        progress: ((String) -> Void)?
    ) async throws {
        var downloaded = 0
        var skipped = 0
        for file in files {
            if await store.hasFile(file) {
                continue
            }
            let didDownload = try await download(file)
            if didDownload {
                downloaded += 1
            } else {
                skipped += 1
            }
            if downloaded % 25 == 0 {
                progress?("Downloaded \(downloaded) files")
            }
        }
        if downloaded > 0 {
            progress?("Downloaded \(downloaded) files")
        }
        if skipped > 0 {
            progress?("Skipped \(skipped) missing files")
        }
    }

    private func download(_ file: StuffFile) async throws -> Bool {
        guard let url = URL(string: file.url, relativeTo: StuffConfig.serverURL) else {
            throw SyncError.invalidFileURL(file.url)
        }
        let (tempURL, response) = try await session.download(from: url)
        if let http = response as? HTTPURLResponse, http.statusCode == 404 {
            return false
        }
        try validate(response, path: url.path)
        try await store.saveDownloadedFile(tempURL: tempURL, for: file)
        return true
    }

    private func validate(_ response: URLResponse, path: String? = nil) throws {
        guard let http = response as? HTTPURLResponse else {
            return
        }
        guard (200..<300).contains(http.statusCode) else {
            if [401, 403].contains(http.statusCode) || (300..<400).contains(http.statusCode) {
                throw SyncError.signInRequired
            }
            if let path {
                throw SyncError.badResponseAt(path, http.statusCode)
            }
            throw SyncError.badResponse(http.statusCode)
        }
    }
}

extension StuffSyncClient.SyncError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .badResponse(let status):
            return "Stuff sync failed with HTTP \(status)."
        case .badResponseAt(let path, let status):
            return "Stuff sync failed with HTTP \(status) at \(path)."
        case .invalidFileURL(let path):
            return "Stuff sync found an invalid file URL: \(path)."
        case .signInRequired:
            return "Open Live Stuff, sign in, tap Done, then Sync."
        case .invalidJSON(let detail):
            return "Stuff returned data the iPhone app could not read: \(detail)"
        }
    }
}
