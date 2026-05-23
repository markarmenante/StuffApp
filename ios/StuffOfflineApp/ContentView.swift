import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = StuffOfflineViewModel()
    @State private var showingWebApp = false
    @AppStorage("stuff.syncOnOpen") private var syncOnOpen = true

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.orderedCategories.isEmpty {
                    firstRunView
                } else {
                    StuffHomeView(
                        showingWebApp: $showingWebApp,
                        syncOnOpen: $syncOnOpen
                    )
                    .environmentObject(viewModel)
                    .toolbar(.hidden, for: .navigationBar)
                }
            }
        }
        .task {
            await viewModel.loadLocalCache()
            if syncOnOpen && !viewModel.records.isEmpty {
                await viewModel.sync()
            }
        }
        .sheet(isPresented: $showingWebApp, onDismiss: {
            Task { await viewModel.sync() }
        }) {
            NavigationStack {
                StuffWebView(url: StuffConfig.serverURL)
                    .ignoresSafeArea(.container, edges: .bottom)
                    .navigationTitle("Live Stuff")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("Done") {
                                showingWebApp = false
                            }
                        }
                    }
            }
        }
    }

    private var firstRunView: some View {
        VStack(alignment: .leading, spacing: 18) {
            appHeader

            Spacer()

            Image(systemName: "shippingbox")
                .font(.system(size: 42, weight: .semibold))
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 8) {
                Text("No offline cache yet")
                    .font(.title3.weight(.semibold))
                Text("Open the live Stuff app once, complete the sign-in in this app, tap Done, then sync to keep records and files on this iPhone.")
                    .foregroundStyle(.secondary)
            }

            if viewModel.isSyncing {
                HStack(spacing: 10) {
                    ProgressView()
                    Text(viewModel.statusText)
                        .foregroundStyle(.secondary)
                }
                .font(.footnote)
            } else {
                VStack(alignment: .leading, spacing: 3) {
                    Text(viewModel.errorMessage ?? viewModel.statusText)
                        .foregroundStyle(viewModel.errorMessage == nil ? Color.secondary : Color.red)
                    Text(viewModel.lastSyncedText)
                        .foregroundStyle(.secondary)
                }
                .font(.footnote)
            }

            HStack {
                Button {
                    showingWebApp = true
                } label: {
                    Label("Open Live Stuff", systemImage: "safari")
                }
                .buttonStyle(.borderedProminent)

                Button {
                    Task { await viewModel.sync() }
                } label: {
                    Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.isSyncing)
            }

            Spacer()
        }
        .padding()
        .toolbar(.hidden, for: .navigationBar)
    }

    private var appHeader: some View {
        HStack {
            Text("Stuff")
                .font(.system(size: 38, weight: .black))
            Spacer()
            headerActions
        }
    }

    private var headerActions: some View {
        HStack(spacing: 0) {
            Menu {
                Toggle("Sync on Open", isOn: $syncOnOpen)
                Text(syncOnOpen ? "Syncs when the app opens" : "Manual sync only")
            } label: {
                Image(systemName: "gearshape")
                    .frame(width: 42, height: 34)
            }
            .accessibilityLabel("Sync settings")

            Divider()
                .frame(height: 20)

            Button {
                showingWebApp = true
            } label: {
                Image(systemName: "safari")
                    .frame(width: 42, height: 34)
            }
            .accessibilityLabel("Open live web app")
        }
        .buttonStyle(.plain)
        .font(.title3.weight(.semibold))
        .foregroundStyle(.primary)
        .background(.regularMaterial, in: Capsule())
    }
}

struct StuffHomeView: View {
    @EnvironmentObject private var viewModel: StuffOfflineViewModel
    @Binding var showingWebApp: Bool
    @Binding var syncOnOpen: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            CategoryToolbar()
                .environmentObject(viewModel)
            RecordListView()
                .environmentObject(viewModel)
        }
        .background(Color(.systemGroupedBackground))
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("Stuff")
                .font(.system(size: 38, weight: .black))
            if let category = viewModel.categories[viewModel.selectedCategory] {
                Text(stuffCategoryDisplayName(viewModel.selectedCategory, category.name))
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            HStack(spacing: 0) {
                Menu {
                    Toggle("Sync on Open", isOn: $syncOnOpen)
                    Text(syncOnOpen ? "Syncs when the app opens" : "Manual sync only")
                } label: {
                    Image(systemName: "gearshape")
                        .frame(width: 42, height: 34)
                }
                .accessibilityLabel("Sync settings")

                Divider()
                    .frame(height: 20)

                Button {
                    showingWebApp = true
                } label: {
                    Image(systemName: "safari")
                        .frame(width: 42, height: 34)
                }
                .accessibilityLabel("Open live web app")
            }
            .buttonStyle(.plain)
            .font(.title3.weight(.semibold))
            .foregroundStyle(.primary)
            .background(.regularMaterial, in: Capsule())
        }
        .padding(.horizontal, 18)
        .padding(.top, 12)
        .padding(.bottom, 10)
        .background(Color(.systemGroupedBackground))
    }
}

struct CategoryToolbar: View {
    @EnvironmentObject private var viewModel: StuffOfflineViewModel

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 0) {
                ForEach(viewModel.orderedCategories, id: \.0) { slug, category in
                    Button {
                        viewModel.selectedCategory = slug
                    } label: {
                        VStack(spacing: 5) {
                            Image(systemName: stuffIconName(for: slug))
                                .font(.title2.weight(.medium))
                            Text(stuffCategoryDisplayName(slug, category.name))
                                .font(.caption.weight(.semibold))
                                .lineLimit(1)
                        }
                        .frame(width: 86, height: 68)
                        .foregroundStyle(viewModel.selectedCategory == slug ? Color.primary : Color.secondary)
                        .background(viewModel.selectedCategory == slug ? Color(.systemGray4) : Color(.systemGray5))
                    }
                    .buttonStyle(.plain)
                    Divider()
                        .frame(height: 68)
                }
            }
        }
        .background(Color(.systemGray5))
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(Color(.separator))
                .frame(height: 1)
        }
    }
}

struct RecordListView: View {
    @EnvironmentObject private var viewModel: StuffOfflineViewModel

    var body: some View {
        List(viewModel.selectedRecords) { record in
            NavigationLink {
                RecordDetailView(record: record)
                    .environmentObject(viewModel)
            } label: {
                RecordRowView(record: record)
                    .environmentObject(viewModel)
            }
        }
        .listStyle(.plain)
        .overlay {
            if viewModel.selectedRecords.isEmpty {
                ContentUnavailableView(
                    "No cached records",
                    systemImage: "arrow.triangle.2.circlepath",
                    description: Text("Tap Sync when you have a connection.")
                )
            }
        }
        .safeAreaInset(edge: .bottom) {
            syncBar
        }
    }

    private var syncBar: some View {
        HStack(spacing: 12) {
            if viewModel.isSyncing {
                ProgressView()
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(viewModel.errorMessage ?? viewModel.statusText)
                    .foregroundStyle(viewModel.errorMessage == nil ? Color.secondary : Color.red)
                    .lineLimit(1)
                Text(viewModel.lastSyncedText)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .font(.footnote)
            Spacer()
            Button {
                Task { await viewModel.sync() }
            } label: {
                Label("Sync", systemImage: "arrow.triangle.2.circlepath")
            }
            .buttonStyle(.borderedProminent)
            .disabled(viewModel.isSyncing)
        }
        .padding()
        .background(.bar)
    }
}

private func stuffIconName(for category: String) -> String {
    switch category {
    case "watches": return "clock"
    case "coins": return "circle.hexagongrid"
    case "properties": return "house"
    case "credit_cards": return "creditcard"
    case "persons": return "person.2"
    case "cameras": return "camera"
    case "lenses": return "camera.aperture"
    case "pens": return "pencil.tip"
    case "art": return "paintpalette"
    case "vehicles": return "car"
    case "recordings": return "music.note"
    case "audio": return "hifispeaker"
    case "rifles": return "scope"
    default: return "shippingbox"
    }
}

private func stuffCategoryDisplayName(_ slug: String, _ fallback: String) -> String {
    switch slug {
    case "properties": return "Property"
    case "credit_cards": return "Cards"
    case "persons": return "People"
    case "recordings": return "Music"
    default: return fallback
    }
}

struct RecordRowView: View {
    @EnvironmentObject private var viewModel: StuffOfflineViewModel
    let record: StuffRecord
    @State private var imageURL: URL?

    var body: some View {
        HStack(spacing: 12) {
            thumbnail
            VStack(alignment: .leading, spacing: 4) {
                Text(viewModel.title(for: record))
                    .font(.headline)
                    .lineLimit(2)
                Text(viewModel.subtitle(for: record))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .task {
            if let cover = viewModel.coverFile(for: record) {
                imageURL = await viewModel.localURL(for: cover)
            }
        }
    }

    private var thumbnail: some View {
        Group {
            if let imageURL {
                AsyncImage(url: imageURL) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    Image(systemName: "photo").foregroundStyle(.secondary)
                }
            } else {
                Image(systemName: "photo").foregroundStyle(.secondary)
            }
        }
        .frame(width: 58, height: 58)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 8))
    }
}

struct RecordDetailView: View {
    @EnvironmentObject private var viewModel: StuffOfflineViewModel
    let record: StuffRecord
    @State private var showingEditor = false
    @State private var coverURL: URL?

    var body: some View {
        List {
            if let coverURL {
                AsyncImage(url: coverURL) { image in
                    image
                        .resizable()
                        .scaledToFit()
                } placeholder: {
                    ProgressView()
                }
                .frame(maxWidth: .infinity)
                .listRowInsets(EdgeInsets())
            }

            Section("Details") {
                ForEach(displayFields, id: \.0) { label, value in
                    HStack(alignment: .top) {
                        Text(label)
                            .foregroundStyle(.secondary)
                        Spacer(minLength: 20)
                        Text(value)
                            .multilineTextAlignment(.trailing)
                    }
                }
            }

            if !record.files.isEmpty {
                Section("Files") {
                    ForEach(record.files) { file in
                        FileRowView(file: file)
                    }
                }
            }
        }
        .navigationTitle(viewModel.title(for: record))
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Edit Live") {
                    showingEditor = true
                }
            }
        }
        .task {
            if let cover = viewModel.coverFile(for: record) {
                coverURL = await viewModel.localURL(for: cover)
            }
        }
        .sheet(isPresented: $showingEditor, onDismiss: {
            Task { await viewModel.sync() }
        }) {
            NavigationStack {
                StuffWebView(url: viewModel.detailURL(for: record))
                    .ignoresSafeArea(.container, edges: .bottom)
                    .navigationTitle("Edit Live")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("Done") {
                                showingEditor = false
                            }
                        }
                    }
            }
        }
    }

    private var displayFields: [(String, String)] {
        guard let fields = viewModel.categories[record.category]?.fields else {
            return []
        }
        return fields.compactMap { field in
            guard field.type != "file" else { return nil }
            let value = record.data[field.name]?.displayString
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return value.isEmpty ? nil : (field.label, value)
        }
    }
}

struct FileRowView: View {
    @EnvironmentObject private var viewModel: StuffOfflineViewModel
    let file: StuffFile
    @State private var localURL: URL?

    var body: some View {
        HStack {
            Image(systemName: file.isImage ? "photo" : "doc")
                .foregroundStyle(.secondary)
            VStack(alignment: .leading) {
                Text(file.label.isEmpty ? file.filename : file.label)
                Text(file.filename)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            if localURL != nil {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            }
        }
        .task {
            localURL = await viewModel.localURL(for: file)
        }
    }
}
