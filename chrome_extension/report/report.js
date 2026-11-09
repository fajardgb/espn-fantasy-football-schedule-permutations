/*
 * Schedule luck report: page layout and charts (Plotly, drawn as still images).
 *
 * Shared by both ways of making a report:
 *   - build_report.py inlines this file into a standalone .html file
 *   - the Chrome extension's report page loads it directly (and builds PDFs
 *     from the same figures, via window.ReportFigures)
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

  <section id="swap-section">
    <h2>What if you had their schedule?</h2>
    <p>Each team's real weekly scores, replayed against every other team's actual schedule.
      It shows how much a record came down to who you happened to play each week. Pick a team
      to see its record with each schedule, or show all teams at once (each row is a team, and
      the bold diagonal is each team's real record).</p>
    <div class="swap-controls">
      <label class="swap-team" id="swap-team-label">Team
        <select id="swap-team"></select>
      </label>
      <div class="toggle" role="group" aria-label="Show">
        <button type="button" data-view="one" aria-pressed="true">One team</button>
        <button type="button" data-view="all" aria-pressed="false">All teams</button>
      </div>
    </div>
    <div class="chart" id="chart-swap"></div>
  </section>

  <section>
    <h2>Where each team finishes</h2>
    <p>Share of simulations ending at each seed. Blue bars are playoff seeds; gray bars miss the playoffs.</p>
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

  // Charts are pictures: no zooming, panning, hover or toolbar
  const CONFIG = { staticPlot: true, displayModeBar: false };
  const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  const LUCK_COLORS = ['#d03b3b', '#f08a24', '#f2c200', '#8cc63f', '#1a9b4b'];

  /** Colors for images that don't follow the page's theme (the PDF). */
  const LIGHT_THEME = {
    surface: '#ffffff', text: '#0b0b0b', text2: '#52514e', muted: '#7a7974', grid: '#e8e7e2',
    neutral: '#9a9993', accent: '#2a78d6', barOff: '#c9c8c2',
    more: '#2a78d6', fewer: '#e34948', same: '#e6e5e0', own: '#52514e',
  };

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmtPct = (v) => v.toFixed(1) + '%';
  const fmtLuck = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1);
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  function baseLayout(t, extra) {
    return Object.assign({
      paper_bgcolor: t.surface, plot_bgcolor: t.surface,
      font: { family: FONT, size: 13, color: t.text },
      margin: { l: 10, r: 10, t: 10, b: 10 },
    }, extra);
  }

  function axis(t, extra) {
    return Object.assign({ gridcolor: t.grid, zerolinecolor: t.grid, linecolor: t.neutral,
                           tickfont: { color: t.text2 }, automargin: true, fixedrange: true }, extra);
  }

  // Interpolate between two hex colors
  const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const mix = (a, b, f) => rgb(a).map((v, i) => Math.round(v + (rgb(b)[i] - v) * f));
  const luminance = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  const toHex = (c) => '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');

  /**
   * Diverging scale for "wins vs. real record": red (fewer), light gray
   * (same), blue (more). f runs from -1 to 1 (difference / largest difference).
   */
  function divergingColor(t, f) {
    if (!f) return t.same;
    const strength = Math.pow(Math.min(1, Math.abs(f)), 0.75);
    return toHex(mix(t.same, f > 0 ? t.more : t.fewer, strength));
  }
  function divergingScale(t) {
    return Array.from({ length: 21 }, (_, k) => {
      const f = k / 10 - 1;
      return [k / 20, divergingColor(t, f)];
    });
  }
  const inkOn = (hex) => (luminance(rgb(hex)) > 0.55 ? '#0b0b0b' : '#f7f7f5');

  // ------------------------------------------------------------- figures
  // Each returns {data, layout} for Plotly; `width` is the drawing width in px.

  function playoffFigure(w, t, { width }) {
    const rows = [...w.results].sort((a, b) => a.playoff - b.playoff);
    return {
      data: [{
        type: 'bar', orientation: 'h',
        y: rows.map((r) => r.team), x: rows.map((r) => r.playoff),
        marker: { color: t.accent, cornerradius: 4 },
        text: rows.map((r) => fmtPct(r.playoff)), textposition: 'outside', cliponaxis: false,
        textfont: { color: t.text },
      }],
      layout: baseLayout(t, {
        width, height: 60 + rows.length * 34, bargap: 0.3,
        xaxis: axis(t, { range: [0, width < 560 ? 128 : 112], ticksuffix: '%', tickvals: [0, 25, 50, 75, 100] }),
        yaxis: axis(t, { ticksuffix: '  ', gridcolor: 'rgba(0,0,0,0)',
                         tickvals: rows.map((r) => r.team),
                         ticktext: rows.map((r) => `<b>${esc(r.team)}</b> <span style="color:${t.muted}">${r.record}</span>`) }),
      }),
    };
  }

  function luckFigure(w, t, { width }) {
    const rows = w.results;
    const limit = Math.max(1, ...rows.map((r) => Math.abs(r.luck)));
    // Phones: colorbar under the plot and shorter labels on the corner boxes
    const narrow = width < 560;
    const X_RANGE = [-3, 103], Y_RANGE = [-5, 108], HEIGHT = narrow ? 680 : 600;
    const plotW = Math.max(200, width - (narrow ? 60 : 170));
    const plotH = HEIGHT - (narrow ? 170 : 90);
    const fontSize = narrow ? 11 : 12;
    const charW = narrow ? 6.4 : 6.6;
    // Place each name above or below its dot, trying wider offsets until its
    // (estimated) box clears every dot and every label placed so far. Labels
    // pushed past the first offset get a thin leader line.
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
    [...rows].sort((a, b) => a.actual - b.actual || a.expected - b.expected).forEach((r, i) => {
      const [px, py] = toPx(r.expected, r.actual);
      const xanchor = r.expected < 10 ? 'left' : r.expected > 90 ? 'right' : 'center';
      const boxWidth = r.team.length * charW + 6;
      const l = xanchor === 'left' ? px : xanchor === 'right' ? px - boxWidth : px - boxWidth / 2;
      const first = i % 2 === 0 ? 1 : -1;
      const offsets = [16, 32, 48, 64, 80].flatMap((d) => [first * d, -first * d]);
      let dy = offsets[0], box;
      for (const candidate of offsets) {
        const top = candidate > 0 ? py - candidate - 16 : py - candidate;
        box = { l, r: l + boxWidth, t: top, b: top + 16 };
        dy = candidate;
        if (!placed.some((o) => overlaps(box, o))) break;
      }
      placed.push(box);
      labels.push({
        x: r.expected, y: r.actual, text: esc(r.team), ax: 0, ay: -dy,
        xanchor, yanchor: dy > 0 ? 'bottom' : 'top', font: { size: fontSize, color: t.text },
        showarrow: true, arrowhead: 0, arrowwidth: 0.8, standoff: 7,
        arrowcolor: Math.abs(dy) > 16 ? t.neutral : 'rgba(0,0,0,0)',
      });
    });
    return {
      data: [{
        type: 'scatter', mode: 'lines', x: [0, 100], y: [0, 100],
        line: { color: t.neutral, dash: 'dash', width: 1.5 }, showlegend: false,
      }, {
        type: 'scatter', mode: 'markers', cliponaxis: false,
        x: rows.map((r) => r.expected), y: rows.map((r) => r.actual),
        marker: {
          size: 14, color: rows.map((r) => r.luck), cmin: -limit, cmax: limit,
          colorscale: LUCK_COLORS.map((c, i) => [i / (LUCK_COLORS.length - 1), c]),
          line: { color: t.surface, width: 2 },
          colorbar: Object.assign(
            { title: { text: 'Luck index', side: narrow ? 'top' : 'right', font: { color: t.text2 } },
              tickfont: { color: t.text2 }, outlinewidth: 0, thickness: 12, len: 0.8, tickformat: '+.0f' },
            narrow ? { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.2, yanchor: 'top' } : {}),
        },
        showlegend: false,
      }],
      layout: baseLayout(t, {
        width, height: HEIGHT,
        xaxis: axis(t, { title: { text: narrow ? 'Expected win %' : 'Expected win % (avg. over simulated schedules)' },
                         range: X_RANGE, ticksuffix: '%', dtick: 20 }),
        yaxis: axis(t, { title: { text: 'Actual win %' }, range: Y_RANGE, ticksuffix: '%', dtick: 20 }),
        annotations: [...labels,
          { x: 2, y: 104, xanchor: 'left', yanchor: 'top', showarrow: false, align: 'left',
            text: narrow ? '<b>LUCKY</b>' : '<b>LUCKY</b><br>won more than expected', font: { size: 11, color: t.text2 },
            bordercolor: LUCK_COLORS[4], borderwidth: 2, borderpad: 5, bgcolor: t.surface },
          { x: 98, y: -2, xanchor: 'right', yanchor: 'bottom', showarrow: false, align: 'left',
            text: narrow ? '<b>UNLUCKY</b>' : '<b>UNLUCKY</b><br>won fewer than expected', font: { size: 11, color: t.text2 },
            bordercolor: LUCK_COLORS[0], borderwidth: 2, borderpad: 5, bgcolor: t.surface },
        ],
      }),
    };
  }

  /**
   * A grid of records: rows are teams, columns are whose schedule they play.
   * Cells are colored by wins compared with that team's real record, with a
   * colorbar as the key.
   */
  function swapGrid(w, t, { rows, cols, rowLabels, colLabels, width, height, horizontalBar, fontSize, transpose = false }) {
    const idx = Object.fromEntries(w.swap.teams.map((name, i) => [name, i]));
    const diff = (x, y) => w.swap.wins[idx[x]][idx[y]] - w.swap.wins[idx[x]][idx[x]];
    const limit = Math.max(1, Math.ceil(Math.max(...rows.flatMap((x) => cols.map((y) => Math.abs(diff(x, y)))))));
    // cell(i, j): team rows[i] playing cols[j]'s schedule. Transposed, schedules run down the side.
    const nr = transpose ? cols.length : rows.length;
    const nc = transpose ? rows.length : cols.length;
    const at = (r, c) => (transpose ? [rows[c], cols[r]] : [rows[r], cols[c]]);
    const z = Array.from({ length: nr }, (_, r) => Array.from({ length: nc }, (__, c) => diff(...at(r, c))));
    const annotations = [];
    z.forEach((row, r) => row.forEach((d, c) => {
      const [x, y] = at(r, c);
      const record = w.swap.records[idx[x]][idx[y]];
      annotations.push({ x: c, y: r, text: x === y ? `<b>${record}</b>` : record, showarrow: false,
                         font: { size: fontSize, color: inkOn(divergingColor(t, d / limit)) } });
    }));
    const xLabels = transpose ? rowLabels : colLabels;
    const yLabels = transpose ? colLabels : rowLabels;
    const scheduleTitle = { text: 'Playing this team’s schedule' };
    // Narrow colorbars only have room for the ends and the middle
    const compact = horizontalBar && width < 640;
    const step = limit > 6 ? 2 : 1;
    const ticks = [];
    if (compact) ticks.push(-limit, 0, limit);
    else for (let v = -limit; v <= limit; v += step) ticks.push(v);
    if (!ticks.includes(0)) ticks.push(0);
    const colorbar = Object.assign({
      // Wide horizontal bars get their title beside them: Plotly misplaces a
      // title below a wide horizontal colorbar
      title: { text: 'Wins vs. real record', side: horizontalBar && compact ? 'bottom' : 'right',
               font: { color: t.text2, size: 12 } },
      tickvals: ticks, ticktext: ticks.map((v) => (v > 0 ? `+${v}` : v < 0 ? `−${-v}` : (compact ? 'same' : '0 (same)'))),
      tickfont: { color: t.text2, size: 11 }, outlinewidth: 0, thickness: 12,
    }, horizontalBar
      ? { orientation: 'h', x: 0.5, xanchor: 'center', yref: 'container', y: (compact ? 46 : 22) / height, yanchor: 'bottom',
          len: compact ? 0.9 : 0.6 }
      : { len: 0.9, y: 0.5 });
    return {
      data: [{
        type: 'heatmap', z, x: [...Array(nc).keys()], y: [...Array(nr).keys()],
        zmin: -limit, zmax: limit, colorscale: divergingScale(t), colorbar, xgap: 2, ygap: 2,
      }],
      layout: baseLayout(t, {
        width, height, annotations,
        // Tilted column labels lean right: leave room so the last one isn't cut off
        // (the all-teams view's colorbar already leaves room on the right)
        margin: { l: 10, r: !transpose && horizontalBar ? 110 : 10, t: 10,
                  b: horizontalBar ? (width < 640 ? 100 : 64) : 10 },
        xaxis: axis(t, { title: transpose ? undefined : scheduleTitle, side: 'top', tickangle: transpose ? 0 : -40,
                         ticklabeloverflow: 'allow',
                         showgrid: false, tickvals: [...Array(nc).keys()], ticktext: xLabels }),
        yaxis: axis(t, { title: transpose ? scheduleTitle : undefined, autorange: 'reversed', showgrid: false,
                         ticksuffix: '  ', tickvals: [...Array(nr).keys()], ticktext: yLabels }),
      }),
    };
  }

  /**
   * One team's row: its own schedule first, then every other team's. On
   * narrow screens the row turns into a column so it fits without scrolling.
   */
  function swapOneFigure(w, t, team, { width, order }) {
    const cols = [team, ...order.filter((x) => x !== team)];
    const narrow = width < 640;
    return swapGrid(w, t, {
      rows: [team], cols, width, horizontalBar: true, fontSize: 12, transpose: narrow,
      height: narrow ? 170 + cols.length * 36 : 270,
      rowLabels: [`<b>${esc(team)}</b>`],
      colLabels: cols.map((y, j) => (j === 0 ? '<b>Own schedule</b><br>(actual record)' : esc(y))),
    });
  }

  /** Every team on every schedule; the diagonal is each team's real record. */
  function swapAllFigure(w, t, { width, order }) {
    const n = order.length;
    return swapGrid(w, t, {
      rows: order, cols: order, width, height: 150 + n * 38, horizontalBar: false,
      fontSize: n > 14 ? 9.5 : 11, rowLabels: order.map(esc), colLabels: order.map(esc),
    });
  }

  function seedsFigure(w, t, { width, nPlayoffTeams, nTeams, gridCols }) {
    // Wide: the precomputed grid (e.g. 2x6 for 12 teams); phones get 2 columns
    const narrow = width < 640;
    const cols = narrow ? 2 : gridCols;
    const rows = Math.ceil(nTeams / cols);
    const order = [...w.results].sort((a, b) => b.playoff - a.playoff);
    const seeds = Array.from({ length: nTeams }, (_, i) => i + 1);
    const yMax = Math.max(...order.flatMap((r) => w.seeds[r.team])) * 1.12;
    const traces = [], annotations = [], shapes = [];
    const layout = baseLayout(t, {
      width, height: rows * (narrow ? 180 : 200) + (narrow ? 115 : 90), bargap: 0.15,
      grid: { rows, columns: cols, pattern: 'independent', xgap: 0.14, ygap: 0.42 },
      margin: { l: 10, r: 10, t: narrow ? 105 : 80, b: 10 },
      showlegend: true,
      legend: { orientation: 'h', x: 0, xanchor: 'left', y: 1, yanchor: 'top',
                yref: 'container', font: { size: 13, color: t.text }, itemclick: false },
    });
    order.forEach((r, i) => {
      const s = i === 0 ? '' : String(i + 1);
      traces.push({
        type: 'bar', x: seeds, y: w.seeds[r.team], xaxis: 'x' + s, yaxis: 'y' + s, showlegend: false,
        marker: { color: seeds.map((k) => (k <= nPlayoffTeams ? t.accent : t.barOff)), cornerradius: 2 },
      });
      layout['xaxis' + s] = axis(t, { tickvals: seeds.filter((k) => nTeams <= 8 || k % 2 === 1),
                                      tickangle: 0, range: [0.4, nTeams + 0.6], showgrid: false,
                                      tickfont: { size: 10, color: t.text2 } });
      layout['yaxis' + s] = axis(t, { range: [0, yMax], ticksuffix: '%', nticks: 4,
                                      showticklabels: i % cols === 0, tickfont: { size: 10, color: t.text2 } });
      annotations.push({ xref: `x${s} domain`, yref: `y${s} domain`, x: 0, y: 1.04,
                         xanchor: 'left', yanchor: 'bottom', showarrow: false, align: 'left',
                         text: `<b>${esc(r.team)}</b><br><span style="color:${t.muted}">${fmtPct(r.playoff)} playoffs</span>`,
                         font: { size: 12, color: t.text } });
      shapes.push({ type: 'line', xref: 'x' + s, yref: `y${s} domain`,
                    x0: nPlayoffTeams + 0.5, x1: nPlayoffTeams + 0.5, y0: 0, y1: 1,
                    line: { color: t.neutral, width: 1, dash: 'dash' } });
    });
    // Legend entries only (no data): what blue and gray mean
    const seedRange = nPlayoffTeams > 1 ? `seeds 1–${nPlayoffTeams}` : 'seed 1';
    traces.push(
      { type: 'bar', x: [null], y: [null], name: `Made playoffs (${seedRange})`, marker: { color: t.accent }, showlegend: true },
      { type: 'bar', x: [null], y: [null], name: 'Missed playoffs', marker: { color: t.barOff }, showlegend: true },
    );
    layout.annotations = annotations;
    layout.shapes = shapes;
    return { data: traces, layout };
  }

  /** The numbers as a table image (for the PDF). */
  function tableFigure(w, t, { width, fontSize = 12, rowHeight = 26 }) {
    const rows = w.results;
    const header = ['Team', 'Record', 'Points for', 'Actual win %', 'Expected win %', 'Luck (pts)', 'Playoff %'];
    const columns = [
      rows.map((r) => r.team), rows.map((r) => r.record), rows.map((r) => r.points_for.toFixed(1)),
      rows.map((r) => fmtPct(r.actual)), rows.map((r) => fmtPct(r.expected)),
      rows.map((r) => fmtLuck(r.luck)), rows.map((r) => fmtPct(r.playoff)),
    ];
    return {
      data: [{
        type: 'table', columnwidth: [2.2, 1, 1.1, 1.2, 1.3, 1.1, 1.1],
        header: { values: header.map((h) => `<b>${h}</b>`), align: ['left', 'right'], height: rowHeight + 4,
                  fill: { color: t.surface }, line: { color: t.grid }, font: { color: t.text2, size: fontSize, family: FONT } },
        cells: { values: columns, align: ['left', 'right'], height: rowHeight,
                 fill: { color: t.surface }, line: { color: t.grid }, font: { color: t.text, size: fontSize, family: FONT } },
      }],
      layout: baseLayout(t, { width, height: rowHeight + 4 + rows.length * rowHeight + 24 }),
    };
  }

  // Expose the figures so the extension can draw the same charts into a PDF
  window.ReportFigures = {
    LIGHT_THEME, playoffFigure, luckFigure, swapOneFigure, swapAllFigure, seedsFigure, tableFigure,
  };

  // ------------------------------------------------------------- the page

  function renderReport(DATA, root) {
    const L = DATA.league;
    root.innerHTML = REPORT_MARKUP;
    const $ = (id) => document.getElementById(id);
    const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

    function theme() {
      return {
        surface: css('--surface-1'), text: css('--text-primary'), text2: css('--text-secondary'),
        muted: css('--text-muted'), grid: css('--grid'), neutral: css('--neutral'),
        accent: css('--accent'), barOff: css('--bar-off'),
        more: css('--more'), fewer: css('--fewer'), same: css('--same'), own: css('--own'),
      };
    }

    // ---------------------------------------------------------- header
    $('title').textContent = `Schedule luck — ${L.name || `league ${L.id}`}, ${L.year}`;
    const parts = [`${L.n_teams} teams`, `${L.n_playoff_teams} make the playoffs`];
    if (L.divisions.length) parts.push(`divisions: ${L.divisions.join(', ')}`);
    parts.push(`${L.num_schedules.toLocaleString()} simulated schedules per week`);
    $('subtitle').textContent = parts.join(' · ');
    $('footer').textContent = `Generated ${L.generated} · ESPN fantasy football schedule permutations`;
    if (L.notes.length) {
      $('notes').innerHTML = L.notes.map((n) => `<p>${esc(n)}</p>`).join('');
      $('notes').hidden = false;
    }

    // Stepped week slider: click a week, drag across weeks, or use arrow keys
    const slider = $('week');
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
      const index = weekEls.findIndex((el) => clientX <= el.getBoundingClientRect().right + 2);
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
      $('week-hint').textContent = 'Only the full season is available (no schedule file).';
    } else {
      $('week-hint').textContent = 'Click or drag across the weeks to see how the luck built up.';
    }

    // ------------------------------------------- schedule swap controls
    const finalWeek = DATA.weeks[DATA.weeks.length - 1];
    let swapView = 'one';
    // Start with the unluckiest team: usually the most interesting story
    let swapTeam = [...finalWeek.results].sort((a, b) => a.luck - b.luck)[0]?.team;
    const select = $('swap-team');
    [...finalWeek.results].map((r) => r.team).sort((a, b) => a.localeCompare(b)).forEach((team) => {
      select.append(new Option(team, team, false, team === swapTeam));
    });
    select.addEventListener('change', () => { swapTeam = select.value; render(); });
    root.querySelectorAll('.toggle button').forEach((button) => {
      button.addEventListener('click', () => { swapView = button.dataset.view; render(); });
    });

    // ---------------------------------------------------------- drawing
    const draw = (id, figure) => Plotly.react($(id), figure.data, figure.layout, CONFIG);
    const widthOf = (id) => $(id).clientWidth || 800;

    function drawSwap(w, t) {
      const section = $('swap-section');
      if (!w.swap) { section.hidden = true; return; }
      section.hidden = false;
      root.querySelectorAll('.toggle button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === swapView)));
      $('swap-team-label').hidden = swapView !== 'one';
      const chart = $('chart-swap');
      // Same column order in both views; on small screens the grid keeps a
      // readable size and scrolls sideways inside the card
      const order = [...w.results].sort((a, b) => b.playoff - a.playoff).map((r) => r.team);
      const available = chart.parentElement.clientWidth - 40;
      // Switching views changes the chart's whole shape: start it fresh
      if (chart.dataset.view !== swapView) {
        Plotly.purge(chart);
        chart.dataset.view = swapView;
      }
      if (swapView === 'one') {
        const width = available < 640 ? available : Math.max(available, 200 + order.length * 56);
        draw('chart-swap', swapOneFigure(w, t, swapTeam, { width, order }));
      } else {
        draw('chart-swap', swapAllFigure(w, t, { width: Math.max(available, 200 + order.length * 56), order }));
      }
    }

    function drawTable(w) {
      const head = ['Team', 'Record', 'Points for', 'Actual win %', 'Expected win %', 'Luck (pts)', 'Playoff %'];
      const body = w.results.map((r) => `<tr><td>${esc(r.team)}</td><td>${r.record}</td>` +
        `<td>${r.points_for.toFixed(1)}</td><td>${fmtPct(r.actual)}</td><td>${fmtPct(r.expected)}</td>` +
        `<td>${fmtLuck(r.luck)}</td><td>${fmtPct(r.playoff)}</td></tr>`).join('');
      $('table').innerHTML = `<thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${body}</tbody>`;
    }

    function render() {
      const w = DATA.weeks[current];
      $('week-label').textContent = `${w.week} of ${L.weeks_played}`;
      paintWeeks();
      const t = theme();
      draw('chart-playoff', playoffFigure(w, t, { width: widthOf('chart-playoff') }));
      draw('chart-luck', luckFigure(w, t, { width: widthOf('chart-luck') }));
      drawSwap(w, t);
      draw('chart-seeds', seedsFigure(w, t, {
        width: widthOf('chart-seeds'), nPlayoffTeams: L.n_playoff_teams, nTeams: L.n_teams, gridCols: L.grid.cols,
      }));
      drawTable(w);
    }

    // #week=N in the URL opens the report at that week (handy for sharing)
    const linked = cutoffs.indexOf(Number((location.hash.match(/week=(\d+)/) || [])[1]));
    if (linked >= 0) current = linked;
    let resizeTimer;
    let lastWidth = window.innerWidth;
    window.addEventListener('resize', () => {
      if (window.innerWidth === lastWidth) return; // ignore phone address-bar height changes
      lastWidth = window.innerWidth;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(render, 200);
    });
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
