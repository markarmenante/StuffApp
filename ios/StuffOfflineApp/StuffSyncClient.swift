import Foundation

actor StuffSyncClient {
    enum SyncError: Error {
        case badResponse(Int)
        case invalidFileURL(String)
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
        return try decoder.decode(T.self, from: data)
    }

    private func downloadMissingFiles(
        _ files: [StuffFile],
        progress: ((String) -> Void)?
    ) async throws {
        var downloaded = 0
        for file in files {
            if await store.hasFile(file) {
                continue
            }
            try await download(file)
            downloaded += 1
            if downloaded % 25 == 0 {
                progress?("Downloaded \(downloaded) files")
            }
        }
        if downloaded > 0 {
            progress?("Downloaded \(downloaded) files")
        }
    }

    private func download(_ file: StuffFile) async throws {
        guard let url = URL(string: file.url, relativeTo: StuffConfig.serverURL) else {
            throw SyncError.invalidFileURL(file.url)
        }
        let (tempURL, response) = try await session.download(from: url)
        try validate(response)
        try await store.saveDownloadedFile(tempURL: tempURL, for: file)
    }

    private func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            return
        }
        guard (200..<300).contains(http.statusCode) else {
            throw SyncError.badResponse(http.statusCode)
        }
    }
}
