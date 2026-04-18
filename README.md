# Volts — Latvian Electricity Prices

A small, nice-looking SwiftUI iPhone app that shows Nordpool 15-minute electricity prices for **today** and **tomorrow** in Latvia.

Data source: `https://nordpool.didnt.work/nordpool-lv.csv`

## Features

- Today / Tomorrow toggle (tomorrow appears after Nordpool publishes, usually ~13:00 CET)
- Smooth area + line chart of 15-minute prices
- "Right now" hero card with the current slot highlighted
- **Green leaf** markers on the 4 cheapest 15-min periods
- **Red flame** markers on the 4 most expensive 15-min periods
- Rows colour-shift from green → amber → red based on relative price
- Pull-to-refresh and a refresh toolbar button
- Prices shown in ¢/kWh (converted from the Nordpool EUR/MWh feed)

## Requirements

- macOS with **Xcode 15 or newer** (iOS 17 SDK)
- An **iPhone** running iOS 17+
- A free Apple ID (no paid developer account needed for 7-day on-device signing)

## Deploy to your phone

1. Open `ElectricityPrices.xcodeproj` in Xcode.
2. Select the **ElectricityPrices** target → *Signing & Capabilities*.
3. Sign in with your Apple ID under *Team* and let Xcode create an automatic signing profile. If the bundle id `work.didnt.ElectricityPrices` is taken, change `PRODUCT_BUNDLE_IDENTIFIER` in the target's Build Settings to something unique like `com.<yourname>.volts`.
4. Plug your iPhone in via USB (or pair it wirelessly).
5. In Xcode's device menu, pick your iPhone, then press ⌘R.
6. First launch on-device: on the iPhone go to *Settings → General → VPN & Device Management* and trust your developer profile.

## Project layout

```
ElectricityPrices.xcodeproj/          Xcode project
ElectricityPrices/
  ElectricityPricesApp.swift          App entry
  ContentView.swift                   UI (chart, hero, list)
  PricesViewModel.swift               Observable state
  PriceService.swift                  URLSession fetch + CSV parsing
  Models.swift                        PricePoint, DayPrices
  Assets.xcassets/                    App icon + accent colour
  Preview Content/                    Preview-only assets
project.yml                           XcodeGen spec (optional, see below)
```

## Regenerating the project with XcodeGen (optional)

If the included `.xcodeproj` misbehaves, you can regenerate it from `project.yml`:

```bash
brew install xcodegen
xcodegen generate
```

## Notes

- The CSV parser auto-detects `,` / `;` / `\t` delimiters and tolerates several header name variants (`start`, `timestamp`, `deliveryStart`, …). If the upstream feed ever changes, only `PriceService.swift` should need an update.
- All price math is done in local time for `Europe/Riga` to bucket prices into today vs. tomorrow correctly.
