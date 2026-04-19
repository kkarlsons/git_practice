(() => {
  const CSV_URL = 'https://nordpool.didnt.work/nordpool-lv.csv';
  const SOURCES = [
    { name: 'direct',     url: CSV_URL },
    { name: 'corsproxy',  url: `https://corsproxy.io/?${encodeURIComponent(CSV_URL)}` },
    { name: 'allorigins', url: `https://api.allorigins.win/raw?url=${encodeURIComponent(CSV_URL)}` },
    { name: 'codetabs',   url: `https://api.codetabs.com/v1/proxy/?quest=${encodeURIComponent(CSV_URL)}` },
    { name: 'thingproxy', url: `https://thingproxy.freeboard.io/fetch/${CSV_URL}` },
  ];
  const TZ = 'Europe/Riga';
  const PER_SOURCE_TIMEOUT_MS = 8000;

  const $ = id => document.getElementById(id);
  const state = { selected: 'today', today: [], tomorrow: [], updatedAt: null, diag: [] };

  // ------------------------------ Networking

  function looksLikeCSV(text) {
    if (!text || text.length < 50) return false;
    const head = text.slice(0, 2000).toLowerCase();
    if (head.includes('<html') || head.includes('<!doctype')) return false;
    const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
    if (lines.length < 3) return false;
    return /[;,\t]/.test(lines[0]);
  }

  async function tryFetch(src) {
    const entry = { source: src.name, url: src.url, status: '-', bytes: 0, preview: '', ok: false, error: null };
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), PER_SOURCE_TIMEOUT_MS);
    try {
      const res = await fetch(src.url, {
        cache: 'no-store',
        signal: ctrl.signal,
        headers: { 'Accept': 'text/csv, text/plain, */*' },
        redirect: 'follow',
      });
      entry.status = res.status;
      const text = await res.text();
      entry.bytes = text.length;
      entry.preview = text.slice(0, 180).replace(/\s+/g, ' ').trim();
      if (!res.ok) { entry.error = `HTTP ${res.status}`; return entry; }
      if (!looksLikeCSV(text)) { entry.error = 'Did not look like CSV'; return entry; }
      entry.ok = true;
      entry.text = text;
      return entry;
    } catch (e) {
      entry.error = (e.name === 'AbortError') ? `timeout after ${PER_SOURCE_TIMEOUT_MS/1000}s` : (e.message || String(e));
      return entry;
    } finally { clearTimeout(timer); }
  }

  function setLoadingMsg(m) { const el = $('loading-msg'); if (el) el.textContent = m; }

  async function fetchCSV() {
    state.diag = [];
    for (let i = 0; i < SOURCES.length; i++) {
      const src = SOURCES[i];
      setLoadingMsg(`Trying ${src.name}… (${i+1}/${SOURCES.length})`);
      const entry = await tryFetch(src);
      state.diag.push(entry);
      if (entry.ok) return entry.text;
    }
    const msg = state.diag.map(d => `• ${d.source}: ${d.ok ? 'OK' : d.error} (${d.bytes}B)`).join('\n');
    throw new Error(`All sources failed.\n${msg}`);
  }

  // ------------------------------ CSV parsing with auto-unit-detection

  function parseCSV(text) {
    const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (lines.length < 2) throw new Error('CSV is empty');
    const delim = detectDelim(lines[0]);
    const header = splitLine(lines[0], delim).map(normalize);

    const startIdx = findCol(header, ['start','begin','from','deliverystart','timestamp','datetime','time','date']);
    const endIdx   = findCol(header, ['end','to','deliveryend']);
    const priceIdx = findCol(header, ['price','value','eurmwh','eurkwh','eur','cost','centkwh']);
    if (startIdx < 0 || priceIdx < 0) throw new Error("Couldn't find time/price columns in CSV");

    // Parse raw rows first (keep native unit).
    const raw = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = splitLine(lines[i], delim);
      if (cols.length <= Math.max(startIdx, priceIdx)) continue;
      const start = parseDate(cols[startIdx]);
      const price = parseNum(cols[priceIdx]);
      if (!start || Number.isNaN(price)) continue;
      const end = (endIdx >= 0 && cols[endIdx]) ? (parseDate(cols[endIdx]) || new Date(start.getTime() + 15*60*1000))
                                                : new Date(start.getTime() + 15*60*1000);
      raw.push({ start, end, native: price });
    }
    if (!raw.length) throw new Error('No rows parsed');

    // Determine multiplier to get ¢/kWh.
    const headerText = header[priceIdx] || '';
    const unit = detectUnit(headerText, raw);
    for (const r of raw) r.centsKWh = r.native * unit.mul;

    raw.sort((a, b) => a.start - b.start);
    return raw;
  }

  /** Detect unit from header hints + magnitude heuristic. Returns { mul, label }. */
  function detectUnit(header, rows) {
    // Header hints
    if (/centkwh|ckwh|cent_?per_?kwh/.test(header)) return { mul: 1,   label: '¢/kWh' };
    if (/eur.*mwh|mwh/.test(header))                return { mul: 0.1, label: 'EUR/MWh → ¢/kWh' };
    if (/eur.*kwh|kwh/.test(header))                return { mul: 100, label: 'EUR/kWh → ¢/kWh' };

    // Magnitude heuristic on median of |value|
    const abs = rows.map(r => Math.abs(r.native)).filter(v => v > 0).sort((a,b) => a-b);
    if (!abs.length) return { mul: 1, label: '¢/kWh' };
    const median = abs[Math.floor(abs.length / 2)];
    // Typical consumer prices: 2–30 ¢/kWh
    if (median >= 2 && median <= 60)   return { mul: 1,   label: '¢/kWh' };
    if (median > 60)                   return { mul: 0.1, label: 'EUR/MWh → ¢/kWh' };
    // median < 2 → likely EUR/kWh (0.02–0.30)
    return { mul: 100, label: 'EUR/kWh → ¢/kWh' };
  }

  function normalize(s) { return s.toLowerCase().replace(/["_\-\s/]/g, ''); }
  function findCol(header, needles) {
    for (const n of needles) {
      const i = header.findIndex(h => h.includes(n));
      if (i >= 0) return i;
    }
    return -1;
  }
  function detectDelim(line) {
    const s = (line.match(/;/g)||[]).length, c = (line.match(/,/g)||[]).length, t = (line.match(/\t/g)||[]).length;
    if (t > s && t > c) return '\t';
    return s > c ? ';' : ',';
  }
  function splitLine(line, delim) {
    const out = []; let cur = ''; let q = false;
    for (const ch of line) {
      if (ch === '"') { q = !q; continue; }
      if (ch === delim && !q) { out.push(cur.trim()); cur = ''; }
      else cur += ch;
    }
    out.push(cur.trim()); return out;
  }
  function parseNum(raw) {
    if (raw == null) return NaN;
    const cleaned = String(raw).replace(/[\s\u00a0]/g, '').replace(',', '.');
    return parseFloat(cleaned);
  }
  function parseDate(raw) {
    if (!raw) return null;
    const s = String(raw).trim().replace(/^"|"$/g, '');

    // Explicit TZ marker (Z or ±HH:MM) — use native parser directly.
    if (/[Zz]|[+-]\d{2}:?\d{2}(?:$|[^\d])/.test(s)) {
      const d = new Date(s);
      if (!isNaN(d)) return d;
    }

    // Naive "YYYY-MM-DD HH:MM[:SS]" — treat as Riga local (Nordpool day-ahead
    // publishes slots in local wall-clock time). Parsing as UTC would leak
    // the last 3 evening slots into "tomorrow" in Riga TZ.
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
    if (m) return rigaLocalToDate(+m[1], +m[2], +m[3], +m[4], +m[5], +(m[6]||0));

    const d = new Date(s);
    if (!isNaN(d)) return d;

    const epoch = Number(s);
    if (!Number.isNaN(epoch)) return new Date(epoch > 1e12 ? epoch : epoch * 1000);
    return null;
  }

  // Given Riga wall-clock components, return the correct UTC Date.
  const _rigaPartsFmt = new Intl.DateTimeFormat('en-GB', {
    timeZone: TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
  function rigaLocalToDate(y, mo, d, h, mi, s) {
    const guess = new Date(Date.UTC(y, mo-1, d, h, mi, s));
    const parts = _rigaPartsFmt.formatToParts(guess).reduce((o, p) => (o[p.type] = p.value, o), {});
    const rigaAsUTC = Date.UTC(+parts.year, +parts.month - 1, +parts.day,
                               +parts.hour === 24 ? 0 : +parts.hour,
                               +parts.minute, +parts.second);
    const offset = rigaAsUTC - guess.getTime();
    return new Date(guess.getTime() - offset);
  }

  // ------------------------------ Day bucketing (Europe/Riga)

  const ymdFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year:'numeric', month:'2-digit', day:'2-digit' });
  const rigaYMD = d => ymdFmt.format(d);
  function bucket(rows) {
    const today    = rigaYMD(new Date());
    const tomorrow = rigaYMD(new Date(Date.now() + 24*60*60*1000));
    const t = [], tm = [];
    for (const r of rows) {
      const d = rigaYMD(r.start);
      if (d === today) t.push(r);
      else if (d === tomorrow) tm.push(r);
    }
    return { today: t, tomorrow: tm };
  }

  // ------------------------------ Formatting

  const timeFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
  const fmtTime = d => timeFmt.format(d);
  const fmt2 = n => (n == null || Number.isNaN(n)) ? '—' : n.toFixed(2);

  // ------------------------------ Segmented control thumb

  function updateSegThumb() {
    const thumb = $('seg-thumb');
    if (!thumb) return;
    thumb.classList.toggle('right', state.selected === 'tomorrow');
  }

  // ------------------------------ Rendering

  function render() {
    const rows = state.selected === 'today' ? state.today : state.tomorrow;
    const content = $('content');
    $('loading').classList.add('hidden');

    if (!rows.length) {
      content.classList.remove('hidden');
      const isTomorrow = state.selected === 'tomorrow';
      setPill('normal', isTomorrow ? 'NOT PUBLISHED' : 'NO DATA');
      setHeroLabel(isTomorrow ? 'Tomorrow' : 'Today', false);
      setHeroValue('—', null);
      $('hero-sub').textContent = isTomorrow
        ? 'Usually published around 14:00 Riga'
        : 'Tap refresh to retry';
      $('hero-delta').textContent = '';
      $('hero-delta').className = 'hero-delta';
      $('hero-spark').innerHTML = '';
      if (isTomorrow) {
        $('insight-icon').textContent = '🕒';
        $('insight-title').textContent = 'Prices not yet published';
        $('insight-sub').textContent = 'Nordpool publishes tomorrow\'s prices around 14:00 Riga time. Check back later.';
        $('insight').classList.remove('hidden');
      } else {
        $('insight').classList.add('hidden');
      }
      $('stat-lo').textContent = '—'; $('stat-lo-sub').textContent = '';
      $('stat-hi').textContent = '—'; $('stat-hi-sub').textContent = '';
      $('chart').innerHTML = '';
      $('list').innerHTML = '';
      $('slot-count').textContent = '';
      return;
    }

    const prices = rows.map(r => r.centsKWh);
    const lo = Math.min(...prices);
    const hi = Math.max(...prices);
    const avg = prices.reduce((a,b) => a + b, 0) / prices.length;
    const loIdx = prices.indexOf(lo);
    const hiIdx = prices.indexOf(hi);

    const cheapestSorted = [...rows].sort((a,b) => a.centsKWh - b.centsKWh);
    const priciestSorted = [...rows].sort((a,b) => b.centsKWh - a.centsKWh);
    const cheapest = new Set(cheapestSorted.slice(0, 4).map(r => +r.start));
    const priciest = new Set(priciestSorted.slice(0, 4).map(r => +r.start));

    const now = new Date();
    const currentRow = state.selected === 'today'
      ? rows.find(r => r.start <= now && now < r.end)
      : null;

    // ---- Hero ----
    if (currentRow) {
      const key = +currentRow.start;
      const isCheap = cheapest.has(key);
      const isPricy = priciest.has(key);
      const variant = isCheap ? 'cheap' : isPricy ? 'pricy' : 'normal';
      const label = isCheap ? '🌿 CHEAP NOW' : isPricy ? '🔥 EXPENSIVE NOW' : '⚡ NORMAL';

      setPill(variant, label);
      setHeroLabel('Right now', true);
      setHeroValue(fmt2(currentRow.centsKWh), variant);
      $('hero-sub').textContent = `${fmtTime(currentRow.start)}–${fmtTime(currentRow.end)}`;

      const deltaPct = ((currentRow.centsKWh - avg) / avg) * 100;
      const deltaEl = $('hero-delta');
      deltaEl.textContent = (deltaPct >= 0 ? '+' : '') + deltaPct.toFixed(0) + '% vs day avg';
      deltaEl.className = 'hero-delta ' + (deltaPct < -5 ? 'good' : deltaPct > 5 ? 'bad' : '');
    } else {
      setPill('normal', state.selected === 'tomorrow' ? 'TOMORROW' : 'AVERAGE');
      setHeroLabel(state.selected === 'tomorrow' ? 'Tomorrow · avg' : 'Day average', false);
      setHeroValue(fmt2(avg), 'normal');
      $('hero-sub').textContent = `${fmtTime(rows[0].start)}–${fmtTime(rows[rows.length-1].end)}`;
      $('hero-delta').textContent = `range ${fmt2(lo)} – ${fmt2(hi)}`;
      $('hero-delta').className = 'hero-delta';
    }

    drawSparkline(rows, lo, hi, currentRow);

    // ---- Insight ----
    renderInsight(rows, lo, hi, currentRow, cheapest, priciest, avg);

    // ---- Stats ----
    $('stat-lo').innerHTML = `${fmt2(lo)}<span class="cents"> ¢</span>`;
    $('stat-lo-sub').textContent = `at ${fmtTime(rows[loIdx].start)}`;
    $('stat-hi').innerHTML = `${fmt2(hi)}<span class="cents"> ¢</span>`;
    $('stat-hi-sub').textContent = `at ${fmtTime(rows[hiIdx].start)}`;

    // ---- Chart ----
    drawChart(rows, lo, hi, avg, cheapest, priciest);

    // ---- List ----
    renderList(rows, lo, hi, cheapest, priciest, currentRow);

    // ---- Slot count ----
    $('slot-count').textContent = `${rows.length} slots`;

    // ---- Updated ----
    $('updated').textContent = state.updatedAt
      ? `Updated ${fmtTime(state.updatedAt)} · source: nordpool.didnt.work`
      : '';

    content.classList.remove('hidden');
  }

  function setPill(variant, text) {
    const p = $('hero-pill');
    p.className = 'pill ' + variant;
    p.textContent = text;
  }
  function setHeroLabel(text, live) {
    const el = $('hero-label');
    el.textContent = text;
    el.className = 'hero-label' + (live ? ' live' : '');
  }
  function setHeroValue(text, variant) {
    const v = $('hero-value');
    v.textContent = text;
    v.className = 'hero-value' + (variant ? ' ' + variant : '');
  }

  // ------------------------------ Insight generation

  function renderInsight(rows, lo, hi, currentRow, cheapest, priciest, avg) {
    const box = $('insight');
    const now = new Date();
    const isToday = state.selected === 'today';

    let icon = '💡', title = '', sub = '';

    if (isToday && currentRow) {
      const key = +currentRow.start;
      if (cheapest.has(key)) {
        icon = '🌿';
        title = 'You\'re in one of the 4 cheapest slots';
        const nextPricy = rows.find(r => r.start > now && priciest.has(+r.start));
        sub = nextPricy
          ? `Next expensive slot at ${fmtTime(nextPricy.start)} · ${fmt2(nextPricy.centsKWh)} ¢`
          : `Slot ends at ${fmtTime(currentRow.end)}`;
      } else if (priciest.has(key)) {
        icon = '🔥';
        title = 'One of the 4 priciest slots right now';
        const nextCheap = rows.find(r => r.start > now && cheapest.has(+r.start));
        sub = nextCheap
          ? `Wait until ${fmtTime(nextCheap.start)} for ${fmt2(nextCheap.centsKWh)} ¢ · save ${Math.round(((currentRow.centsKWh - nextCheap.centsKWh)/currentRow.centsKWh)*100)}%`
          : 'No cheap slots left today';
      } else {
        // Normal — point to next cheap slot ahead
        const nextCheap = rows.find(r => r.start > now && cheapest.has(+r.start));
        if (nextCheap) {
          icon = '⏱️';
          const mins = Math.round((nextCheap.start - now) / 60000);
          const when = mins < 60 ? `in ${mins} min` : `in ${Math.floor(mins/60)}h ${mins%60}m`;
          title = `Cheapest slot coming ${when}`;
          sub = `${fmtTime(nextCheap.start)} · ${fmt2(nextCheap.centsKWh)} ¢/kWh`;
        } else {
          icon = '🌙';
          title = 'All cheap slots have passed';
          sub = 'Come back tomorrow';
        }
      }
    } else if (!isToday) {
      // Tomorrow — show cheapest window
      const cheapestRow = rows.reduce((a, b) => a.centsKWh <= b.centsKWh ? a : b);
      icon = '🌅';
      title = `Cheapest tomorrow at ${fmtTime(cheapestRow.start)}`;
      sub = `${fmt2(cheapestRow.centsKWh)} ¢/kWh · plan big appliances then`;
    } else {
      box.classList.add('hidden');
      return;
    }

    $('insight-icon').textContent = icon;
    $('insight-title').textContent = title;
    $('insight-sub').textContent = sub;
    box.classList.remove('hidden');
  }

  // ------------------------------ Sparkline under hero

  function drawSparkline(rows, lo, hi, currentRow) {
    const svg = $('hero-spark');
    const containerW = Math.max(280, Math.round(svg.getBoundingClientRect().width || 340));
    const W = containerW, H = 60, pad = 2;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const n = rows.length;
    const chartW = W - pad*2, chartH = H - pad*2;
    const yMin = Math.min(lo, 0), yMax = hi + (hi - yMin) * 0.1;
    const x = i => pad + (n <= 1 ? chartW/2 : (i * chartW) / (n - 1));
    const y = v => pad + chartH - ((v - yMin) / (yMax - yMin || 1)) * chartH;

    const pts = rows.map((r, i) => [x(i), y(r.centsKWh)]);
    const line = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const area = line + ` L${pts[n-1][0].toFixed(1)},${(H-pad).toFixed(1)} L${pts[0][0].toFixed(1)},${(H-pad).toFixed(1)} Z`;

    let nowDot = '';
    if (currentRow) {
      const i = rows.indexOf(currentRow);
      if (i >= 0) {
        nowDot = `<circle cx="${x(i)}" cy="${y(currentRow.centsKWh)}" r="4" fill="#EEEEEE"/>
                  <circle cx="${x(i)}" cy="${y(currentRow.centsKWh)}" r="2.4" fill="#98BD09"/>`;
      }
    }

    svg.innerHTML = `
      <defs>
        <linearGradient id="sparkG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"  stop-color="rgba(152, 189, 9, 0.55)"/>
          <stop offset="100%" stop-color="rgba(152, 189, 9, 0.02)"/>
        </linearGradient>
        <linearGradient id="sparkL" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"  stop-color="#03413C"/>
          <stop offset="55%" stop-color="#98BD09"/>
          <stop offset="100%" stop-color="#B7D910"/>
        </linearGradient>
      </defs>
      <path d="${area}" fill="url(#sparkG)"/>
      <path d="${line}" fill="none" stroke="url(#sparkL)" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
      ${nowDot}
    `;
  }

  // ------------------------------ Main chart (bar field)

  function drawChart(rows, lo, hi, avg, cheapest, priciest) {
    const svg = $('chart');
    // Size the viewBox to the actual container width so bars render crisply
    // without horizontal scaling.
    const containerW = Math.max(320, Math.round(svg.getBoundingClientRect().width || 360));
    const W = containerW, H = 280, padL = 34, padR = 14, padT = 30, padB = 30;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const n = rows.length;
    const chartW = W - padL - padR, chartH = H - padT - padB;
    const gap = 1;
    const barW = Math.max(1.8, (chartW - gap * (n - 1)) / n);

    // Always start bars from 0 so magnitude reads clearly.
    const yMin = 0;
    const yMax = Math.max(hi * 1.15, 0.01);
    const y = v => padT + chartH - ((Math.max(0, v) - yMin) / (yMax - yMin)) * chartH;

    const css = getComputedStyle(document.documentElement);
    const muted = css.getPropertyValue('--muted').trim() || 'rgba(238,238,238,0.58)';
    const text  = css.getPropertyValue('--text').trim()  || '#EEEEEE';
    const acc1  = css.getPropertyValue('--brand').trim() || '#98BD09';

    // Absolute min/max (for the "crown" and "siren" accents)
    let minIdx = 0, maxIdx = 0;
    rows.forEach((r, i) => { if (r.centsKWh < rows[minIdx].centsKWh) minIdx = i; if (r.centsKWh > rows[maxIdx].centsKWh) maxIdx = i; });

    // Hourly gridlines (subtle vertical separators at each full hour)
    let hourGrid = '';
    rows.forEach((r, i) => {
      const m = r.start.getMinutes();
      if (m === 0 && i > 0) {
        const xh = padL + i * (barW + gap) - gap/2;
        const hrs = Number(timeFmt.format(r.start).split(':')[0]);
        if ([0, 6, 12, 18].includes(hrs)) {
          hourGrid += `<line x1="${xh}" x2="${xh}" y1="${padT}" y2="${padT+chartH}" stroke="${muted}" stroke-opacity="0.08"/>`;
        }
      }
    });

    // Y gridlines (3 horizontal rules)
    let yGrid = '';
    for (let i = 0; i <= 3; i++) {
      const v = yMin + (yMax - yMin) * (i / 3);
      const yy = y(v);
      yGrid += `<line x1="${padL}" x2="${W-padR}" y1="${yy}" y2="${yy}" stroke="${muted}" stroke-opacity="0.10"/>`;
      yGrid += `<text x="${padL - 6}" y="${yy + 3}" font-size="9.5" fill="${muted}" text-anchor="end" font-weight="600" letter-spacing="0.03em">${v.toFixed(0)}</text>`;
    }

    // Average line
    const ay = y(avg);
    const avgLine = `
      <line x1="${padL}" x2="${W-padR}" y1="${ay}" y2="${ay}" stroke="${muted}" stroke-opacity="0.45" stroke-dasharray="2 3"/>
      <g transform="translate(${W-padR-2}, ${ay})">
        <rect x="-34" y="-8" width="34" height="14" rx="3" fill="var(--bg-1)" opacity="0.85"/>
        <text x="-3" y="2" font-size="9" fill="${muted}" text-anchor="end" font-weight="700" letter-spacing="0.05em">AVG ${avg.toFixed(1)}</text>
      </g>
    `;

    // X ticks — show 00 / 06 / 12 / 18 at hourly boundaries
    let xlabels = '';
    rows.forEach((r, i) => {
      const parts = timeFmt.format(r.start).split(':');
      const hr = Number(parts[0]);
      const mn = Number(parts[1]);
      if (mn === 0 && [0, 6, 12, 18].includes(hr)) {
        const cx = padL + i * (barW + gap) + barW/2;
        xlabels += `<text x="${cx}" y="${H-10}" font-size="10" fill="${muted}" text-anchor="middle" font-weight="600" letter-spacing="0.05em">${parts[0]}:00</text>`;
      }
    });

    // Bars
    let bars = '';
    rows.forEach((r, i) => {
      const k = +r.start;
      const isCheap = cheapest.has(k);
      const isPricy = priciest.has(k);
      const bx = padL + i * (barW + gap);
      const by = y(r.centsKWh);
      const bh = Math.max(1, padT + chartH - by);
      let fill;
      let extra = '';
      if (isCheap) {
        fill = 'url(#barCheap)';
        extra = `filter="url(#glowGreen)"`;
      } else if (isPricy) {
        fill = 'url(#barPricy)';
        extra = `filter="url(#glowRed)"`;
      } else {
        // Normal: colour by relative price using a subtle purple-to-amber hue.
        const t = (r.centsKWh - lo) / Math.max(0.0001, hi - lo);
        fill = `url(#barNormal${Math.round(t * 100)})`;
      }
      const rx = Math.min(barW/2, 1.8);
      bars += `<rect x="${bx.toFixed(2)}" y="${by.toFixed(2)}" width="${barW.toFixed(2)}" height="${bh.toFixed(2)}" rx="${rx}" fill="${fill}" ${extra}/>`;
    });

    // Marker badges above cheapest/priciest (tiny pills) — brand-coloured
    let badges = '';
    rows.forEach((r, i) => {
      const k = +r.start;
      const bx = padL + i * (barW + gap) + barW/2;
      const by = y(r.centsKWh);
      if (cheapest.has(k)) {
        const isCrown = i === minIdx;
        const color = isCrown ? '#B7D910' : '#98BD09';
        badges += `
          <g transform="translate(${bx.toFixed(2)}, ${(by - 10).toFixed(2)})">
            <circle r="5" fill="${color}" style="filter: drop-shadow(0 0 6px ${color})"/>
            <circle r="2" fill="#071C23" opacity="0.9"/>
          </g>`;
      } else if (priciest.has(k)) {
        const isSiren = i === maxIdx;
        const color = isSiren ? '#FBBF24' : '#F59E0B';
        badges += `
          <g transform="translate(${bx.toFixed(2)}, ${(by - 10).toFixed(2)})">
            <circle r="5" fill="${color}" style="filter: drop-shadow(0 0 6px ${color})"/>
            <circle r="2" fill="#071C23" opacity="0.9"/>
          </g>`;
      }
    });

    // Crown icon above absolute cheapest
    const crownX = padL + minIdx * (barW + gap) + barW/2;
    const crownY = y(rows[minIdx].centsKWh);
    const crown = `
      <g transform="translate(${crownX.toFixed(2)}, ${(crownY - 22).toFixed(2)})">
        <text text-anchor="middle" font-size="14">👑</text>
      </g>`;

    // Flame above absolute priciest
    const flameX = padL + maxIdx * (barW + gap) + barW/2;
    const flameY = y(rows[maxIdx].centsKWh);
    const flame = `
      <g transform="translate(${flameX.toFixed(2)}, ${(flameY - 22).toFixed(2)})">
        <text text-anchor="middle" font-size="13">🔥</text>
      </g>`;

    // Now indicator (today only)
    let nowLine = '';
    if (state.selected === 'today') {
      const now = new Date();
      const first = +rows[0].start, last = +rows[n-1].end;
      const t = (now - first) / (last - first);
      if (t >= 0 && t <= 1) {
        const xn = padL + t * chartW;
        nowLine = `
          <line x1="${xn}" x2="${xn}" y1="${padT-6}" y2="${padT+chartH}" stroke="${acc1}" stroke-opacity="0.55" stroke-width="1.2" stroke-dasharray="2 3"/>
          <g transform="translate(${xn}, ${padT - 8})">
            <circle r="4.5" fill="${acc1}">
              <animate attributeName="r" values="3.5;6;3.5" dur="2s" repeatCount="indefinite"/>
              <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite"/>
            </circle>
            <circle r="2" fill="white"/>
          </g>`;
      }
    }

    // Build gradient defs. Normal bars: a teal-to-green ramp so the chart
    // feels Engycell-brand: darker teal at low relative price, vivid green
    // at the high end of the normal range.
    let normalDefs = '';
    for (let i = 0; i <= 100; i += 5) {
      const t = i / 100;
      // Interpolate HSL from deep teal (#03413C ≈ 173° 91% 13%) to brand green (#98BD09 ≈ 73° 91% 39%)
      const hue = 173 + (73 - 173) * t;
      const sat = 72;
      const bri = 22 + t * 28;
      normalDefs += `
        <linearGradient id="barNormal${i}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="hsl(${hue.toFixed(1)}, ${sat}%, ${(bri+10).toFixed(1)}%)" stop-opacity="0.95"/>
          <stop offset="100%" stop-color="hsl(${hue.toFixed(1)}, ${sat}%, ${bri.toFixed(1)}%)" stop-opacity="0.35"/>
        </linearGradient>`;
    }
    for (let i = 0; i <= 100; i++) {
      if (i % 5 === 0) continue;
      const nearest = Math.round(i / 5) * 5;
      normalDefs += `<linearGradient id="barNormal${i}" href="#barNormal${nearest}"/>`;
    }

    svg.innerHTML = `
      <defs>
        <linearGradient id="barCheap" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="#B7D910" stop-opacity="1"/>
          <stop offset="100%" stop-color="#98BD09" stop-opacity="0.55"/>
        </linearGradient>
        <linearGradient id="barPricy" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="#FBBF24" stop-opacity="1"/>
          <stop offset="100%" stop-color="#F59E0B" stop-opacity="0.55"/>
        </linearGradient>
        <filter id="glowGreen" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.2" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="glowRed" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.2" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        ${normalDefs}
      </defs>
      ${yGrid}
      ${hourGrid}
      ${avgLine}
      ${bars}
      ${nowLine}
      ${badges}
      ${crown}
      ${flame}
      ${xlabels}
    `;
  }

  // ------------------------------ Price list (compact 4-col grid)

  function renderList(rows, lo, hi, cheapest, priciest, currentRow) {
    const list = $('list');
    const range = Math.max(0.0001, hi - lo);

    // Find absolute min/max indices in the data for crown/flame decoration.
    let minIdx = 0, maxIdx = 0;
    rows.forEach((r, i) => {
      if (r.centsKWh < rows[minIdx].centsKWh) minIdx = i;
      if (r.centsKWh > rows[maxIdx].centsKWh) maxIdx = i;
    });

    const frag = document.createDocumentFragment();
    rows.forEach((r, i) => {
      const k = +r.start;
      const cell = document.createElement('div');
      const isNow = currentRow && k === +currentRow.start;
      const isCheap = cheapest.has(k);
      const isPricy = priciest.has(k);
      const isCrown = i === minIdx;
      const isFlame = i === maxIdx;

      cell.className = 'cell'
        + (isCheap ? ' cheap' : '')
        + (isPricy ? ' pricy' : '')
        + (isNow ? ' now' : '')
        + (isCrown ? ' crown' : '')
        + (isFlame ? ' flame' : '');

      const pct = Math.max(6, ((r.centsKWh - lo) / range) * 100);
      const badge =
        isCrown ? '<span class="cell-badge">👑</span>' :
        isFlame ? '<span class="cell-badge">🔥</span>' :
        isCheap ? '<span class="cell-badge">•</span>' :
        isPricy ? '<span class="cell-badge">•</span>' :
        isNow   ? '<span class="cell-badge">●</span>' : '';

      cell.innerHTML = `
        ${badge}
        <div class="cell-time">${fmtTime(r.start)}</div>
        <div class="cell-price">${fmt2(r.centsKWh)}<span class="cell-unit">¢</span></div>
        <div class="cell-bar"><span style="width:${pct}%"></span></div>
      `;
      frag.appendChild(cell);
    });
    list.innerHTML = '';
    list.appendChild(frag);
  }

  // ------------------------------ Diagnostics

  function renderDiagnostics() {
    const box = $('diag');
    if (!box) return;
    if (!state.diag.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<div class="diag-title">What happened</div>' + state.diag.map(d => `
      <details class="diag-item">
        <summary>
          <span class="pill-mini ${d.ok ? 'ok' : 'bad'}">${d.source}</span>
          <span class="diag-status">${d.ok ? `OK · ${d.bytes} bytes` : (d.error || 'failed')}</span>
        </summary>
        <div class="diag-body">
          <div class="diag-url">${d.url}</div>
          <pre>${escapeHTML(d.preview || '(empty)')}</pre>
        </div>
      </details>
    `).join('');
  }
  function escapeHTML(s) { return String(s).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }

  // ------------------------------ Cache (localStorage)

  const CACHE_KEY = 'engycell.prices.v1';

  function loadCache() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !Array.isArray(parsed.rows)) return null;
      const rows = parsed.rows.map(r => ({
        start: new Date(r.s),
        end: new Date(r.e),
        centsKWh: r.p,
        native: r.n,
      })).filter(r => r.start && !isNaN(r.start));
      return { fetchedAt: new Date(parsed.fetchedAt), rows };
    } catch { return null; }
  }

  function saveCache(rows) {
    try {
      const payload = {
        fetchedAt: Date.now(),
        rows: rows.map(r => ({ s: +r.start, e: +r.end, p: r.centsKWh, n: r.native })),
      };
      localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
    } catch {}
  }

  // Only refetch when the cache can't answer — saves the feed a lot of hits.
  function shouldRefresh(cache) {
    if (!cache) return true;
    const ageMs = Date.now() - cache.fetchedAt;
    if (ageMs > 8 * 60 * 60 * 1000) return true;
    const { today, tomorrow } = bucket(cache.rows);
    if (today.length === 0) return true;
    if (tomorrow.length === 0) {
      const rigaHour = Number(new Intl.DateTimeFormat('en-GB',
        { timeZone: TZ, hour: '2-digit', hour12: false }).format(new Date()));
      if (rigaHour >= 14 && ageMs > 15 * 60 * 1000) return true;
    }
    return false;
  }

  // ------------------------------ Load

  async function load(opts = {}) {
    const { force = false, silent = false } = opts;
    $('error').classList.add('hidden');

    if (!silent) {
      $('refresh').classList.add('spinning');
      if (!state.today.length && !state.tomorrow.length) {
        $('loading').classList.remove('hidden');
        $('content').classList.add('hidden');
      }
    }

    try {
      const text = await fetchCSV();
      const rows = parseCSV(text);
      const { today, tomorrow } = bucket(rows);
      state.today = today;
      state.tomorrow = tomorrow;
      state.updatedAt = new Date();
      saveCache(rows);
      render();
    } catch (e) {
      if (!silent) {
        $('error-msg').textContent = e.message || String(e);
        renderDiagnostics();
        $('error').classList.remove('hidden');
        $('content').classList.add('hidden');
      }
    } finally {
      $('loading').classList.add('hidden');
      $('refresh').classList.remove('spinning');
    }
  }

  async function init() {
    const cache = loadCache();
    if (cache && cache.rows.length) {
      const { today, tomorrow } = bucket(cache.rows);
      state.today = today;
      state.tomorrow = tomorrow;
      state.updatedAt = cache.fetchedAt;
      render();
    }
    if (shouldRefresh(cache)) {
      await load({ silent: !!(cache && cache.rows.length) });
    }
  }

  // ------------------------------ Wiring

  document.querySelectorAll('.seg').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.seg').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected','false'); });
      btn.classList.add('active');
      btn.setAttribute('aria-selected','true');
      state.selected = btn.dataset.day;
      updateSegThumb();
      render();
    });
  });
  $('refresh').addEventListener('click', () => load({ force: true }));
  $('retry').addEventListener('click', () => load({ force: true }));
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      const cache = loadCache();
      if (shouldRefresh(cache)) load({ silent: true });
    }
  });

  // Re-render "now" every minute so the indicator moves
  setInterval(() => {
    if (state.today.length && state.selected === 'today') render();
  }, 60 * 1000);

  // Re-render on resize / orientation change so bar widths recompute
  let resizeT;
  window.addEventListener('resize', () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => { if (state.today.length || state.tomorrow.length) render(); }, 150);
  });

  updateSegThumb();
  init();

  // Remove the launch-animation class after the entrance finishes so that
  // subsequent renders don't replay the sweep.
  setTimeout(() => document.body.classList.remove('app-entering'), 900);

  // Network-first service worker so the plain URL always resolves to the
  // latest deployed assets; cached copy is only used when offline.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('sw.js').catch(() => {});
    });
  }
})();
