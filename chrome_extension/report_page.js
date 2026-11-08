/**
 * The extension's report tab: download the league from ESPN, simulate it in
 * the browser, and draw the same report the Python tool makes.
 *
 * Opened by the popup as report.html?league=<id>&year=<season>.
 */
import { API_VIEWS, parseLeague } from './lib/espn.js';
import { describeLeagueResponse, leagueApiUrl, validateInputs } from './lib/league.js';
import { buildReportData } from './lib/simulate.js';
import { standaloneHtml } from './lib/standalone.js';

const NUM_SCHEDULES = 10000;

const $ = (id) => document.getElementById(id);

class ReportProblem extends Error {}

function setStep(id, state) {
  $(id).dataset.state = state;
}

function setProgress(fraction) {
  const pct = Math.round(fraction * 100);
  $('bar-fill').style.width = `${pct}%`;
  document.querySelector('.bar').setAttribute('aria-valuenow', String(pct));
}

function showProblem(paragraphs) {
  const box = $('problem');
  box.replaceChildren(...paragraphs.map((text) => {
    const p = document.createElement('p');
    p.textContent = text;
    return p;
  }));
  box.hidden = false;
  $('progress-title').textContent = 'Couldn’t build the report';
  document.querySelector('.bar').hidden = true;
}

async function downloadLeague(leagueId, year) {
  let response;
  try {
    response = await fetch(leagueApiUrl(leagueId, year, API_VIEWS), { credentials: 'include' });
  } catch {
    throw new ReportProblem('Couldn’t reach ESPN. Check your internet connection and try again.');
  }
  if (response.status === 401) {
    throw new ReportProblem(
      'ESPN wouldn’t share this league’s data. Private leagues need you to be logged in to ESPN in this browser.',
      { cause: 401 });
  }
  if (!response.ok) {
    throw new ReportProblem(describeLeagueResponse(response.status, null, true).message, { cause: response.status });
  }
  return response.json();
}

// ----------------------------------------------------------- download file

function fileName(league) {
  return `league${league.id}_year${league.year}_report.html`;
}

/** A standalone .html file, built from the same files as build_report.py's reports. */
async function reportFile(data) {
  const [template, css, js] = await Promise.all(
    ['report/report_template.html', 'report/report.css', 'report/report.js']
      .map((path) => fetch(path).then((r) => r.text())),
  );
  return standaloneHtml({ template, css, js, data });
}

async function saveReport(data) {
  const button = $('download');
  button.disabled = true;
  try {
    const blob = new Blob([await reportFile(data)], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement('a'), { href: url, download: fileName(data.league) });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } finally {
    button.disabled = false;
  }
}

// -------------------------------------------------------------------- main

async function main() {
  const params = new URLSearchParams(location.search);
  const leagueId = (params.get('league') || '').trim();
  const year = (params.get('year') || '').trim();
  const inputError = validateInputs({ leagueId, year });
  if (inputError) throw new ReportProblem(inputError, { cause: 'input' });

  const raw = await downloadLeague(leagueId, year);
  let league;
  try {
    league = parseLeague(raw);
  } catch (error) {
    throw new ReportProblem(`ESPN’s league data looked different than expected (${error.message}).`);
  }
  if (!league.weeks.length) {
    throw new ReportProblem(`No games have been completed yet in the ${year} season, so there’s nothing to simulate yet.`);
  }
  setStep('step-download', 'done');
  setStep('step-simulate', 'active');
  document.title = `Schedule luck — ${league.name || `league ${leagueId}`}, ${year}`;

  const total = league.weeks.length;
  $('simulate-detail').textContent = `(week 0 of ${total})`;
  const data = await buildReportData(league, {
    numSchedules: NUM_SCHEDULES,
    meta: { id: leagueId, year: Number(year), name: league.name, generated: new Date().toISOString().slice(0, 10) },
    onProgress: (done) => {
      $('simulate-detail').textContent = `(week ${done} of ${total})`;
      setProgress(done / total);
    },
  });
  setStep('step-simulate', 'done');

  $('progress').dataset.state = 'done';
  $('page-bar').hidden = false;
  $('download').addEventListener('click', () => saveReport(data));
  window.renderReport(data, $('report-root'));
}

main().catch((error) => {
  const step = $('step-download').dataset.state === 'done' ? 'step-simulate' : 'step-download';
  setStep(step, 'failed');
  if (error instanceof ReportProblem) {
    const tips = {
      input: ['Open the extension again from your league’s page on ESPN.'],
      401: ['Log in at espn.com, then reload this page.'],
      404: ['Check the league ID and season in the extension’s popup.'],
      400: ['Check the league ID and season in the extension’s popup.'],
    }[error.cause] || [];
    showProblem([error.message, ...tips]);
  } else {
    console.error(error);
    showProblem(['Something went wrong while building the report.', String(error?.message || error)]);
  }
});
