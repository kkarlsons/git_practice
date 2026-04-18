import SwiftUI
import Charts

struct ContentView: View {
    @StateObject private var vm = PricesViewModel()
    @State private var selected: DayBucket = .today

    var body: some View {
        NavigationStack {
            ZStack {
                backgroundGradient.ignoresSafeArea()
                content
            }
            .navigationTitle("Electricity")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await vm.load() }
                    } label: {
                        if vm.isLoading {
                            ProgressView()
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                    .disabled(vm.isLoading)
                }
            }
        }
        .task { await vm.load() }
    }

    private var backgroundGradient: some View {
        LinearGradient(
            colors: [Color(.systemBackground), Color.blue.opacity(0.08), Color.purple.opacity(0.05)],
            startPoint: .top, endPoint: .bottom
        )
    }

    @ViewBuilder
    private var content: some View {
        if vm.isLoading && vm.todayPoints.isEmpty {
            ProgressView("Loading prices…")
                .controlSize(.large)
        } else if let err = vm.errorMessage, vm.todayPoints.isEmpty {
            ErrorView(message: err) { Task { await vm.load() } }
        } else {
            ScrollView {
                VStack(spacing: 16) {
                    dayPicker
                    let day = vm.day(selected)
                    if day.isEmpty {
                        EmptyDayView(day: selected)
                            .padding(.top, 40)
                    } else {
                        HeroCard(day: day)
                        ChartCard(day: day)
                        LegendRow()
                        PriceList(day: day)
                    }
                    if let updated = vm.lastUpdated {
                        Text("Updated \(updated.formatted(date: .omitted, time: .shortened))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.top, 8)
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 24)
            }
            .refreshable { await vm.load() }
        }
    }

    private var dayPicker: some View {
        Picker("", selection: $selected) {
            ForEach(DayBucket.allCases) { d in
                Text(d.rawValue).tag(d)
            }
        }
        .pickerStyle(.segmented)
        .padding(.top, 4)
    }
}

// MARK: - Hero card

private struct HeroCard: View {
    let day: DayPrices

    private var currentPoint: PricePoint? {
        guard day.day == .today else { return nil }
        let now = Date()
        return day.points.first { $0.start <= now && now < $0.end }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(day.day == .today ? "Right now" : "Tomorrow", systemImage: day.day == .today ? "bolt.fill" : "sun.max.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
            }

            if let p = currentPoint {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(formattedPrice(p.centsPerKWh))
                        .font(.system(size: 52, weight: .bold, design: .rounded))
                        .foregroundStyle(PriceColor.color(for: p, in: day))
                    Text("¢/kWh")
                        .font(.title3.weight(.medium))
                        .foregroundStyle(.secondary)
                }
                Text("for \(p.start.formatted(date: .omitted, time: .shortened))–\(p.end.formatted(date: .omitted, time: .shortened))")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else if let avg = day.average {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(formattedPrice(avg))
                        .font(.system(size: 52, weight: .bold, design: .rounded))
                    Text("¢/kWh avg")
                        .font(.title3.weight(.medium))
                        .foregroundStyle(.secondary)
                }
            }

            HStack(spacing: 12) {
                if let lo = day.min {
                    Stat(icon: "arrow.down", title: "Cheapest", value: formattedPrice(lo.centsPerKWh), sub: lo.start.formatted(date: .omitted, time: .shortened), tint: .green)
                }
                if let hi = day.max {
                    Stat(icon: "arrow.up", title: "Priciest", value: formattedPrice(hi.centsPerKWh), sub: hi.start.formatted(date: .omitted, time: .shortened), tint: .red)
                }
            }
        }
        .padding(20)
        .background(RoundedRectangle(cornerRadius: 24, style: .continuous)
            .fill(.ultraThinMaterial)
            .shadow(color: .black.opacity(0.08), radius: 12, y: 6))
    }
}

private struct Stat: View {
    let icon: String
    let title: String
    let value: String
    let sub: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(title, systemImage: icon)
                .font(.caption.weight(.semibold))
                .foregroundStyle(tint)
            Text("\(value) ¢/kWh")
                .font(.headline)
            Text(sub)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(tint.opacity(0.12)))
    }
}

// MARK: - Chart

private struct ChartCard: View {
    let day: DayPrices

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("15-minute prices")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)

            Chart {
                ForEach(day.points) { p in
                    AreaMark(
                        x: .value("Time", p.start),
                        yStart: .value("Min", 0),
                        yEnd: .value("Price", p.centsPerKWh)
                    )
                    .foregroundStyle(LinearGradient(
                        colors: [.accentColor.opacity(0.35), .accentColor.opacity(0.05)],
                        startPoint: .top, endPoint: .bottom))
                    .interpolationMethod(.monotone)

                    LineMark(
                        x: .value("Time", p.start),
                        y: .value("Price", p.centsPerKWh)
                    )
                    .foregroundStyle(Color.accentColor)
                    .interpolationMethod(.monotone)
                }

                ForEach(day.points.filter { day.cheapest.contains($0.start) }) { p in
                    PointMark(x: .value("Time", p.start), y: .value("Price", p.centsPerKWh))
                        .foregroundStyle(.green)
                        .symbolSize(80)
                }

                ForEach(day.points.filter { day.priciest.contains($0.start) }) { p in
                    PointMark(x: .value("Time", p.start), y: .value("Price", p.centsPerKWh))
                        .foregroundStyle(.red)
                        .symbolSize(80)
                }

                if day.day == .today {
                    RuleMark(x: .value("Now", Date()))
                        .foregroundStyle(.primary.opacity(0.5))
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                }
            }
            .chartXAxis {
                AxisMarks(values: .stride(by: .hour, count: 3)) { value in
                    AxisGridLine()
                    AxisValueLabel(format: .dateTime.hour())
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading) { _ in
                    AxisGridLine()
                    AxisValueLabel()
                }
            }
            .frame(height: 220)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: 24, style: .continuous)
            .fill(.ultraThinMaterial)
            .shadow(color: .black.opacity(0.06), radius: 10, y: 4))
    }
}

// MARK: - Legend

private struct LegendRow: View {
    var body: some View {
        HStack(spacing: 16) {
            LegendDot(color: .green, text: "4 cheapest")
            LegendDot(color: .red, text: "4 priciest")
            Spacer()
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 4)
    }
}

private struct LegendDot: View {
    let color: Color
    let text: String
    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(text)
        }
    }
}

// MARK: - List

private struct PriceList: View {
    let day: DayPrices

    var body: some View {
        VStack(spacing: 6) {
            ForEach(day.points) { p in
                PriceRow(point: p, day: day)
            }
        }
    }
}

private struct PriceRow: View {
    let point: PricePoint
    let day: DayPrices

    private var isCheap: Bool { day.cheapest.contains(point.start) }
    private var isExpensive: Bool { day.priciest.contains(point.start) }
    private var isNow: Bool {
        day.day == .today && point.start <= Date() && Date() < point.end
    }

    var body: some View {
        HStack(spacing: 12) {
            // Rank badge
            if isCheap {
                badge("leaf.fill", color: .green)
            } else if isExpensive {
                badge("flame.fill", color: .red)
            } else {
                badge("clock", color: .secondary)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("\(point.start.formatted(date: .omitted, time: .shortened)) – \(point.end.formatted(date: .omitted, time: .shortened))")
                    .font(.callout.weight(isNow ? .bold : .regular))
                if isNow {
                    Text("Now")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(Color.accentColor))
                }
            }

            Spacer()

            // Price bar
            PriceBar(value: point.centsPerKWh,
                     min: day.min?.centsPerKWh ?? 0,
                     max: day.max?.centsPerKWh ?? 1,
                     color: PriceColor.color(for: point, in: day))
                .frame(width: 80, height: 8)

            Text("\(formattedPrice(point.centsPerKWh)) ¢")
                .font(.callout.monospacedDigit().weight(.semibold))
                .foregroundStyle(PriceColor.color(for: point, in: day))
                .frame(width: 64, alignment: .trailing)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(rowBackground)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(isNow ? Color.accentColor.opacity(0.6) : .clear, lineWidth: 1.5)
        )
    }

    private var rowBackground: some ShapeStyle {
        if isCheap { return AnyShapeStyle(Color.green.opacity(0.12)) }
        if isExpensive { return AnyShapeStyle(Color.red.opacity(0.12)) }
        return AnyShapeStyle(Color(.systemBackground).opacity(0.6))
    }

    @ViewBuilder
    private func badge(_ symbol: String, color: Color) -> some View {
        Image(systemName: symbol)
            .font(.footnote.weight(.bold))
            .foregroundStyle(color)
            .frame(width: 28, height: 28)
            .background(Circle().fill(color.opacity(0.15)))
    }
}

private struct PriceBar: View {
    let value: Double
    let min: Double
    let max: Double
    let color: Color

    var body: some View {
        GeometryReader { geo in
            let range = Swift.max(max - min, 0.0001)
            let pct = (value - min) / range
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.15))
                Capsule().fill(color)
                    .frame(width: Swift.max(4, geo.size.width * pct))
            }
        }
    }
}

// MARK: - Error / empty

private struct ErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text("Couldn't load prices")
                .font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Try again", action: retry)
                .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

private struct EmptyDayView: View {
    let day: DayBucket
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "clock.badge.questionmark")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text(day == .tomorrow ? "Tomorrow's prices aren't published yet" : "No prices available")
                .font(.headline)
            Text(day == .tomorrow ? "Nordpool usually publishes tomorrow around 13:00 CET." : "Pull down to refresh.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}

// MARK: - Color scale

enum PriceColor {
    static func color(for point: PricePoint, in day: DayPrices) -> Color {
        guard let lo = day.min?.centsPerKWh, let hi = day.max?.centsPerKWh, hi > lo else {
            return .accentColor
        }
        let t = max(0, min(1, (point.centsPerKWh - lo) / (hi - lo)))
        // Hue sweep: green (0.33) → amber (0.12) → red (0.0)
        let hue = 0.33 * (1 - t)
        return Color(hue: hue, saturation: 0.75, brightness: 0.85)
    }
}

// MARK: - Formatting helpers

func formattedPrice(_ cents: Double) -> String {
    String(format: "%.2f", cents)
}

#Preview {
    ContentView()
}
