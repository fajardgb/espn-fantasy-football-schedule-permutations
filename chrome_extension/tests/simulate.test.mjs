// Checks the JavaScript port against the Python tool.
// Reference results come from tests/make_golden.py; regenerate them with
//   uv run python chrome_extension/tests/make_golden.py
// whenever the Python logic changes.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, test } from 'node:test';

import { parseLeague, disambiguateNames, standardizeName } from '../lib/espn.js';
import {
  actualRecords,
  buildReportData,
  formatRecord,
  gridShape,
  recordToWinPct,
  runSimulation,
  seedOrder,
  seededRandom,
  swapMatrix,
} from '../lib/simulate.js';

const FIXTURES = ['espn_completed_season.json', 'espn_in_progress_season.json'];
const load = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url)));
const fixture = (name) => load(`../../tests/fixtures/${name}`);
const golden = (name) => load(`./golden/${name}`);

for (const name of FIXTURES) {
  describe(`matches the Python tool: ${name}`, () => {
    const league = parseLeague(fixture(name));
    const ref = golden(name);
    const names = league.teams.map((t) => t.name);

    test('teams, divisions and weeks', () => {
      assert.deepEqual(league.teams, ref.teams);
      assert.deepEqual(league.weeks, ref.weeks);
      assert.equal(league.nPlayoffTeams, ref.n_playoff_teams);
      assert.deepEqual(league.notes, ref.notes);
      assert.deepEqual(league.divisions, [...new Set(ref.teams.map((t) => t.division))].sort());
    });

    test('weekly scores', () => {
      league.teams.forEach((team, t) => assert.deepEqual(league.scores[t], ref.scores[team.name]));
    });

    test('schedule', () => {
      const asNames = league.schedule.map((week) => week.map(([a, b]) => [names[a], names[b]]));
      assert.deepEqual(asNames, ref.schedule);
    });

    test('actual records at every week', () => {
      for (const cutoff of ref.cutoffs) {
        const records = actualRecords(league, cutoff.week);
        const got = Object.fromEntries(names.map((n, t) =>
          [n, formatRecord(records[t].wins, records[t].losses, records[t].ties)]));
        assert.deepEqual(got, cutoff.actual_records, `week ${cutoff.week}`);
      }
    });

    test('schedule-swap matrix at every week', () => {
      for (const cutoff of ref.cutoffs) {
        const swap = swapMatrix(league, cutoff.week);
        const got = Object.fromEntries(names.map((x, i) =>
          [x, Object.fromEntries(names.map((y, j) => [y, swap.records[i][j]]))]));
        assert.deepEqual(got, cutoff.swap, `week ${cutoff.week}`);
      }
    });

    test('simulated playoff % and expected win % agree within sampling error', () => {
      for (const cutoff of ref.cutoffs.filter((c) => c.simulated)) {
        const { results } = runSimulation(league, { week: cutoff.week, numSchedules: ref.simulations, seed: 11 });
        for (const r of results) {
          const want = cutoff.simulated[r.team];
          // Two independent 20,000-run estimates: differences above ~1.5 points are very unlikely
          assert.ok(Math.abs(r.playoff - want.playoff) < 2,
            `week ${cutoff.week} ${r.team}: playoff ${r.playoff.toFixed(2)} vs Python ${want.playoff}`);
          assert.ok(Math.abs(r.expected - want.expected) < 1,
            `week ${cutoff.week} ${r.team}: expected ${r.expected.toFixed(2)} vs Python ${want.expected}`);
        }
      }
    });
  });
}

// ------------------------------------------------------------ playoff rules

function rulesSeason({ n, points, useH2H = false }) {
  return { n, points, useH2H };
}

function records(rows, n) {
  const rec = {
    wins: new Int32Array(n), losses: new Int32Array(n), ties: new Int32Array(n),
    h2hWins: new Float64Array(n * n), h2hGames: new Int32Array(n * n),
  };
  rows.forEach(([w, l, t = 0], i) => { rec.wins[i] = w; rec.losses[i] = l; rec.ties[i] = t; });
  return rec;
}

test('reproduces the playoff seeds ESPN assigned', () => {
  for (const name of FIXTURES) {
    const data = fixture(name);
    const league = parseLeague(data);
    const byId = new Map(data.teams.map((t) => [t.id, t]));
    const overall = league.teams.map((t) => byId.get(t.id).record.overall);
    const season = rulesSeason({ n: league.teams.length, points: overall.map((o) => o.pointsFor) });
    const rec = records(overall.map((o) => [o.wins, o.losses]), league.teams.length);
    const order = seedOrder(season, rec, league.teams.map((t) => t.division));
    const espn = [...league.teams.keys()].sort((a, b) =>
      byId.get(league.teams[a].id).playoffSeed - byId.get(league.teams[b].id).playoffSeed);
    assert.deepEqual(order.slice(0, league.nPlayoffTeams), espn.slice(0, league.nPlayoffTeams), name);
  }
});

test('division winner makes the playoffs even with a weak record', () => {
  const season = rulesSeason({ n: 5, points: [1500, 1400, 1300, 1200, 1100] });
  const rec = records([[10, 4], [9, 5], [8, 6], [5, 9], [4, 10]], 5);
  const order = seedOrder(season, rec, ['E', 'E', 'E', 'W', 'W']);
  assert.deepEqual(order.slice(0, 2), [0, 3]);
});

test('head-to-head breaks win % ties before points', () => {
  const rec = records([[7, 7], [7, 7]], 2);
  rec.h2hWins[0 * 2 + 1] = 0; rec.h2hGames[0 * 2 + 1] = 1;
  rec.h2hWins[1 * 2 + 0] = 1; rec.h2hGames[1 * 2 + 0] = 1;
  const points = [1500, 1000];
  assert.deepEqual(seedOrder(rulesSeason({ n: 2, points, useH2H: true }), rec, ['', '']), [1, 0]);
  assert.deepEqual(seedOrder(rulesSeason({ n: 2, points }), rec, ['', '']), [0, 1]);
});

test('head-to-head is skipped when tied teams met unequally', () => {
  const rec = records([[7, 7], [7, 7], [7, 7]], 3);
  rec.h2hWins[0 * 3 + 1] = 0; rec.h2hGames[0 * 3 + 1] = 1;
  rec.h2hWins[1 * 3 + 0] = 1; rec.h2hGames[1 * 3 + 0] = 1;
  const season = rulesSeason({ n: 3, points: [1500, 1000, 1200], useH2H: true });
  assert.deepEqual(seedOrder(season, rec, ['', '', '']), [0, 2, 1]);
});

// ------------------------------------------------------------- report data

test('report data has every week and consistent seed shares', async () => {
  const league = parseLeague(fixture('espn_in_progress_season.json'));
  const progress = [];
  const data = await buildReportData(league, {
    numSchedules: 300, onProgress: (done, total) => progress.push([done, total]), meta: { id: '1', year: 2026 },
  });
  assert.deepEqual(data.weeks.map((w) => w.week), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.deepEqual(progress.at(-1), [8, 8]);
  assert.deepEqual(data.league.grid, { rows: 2, cols: 6 });
  assert.equal(data.league.id, '1');
  for (const w of data.weeks) {
    for (const r of w.results) {
      const shares = w.seeds[r.team];
      assert.ok(Math.abs(shares.reduce((a, b) => a + b, 0) - 100) < 0.1);
      const playoffShare = shares.slice(0, data.league.n_playoff_teams).reduce((a, b) => a + b, 0);
      assert.ok(Math.abs(playoffShare - r.playoff) < 0.1);
    }
    // Swap diagonal is each team's actual record
    w.swap.teams.forEach((team, i) => {
      assert.equal(w.swap.records[i][i], w.results.find((r) => r.team === team).record);
    });
  }
  // Best playoff odds first
  const odds = data.weeks.at(-1).results.map((r) => r.playoff);
  assert.deepEqual(odds, [...odds].sort((a, b) => b - a));
});

test('same seed gives the same results', () => {
  const league = parseLeague(fixture('espn_completed_season.json'));
  const a = runSimulation(league, { numSchedules: 500, seed: 3 }).results;
  const b = runSimulation(league, { numSchedules: 500, seed: 3 }).results;
  assert.deepEqual(a, b);
});

// ----------------------------------------------------------------- helpers

test('helpers', () => {
  assert.equal(standardizeName('jason  wu'), 'Jason Wu');
  assert.equal(standardizeName('mcDonald'), 'McDonald');
  assert.deepEqual(disambiguateNames(['MM', 'BK', 'MM']), ['MM', 'BK', 'MM (2)']);
  assert.equal(recordToWinPct('5-9'), 5 / 14 * 100);
  assert.equal(recordToWinPct('6-7-1'), 6.5 / 14 * 100);
  assert.equal(formatRecord(6, 7, 1), '6-7-1');
  assert.deepEqual([8, 10, 12, 14, 16, 5].map((n) => gridShape(n)),
    [{ rows: 2, cols: 4 }, { rows: 2, cols: 5 }, { rows: 2, cols: 6 }, { rows: 2, cols: 7 },
     { rows: 3, cols: 6 }, { rows: 1, cols: 5 }]);
  const r = seededRandom(1);
  const values = Array.from({ length: 1000 }, r);
  assert.ok(values.every((v) => v >= 0 && v < 1));
  assert.ok(Math.abs(values.reduce((a, b) => a + b) / 1000 - 0.5) < 0.05);
});

test('downloaded report file embeds everything it needs', async () => {
  const { standaloneHtml, PLOTLY_CDN } = await import('../lib/standalone.js');
  const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8');
  const league = parseLeague(fixture('espn_in_progress_season.json'));
  const data = await buildReportData(league, { numSchedules: 50, meta: { id: '9', year: 2026, name: 'A </script> League' } });
  const html = standaloneHtml({
    template: read('../report/report_template.html'), css: read('../report/report.css'),
    js: read('../report/report.js'), data,
  });
  assert.ok(!/__(TITLE|PLOTLY|CSS|JS|DATA)__/.test(html));
  assert.ok(html.includes(PLOTLY_CDN));
  assert.ok(html.includes('window.renderReport'));
  // The data block survives a name containing </script>
  const block = html.match(/<script type="application\/json" id="report-data">([\s\S]*?)<\/script>/)[1];
  assert.equal(JSON.parse(block).league.name, 'A </script> League');
});
