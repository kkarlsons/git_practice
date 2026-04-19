# EngyCell Prices — Latvia electricity

A small, premium-feeling app in the **Engycell brand** that shows **15-minute Nord Pool electricity prices** for today and tomorrow in Latvia, with the **4 cheapest** and **4 most expensive** slots highlighted — plus a crown on the absolute cheapest and a flame on the absolute priciest 15-minute window of the day.

Colors, type and mark follow the Engycell Brand Style Guide:
- Deep teal `#071C23` surfaces
- Vivid green `#98BD09` accents
- Secondary teal `#03413C`
- Off-white `#EEEEEE` type
- Kumbh Sans (400 / 600 / 700)

Two versions live in this repo:

- **Web app** (`docs/`) — opens in Safari, can be added to your iPhone home screen, no Xcode / no Mac required. **This is the easy one.**
- **Native iOS app** (`ElectricityPrices/` + `ElectricityPrices.xcodeproj`) — requires a Mac + Xcode. See bottom of this file.

---

## 🟢 Easy path — put the web app on your iPhone

### Step 1 — Turn on GitHub Pages (one-time, ~30 seconds)
1. On GitHub, open this repository: **`kkarlsons/git_practice`**.
2. Click **Settings** (top tab).
3. In the left sidebar click **Pages**.
4. Under *Build and deployment*:
   - **Source:** *Deploy from a branch*
   - **Branch:** pick `claude/electricity-price-app-gztas` (or `main` if you've merged it) and folder **`/docs`**.
   - Click **Save**.
5. Wait ~1 minute. The page will show a green box with a URL that looks like:
   `https://kkarlsons.github.io/git_practice/`
6. That's the app. Open it in any browser to test.

### Step 2 — Add it to your iPhone home screen
1. Open the URL above in **Safari on your iPhone** (it has to be Safari, not Chrome).
2. Tap the **Share** button (the square with an arrow pointing up).
3. Scroll down and tap **Add to Home Screen**.
4. Tap **Add** (top right).

Done — there's now a **EngyCell** icon on your home screen. Tap it and it opens full-screen, no browser bars, just like a native app. It will remember your pick between Today/Tomorrow and refresh every time you open it.

### If prices don't load
The app tries the Nordpool CSV directly first, then falls back to three public CORS proxies. If all four fail, tap the refresh button. The error shown on screen will say which step failed.

---

## What the app shows
- **Today / Tomorrow** toggle (tomorrow usually appears around 14:00 Riga time)
- A hero card with the **current 15-min slot** price in ¢/kWh
- A smooth area + line **chart** of all 96 slots
- 🌿 Green markers on the **4 cheapest** slots
- 🔥 Red markers on the **4 most expensive** slots
- A scrollable list with a per-slot price bar and "NOW" badge
- Pull-to-refresh, plus a refresh button
- Automatic dark mode that follows your phone's setting

---

## 🔵 Hard path — native iOS app (needs a Mac + Xcode)

If you ever want to build the native version, the Xcode project is in this repo:

1. Open `ElectricityPrices.xcodeproj` in Xcode 15+.
2. Select the **ElectricityPrices** target → *Signing & Capabilities* → sign in with your Apple ID under *Team*.
3. If the bundle id `work.didnt.ElectricityPrices` is taken, change it to something unique.
4. Plug in your iPhone, pick it in Xcode's device menu, press ⌘R.
5. On the iPhone: *Settings → General → VPN & Device Management* → trust your dev profile.

With a free Apple ID the app expires after 7 days; re-run ⌘R to refresh it.
