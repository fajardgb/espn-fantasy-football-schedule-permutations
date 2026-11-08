// Run with: node --test chrome_extension/tests/
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  buildEnv,
  defaultSeason,
  describeLeagueResponse,
  leagueApiUrl,
  maskSecret,
  parseLeagueUrl,
  validateInputs,
} from '../lib/league.js';

test('parses league pages', () => {
  assert.deepEqual(
    parseLeagueUrl('https://fantasy.espn.com/football/league?leagueId=12345678&seasonId=2025'),
    { leagueId: '12345678', seasonId: 2025, sport: 'football' },
  );
  assert.deepEqual(
    parseLeagueUrl('https://fantasy.espn.com/football/team?leagueId=42&teamId=4'),
    { leagueId: '42', seasonId: null, sport: 'football' },
  );
  assert.deepEqual(
    parseLeagueUrl('https://fantasy.espn.com/football/league/standings?seasonId=2024&leagueId=7'),
    { leagueId: '7', seasonId: 2024, sport: 'football' },
  );
  assert.equal(parseLeagueUrl('https://fantasy.espn.com/basketball/league?leagueId=9').sport, 'basketball');
});

test('rejects pages that are not ESPN leagues', () => {
  assert.equal(parseLeagueUrl('https://fantasy.espn.com/football/'), null);
  assert.equal(parseLeagueUrl('https://example.com/football/league?leagueId=1'), null);
  assert.equal(parseLeagueUrl('https://notespn.com/football/league?leagueId=1'), null);
  assert.equal(parseLeagueUrl('https://fantasy.espn.com/football/league?leagueId=abc'), null);
  assert.equal(parseLeagueUrl('chrome://extensions'), null);
  assert.equal(parseLeagueUrl(''), null);
  assert.equal(parseLeagueUrl(undefined), null);
});

test('ignores malformed season IDs', () => {
  assert.equal(parseLeagueUrl('https://fantasy.espn.com/football/league?leagueId=1&seasonId=25').seasonId, null);
});

test('default season is the one that started most recently', () => {
  assert.equal(defaultSeason(new Date(2026, 0, 15)), 2025);  // January: last year's season
  assert.equal(defaultSeason(new Date(2026, 5, 30)), 2025);  // June: still last year's
  assert.equal(defaultSeason(new Date(2026, 6, 1)), 2026);   // July: new season
  assert.equal(defaultSeason(new Date(2026, 10, 8)), 2026);
});

test('validates inputs', () => {
  assert.equal(validateInputs({ leagueId: '123', year: '2025' }), null);
  assert.equal(validateInputs({ leagueId: ' 123 ', year: 2025 }), null);
  assert.match(validateInputs({ leagueId: '', year: '2025' }), /League ID/);
  assert.match(validateInputs({ leagueId: '12a', year: '2025' }), /League ID/);
  assert.match(validateInputs({ leagueId: '1', year: '25' }), /4-digit/);
});

test('builds a .env file the Python tool can read', () => {
  const text = buildEnv({ leagueId: ' 123 ', year: 2025, espnS2: 'AE%2Bx', swid: '{AB-CD}' });
  const values = Object.fromEntries(
    text.split('\n').filter((l) => l && !l.startsWith('#')).map((l) => l.split(/=(.*)/s).slice(0, 2)),
  );
  assert.deepEqual(values, { LEAGUE_ID: '123', YEAR: '2025', ESPN_S2: 'AE%2Bx', SWID: '{AB-CD}' });
  assert.ok(text.endsWith('\n'));
});

test('public leagues get empty cookie values', () => {
  const text = buildEnv({ leagueId: '1', year: 2025, espnS2: null, swid: undefined });
  assert.match(text, /^ESPN_S2=$/m);
  assert.match(text, /^SWID=$/m);
});

test('masks secrets', () => {
  assert.equal(maskSecret('AEBx7kLONGSECRETVALUE9f2A'), 'AEBx7k…9f2A');
  assert.equal(maskSecret('short'), '•••••');
  assert.equal(maskSecret(''), '');
  assert.equal(maskSecret(null), '');
});

test('builds the API address', () => {
  assert.equal(
    leagueApiUrl('123', 2025),
    'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2025/segments/0/leagues/123?view=mSettings',
  );
  assert.match(leagueApiUrl('1', 2025, ['mSettings', 'mTeam']), /view=mSettings&view=mTeam$/);
});

test('describes ESPN responses', () => {
  const found = describeLeagueResponse(200, { settings: { name: 'The League', size: 12 } }, true);
  assert.equal(found.ok, true);
  assert.equal(found.message, '“The League” · 12 teams');

  assert.match(describeLeagueResponse(401, null, false).message, /private and you’re not logged in/);
  assert.match(describeLeagueResponse(401, null, true).message, /refused/);
  assert.match(describeLeagueResponse(404, null, true).message, /couldn’t find/);
  assert.match(describeLeagueResponse(400, null, true).message, /couldn’t find/);
  assert.equal(describeLeagueResponse(503, null, true).level, 'warning');
  assert.equal(describeLeagueResponse(200, { settings: {} }, true).message, 'League found');
});
