import Foundation
import SwiftUI

@MainActor
final class PricesViewModel: ObservableObject {
    @Published var todayPoints: [PricePoint] = []
    @Published var tomorrowPoints: [PricePoint] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var lastUpdated: Date?

    private let calendar: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "Europe/Riga") ?? .current
        return cal
    }()

    func day(_ bucket: DayBucket) -> DayPrices {
        DayPrices(day: bucket, points: bucket == .today ? todayPoints : tomorrowPoints)
    }

    func hasTomorrow() -> Bool { !tomorrowPoints.isEmpty }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let all = try await PriceService.shared.fetch()
            let now = Date()
            let startOfToday = calendar.startOfDay(for: now)
            let startOfTomorrow = calendar.date(byAdding: .day, value: 1, to: startOfToday)!
            let startOfDayAfter = calendar.date(byAdding: .day, value: 2, to: startOfToday)!

            todayPoints = all.filter { $0.start >= startOfToday && $0.start < startOfTomorrow }
            tomorrowPoints = all.filter { $0.start >= startOfTomorrow && $0.start < startOfDayAfter }
            lastUpdated = Date()
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }
}
