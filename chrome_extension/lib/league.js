/**
 * League helpers shared by the popup (and, later, the in-browser report).
 * Pure functions only: no chrome.* or DOM access, so they run under `node --test`.
 */

/**
 * Where the login cookies are read from. They're set on .espn.com, so they apply
 * here, and the extension only has access to fantasy.espn.com (see manifest.json).
 */
export const ESPN_COOKIE_URL = 'https://fantasy.espn.com/';
export const ESPN_FANTASY_FOOTBALL_URL = 'https://fantasy.espn.com/football/';
export const COOKIE_NAMES = { espnS2: 'espn_s2', swid: 'SWID' };

const API_BASE = 'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl';

/**
 * Read the league ID (and season, sport) from an ESPN fantasy page address.
 *
 * @param {string} url e.g. https://fantasy.espn.com/football/league?leagueId=123&seasonId=2025
 * @returns {{leagueId: string, seasonId: number|null, sport: string|null}|null}
 *   null when the address isn't an ESPN page with a league ID in it
 */
export function parseLeagueUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  const host = parsed.hostname;
  if (host !== 'espn.com' && !host.endsWith('.espn.com')) return null;

  const leagueId = parsed.searchParams.get('leagueId');
  if (!leagueId || !/^\d+$/.test(leagueId)) return null;

  const season = parsed.searchParams.get('seasonId');
  const sport = (parsed.pathname.match(/\/(football|basketball|baseball|hockey)(\/|$)/) || [])[1] || null;
  return {
    leagueId,
    seasonId: season && /^\d{4}$/.test(season) ? Number(season) : null,
    sport,
  };
}

/**
 * The most recent fantasy football season on a given date. Seasons run
 * roughly August to January and are named for the year they start, so from
 * January to June the latest season is last year's.
 */
export function defaultSeason(date = new Date()) {
  return date.getMonth() >= 6 ? date.getFullYear() : date.getFullYear() - 1;
}

/** Validate what the user typed. Returns an error message, or null when fine. */
export function validateInputs({ leagueId, year }) {
  if (!/^\d+$/.test(String(leagueId ?? '').trim())) {
    return 'League ID should be a number (find it after "leagueId=" in your league\'s address).';
  }
  if (!/^\d{4}$/.test(String(year ?? '').trim())) {
    return 'Season should be a 4-digit year, like 2025.';
  }
  return null;
}

/**
 * The text of a .env file for the Python tool. Cookies are left empty when
 * missing (public leagues don't need them).
 */
export function buildEnv({ leagueId, year, espnS2, swid }) {
  return [
    '# Made by the Fantasy Schedule Luck Chrome extension.',
    '# Keep this file private: ESPN_S2 and SWID work like a password for your ESPN account.',
    `LEAGUE_ID=${String(leagueId).trim()}`,
    `YEAR=${String(year).trim()}`,
    `ESPN_S2=${espnS2 ?? ''}`,
    `SWID=${swid ?? ''}`,
    '',
  ].join('\n');
}

/** Show the start and end of a secret, e.g. 'AEBx7k…9f2A' (never the whole thing). */
export function maskSecret(value, keep = 6) {
  if (!value) return '';
  if (value.length <= keep * 2) return '•'.repeat(value.length);
  return `${value.slice(0, keep)}…${value.slice(-4)}`;
}

/** ESPN's league data address. */
export function leagueApiUrl(leagueId, year, views = ['mSettings']) {
  const query = views.map((v) => `view=${encodeURIComponent(v)}`).join('&');
  return `${API_BASE}/seasons/${year}/segments/0/leagues/${leagueId}?${query}`;
}

/**
 * Turn ESPN's answer to a league request into something to show the user.
 *
 * @param {number} status HTTP status code
 * @param {object|null} body parsed JSON (mSettings view) when status is 200
 * @param {boolean} sentCookies whether the request carried the login cookies
 * @returns {{ok: boolean, level: 'good'|'warning'|'critical', message: string, league?: object}}
 */
export function describeLeagueResponse(status, body, sentCookies) {
  if (status === 200 && body) {
    const settings = body.settings || {};
    const league = {
      name: settings.name || null,
      teams: Array.isArray(body.teams) && body.teams.length ? body.teams.length : settings.size || null,
      isPublic: Boolean(settings.isPublic),
    };
    const parts = [league.name ? `“${league.name}”` : 'League found'];
    if (league.teams) parts.push(`${league.teams} teams`);
    return { ok: true, level: 'good', message: parts.join(' · '), league };
  }
  if (status === 401) {
    return {
      ok: false,
      level: 'critical',
      message: sentCookies
        ? 'ESPN refused access. Make sure you’re logged in to ESPN in this browser, then reopen this popup.'
        : 'This league is private and you’re not logged in. Log in to ESPN in this browser, then reopen this popup.',
    };
  }
  if (status === 404 || status === 400) {
    return {
      ok: false,
      level: 'critical',
      message: 'ESPN couldn’t find this league for that season. Check the league ID and season.',
    };
  }
  if (status >= 500) {
    return { ok: false, level: 'warning', message: 'ESPN’s servers had a problem. Try again in a minute.' };
  }
  return { ok: false, level: 'warning', message: `ESPN answered with an unexpected error (${status}).` };
}
