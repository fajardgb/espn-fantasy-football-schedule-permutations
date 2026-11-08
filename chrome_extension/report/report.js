/*
 * Schedule luck report: page layout and interactive charts (Plotly).
 *
 * Shared by both ways of making a report:
 *   - build_report.py inlines this file into a standalone .html file
 *   - the Chrome extension's report page loads it directly
 *
 * renderReport(data, root) draws a report into `root`. A standalone file
 * embeds its data in <script type="application/json" id="report-data"> and
 * is drawn automatically when this script loads.
 */
(function () {
  'use strict';

  const REPORT_MARKUP = `
<main>
  <header>
    <h1 id="title">Schedule luck report</h1>
    <p id="subtitle"></p>
  </header>

  <div class="controls" id="controls">
    <span class="label" id="week-title">Through week <span id="week-label"></span></span>
    <div class="weeks" id="week" role="slider" tabindex="0" aria-labelledby="week-title"></div>
    <span class="hint" id="week-hint"></span>
  </div>

  <div class="notes" id="notes" hidden></div>

  <section>
    <h2>Playoff odds</h2>
    <p>How often each team makes the playoffs if the same weekly scores are replayed against
      thousands of random schedules with the league's real format.</p>
    <div class="chart" id="chart-playoff"></div>
  </section>

  <section>
    <h2>Schedule luck</h2>
    <p>Expected win % is the average record across all simulated schedules. Teams above the
      dashed line won more than their scores earned (lucky); teams below won fewer (unlucky).
      Color shows the luck index: actual minus expected win %, in percentage points.</p>
    <div class="chart" id="chart-luck"></div>
  </section>

  <section>
    <h2>What if you had their schedule?</h2>
    <p>Each row is a team; each column is whose real schedule it plays. A cell is that team's
      record against that schedule. The diagonal is each team's actual record.</p>
    <div class="chart" id="chart-swap"></div>
  </section>

  <section>
    <h2>Where each team finishes</h2>
    <p>Share of simulations ending at each seed. Seeds left of the dashed line make the playoffs.</p>
    <div class="chart" id="chart-seeds"></div>
  </section>

  <section>
    <details>
      <summary>Table view</summary>
      <div class="table-wrap"><table id="table"></table></div>
    </details>
  </section>

  <footer id="footer"></footer>
</main>
`;

  function renderReport(DATA, root) {
    const L = DATA.league;
    root.innerHTML = REPORT_MARKUP;
    const LUCK_COLORS = ['#d03b3b', '#f08a24', '#f2c200', '#8cc63f', '#1a9b4b'];
    const CONFIG = { responsive: true, displaylogo: false,
                     modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'] };

    const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const fmtPct = (v) => v.toFixed(1) + '%';
    const fmtLuck = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1);

    function theme() {
      return {
        surface: css('--surface-1'), text: css('--text-primary'), text2: css('--text-secondary'),
        muted: css('--text-muted'), grid: css('--grid'), neutral: css('--neutral'),
        accent: css('--accent'), barOff: css('--bar-off'),
        seqLow: css('--seq-low'), seqHigh: css('--seq-high'), dark: css('color-scheme') === 'dark',
      };
    }

    function baseLayout(t, extra) {
      return Object.assign({
        paper_bgcolor: t.surface, plot_bgcolor: t.surface,
        font: { family: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', size: 13, color: t.text },
        hoverlabel: { bgcolor: t.surface, bordercolor: t.neutral, font: { color: t.text } },
        margin: { l: 10, r: 10, t: 10, b: 10 },
      }, extra);
    }

    function axis(t, extra) {
      return Object.assign({ gridcolor: t.grid, zerolinecolor: t.grid, linecolor: t.neutral,
                             tickfont: { color: t.text2 }, automargin: true }, extra);
    }

    // ---------------------------------------------------------------- header
    document.getElementById("title").textContent = `Schedule luck — ${L.name || `league ${L.id}`}, ${L.year}`;
    const parts = [`${L.n_teams} teams`, `${L.n_playoff_teams} make the playoffs`];
    if (L.divisions.length) parts.push(`divisions: ${L.divisions.join(', ')}`);
    parts.push(`${L.num_schedules.toLocaleString()} simulated schedules per week`);
    document.getElementById('subtitle').textContent = parts.join(' · ');
    document.getElementById('footer').textContent =
      `Generated ${L.generated} · ESPN fantasy football schedule permutations`;
    if (L.notes.length) {
      const notes = document.getElementById('notes');
      notes.innerHTML = L.notes.map((n) => `<p>${esc(n)}</p>`).join('');
      notes.hidden = false;
    }

    // Stepped week slider: click a week, drag across weeks, or use arrow keys
    const slider = document.getElementById('week');
    const cutoffs = DATA.weeks.map((w) => w.week);
    let current = cutoffs.length - 1;
    slider.innerHTML = cutoffs.map((wk, i) =>
      `<div class="week" data-i="${i}"><div class="block"></div><span class="num">${wk}</span></div>`).join('');
    slider.setAttribute('aria-valuemin', cutoffs[0]);
    slider.setAttribute('aria-valuemax', cutoffs[cutoffs.length - 1]);
    const weekEls = [...slider.children];

    function paintWeeks() {
      weekEls.forEach((el, i) => {
        el.classList.toggle('on', i < current);
        el.classList.toggle('current', i === current);
      });
      slider.setAttribute('aria-valuenow', cutoffs[current]);
      slider.setAttribute('aria-valuetext', `Through week ${cutoffs[current]}`);
    }

    function selectWeek(i) {
      i = Math.max(0, Math.min(cutoffs.length - 1, i));
      if (i === current) return;
      current = i;
      history.replaceState(null, '', `#week=${cutoffs[current]}`);
      render();
    }

    function weekAt(clientX) {
      const index = weekEls.findIndex((el) => {
        const r = el.getBoundingClientRect();
        return clientX <= r.right + 2;
      });
      return index === -1 ? cutoffs.length - 1 : index;
    }

    slider.addEventListener('pointerdown', (e) => {
      slider.setPointerCapture(e.pointerId);
      selectWeek(weekAt(e.clientX));
    });
    slider.addEventListener('pointermove', (e) => {
      if (slider.hasPointerCapture(e.pointerId)) selectWeek(weekAt(e.clientX));
    });
    slider.addEventListener('keydown', (e) => {
      const step = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[e.key];
      if (step) { e.preventDefault(); selectWeek(current + step); }
      if (e.key === 'Home') { e.preventDefault(); selectWeek(0); }
      if (e.key === 'End') { e.preventDefault(); selectWeek(cutoffs.length - 1); }
    });

    if (cutoffs.length === 1) {
      slider.hidden = true;
      document.getElementById('week-hint').textContent = 'Only the full season is available (no schedule file).';
    } else {
      document.getElementById('week-hint').textContent = 'Click or drag across the weeks to see how the luck built up.';
    }

    // ---------------------------------------------------------------- charts
    function drawPlayoff(w, t) {
      const rows = [...w.results].sort((a, b) => a.playoff - b.playoff);
      Plotly.react('chart-playoff', [{
        type: 'bar', orientation: 'h',
        y: rows.map((r) => r.team), x: rows.map((r) => r.playoff),
        marker: { color: t.accent, cornerradius: 4 },
        text: rows.map((r) => fmtPct(r.playoff)), textposition: 'outside', cliponaxis: false,
        textfont: { color: t.text },
        customdata: rows.map((r) => [r.record, r.points_for.toFixed(1)]),
        hovertemplate: '<b>%{y}</b><br>Playoff odds: %{x:.1f}%<br>Record: %{customdata[0]}' +
                       '<br>Points for: %{customdata[1]}<extra></extra>',
      }], baseLayout(t, {
        height: 60 + rows.length * 34, bargap: 0.3,
        xaxis: axis(t, { range: [0, document.getElementById('chart-playoff').clientWidth < 560 ? 128 : 112], ticksuffix: '%', tickvals: [0, 25, 50, 75, 100] }),
        yaxis: axis(t, { ticksuffix: '  ', gridcolor: 'rgba(0,0,0,0)',
                         tickvals: rows.map((r) => r.team),
                         ticktext: rows.map((r) => `<b>${esc(r.team)}</b> <span style="color:${t.muted}">${r.record}</span>`) }),
      }), CONFIG);
    }

    function drawLuck(w, t) {
      const rows = w.results;
      const limit = Math.max(1, ...rows.map((r) => Math.abs(r.luck)));
      // Place each name above or below its dot, trying wider offsets until its
      // (estimated) box clears every dot and every label placed so far. Labels
      // pushed past the first offset get a thin leader line.
      // On phones: colorbar below the plot, and only the 4 most extreme teams
      // are labeled (tap a dot for the rest).
      const narrow = document.getElementById('chart-luck').clientWidth < 560;
      const X_RANGE = [-3, 103], Y_RANGE = [-5, 108], HEIGHT = narrow ? 520 : 600;
      const plotW = Math.max(200, document.getElementById('chart-luck').clientWidth - (narrow ? 60 : 170));
      const plotH = HEIGHT - (narrow ? 150 : 90);
      const extremes = new Set([...rows].sort((a, b) => Math.abs(b.luck) - Math.abs(a.luck))
                                        .slice(0, narrow ? 4 : rows.length).map((r) => r.team));
      const toPx = (x, y) => [(x - X_RANGE[0]) / (X_RANGE[1] - X_RANGE[0]) * plotW,
                              (Y_RANGE[1] - y) / (Y_RANGE[1] - Y_RANGE[0]) * plotH];
      const overlaps = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
      const placed = rows.map((r) => {
        const [px, py] = toPx(r.expected, r.actual);
        return { l: px - 8, r: px + 8, t: py - 8, b: py + 8 };
      });
      // The LUCKY / UNLUCKY boxes in the corners are obstacles too
      const [boxW, boxH] = narrow ? [64, 26] : [150, 44];
      const [lx, ly] = toPx(2, 104), [ux, uy] = toPx(98, -2);
      placed.push({ l: lx, r: lx + boxW, t: ly, b: ly + boxH },
                  { l: ux - boxW, r: ux, t: uy - boxH, b: uy });
      const labels = [];
      const order = [...rows].filter((r) => extremes.has(r.team))
                             .sort((a, b) => a.actual - b.actual || a.expected - b.expected);
      order.forEach((r, i) => {
        const [px, py] = toPx(r.expected, r.actual);
        const xanchor = r.expected < 10 ? 'left' : r.expected > 90 ? 'right' : 'center';
        const w = r.team.length * 6.6 + 6;
        const l = xanchor === 'left' ? px : xanchor === 'right' ? px - w : px - w / 2;
        const first = i % 2 === 0 ? 1 : -1;
        const offsets = [16, 32, 48, 64].flatMap((d) => [first * d, -first * d]);
        let dy = offsets[0], box;
        for (const candidate of offsets) {
          const top = candidate > 0 ? py - candidate - 16 : py - candidate;
          box = { l, r: l + w, t: top, b: top + 16 };
          dy = candidate;
          if (!placed.some((o) => overlaps(box, o))) break;
        }
        placed.push(box);
        labels.push({
          x: r.expected, y: r.actual, text: esc(r.team), ax: 0, ay: -dy,
          xanchor, yanchor: dy > 0 ? 'bottom' : 'top', font: { size: 12, color: t.text },
          showarrow: true, arrowhead: 0, arrowwidth: 0.8, standoff: 7,
          arrowcolor: Math.abs(dy) > 16 ? t.neutral : 'rgba(0,0,0,0)',
        });
      });
      Plotly.react('chart-luck', [{
        type: 'scatter', mode: 'lines', x: [0, 100], y: [0, 100], hoverinfo: 'skip',
        line: { color: t.neutral, dash: 'dash', width: 1.5 }, showlegend: false,
      }, {
        type: 'scatter', mode: 'markers',
        x: rows.map((r) => r.expected), y: rows.map((r) => r.actual),
        text: rows.map((r) => r.team), cliponaxis: false,
        marker: {
          size: 14, color: rows.map((r) => r.luck), cmin: -limit, cmax: limit,
          colorscale: LUCK_COLORS.map((c, i) => [i / (LUCK_COLORS.length - 1), c]),
          line: { color: t.surface, width: 2 },
          colorbar: Object.assign(
            { title: { text: 'Luck index', side: narrow ? 'top' : 'right', font: { color: t.text2 } },
              tickfont: { color: t.text2 }, outlinewidth: 0, thickness: 12, len: 0.8, tickformat: '+.0f' },
            narrow ? { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.32, yanchor: 'top' } : {}),
        },
        customdata: rows.map((r) => [r.record, fmtLuck(r.luck)]),
        hovertemplate: '<b>%{text}</b><br>Actual: %{y:.1f}% (%{customdata[0]})' +
                       '<br>Expected: %{x:.1f}%<br>Luck: %{customdata[1]} pts<extra></extra>',
        showlegend: false,
      }], baseLayout(t, {
        height: HEIGHT,
        xaxis: axis(t, { title: { text: narrow ? 'Expected win %' : 'Expected win % (avg. over simulated schedules)' },
                         range: [-3, 103], ticksuffix: '%', dtick: 20 }),
        yaxis: axis(t, { title: { text: 'Actual win %' }, range: [-5, 108], ticksuffix: '%', dtick: 20 }),
        annotations: [...labels,
          { x: 2, y: 104, xanchor: 'left', yanchor: 'top', showarrow: false, align: 'left',
            text: narrow ? '<b>LUCKY</b>' : '<b>LUCKY</b><br>won more than expected', font: { size: 11, color: t.text2 },
            bordercolor: LUCK_COLORS[4], borderwidth: 2, borderpad: 5, bgcolor: t.surface },
          { x: 98, y: -2, xanchor: 'right', yanchor: 'bottom', showarrow: false, align: 'left',
            text: narrow ? '<b>UNLUCKY</b>' : '<b>UNLUCKY</b><br>won fewer than expected', font: { size: 11, color: t.text2 },
            bordercolor: LUCK_COLORS[0], borderwidth: 2, borderpad: 5, bgcolor: t.surface },
        ],
      }), CONFIG);
    }

    // Interpolate between two hex colors (for the heatmap cells' text contrast)
    function mix(a, b, f) {
      const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
      const [x, y] = [p(a), p(b)];
      return x.map((v, i) => Math.round(v + (y[i] - v) * f));
    }
    const luminance = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;

    function drawSwap(w, t) {
      const el = document.getElementById('chart-swap');
      const section = el.closest('section');
      if (!w.swap) { section.hidden = true; return; }
      section.hidden = false;
      const order = [...w.results].sort((a, b) => b.playoff - a.playoff).map((r) => r.team);
      const idx = Object.fromEntries(w.swap.teams.map((name, i) => [name, i]));
      const z = order.map((x) => order.map((y) => w.swap.wins[idx[x]][idx[y]]));
      const rec = order.map((x) => order.map((y) => w.swap.records[idx[x]][idx[y]]));
      const actual = order.map((x) => w.swap.wins[idx[x]][idx[x]]);
      const flat = z.flat();
      const [lo, hi] = [Math.min(...flat), Math.max(...flat)];
      const annotations = [];
      order.forEach((x, i) => order.forEach((y, j) => {
        const f = hi > lo ? (z[i][j] - lo) / (hi - lo) : 0.5;
        const light = luminance(mix(t.seqLow, t.seqHigh, f)) > 0.55;
        annotations.push({ x: y, y: x, text: i === j ? `<b>${rec[i][j]}</b>` : rec[i][j],
                           showarrow: false, font: { size: 11, color: light ? '#0b0b0b' : '#f7f7f5' } });
      }));
      const diff = z.map((row, i) => row.map((v) => {
        const d = v - actual[i];
        return d === 0 ? 'same as actual' : `${d > 0 ? '+' : '−'}${Math.abs(d)} win${Math.abs(d) === 1 ? '' : 's'} vs actual`;
      }));
      const n = order.length;
      // Too narrow for readable cells: keep a minimum width and scroll inside the card
      const minWidth = 160 + n * 52;
      const width = el.parentElement.clientWidth - 40 < minWidth ? minWidth : undefined;
      Plotly.react(el, [{
        type: 'heatmap', x: order, y: order, z, zmin: lo, zmax: hi, xgap: 2, ygap: 2,
        colorscale: [[0, t.seqLow], [1, t.seqHigh]],
        colorbar: { title: { text: 'Wins', side: 'right', font: { color: t.text2 } },
                    tickfont: { color: t.text2 }, outlinewidth: 0, thickness: 12, len: 0.8 },
        customdata: rec.map((row, i) => row.map((r, j) => [r, diff[i][j]])),
        hovertemplate: '<b>%{y}</b> with <b>%{x}</b>’s schedule<br>Record: %{customdata[0]}' +
                       '<br>%{customdata[1]}<extra></extra>',
      }], baseLayout(t, {
        height: 140 + n * 40, width, annotations,
        xaxis: axis(t, { title: { text: 'Playing this team’s schedule' }, side: 'top', tickangle: -40,
                         showgrid: false }),
        yaxis: axis(t, { autorange: 'reversed', showgrid: false, ticksuffix: '  ' }),
      }), CONFIG);
    }

    function drawSeeds(w, t) {
      // Desktop uses the precomputed grid (e.g. 2x6 for 12 teams); phones get 2 columns
      const narrow = document.getElementById('chart-seeds').clientWidth < 640;
      const cols = narrow ? 2 : L.grid.cols;
      const rows = Math.ceil(L.n_teams / cols);
      const order = [...w.results].sort((a, b) => b.playoff - a.playoff);
      const nSeeds = L.n_teams;
      const seeds = Array.from({ length: nSeeds }, (_, i) => i + 1);
      const yMax = Math.max(...order.flatMap((r) => w.seeds[r.team])) * 1.12;
      const traces = [], annotations = [], shapes = [];
      const layout = baseLayout(t, {
        height: rows * (narrow ? 180 : 200) + 60, showlegend: false, bargap: 0.15,
        grid: { rows, columns: cols, pattern: 'independent', xgap: 0.14, ygap: 0.42 },
        margin: { l: 10, r: 10, t: 46, b: 10 },
      });
      order.forEach((r, i) => {
        const s = i === 0 ? '' : String(i + 1);
        traces.push({
          type: 'bar', x: seeds, y: w.seeds[r.team], xaxis: 'x' + s, yaxis: 'y' + s,
          marker: { color: seeds.map((k) => (k <= L.n_playoff_teams ? t.accent : t.barOff)),
                    cornerradius: 2 },
          hovertemplate: `<b>${esc(r.team)}</b><br>Seed %{x}: %{y:.1f}%<extra></extra>`,
        });
        layout['xaxis' + s] = axis(t, { tickvals: seeds.filter((k) => nSeeds <= 8 || k % 2 === 1),
                                        tickangle: 0, range: [0.4, nSeeds + 0.6], showgrid: false,
                                        tickfont: { size: 10, color: t.text2 } });
        layout['yaxis' + s] = axis(t, { range: [0, yMax], ticksuffix: '%', nticks: 4,
                                        showticklabels: i % cols === 0, tickfont: { size: 10, color: t.text2 } });
        annotations.push({ xref: `x${s} domain`, yref: `y${s} domain`, x: 0, y: 1.04,
                           xanchor: 'left', yanchor: 'bottom', showarrow: false, align: 'left',
                           text: `<b>${esc(r.team)}</b><br><span style="color:${t.muted}">${fmtPct(r.playoff)} playoffs</span>`,
                           font: { size: 12, color: t.text } });
        shapes.push({ type: 'line', xref: 'x' + s, yref: `y${s} domain`,
                      x0: L.n_playoff_teams + 0.5, x1: L.n_playoff_teams + 0.5, y0: 0, y1: 1,
                      line: { color: t.neutral, width: 1, dash: 'dash' } });
      });
      layout.annotations = annotations;
      layout.shapes = shapes;
      Plotly.react('chart-seeds', traces, layout, CONFIG);
    }

    function drawTable(w) {
      const head = ['Team', 'Record', 'Points for', 'Actual win %', 'Expected win %', 'Luck (pts)', 'Playoff %'];
      const body = w.results.map((r) => `<tr><td>${esc(r.team)}</td><td>${r.record}</td>` +
        `<td>${r.points_for.toFixed(1)}</td><td>${fmtPct(r.actual)}</td><td>${fmtPct(r.expected)}</td>` +
        `<td>${fmtLuck(r.luck)}</td><td>${fmtPct(r.playoff)}</td></tr>`).join('');
      document.getElementById('table').innerHTML =
        `<thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${body}</tbody>`;
    }

    function render() {
      const w = DATA.weeks[current];
      document.getElementById('week-label').textContent = `${w.week} of ${L.weeks_played}`;
      paintWeeks();
      const t = theme();
      drawPlayoff(w, t);
      drawLuck(w, t);
      drawSwap(w, t);
      drawSeeds(w, t);
      drawTable(w);
    }

    // #week=N in the URL opens the report at that week (handy for sharing)
    const linked = cutoffs.indexOf(Number((location.hash.match(/week=(\d+)/) || [])[1]));
    if (linked >= 0) current = linked;
    let resizeTimer;
    window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(render, 200); });
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
    new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    render();
  }

  window.renderReport = renderReport;
  const embedded = document.getElementById('report-data');
  if (embedded && embedded.textContent.trim()) {
    renderReport(JSON.parse(embedded.textContent), document.getElementById('report-root'));
  }
})();
