import Foundation

struct PricePoint: Identifiable, Hashable {
    let start: Date
    let end: Date
    let eurPerMWh: Double

    var id: Date { start }

    /// Cents per kWh (the unit consumers actually see on their bill).
    var centsPerKWh: Double { eurPerMWh / 10.0 }
}

enum DayBucket: String, CaseIterable, Identifiable {
    case today = "Today"
    case tomorrow = "Tomorrow"
    var id: String { rawValue }
}

struct DayPrices {
    let day: DayBucket
    let points: [PricePoint]

    var isEmpty: Bool { points.isEmpty }

    var average: Double? {
        guard !points.isEmpty else { return nil }
        return points.map(\.centsPerKWh).reduce(0, +) / Double(points.count)
    }

    var min: PricePoint? { points.min(by: { $0.centsPerKWh < $1.centsPerKWh }) }
    var max: PricePoint? { points.max(by: { $0.centsPerKWh < $1.centsPerKWh }) }

    /// Four cheapest 15-min slots.
    var cheapest: Set<Date> {
        Set(points.sorted(by: { $0.centsPerKWh < $1.centsPerKWh }).prefix(4).map(\.start))
    }

    /// Four most expensive 15-min slots.
    var priciest: Set<Date> {
        Set(points.sorted(by: { $0.centsPerKWh > $1.centsPerKWh }).prefix(4).map(\.start))
    }
}
