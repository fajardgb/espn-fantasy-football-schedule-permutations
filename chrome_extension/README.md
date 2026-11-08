# Fantasy Schedule Luck (Chrome extension)

Build the schedule luck report for your ESPN fantasy football league right in your browser. There's nothing to install besides the extension, and no terminal or Python needed.

Open your league on ESPN, click the extension, and click **Build report**. A new tab downloads your league, simulates 100,000 random schedules for every week of the season (a few seconds), and shows the full report:
- **Playoff odds** for each team
- **Schedule luck**: actual vs. expected win %
- **What if you had their schedule?**: pick a team to see its record on every other team's real schedule, next to its actual record, or switch to **All teams** to see the whole league at once
- **Where each team finishes**: each team's spread of final seeds
- A **"through week N"** picker that shows how the luck built up over the season

Click **Download PDF** to save the full-season report as a PDF you can post in your league chat. **Web page (.html)** saves the version with the week picker instead. It opens in any browser.

## Install (takes about a minute)
The extension isn't in the Chrome Web Store yet, so you install it from this folder:

1. Download this project: on the [GitHub page](https://github.com/fajardgb/espn-fantasy-football-schedule-permutations), click the green **Code** button → **Download ZIP**, and unzip it.
2. In Chrome, go to `chrome://extensions`.
3. Turn on **Developer mode** (top right).
4. Click **Load unpacked** and choose this `chrome_extension` folder.
5. Click the puzzle-piece icon in Chrome's toolbar and pin **Fantasy Schedule Luck** so it's always visible.

It also works in other Chromium browsers, such as Edge and Brave (use `edge://extensions` or `brave://extensions`).

**Updating:** after downloading a newer version of the project, go to `chrome://extensions` and click the reload arrow on the extension's card.

## Use
1. Log in to ESPN and open your league on [fantasy.espn.com](https://fantasy.espn.com/football/). Any page with the league in its address works (league home, standings, your team).
2. Click the extension's icon. The league ID and season fill in, and you'll see:
   - **✓ Logged in to ESPN in this browser:** needed for private leagues.
   - **✓ "Your League Name" · 12 teams:** ESPN confirmed the league can be reached.
3. Click **Build report**. It takes a few seconds.

If the season isn't in the page address, the extension picks the most recent season. You can type a different league ID or season in the boxes.

**Using the Python tool instead?** The popup's **Copy as .env** button copies your league details and login values in the format the Python tool's `.env` file needs.

## Privacy and permissions
- **Your ESPN login never leaves your browser.** The extension has no server and collects nothing. It uses your login only to ask ESPN for your league's data, exactly as your browser does when you view your league.
- **Downloaded reports (PDF or web page) don't include your login.** They contain team names, records and scores, the same things anyone in your league can see.
- Chrome describes the permissions as:
  - **"Read and change your data on espn.com"**: needed to use your ESPN login and download your league. The extension doesn't change anything on ESPN.
  - Reading the current tab's address only happens when you click the extension (the `activeTab` permission), so it can't see your browsing otherwise.

Treat what **Copy as .env** copies like a password: anyone with your `ESPN_S2` and `SWID` can use your ESPN account. Don't paste them anywhere public, including when asking for help.

## How it works (for developers)
| File | What it does |
|---|---|
| `popup.html` / `popup.js` / `popup.css` | The popup: finds the league and login, checks access, opens the report |
| `report.html` / `report_page.js` / `report_page.css` | The report tab: downloads the league, runs the simulation, shows progress, offers the downloads |
| `report_pdf.js` | Lays out the full-season charts on PDF pages |
| `lib/league.js` | Popup helpers: reading league pages' addresses, `.env` text, ESPN error messages |
| `lib/espn.js` | Reads ESPN's league data (JavaScript port of `get_espn_league_data.py`) |
| `lib/simulate.js` | The simulation and report data (port of `simulate_schedule_permutations.py` and `build_report.py`) |
| `lib/standalone.js` | Assembles the downloadable `.html` file |
| `report/` | The report's page, styles and charts. **Shared with the Python tool**, which reads them from here, so both make identical reports |
| `vendor/plotly.min.js` | Plotly 4.1.1 (MIT license), the charting library |
| `vendor/jspdf.umd.min.js` | jsPDF 3.0.4 (MIT license), for making PDFs |

Extensions can't load code from the internet, so both libraries are bundled.

**Tests:** `npm test` (Node.js 20 or newer, no dependencies to install). The simulation is checked against reference results from the Python code in `tests/golden/`:
- Parsing, actual records and the schedule-swap matrix must match exactly.
- Playoff odds and expected win % must agree within sampling error.

After changing the Python logic, regenerate the reference results from the project root with `uv run python chrome_extension/tests/make_golden.py`. A Python test fails until you do.
