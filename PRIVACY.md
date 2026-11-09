# Privacy policy: Fantasy Schedule Luck

*Effective November 8, 2026*

Fantasy Schedule Luck is a browser extension that builds a "schedule luck" report for your ESPN fantasy football league. This policy explains what it accesses and what happens to it.

## The short version
The extension runs entirely in your browser. It has no server, no accounts, no analytics and no ads. It doesn't collect, store, sell or share any information about you. The developer never receives your data.

## What the extension accesses, and why

| What | Why | Where it goes |
|---|---|---|
| The address of the tab you're on, **only when you click the extension's icon** | To read your league ID and season from the ESPN page you're viewing | Nowhere. It's only used to fill in the popup |
| Your ESPN login cookies (`espn_s2` and `SWID`) on fantasy.espn.com | Private ESPN leagues only share their data with logged-in members | Only to ESPN's fantasy service (`lm-api-reads.fantasy.espn.com`), with the request for your league's data, exactly as when you view your league on ESPN |
| Your league's data from ESPN (team names, schedule, weekly scores, league settings) | To run the simulation and draw the report | Stays in your browser tab. It's discarded when you close the tab, unless you choose to download the report |

The extension can't see any other website or any other part of espn.com. Chrome enforces this through the permissions it requests.

## Things you choose to do
- **Download PDF / Web page:** saves the report to your computer. The file contains your league's team names, records and scores, the same information every member of your league can see. It never contains your login cookies.
- **Copy as .env:** copies your league ID, season and login cookies to your clipboard, for use with the project's optional Python tool. Treat what you copy like a password: anyone with your `espn_s2` and `SWID` can use your ESPN account.

## What is not done
- No data is sent to the developer or any third party. The only network requests go to ESPN.
- Nothing is stored after you close the report tab. The extension uses no extension storage, cookies of its own, or tracking.
- Your data is not sold, not used for advertising, and not used for anything other than building the report you asked for.

## Open source
All of the extension's code is public, so you can check every point above: https://github.com/fajardgb/espn-fantasy-football-schedule-permutations

## Contact
Questions or concerns: open an issue at https://github.com/fajardgb/espn-fantasy-football-schedule-permutations/issues

Fantasy Schedule Luck is not affiliated with or endorsed by ESPN.
