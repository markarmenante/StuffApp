import Foundation

struct StuffMobileSnapshot: Codable {
    let schemaVersion: Int
    let generatedAt: String
    let maxUpdatedAt: String
    let categories: [String: StuffCategory]
    let records: [String: [StuffRecord]]
    let files: [StuffFile]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case maxUpdatedAt = "max_updated_at"
        case categories
        case records
        case files
    }
}

struct StuffMobileChanges: Codable {
    let schemaVersion: Int
    let generatedAt: String
    let maxUpdatedAt: String
    let records: [String: [StuffRecord]]
    let files: [StuffFile]
    let recordTombstones: [StuffRecordTombstone]
    let fileTombstones: [StuffFileTombstone]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case maxUpdatedAt = "max_updated_at"
        case records
        case files
        case recordTombstones = "record_tombstones"
        case fileTombstones = "file_tombstones"
    }
}

struct StuffCategory: Codable {
    let name: String
    let singular: String
    let labelField: String
    let sublabelField: String
    let imageField: String
    let fields: [StuffField]

    enum CodingKeys: String, CodingKey {
        case name
        case singular
        case labelField = "label_field"
        case sublabelField = "sublabel_field"
        case imageField = "image_field"
        case fields
    }
}

struct StuffField: Codable {
    let name: String
    let label: String
    let type: String
    let options: [String]?
    let readonly: Bool?
}

struct StuffRecord: Codable, Identifiable {
    let category: String
    let id: String
    let updatedAt: String?
    let sortIndex: Int?
    let data: [String: StuffValue]
    let files: [StuffFile]

    enum CodingKeys: String, CodingKey {
        case category
        case id
        case updatedAt = "updated_at"
        case sortIndex = "sort_index"
        case data
        case files
    }
}

struct StuffFile: Codable, Identifiable {
    var id: String { filename }

    let filename: String
    let label: String
    let field: String
    let docSet: String
    let isImage: Bool
    let url: String
    let thumbURL: String?
    let size: Int?
    let mtime: String?

    enum CodingKeys: String, CodingKey {
        case filename
        case label
        case field
        case docSet = "doc_set"
        case isImage = "is_image"
        case url
        case thumbURL = "thumb_url"
        case size
        case mtime
    }
}

struct StuffRecordTombstone: Codable {
    let category: String
    let recordID: String
    let deletedAt: String

    enum CodingKeys: String, CodingKey {
        case category
        case recordID = "record_id"
        case deletedAt = "deleted_at"
    }
}

struct StuffFileTombstone: Codable {
    let category: String?
    let filename: String?
    let label: String?
    let deletedAt: String?

    enum CodingKeys: String, CodingKey {
        case category
        case filename
        case label
        case deletedAt = "deleted_at"
    }
}

enum StuffValue: Codable, Equatable {
    case string(String)
    case double(Double)
    case int(Int)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else {
            self = .string(try container.decode(String.self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .double(let value): try container.encode(value)
        case .int(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var displayString: String {
        switch self {
        case .string(let value): return value
        case .double(let value): return String(value)
        case .int(let value): return String(value)
        case .bool(let value): return value ? "Yes" : "No"
        case .null: return ""
        }
    }
}
