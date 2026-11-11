/**
 * Schedule-luck simulation, in the browser.
 *
 * JavaScript port of simulate_schedule_permutations.py (TemplateScheduleGenerator,
 * PlayoffSimulator, schedule_swap_matrix) and build_report.py (build_report_data).
 * It produces the same report data, so the same report.js draws both. Tests in
 * tests/simulate.test.mjs check it against reference results from the Python.
 *
 * Teams are referred to by their index in league.teams (see lib/espn.js).
 */

import { isHeadToHeadRule } from './espn.js';

// ------------------------------------------------------------------ helpers

/** Small, fast, seedable random number generator (mulberry32). Returns floats in [0, 1). */
export function seededRandom(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffleInPlace(array, random) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  return array;
}

/** 'W-L', or 'W-L-T' when there are ties. */
export function formatRecord(wins, losses, ties) {
  return ties ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`;
}

/** Win % from a 'W-L' or 'W-L-T' record; ties count as half a win. */
export function recordToWinPct(record) {
  const [wins, losses, ties = 0] = String(record).split('-').map(Number);
  const games = wins + losses + ties;
  return games ? ((wins + 0.5 * ties) / games) * 100 : 0;
}

function winPct(wins, losses, ties) {
  const games = wins + losses + ties;
  return games ? (wins + 0.5 * ties) / games : 0;
}

/** Rows and columns for one small panel per team (12 -> 2x6, 14 -> 2x7, 16 -> 3x6). */
export function gridShape(nTeams, maxColumns = 7) {
  const rows = Math.ceil(nTeams / maxColumns);
  return { rows, cols: Math.ceil(nTeams / rows) };
}

const round2 = (x) => Math.round(x * 100) / 100;

/**
 * Who won a matchup: 1 if a outscored b, 0 if b did, 0.5 for a tie. A missing
 * score never wins (it compares like NaN in the Python, which makes a tie).
 */
function result(scoreA, scoreB) {
  if (scoreA == null || scoreB == null) return 0.5;
  return scoreA > scoreB ? 1 : scoreA < scoreB ? 0 : 0.5;
}

// --------------------------------------------------------------- the season

/** The league cut down to its first `week` weeks. */
function seasonThrough(league, week) {
  const n = league.teams.length;
  const nWeeks = league.weeks.length;
  if (!(week >= 1 && week <= nWeeks)) throw new RangeError(`week must be between 1 and ${nWeeks}`);
  const scores = league.scores.map((row) => row.slice(0, week));
  return {
    n,
    weeks: week,
    scores,
    schedule: league.schedule.slice(0, week),
    points: scores.map((row) => row.reduce((sum, s) => sum + (s ?? 0), 0)),
    divisions: league.teams.map((t) => t.division),
    nPlayoffTeams: league.nPlayoffTeams,
    useH2H: isHeadToHeadRule(league.seedingRule),
  };
}

/**
 * Play a season. `teamInSlot[slot]` is the team playing the real schedule of
 * team `slot`. Records go into the given arrays (reset first).
 */
function playSeason(season, teamInSlot, rec) {
  const { n, schedule, scores, useH2H } = season;
  rec.wins.fill(0); rec.losses.fill(0); rec.ties.fill(0);
  if (useH2H) { rec.h2hWins.fill(0); rec.h2hGames.fill(0); }
  for (let w = 0; w < schedule.length; w++) {
    for (const [slotA, slotB] of schedule[w]) {
      const a = teamInSlot[slotA];
      const b = teamInSlot[slotB];
      const r = result(scores[a][w], scores[b][w]);
      if (r === 1) { rec.wins[a]++; rec.losses[b]++; }
      else if (r === 0) { rec.wins[b]++; rec.losses[a]++; }
      else { rec.ties[a]++; rec.ties[b]++; }
      if (useH2H) {
        rec.h2hWins[a * n + b] += r; rec.h2hGames[a * n + b]++;
        rec.h2hWins[b * n + a] += 1 - r; rec.h2hGames[b * n + a]++;
      }
    }
  }
}

function newRecords(n) {
  return {
    wins: new Int32Array(n), losses: new Int32Array(n), ties: new Int32Array(n),
    h2hWins: new Float64Array(n * n), h2hGames: new Int32Array(n * n),
  };
}

/**
 * Order teams tied on win %. With a head-to-head rule, their record against
 * each other decides, but only if every pair met equally often (ESPN's rule);
 * total points breaks anything left.
 */
function breakTie(tied, season, rec) {
  const byPoints = (a, b) => season.points[b] - season.points[a];
  if (tied.length < 2 || !season.useH2H) return tied.sort(byPoints);

  const { n } = season;
  const meetings = new Set();
  for (let i = 0; i < tied.length; i++) {
    for (let j = i + 1; j < tied.length; j++) meetings.add(rec.h2hGames[tied[i] * n + tied[j]]);
  }
  if (meetings.size !== 1) return tied.sort(byPoints);

  const h2h = new Map(tied.map((t) => {
    let wins = 0; let games = 0;
    for (const o of tied) {
      if (o === t) continue;
      wins += rec.h2hWins[t * n + o];
      games += rec.h2hGames[t * n + o];
    }
    return [t, games ? wins / games : 0];
  }));
  return tied.sort((a, b) => h2h.get(b) - h2h.get(a) || byPoints(a, b));
}

/**
 * Every team's seed, best first: division winners take the top seeds, then
 * everyone else by win %, then the league's tiebreaker.
 *
 * @param {string[]} divisionOfTeam each team's division this season
 */
export function seedOrder(season, rec, divisionOfTeam) {
  const pct = Array.from({ length: season.n }, (_, t) => winPct(rec.wins[t], rec.losses[t], rec.ties[t]));
  const byPct = [...pct.keys()].sort((a, b) => pct[b] - pct[a]);
  const ranked = [];
  for (let i = 0; i < byPct.length;) {
    let j = i;
    while (j < byPct.length && pct[byPct[j]] === pct[byPct[i]]) j++;
    ranked.push(...breakTie(byPct.slice(i, j), season, rec));
    i = j;
  }

  const winners = [];
  const taken = new Set();
  for (const team of ranked) {
    if (!taken.has(divisionOfTeam[team])) { winners.push(team); taken.add(divisionOfTeam[team]); }
  }
  const isWinner = new Set(winners);
  return winners.concat(ranked.filter((t) => !isWinner.has(t)));
}

/** Each team's real record over the first `week` weeks. */
export function actualRecords(league, week) {
  const season = seasonThrough(league, week);
  const rec = newRecords(season.n);
  playSeason({ ...season, useH2H: false }, [...Array(season.n).keys()], rec);
  return Array.from({ length: season.n }, (_, t) => ({
    wins: rec.wins[t], losses: rec.losses[t], ties: rec.ties[t],
  }));
}

/**
 * Simulate random schedules for the season as if it ended after `week` weeks.
 *
 * Each simulated season randomly reassigns teams to the slots of the real
 * schedule, so it keeps the league's format; a team takes on its slot's division.
 *
 * @returns {{results: object[], seedCounts: number[][]}} results sorted by
 *   playoff % (best first); seedCounts[team][k] = simulations finishing seed k+1
 */
export function runSimulation(league, { week, numSchedules = 100000, seed = 42 } = {}) {
  const season = seasonThrough(league, week ?? league.weeks.length);
  const { n } = season;
  const random = seededRandom(seed);
  const rec = newRecords(n);
  const teamInSlot = [...Array(n).keys()];
  const divisionOfTeam = new Array(n);
  const seedCounts = Array.from({ length: n }, () => new Array(n).fill(0));
  const playoffCount = new Array(n).fill(0);
  const totalWins = new Array(n).fill(0);
  const totalGames = new Array(n).fill(0);

  for (let s = 0; s < numSchedules; s++) {
    shuffleInPlace(teamInSlot, random);
    for (let slot = 0; slot < n; slot++) divisionOfTeam[teamInSlot[slot]] = season.divisions[slot];
    playSeason(season, teamInSlot, rec);
    for (let t = 0; t < n; t++) {
      totalWins[t] += rec.wins[t] + 0.5 * rec.ties[t];
      totalGames[t] += rec.wins[t] + rec.losses[t] + rec.ties[t];
    }
    const order = seedOrder(season, rec, divisionOfTeam);
    order.forEach((team, k) => {
      seedCounts[team][k]++;
      if (k < season.nPlayoffTeams) playoffCount[team]++;
    });
  }

  const actual = actualRecords(league, season.weeks);
  const results = league.teams.map((team, t) => {
    const record = formatRecord(actual[t].wins, actual[t].losses, actual[t].ties);
    const expected = totalGames[t] ? (totalWins[t] / totalGames[t]) * 100 : 0;
    const actualPct = recordToWinPct(record);
    return {
      team: team.name,
      record,
      points_for: season.points[t],
      actual: actualPct,
      expected,
      luck: actualPct - expected,
      playoff: (playoffCount[t] / numSchedules) * 100,
    };
  });
  const order = results.map((_, t) => t).sort((a, b) => results[b].playoff - results[a].playoff);
  return { results: order.map((t) => results[t]), seedCounts, teamOrder: order };
}

/**
 * Every team's record if it had played every other team's real schedule over
 * the first `week` weeks. wins[x][y] is x's wins (ties count half) on y's
 * schedule: x faces y's opponent each week, and y itself when y played x.
 */
export function swapMatrix(league, week) {
  const season = seasonThrough(league, week);
  const { n, schedule, scores } = season;
  const opponents = schedule.map((pairs) => {
    const opp = new Array(n).fill(null);
    for (const [a, b] of pairs) { opp[a] = b; opp[b] = a; }
    return opp;
  });
  const wins = []; const records = [];
  for (let x = 0; x < n; x++) {
    wins.push([]); records.push([]);
    for (let y = 0; y < n; y++) {
      let w = 0; let l = 0; let t = 0;
      opponents.forEach((opp, week) => {
        let o = opp[y];
        if (o === null) return; // y had a bye
        if (o === x) o = y;
        const r = result(scores[x][week], scores[o][week]);
        if (r === 1) w++; else if (r === 0) l++; else t++;
      });
      wins[x].push(w + 0.5 * t);
      records[x].push(formatRecord(w, l, t));
    }
  }
  return { teams: league.teams.map((t) => t.name), wins, records };
}

/**
 * The data the report draws: one entry per "through week N" cutoff, plus
 * league details. Same shape as build_report.py's build_report_data().
 *
 * @param {object} options
 * @param {number} [options.numSchedules]
 * @param {number} [options.seed]
 * @param {(done: number, total: number) => void} [options.onProgress]
 *   called after each cutoff; between cutoffs the browser gets a chance to repaint
 * @param {object} [options.meta] extra league fields (id, year, name, generated)
 */
export async function buildReportData(league, { numSchedules = 100000, seed = 42, onProgress, meta = {} } = {}) {
  const total = league.weeks.length;
  const weeks = [];
  for (let week = 1; week <= total; week++) {
    const { results, seedCounts } = runSimulation(league, { week, numSchedules, seed });
    const seeds = {};
    league.teams.forEach((team, t) => {
      seeds[team.name] = seedCounts[t].map((c) => round2((c / numSchedules) * 100));
    });
    weeks.push({
      week,
      results: results.map((r) => ({
        team: r.team, record: r.record, points_for: round2(r.points_for), actual: round2(r.actual),
        expected: round2(r.expected), luck: round2(r.luck), playoff: round2(r.playoff),
      })),
      seeds,
      swap: swapMatrix(league, week),
    });
    if (onProgress) {
      onProgress(week, total);
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }
  return {
    league: {
      n_teams: league.teams.length,
      n_playoff_teams: league.nPlayoffTeams,
      num_schedules: numSchedules,
      weeks_played: total,
      divisions: league.divisions,
      seeding_rule: league.seedingRule,
      real_schedule: true,
      notes: league.notes,
      grid: gridShape(league.teams.length),
      ...meta,
    },
    weeks,
  };
}
