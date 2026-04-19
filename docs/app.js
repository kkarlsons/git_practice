(() => {
  const CSV_URL = 'https://nordpool.didnt.work/nordpool-lv.csv';
  // CORS fallbacks in case the feed doesn't set Access-Control-Allow-Origin.
  const PROXIES = [
    u => `https://corsproxy.io/?${encodeURIComponent(u)}`,
    u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
    u => `https://api.codetabs.com/v1/proxy/?quest=${encodeURIComponent(u)}`,
  ];
  const TZ = 'Europe/Riga';

  const $ = id => document.getElementById(id);
  const state = { selected: 'today', today: [], tomorrow: [], updatedAt: null };

  // -------- Networking --------

  async function fetchCSV() {
    const attempts = [
      async () => await (await fetch(CSV_URL, { cache: 'no-store' })).text(),
      ...PROXIES.map(p => async () => await (await fetch(p(CSV_URL), { cache: 'no-store' })).text()),
    ];
    let lastErr;
    for (const go of attempts) {
      try {
        const text = await go();
        if (text && text.length > 20) return text;
        lastErr = new Error('Empty response');
      } catch (e) { lastErr = e; }
    }
    throw lastErr || new Error('All fetch attempts failed');
  }

  // -------- CSV parsing --------

  function parseCSV(text) {
    const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (lines.length < 2) throw new Error('CSV is empty');
    const delim = detectDelim(lines[0]);
    const header = splitLine(lines[0], delim).map(h => normalize(h));

    const startIdx = findCol(header, ['start','begin','from','deliverystart','timestamp','datetime','time','date']);
    const endIdx   = findCol(header, ['end','to','deliveryend']);
    const priceIdx = findCol(header, ['price','value','eurmwh','eur','cost']);

    if (startIdx < 0 || priceIdx < 0) throw new Error("Couldn't find time/price columns in CSV");

    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = splitLine(lines[i], delim);
      if (cols.length <= Math.max(startIdx, priceIdx)) continue;
      const start = parseDate(cols[startIdx]);
      const price = parseNum(cols[priceIdx]);
      if (!start || Number.isNaN(price)) continue;
      const end = (endIdx >= 0 && cols[endIdx]) ? (parseDate(cols[endIdx]) || new Date(start.getTime() + 15*60*1000))
                                                : new Date(start.getTime() + 15*60*1000);
      rows.push({ start, end, eurMWh: price, centsKWh: price / 10 });
    }
    rows.sort((a, b) => a.start - b.start);
    return rows;
  }

  function normalize(s) {
    return s.toLowerCase().replace(/["_\-\s/]/g, '');
  }
  function findCol(header, needles) {
    for (const n of needles) {
      const i = header.findIndex(h => h.includes(n));
      if (i >= 0) return i;
    }
    return -1;
  }
  function detectDelim(line) {
    const s = (line.match(/;/g)||[]).length;
    const c = (line.match(/,/g)||[]).length;
    const t = (line.match(/\t/g)||[]).length;
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
    out.push(cur.trim());
    return out;
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

  // -------- Day bucketing in Europe/Riga --------

  function rigaYMD(date) {
    // returns "YYYY-MM-DD" for the given instant, in Europe/Riga.
    const f = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year:'numeric', month:'2-digit', day:'2-digit' });
    return f.format(date); // en-CA gives YYYY-MM-DD
  }
  function bucket(rows) {
    const today = rigaYMD(new Date());
    const tomorrow = rigaYMD(new Date(Date.now() + 24*60*60*1000));
    const t = []; const tm = [];
    for (const r of rows) {
      const d = rigaYMD(r.start);
      if (d === today) t.push(r);
      else if (d === tomorrow) tm.push(r);
    }
    return { today: t, tomorrow: tm };
  }

  // -------- Formatting --------

  const timeFmt = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
  const updFmt  = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false });
  const fmtTime = d => timeFmt.format(d);
  const fmt2 = n => n.toFixed(2);

  // -------- Colour scale --------

  function priceColor(value, lo, hi) {
    if (hi <= lo) return getCSSVar('--accent');
    const t = Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
    // hue 130 (green) → 45 (amber) → 0 (red)
    const hue = 130 - 130 * t;
    return `hsl(${hue}, 65%, 45%)`;
  }
  function getCSSVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#2775e0';
  }

  // -------- Rendering --------

  function render() {
    const rows = state.selected === 'today' ? state.today : state.tomorrow;
    const list = $('list');
    const chart = $('chart');
    const content = $('content');

    if (!rows.length) {
      content.classList.remove('hidden');
      $('hero-label').textContent = state.selected === 'tomorrow' ? 'Not published yet' : 'No data';
      $('hero-value').textContent = '—';
      $('hero-sub').textContent = state.selected === 'tomorrow'
        ? 'Nordpool usually publishes tomorrow around 14:00 Riga time.'
        : 'Pull down or tap refresh to retry.';
      $('stat-lo').textContent = '—'; $('stat-lo-sub').textContent = '';
      $('stat-hi').textContent = '—'; $('stat-hi-sub').textContent = '';
      chart.innerHTML = '';
      list.innerHTML = '';
      return;
    }

    const prices = rows.map(r => r.centsKWh);
    const lo = Math.min(...prices);
    const hi = Math.max(...prices);
    const loIdx = prices.indexOf(lo);
    const hiIdx = prices.indexOf(hi);

    const cheapest = new Set([...rows].sort((a,b) => a.centsKWh - b.centsKWh).slice(0, 4).map(r => +r.start));
    const priciest = new Set([...rows].sort((a,b) => b.centsKWh - a.centsKWh).slice(0, 4).map(r => +r.start));

    // Hero
    const now = new Date();
    const currentRow = state.selected === 'today'
      ? rows.find(r => r.start <= now && now < r.end)
      : null;
    if (currentRow) {
      $('hero-label').textContent = 'Right now';
      $('hero-value').textContent = fmt2(currentRow.centsKWh);
      $('hero-value').style.color = priceColor(currentRow.centsKWh, lo, hi);
      $('hero-sub').textContent = `${fmtTime(currentRow.start)}–${fmtTime(currentRow.end)}`;
    } else {
      const avg = prices.reduce((a,b)=>a+b,0) / prices.length;
      $('hero-label').textContent = state.selected === 'tomorrow' ? 'Tomorrow · average' : 'Average';
      $('hero-value').textContent = fmt2(avg);
      $('hero-value').style.color = '';
      $('hero-sub').textContent = '';
    }
    $('stat-lo').textContent = `${fmt2(lo)} ¢`;
    $('stat-lo-sub').textContent = fmtTime(rows[loIdx].start);
    $('stat-hi').textContent = `${fmt2(hi)} ¢`;
    $('stat-hi-sub').textContent = fmtTime(rows[hiIdx].start);

    // Chart
    drawChart(rows, lo, hi, cheapest, priciest);

    // List
    list.innerHTML = '';
    const range = Math.max(0.0001, hi - lo);
    for (const r of rows) {
      const row = document.createElement('div');
      const isNow = currentRow && +r.start === +currentRow.start;
      const isCheap = cheapest.has(+r.start);
      const isPricy = priciest.has(+r.start);
      row.className = 'row' + (isCheap ? ' cheap' : '') + (isPricy ? ' pricy' : '') + (isNow ? ' now' : '');
      const badgeCls = isCheap ? 'c' : isPricy ? 'p' : 'n';
      const badgeSym = isCheap ? '🌿' : isPricy ? '🔥' : '•';
      const pct = Math.max(4, ((r.centsKWh - lo) / range) * 100);
      const color = priceColor(r.centsKWh, lo, hi);
      row.innerHTML = `
        <div class="badge ${badgeCls}">${badgeSym}</div>
        <div class="time">${fmtTime(r.start)}–${fmtTime(r.end)}${isNow ? '<span class="nowtag">NOW</span>' : ''}</div>
        <div class="bar"><span style="width:${pct}%;background:${color}"></span></div>
        <div class="price" style="color:${color}">${fmt2(r.centsKWh)}</div>
      `;
      list.appendChild(row);
    }

    // Updated
    $('updated').textContent = state.updatedAt
      ? `Updated ${updFmt.format(state.updatedAt)} · source: nordpool.didnt.work`
      : '';
    content.classList.remove('hidden');
  }

  function drawChart(rows, lo, hi, cheapest, priciest) {
    const svg = $('chart');
    const W = 600, H = 240, padL = 32, padR = 10, padT = 10, padB = 22;
    const n = rows.length;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;
    const x = i => padL + (n <= 1 ? chartW/2 : (i * chartW) / (n - 1));
    const yRange = Math.max(0.0001, hi - lo);
    // Pad y with 10% headroom
    const yMin = Math.min(lo, 0);
    const yMax = hi + yRange * 0.1;
    const y = v => padT + chartH - ((v - yMin) / (yMax - yMin)) * chartH;

    const pts = rows.map((r, i) => [x(i), y(r.centsKWh)]);
    const pathD = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const areaD = pathD + ` L${pts[pts.length-1][0].toFixed(1)},${(padT+chartH).toFixed(1)} L${pts[0][0].toFixed(1)},${(padT+chartH).toFixed(1)} Z`;

    const accent = getCSSVar('--accent');
    const text = getCSSVar('--text');
    const muted = getCSSVar('--muted');
    const green = getCSSVar('--green');
    const red = getCSSVar('--red');

    // Y gridlines at 4 steps
    let grid = '';
    for (let i = 0; i <= 4; i++) {
      const v = yMin + (yMax - yMin) * (i / 4);
      const yy = y(v);
      grid += `<line x1="${padL}" x2="${W-padR}" y1="${yy}" y2="${yy}" stroke="${muted}" stroke-opacity="0.15"/>`;
      grid += `<text x="${padL - 6}" y="${yy + 3}" font-size="10" fill="${muted}" text-anchor="end">${v.toFixed(1)}</text>`;
    }

    // X labels every ~3 hours (12 slots of 15min)
    let xlabels = '';
    const step = Math.max(1, Math.round(n / 8));
    for (let i = 0; i < n; i += step) {
      xlabels += `<text x="${x(i)}" y="${H-6}" font-size="10" fill="${muted}" text-anchor="middle">${fmtTime(rows[i].start)}</text>`;
    }

    // Now line (only for today)
    let nowLine = '';
    if (state.selected === 'today') {
      const now = new Date();
      const first = +rows[0].start;
      const last  = +rows[rows.length-1].end;
      const t = (now - first) / (last - first);
      if (t >= 0 && t <= 1) {
        const xn = padL + t * chartW;
        nowLine = `<line x1="${xn}" x2="${xn}" y1="${padT}" y2="${padT+chartH}" stroke="${text}" stroke-opacity="0.55" stroke-dasharray="4 3"/>`;
      }
    }

    // Markers
    let marks = '';
    rows.forEach((r, i) => {
      const key = +r.start;
      if (cheapest.has(key)) marks += `<circle cx="${x(i)}" cy="${y(r.centsKWh)}" r="4.5" fill="${green}" stroke="white" stroke-width="1.5"/>`;
      else if (priciest.has(key)) marks += `<circle cx="${x(i)}" cy="${y(r.centsKWh)}" r="4.5" fill="${red}" stroke="white" stroke-width="1.5"/>`;
    });

    svg.innerHTML = `
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${accent}" stop-opacity="0.45"/>
          <stop offset="100%" stop-color="${accent}" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      ${grid}
      <path d="${areaD}" fill="url(#areaGrad)"/>
      <path d="${pathD}" fill="none" stroke="${accent}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      ${nowLine}
      ${marks}
      ${xlabels}
    `;
  }

  // -------- Load / retry --------

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
      $('error').classList.remove('hidden');
      $('content').classList.add('hidden');
    } finally {
      $('loading').classList.add('hidden');
      $('refresh').classList.remove('spinning');
    }
  }

  // -------- UI wiring --------

  document.querySelectorAll('.seg').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.seg').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected','false'); });
      btn.classList.add('active');
      btn.setAttribute('aria-selected','true');
      state.selected = btn.dataset.day;
      render();
    });
  });
  $('refresh').addEventListener('click', load);
  $('retry').addEventListener('click', load);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.updatedAt && Date.now() - state.updatedAt > 10*60*1000) load();
  });

  load();
})();
