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
    const d = new Date(s);
    if (!isNaN(d)) return d;
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
    if (m) return new Date(Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +(m[6]||0)));
    const epoch = Number(s);
    if (!Number.isNaN(epoch)) return new Date(epoch > 1e12 ? epoch : epoch * 1000);
    return null;
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

    if (!rows.length) {
      content.classList.remove('hidden');
      setPill('normal', state.selected === 'tomorrow' ? 'NOT PUBLISHED' : 'NO DATA');
      $('hero-label').textContent = state.selected === 'tomorrow' ? 'Tomorrow' : 'Today';
      setHeroValue('—', null);
      $('hero-sub').textContent = state.selected === 'tomorrow'
        ? 'Usually published around 14:00 Riga'
        : 'Tap refresh to retry';
      $('hero-delta').textContent = '';
      $('hero-delta').className = 'hero-delta';
      $('hero-spark').innerHTML = '';
      $('insight').classList.add('hidden');
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
      $('hero-label').textContent = 'Right now';
      setHeroValue(fmt2(currentRow.centsKWh), variant);
      $('hero-sub').textContent = `${fmtTime(currentRow.start)}–${fmtTime(currentRow.end)}`;

      const deltaPct = ((currentRow.centsKWh - avg) / avg) * 100;
      const deltaEl = $('hero-delta');
      deltaEl.textContent = (deltaPct >= 0 ? '+' : '') + deltaPct.toFixed(0) + '% vs day avg';
      deltaEl.className = 'hero-delta ' + (deltaPct < -5 ? 'good' : deltaPct > 5 ? 'bad' : '');
    } else {
      setPill('normal', state.selected === 'tomorrow' ? 'TOMORROW' : 'AVERAGE');
      $('hero-label').textContent = state.selected === 'tomorrow' ? 'Tomorrow · avg' : 'Day average';
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
    const W = 340, H = 60, pad = 2;
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
        nowDot = `<circle cx="${x(i)}" cy="${y(currentRow.centsKWh)}" r="4" fill="white"/>
                  <circle cx="${x(i)}" cy="${y(currentRow.centsKWh)}" r="3" fill="#4f46e5"/>`;
      }
    }

    svg.innerHTML = `
      <defs>
        <linearGradient id="sparkG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(124,58,237,0.55)"/>
          <stop offset="100%" stop-color="rgba(124,58,237,0.02)"/>
        </linearGradient>
        <linearGradient id="sparkL" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#4f46e5"/>
          <stop offset="50%" stop-color="#7c3aed"/>
          <stop offset="100%" stop-color="#06b6d4"/>
        </linearGradient>
      </defs>
      <path d="${area}" fill="url(#sparkG)"/>
      <path d="${line}" fill="none" stroke="url(#sparkL)" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
      ${nowDot}
    `;
  }

  // ------------------------------ Main chart

  function drawChart(rows, lo, hi, avg, cheapest, priciest) {
    const svg = $('chart');
    const W = 640, H = 260, padL = 38, padR = 14, padT = 18, padB = 28;
    const n = rows.length;
    const chartW = W - padL - padR, chartH = H - padT - padB;
    const x = i => padL + (n <= 1 ? chartW/2 : (i * chartW) / (n - 1));
    const yMin = Math.min(lo, 0);
    const yMax = hi + (hi - yMin) * 0.15;
    const y = v => padT + chartH - ((v - yMin) / (yMax - yMin || 1)) * chartH;

    const css = getComputedStyle(document.documentElement);
    const muted = css.getPropertyValue('--muted').trim() || '#8893a7';
    const text  = css.getPropertyValue('--text').trim()  || '#f1f5f9';
    const green = css.getPropertyValue('--green-1').trim() || '#34d399';
    const red   = css.getPropertyValue('--red-1').trim()   || '#f87171';
    const acc1  = css.getPropertyValue('--accent-1').trim() || '#4f46e5';

    const pts = rows.map((r, i) => [x(i), y(r.centsKWh)]);
    const line = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const area = line + ` L${pts[n-1][0].toFixed(1)},${(padT+chartH).toFixed(1)} L${pts[0][0].toFixed(1)},${(padT+chartH).toFixed(1)} Z`;

    // Y grid
    let grid = '';
    for (let i = 0; i <= 4; i++) {
      const v = yMin + (yMax - yMin) * (i / 4);
      const yy = y(v);
      grid += `<line x1="${padL}" x2="${W-padR}" y1="${yy}" y2="${yy}" stroke="${muted}" stroke-opacity="0.12"/>`;
      grid += `<text x="${padL - 8}" y="${yy + 3}" font-size="10" fill="${muted}" text-anchor="end" font-weight="500">${v.toFixed(1)}</text>`;
    }

    // Average line
    const ay = y(avg);
    const avgLine = `
      <line x1="${padL}" x2="${W-padR}" y1="${ay}" y2="${ay}" stroke="${muted}" stroke-opacity="0.35" stroke-dasharray="2 4"/>
      <text x="${W-padR-4}" y="${ay - 4}" font-size="9" fill="${muted}" text-anchor="end" font-weight="600">AVG ${avg.toFixed(1)}</text>
    `;

    // X ticks
    let xlabels = '';
    const step = Math.max(1, Math.round(n / 6));
    for (let i = 0; i < n; i += step) {
      xlabels += `<text x="${x(i)}" y="${H-8}" font-size="10" fill="${muted}" text-anchor="middle" font-weight="500">${fmtTime(rows[i].start)}</text>`;
    }

    // Now line (today only)
    let nowLine = '';
    if (state.selected === 'today') {
      const now = new Date();
      const first = +rows[0].start, last = +rows[n-1].end;
      const t = (now - first) / (last - first);
      if (t >= 0 && t <= 1) {
        const xn = padL + t * chartW;
        nowLine = `
          <line x1="${xn}" x2="${xn}" y1="${padT}" y2="${padT+chartH}" stroke="${text}" stroke-opacity="0.4" stroke-dasharray="3 3"/>
          <circle cx="${xn}" cy="${padT+4}" r="4" fill="${acc1}">
            <animate attributeName="r" values="3.5;6;3.5" dur="2s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite"/>
          </circle>
        `;
      }
    }

    // Markers for cheapest/priciest
    let marks = '';
    rows.forEach((r, i) => {
      const k = +r.start;
      if (cheapest.has(k)) marks += `<circle cx="${x(i)}" cy="${y(r.centsKWh)}" r="5" fill="${green}" stroke="white" stroke-width="1.5" style="filter: drop-shadow(0 0 6px ${green})"/>`;
      else if (priciest.has(k)) marks += `<circle cx="${x(i)}" cy="${y(r.centsKWh)}" r="5" fill="${red}" stroke="white" stroke-width="1.5" style="filter: drop-shadow(0 0 6px ${red})"/>`;
    });

    svg.innerHTML = `
      <defs>
        <linearGradient id="chartArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="${acc1}" stop-opacity="0.5"/>
          <stop offset="100%" stop-color="${acc1}" stop-opacity="0.02"/>
        </linearGradient>
        <linearGradient id="chartLine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stop-color="#4f46e5"/>
          <stop offset="50%"  stop-color="#7c3aed"/>
          <stop offset="100%" stop-color="#06b6d4"/>
        </linearGradient>
      </defs>
      ${grid}
      ${avgLine}
      <path d="${area}" fill="url(#chartArea)"/>
      <path d="${line}" fill="none" stroke="url(#chartLine)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
      ${nowLine}
      ${marks}
      ${xlabels}
    `;
  }

  // ------------------------------ Price list

  function renderList(rows, lo, hi, cheapest, priciest, currentRow) {
    const list = $('list');
    const range = Math.max(0.0001, hi - lo);
    const frag = document.createDocumentFragment();

    for (const r of rows) {
      const row = document.createElement('div');
      const isNow = currentRow && +r.start === +currentRow.start;
      const isCheap = cheapest.has(+r.start);
      const isPricy = priciest.has(+r.start);
      row.className = 'row' + (isCheap ? ' cheap' : '') + (isPricy ? ' pricy' : '') + (isNow ? ' now' : '');
      const pct = Math.max(5, ((r.centsKWh - lo) / range) * 100);
      const color = isCheap ? 'var(--green-1)' : isPricy ? 'var(--red-1)' : 'var(--accent-1)';
      row.innerHTML = `
        <div class="row-accent"></div>
        <div class="row-time">${fmtTime(r.start)}${isNow ? '<span class="nowtag">NOW</span>' : ''}</div>
        <div class="row-bar"><span style="width:${pct}%;background:${color}"></span></div>
        <div class="row-price">${fmt2(r.centsKWh)}<span class="cents">¢</span></div>
      `;
      frag.appendChild(row);
    }
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

  // ------------------------------ Load

  async function load() {
    $('refresh').classList.add('spinning');
    $('error').classList.add('hidden');
    if (!state.today.length && !state.tomorrow.length) {
      $('loading').classList.remove('hidden');
      $('content').classList.add('hidden');
    }
    try {
      const text = await fetchCSV();
      const rows = parseCSV(text);
      const { today, tomorrow } = bucket(rows);
      state.today = today;
      state.tomorrow = tomorrow;
      state.updatedAt = new Date();
      render();
    } catch (e) {
      $('error-msg').textContent = e.message || String(e);
      renderDiagnostics();
      $('error').classList.remove('hidden');
      $('content').classList.add('hidden');
    } finally {
      $('loading').classList.add('hidden');
      $('refresh').classList.remove('spinning');
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
  $('refresh').addEventListener('click', load);
  $('retry').addEventListener('click', load);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.updatedAt && Date.now() - state.updatedAt > 10*60*1000) load();
  });

  // Re-render "now" every minute so the indicator moves
  setInterval(() => {
    if (state.today.length && state.selected === 'today') render();
  }, 60 * 1000);

  updateSegThumb();
  load();
})();
