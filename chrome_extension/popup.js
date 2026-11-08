import {
  COOKIE_NAMES,
  ESPN_COOKIE_URL,
  ESPN_FANTASY_FOOTBALL_URL,
  buildEnv,
  defaultSeason,
  describeLeagueResponse,
  leagueApiUrl,
  maskSecret,
  parseLeagueUrl,
  validateInputs,
} from './lib/league.js';

const $ = (id) => document.getElementById(id);
const ICONS = { good: '✓', warning: '!', critical: '✕', info: 'i' };

const state = {
  espnS2: null,
  swid: null,
  revealed: false,
  leagueIsPublic: false,
  checkId: 0,
};

// ------------------------------------------------------------- chrome APIs

async function activeTabUrl() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab?.url || '';
  } catch {
    return '';
  }
}

async function readCookie(name) {
  try {
    const cookie = await chrome.cookies.get({ url: ESPN_COOKIE_URL, name });
    return cookie?.value || null;
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ display

function setStatus(el, level, text) {
  el.dataset.level = level;
  el.textContent = '';
  const icon = document.createElement('span');
  icon.className = 'icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = ICONS[level];
  el.append(icon, document.createTextNode(text));
}

function showBanner(level, text, action) {
  const banner = $('page-banner');
  setStatus(banner, level, text);
  if (action) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'link';
    button.textContent = action.label;
    button.addEventListener('click', action.onClick);
    banner.append(' ', button);
  }
  banner.hidden = false;
}

function renderCookies() {
  for (const [key, id] of [['espnS2', 'espn-s2'], ['swid', 'swid']]) {
    const value = state[key];
    const el = $(id);
    el.textContent = value ? (state.revealed ? value : maskSecret(value)) : 'not found';
    el.classList.toggle('missing', !value);
    el.classList.toggle('revealed', Boolean(value && state.revealed));
  }
  const reveal = $('reveal');
  reveal.hidden = !state.espnS2 && !state.swid;
  reveal.textContent = state.revealed ? 'Hide values' : 'Show values';
  reveal.setAttribute('aria-pressed', String(state.revealed));

  const status = $('login-status');
  if (state.espnS2 && state.swid) {
    setStatus(status, 'good', 'Logged in to ESPN in this browser.');
  } else if (!state.espnS2 && !state.swid) {
    setStatus(status, 'warning',
      'Not logged in to ESPN in this browser. Public leagues still work. For a private league, log in at espn.com and reopen this popup.');
  } else {
    setStatus(status, 'warning',
      `Only found ${state.espnS2 ? 'ESPN_S2' : 'SWID'}. Log out of ESPN, log back in, and reopen this popup.`);
  }
}

function inputs() {
  return { leagueId: $('league-id').value.trim(), year: $('year').value.trim() };
}

// ------------------------------------------------------------ league check

async function checkLeague() {
  const checkId = ++state.checkId;
  const { leagueId, year } = inputs();
  const status = $('league-status');
  const error = validateInputs({ leagueId, year });
  $('input-error').hidden = true;
  state.leagueIsPublic = false;
  if (error) {
    if (leagueId) { // don't nag before anything has been typed
      $('input-error').textContent = error;
      $('input-error').hidden = false;
    }
    status.textContent = '';
    delete status.dataset.level;
    return;
  }

  setStatus(status, 'info', 'Checking with ESPN…');
  let response;
  let body = null;
  try {
    response = await fetch(leagueApiUrl(leagueId, year), { credentials: 'include' });
    if (response.ok) body = await response.json();
  } catch {
    if (checkId === state.checkId) {
      setStatus(status, 'warning', 'Couldn’t reach ESPN. Check your internet connection.');
    }
    return;
  }
  if (checkId !== state.checkId) return; // the user changed the inputs meanwhile

  const result = describeLeagueResponse(response.status, body, Boolean(state.espnS2 && state.swid));
  state.leagueIsPublic = Boolean(result.league?.isPublic);
  const extra = result.ok && state.leagueIsPublic && !state.espnS2 ? ' · public league, no login needed' : '';
  setStatus(status, result.level, result.message + extra);
}

let checkTimer;
function scheduleCheck() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(checkLeague, 450);
}

// ------------------------------------------------------------------ copying

async function copyEnv() {
  const { leagueId, year } = inputs();
  const error = validateInputs({ leagueId, year });
  const copied = $('copied');
  if (error) {
    $('input-error').textContent = error;
    $('input-error').hidden = false;
    $(/^\d+$/.test(leagueId) ? 'year' : 'league-id').focus();
    return;
  }
  const text = buildEnv({ leagueId, year, espnS2: state.espnS2, swid: state.swid });
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    copied.textContent = 'Couldn’t copy automatically. Click Show values and copy them by hand.';
    return;
  }
  copied.textContent = state.espnS2 && state.swid
    ? 'Copied! Paste it into your .env file.'
    : 'Copied, without ESPN login values. That only works for public leagues.';
  setTimeout(() => { copied.textContent = ''; }, 6000);
}

// ------------------------------------------------------------------- report

function openReport() {
  const { leagueId, year } = inputs();
  const error = validateInputs({ leagueId, year });
  if (error) {
    $('input-error').textContent = error;
    $('input-error').hidden = false;
    $(/^\d+$/.test(leagueId) ? 'year' : 'league-id').focus();
    return;
  }
  const query = new URLSearchParams({ league: leagueId, year });
  chrome.tabs.create({ url: chrome.runtime.getURL(`report.html?${query}`) });
  window.close();
}

// --------------------------------------------------------------------- start

async function init() {
  const [url, espnS2, swid] = await Promise.all([
    activeTabUrl(),
    readCookie(COOKIE_NAMES.espnS2),
    readCookie(COOKIE_NAMES.swid),
  ]);
  Object.assign(state, { espnS2, swid });

  const page = parseLeagueUrl(url);
  $('league-id').value = page?.leagueId || '';
  $('year').value = page?.seasonId || defaultSeason();

  if (!page) {
    showBanner('info', 'Open your league on ESPN and click the extension again to fill in the league ID, or type it below.', {
      label: 'Open ESPN Fantasy',
      onClick: () => chrome.tabs.create({ url: ESPN_FANTASY_FOOTBALL_URL }),
    });
  } else if (page.sport && page.sport !== 'football') {
    showBanner('warning', `This is a ${page.sport} league. The schedule-luck tool only supports football.`);
  } else if (!page.seasonId) {
    showBanner('info', `Season not in the page address, so it’s set to ${defaultSeason()}. Change it if needed.`);
  }

  renderCookies();
  $('reveal').addEventListener('click', () => { state.revealed = !state.revealed; renderCookies(); });
  $('copy-env').addEventListener('click', copyEnv);
  $('build-report').addEventListener('click', openReport);
  for (const id of ['league-id', 'year']) $(id).addEventListener('input', scheduleCheck);
  checkLeague();
}

init();
