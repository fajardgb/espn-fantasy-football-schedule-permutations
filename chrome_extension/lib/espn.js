/**
 * Read ESPN's league API response into the shape the simulation needs.
 *
 * JavaScript port of get_espn_league_data.py plus the parts of
 * simulate_schedule_permutations.py that load its files (load_scores,
 * load_league_structure). Kept in step with the Python by the reference
 * tests in tests/simulate.test.mjs (see tests/make_golden.py).
 */

/** The API views the Python tool requests: settings, teams and all matchups. */
export const API_VIEWS = ['mSettings', 'mTeam', 'mMatchup'];

/** 'jason wu' -> 'Jason Wu' (only first letters change, so 'McDonald' stays). */
export function standardizeName(name) {
  return String(name).split(/\s+/).filter(Boolean)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1)).join(' ');
}

/** Make names unique: ['MM', 'BK', 'MM'] -> ['MM', 'BK', 'MM (2)']. */
export function disambiguateNames(names) {
  const counts = new Map();
  return names.map((name) => {
    const count = (counts.get(name) || 0) + 1;
    counts.set(name, count);
    return count === 1 ? name : `${name} (${count})`;
  });
}

/** Team ID -> owner's name (or the team's name when it has no owner). */
export function parseTeamNames(data) {
  const members = new Map((data.members || []).map((m) => [m.id, m]));
  const names = new Map();
  for (const team of data.teams || []) {
    let ownerName = null;
    const member = team.owners?.length ? members.get(team.owners[0]) : null;
    if (member) ownerName = `${member.firstName || ''} ${member.lastName || ''}`.trim();
    names.set(team.id, ownerName || (team.name ?? `Team ${team.id}`));
  }
  return names;
}

function regularSeasonMatchups(data) {
  const lastWeek = data.settings.scheduleSettings.matchupPeriodCount;
  return (data.schedule || []).filter((m) => m.matchupPeriodId >= 1 && m.matchupPeriodId <= lastWeek);
}

const isPlayed = (matchup) => (matchup.winner ?? 'UNDECIDED') !== 'UNDECIDED';

/** Scores are stored to 2 decimals, as in the Python tool's CSV file. */
const roundScore = (score) => Number(Number(score).toFixed(2));

export function seedingRuleNote(rule) {
  if (rule == null || rule === 'TOTAL_POINTS_SCORED' || isHeadToHeadRule(rule)) return null;
  return `Playoff tiebreaker '${rule}' isn't modeled; ties are broken by total points.`;
}

export function tieRuleNote(rule) {
  if (rule == null || rule === 'NONE') return null;
  return `Matchup tie rule '${rule}' isn't modeled; equal scores count as ties.`;
}

/** Whether an ESPN playoffSeedingRule means head-to-head record breaks ties. */
export function isHeadToHeadRule(rule) {
  if (!rule) return false;
  const upper = String(rule).toUpperCase();
  return upper.includes('H2H') || upper.includes('HEAD');
}

/**
 * Everything the simulation needs from one API response.
 *
 * Teams are ordered by ESPN team ID, and each team's index in `teams` is used
 * everywhere else (scores rows, schedule pairs). Only completed
 * regular-season weeks are included.
 *
 * @returns {{
 *   name: string|null, seasonId: number|null,
 *   teams: {id: number, name: string, division: string}[],
 *   weeks: number[],            // ESPN week numbers that have been played
 *   scores: (number|null)[][],  // scores[team][weekIndex]
 *   schedule: number[][][],     // schedule[weekIndex] = [[teamIndex, teamIndex], ...]
 *   nPlayoffTeams: number, seedingRule: string|null, tieRule: string|null,
 *   divisions: string[], notes: string[],
 * }}
 */
export function parseLeague(data) {
  const scheduleSettings = data.settings.scheduleSettings;
  const ownerNames = parseTeamNames(data);
  const ids = [...ownerNames.keys()].sort((a, b) => a - b);
  const names = disambiguateNames(ids.map((id) => standardizeName(ownerNames.get(id))));
  const indexOf = new Map(ids.map((id, i) => [id, i]));

  const divisionNames = new Map((scheduleSettings.divisions || []).map((d) => [d.id, d.name]));
  const teamsById = new Map((data.teams || []).map((t) => [t.id, t]));
  const teams = ids.map((id, i) => {
    const divisionId = teamsById.get(id)?.divisionId;
    const division = divisionId == null ? '' : (divisionNames.get(divisionId) ?? String(divisionId));
    return { id, name: names[i], division };
  });

  const matchups = regularSeasonMatchups(data);

  // Weekly scores for completed weeks
  const scoreByWeek = new Map();
  for (const m of matchups) {
    if (!isPlayed(m)) continue;
    const week = m.matchupPeriodId;
    if (!scoreByWeek.has(week)) scoreByWeek.set(week, new Map());
    for (const side of ['home', 'away']) {
      if (m[side]) scoreByWeek.get(week).set(m[side].teamId, roundScore(m[side].totalPoints ?? 0));
    }
  }
  const weeks = [...scoreByWeek.keys()].sort((a, b) => a - b);
  const scores = ids.map((id) => weeks.map((w) => scoreByWeek.get(w).get(id) ?? null));

  // The real schedule for those weeks, as pairs of team indices
  const pairsByWeek = new Map(weeks.map((w) => [w, []]));
  const allPairs = matchups.filter((m) => m.home && m.away)
    .map((m) => [m.matchupPeriodId, m.home.teamId, m.away.teamId])
    .sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  for (const [week, a, b] of allPairs) {
    if (pairsByWeek.has(week) && indexOf.has(a) && indexOf.has(b)) {
      pairsByWeek.get(week).push([indexOf.get(a), indexOf.get(b)]);
    }
  }
  const missing = weeks.filter((w) => !pairsByWeek.get(w).length);
  if (missing.length) throw new Error(`ESPN's schedule has no matchups for weeks ${missing.join(', ')}`);

  const seedingRule = scheduleSettings.playoffSeedingRule ?? null;
  const tieRule = data.settings.scoringSettings?.matchupTieRule ?? null;
  return {
    name: data.settings.name ?? null,
    seasonId: data.seasonId ?? null,
    teams,
    weeks,
    scores,
    schedule: weeks.map((w) => pairsByWeek.get(w)),
    nPlayoffTeams: scheduleSettings.playoffTeamCount ?? 6,
    seedingRule,
    tieRule,
    divisions: [...new Set(teams.map((t) => t.division).filter(Boolean))].sort(),
    notes: [seedingRuleNote(seedingRule), tieRuleNote(tieRule)].filter(Boolean),
  };
}
