import Foundation

enum PriceServiceError: Error, LocalizedError {
    case badResponse(Int)
    case emptyCSV
    case missingColumns

    var errorDescription: String? {
        switch self {
        case .badResponse(let code): return "Server returned HTTP \(code)."
        case .emptyCSV: return "Price feed was empty."
        case .missingColumns: return "Couldn't find time/price columns in the CSV."
        }
    }
}

actor PriceService {
    static let shared = PriceService()

    private let url = URL(string: "https://nordpool.didnt.work/nordpool-lv.csv")!
    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func fetch() async throws -> [PricePoint] {
        var req = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        req.setValue("ElectricityPricesApp/1.0", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await session.data(for: req)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw PriceServiceError.badResponse(http.statusCode)
        }
        guard let text = String(data: data, encoding: .utf8), !text.isEmpty else {
            throw PriceServiceError.emptyCSV
        }
        return try CSVParser.parsePrices(from: text)
    }
}

enum CSVParser {
    static func parsePrices(from text: String) throws -> [PricePoint] {
        let rawLines = text.split(whereSeparator: { $0 == "\n" || $0 == "\r" })
            .map { String($0).trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        guard rawLines.count > 1 else { throw PriceServiceError.emptyCSV }

        let delimiter = detectDelimiter(rawLines[0])
        let header = splitLine(rawLines[0], delimiter: delimiter).map { normalize($0) }

        let startIdx = firstIndex(in: header, matching: ["start", "begin", "from", "deliverystart", "timestamp", "datetime", "time", "date"])
        let endIdx = firstIndex(in: header, matching: ["end", "to", "deliveryend"])
        let priceIdx = firstIndex(in: header, matching: ["price", "value", "eurmwh", "eurperMWh".lowercased(), "eur", "cost"])

        guard let t = startIdx, let p = priceIdx else {
            throw PriceServiceError.missingColumns
        }

        var points: [PricePoint] = []
        points.reserveCapacity(rawLines.count)

        for line in rawLines.dropFirst() {
            let cols = splitLine(line, delimiter: delimiter)
            guard cols.count > max(t, p) else { continue }
            guard let start = parseDate(cols[t]) else { continue }
            guard let price = parseDouble(cols[p]) else { continue }
            let end: Date = {
                if let endIdx, cols.count > endIdx, let d = parseDate(cols[endIdx]) {
                    return d
                }
                return start.addingTimeInterval(15 * 60)
            }()
            points.append(PricePoint(start: start, end: end, eurPerMWh: price))
        }

        points.sort(by: { $0.start < $1.start })
        return points
    }

    // MARK: - Helpers

    private static func normalize(_ s: String) -> String {
        s.lowercased()
            .replacingOccurrences(of: "_", with: "")
            .replacingOccurrences(of: "-", with: "")
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "/", with: "")
            .replacingOccurrences(of: "\"", with: "")
    }

    private static func firstIndex(in header: [String], matching needles: [String]) -> Int? {
        for n in needles {
            if let i = header.firstIndex(where: { $0.contains(n) }) { return i }
        }
        return nil
    }

    private static func detectDelimiter(_ headerLine: String) -> Character {
        let semis = headerLine.filter { $0 == ";" }.count
        let commas = headerLine.filter { $0 == "," }.count
        let tabs = headerLine.filter { $0 == "\t" }.count
        if tabs > semis && tabs > commas { return "\t" }
        return semis > commas ? ";" : ","
    }

    /// Splits a CSV line respecting simple double-quoted fields.
    private static func splitLine(_ line: String, delimiter: Character) -> [String] {
        var fields: [String] = []
        var current = ""
        var inQuotes = false
        for ch in line {
            if ch == "\"" { inQuotes.toggle(); continue }
            if ch == delimiter && !inQuotes {
                fields.append(current)
                current = ""
            } else {
                current.append(ch)
            }
        }
        fields.append(current)
        return fields.map { $0.trimmingCharacters(in: .whitespaces) }
    }

    private static func parseDouble(_ raw: String) -> Double? {
        let cleaned = raw
            .replacingOccurrences(of: "\u{00A0}", with: "")
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: ",", with: ".")
        return Double(cleaned)
    }

    private static let isoFormatters: [ISO8601DateFormatter] = {
        let opts: [ISO8601DateFormatter.Options] = [
            [.withInternetDateTime, .withFractionalSeconds],
            [.withInternetDateTime],
            [.withInternetDateTime, .withTimeZone],
            [.withFullDate, .withTime, .withDashSeparatorInDate, .withColonSeparatorInTime, .withSpaceBetweenDateAndTime]
        ]
        return opts.map { o in
            let f = ISO8601DateFormatter()
            f.formatOptions = o
            return f
        }
    }()

    private static let fallbackFormatters: [DateFormatter] = {
        let patterns = [
            "yyyy-MM-dd'T'HH:mm:ssXXXXX",
            "yyyy-MM-dd'T'HH:mm:ssZZZZZ",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd HH:mm:ssXXXXX",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd HH:mm",
            "dd.MM.yyyy HH:mm",
            "dd/MM/yyyy HH:mm"
        ]
        return patterns.map { p in
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.dateFormat = p
            f.timeZone = TimeZone(identifier: "Europe/Riga")
            return f
        }
    }()

    private static func parseDate(_ raw: String) -> Date? {
        let s = raw.trimmingCharacters(in: CharacterSet(charactersIn: "\" "))
        for f in isoFormatters {
            if let d = f.date(from: s) { return d }
        }
        for f in fallbackFormatters {
            if let d = f.date(from: s) { return d }
        }
        if let epoch = Double(s) {
            return Date(timeIntervalSince1970: epoch > 1_000_000_000_000 ? epoch / 1000 : epoch)
        }
        return nil
    }
}
