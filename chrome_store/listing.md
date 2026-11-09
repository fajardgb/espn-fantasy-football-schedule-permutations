# Chrome Web Store submission: copy and paste

Everything the Developer Dashboard asks for, in the order its tabs ask for it. Images are in `images/` next to this file (made from the anonymized demo league), and the upload file comes from `build_zip.py`.

---

## Package tab
Upload `dist/fantasy-schedule-luck-<version>.zip`, made by:
```
uv run python chrome_store/build_zip.py
```

---

## Store listing tab

**Name** (from the manifest): Fantasy Schedule Luck

**Summary** (from the manifest, max 132 characters):
> See how much schedule luck shaped your ESPN fantasy football season: playoff odds, luck and what-if schedules.

**Description:**
```
Scored a ton of points and still missed the playoffs? Find out how much of your fantasy football season came down to schedule luck.

Fantasy Schedule Luck takes every team's real weekly scores from your ESPN league and replays them against 100,000 random schedules that keep your league's real format: divisions, number of playoff spots and tiebreakers. Then it shows:

• Playoff odds: how often each team makes the playoffs across all those schedules
• Schedule luck: each team's actual win % vs. the win % its scores earned, so you can see who got lucky and who got robbed
• What if you had their schedule?: any team's record with every other team's real schedule, next to its actual record
• Where each team finishes: each team's spread of final seeds
• A week-by-week view showing how the luck built up over the season

Download the full-season report as a PDF and share it in your league chat.

HOW TO USE
1. Log in to ESPN and open your league on fantasy.espn.com.
2. Click the extension's icon. Your league fills in automatically.
3. Click Build report. It takes a few seconds.

Works with public and private ESPN fantasy football leagues.

PRIVACY
Everything runs in your browser. There's no server, no account and no tracking. Your ESPN login is only used to load your league from ESPN, exactly like viewing your league normally, and it never leaves your browser. The code is open source: https://github.com/fajardgb/espn-fantasy-football-schedule-permutations

Not affiliated with or endorsed by ESPN.
```

**Category:** Sports (if the dashboard's category list has no Sports option, pick the closest fit, such as Fun or Tools)

**Language:** English

**Graphic assets** (all in `images/`):
| Field | File | Size |
|---|---|---|
| Store icon | `../chrome_extension/icons/icon128.png` | 128×128 |
| Screenshots (upload in this order) | `screenshot-1-playoff-odds.png` … `screenshot-5-popup.png` | 1280×800 |
| Small promo tile | `promo-small-440x280.png` | 440×280 |

**Official URL / Homepage URL:** https://github.com/fajardgb/espn-fantasy-football-schedule-permutations
**Support URL:** https://github.com/fajardgb/espn-fantasy-football-schedule-permutations/issues

---

## Privacy tab

**Single purpose description:**
```
Builds a schedule-luck report for the user's ESPN fantasy football league: it downloads the league's schedule and weekly scores from ESPN and simulates alternative schedules to show playoff odds and how much luck affected each team's record.
```

**Permission justifications:**

`cookies`
```
Private ESPN fantasy leagues only share their data with logged-in members. The extension reads the user's ESPN login cookies (espn_s2 and SWID) on fantasy.espn.com so it can request the user's own league data from ESPN, and so the popup can show whether the user is logged in. The cookies are only sent to ESPN and are never stored or sent anywhere else.
```

`activeTab`
```
When the user clicks the extension's icon on their ESPN league page, the extension reads that tab's address to fill in the league ID and season automatically. It does not read page content and has no access to other tabs.
```

Host permission (`https://fantasy.espn.com/*`, `https://lm-api-reads.fantasy.espn.com/*`)
```
fantasy.espn.com: needed to read the ESPN login cookies for that site (see the cookies justification). lm-api-reads.fantasy.espn.com: ESPN's fantasy data service, from which the extension downloads the user's league settings, schedule and weekly scores to build the report. No other sites are accessed.
```

**Are you using remote code?** No, I am not using remote code.
(Explanation, if asked: all code, including the bundled Plotly and jsPDF libraries, ships inside the extension package.)

**Data usage: what user data do you collect?**
Check **Authentication information**. The extension reads the ESPN login cookies and sends them only to ESPN to load the user's league. Leave everything else unchecked: no personal or health information, financial data, location, web history, user activity or website content is collected.

**Certify all three statements:**
- I do not sell or transfer user data to third parties, outside of the approved use cases
- I do not use or transfer user data for purposes that are unrelated to my item's single purpose
- I do not use or transfer user data to determine creditworthiness or for lending purposes

**Privacy policy URL:**
```
https://github.com/fajardgb/espn-fantasy-football-schedule-permutations/blob/main/PRIVACY.md
```
(It's only live after `PRIVACY.md` is committed and pushed.)

---

## Distribution tab
- **Visibility:** start with **Unlisted** (installable only by people with the link) to try the published version, then switch to **Public**.
- **Regions:** all regions.

## Publishing updates
1. Raise `version` in `chrome_extension/manifest.json` (every upload needs a new version).
2. Run `uv run python chrome_store/build_zip.py`.
3. Upload the new zip on the Package tab and submit for review.
