# Schedule Luck: League Setup (Chrome extension)

This small Chrome extension fills in your `.env` file for you. Open your league on ESPN, click the extension, and click **Copy as .env**. You don't need developer tools or have to hunt for cookies.

It finds:
- your **league ID** and **season**, from the address of the ESPN page you're on
- your **ESPN_S2** and **SWID** login cookies, from your browser (needed for private leagues)

It also checks with ESPN that the league can be reached with those details. It shows the league's name if everything works, or explains what's wrong.

## Install (takes about a minute)
The extension isn't in the Chrome Web Store yet, so you install it from this folder:

1. Download this project (see the main [README](../README.md#setup-one-time)).
2. In Chrome, go to `chrome://extensions`.
3. Turn on **Developer mode** (top right).
4. Click **Load unpacked** and choose this `chrome_extension` folder.
5. Optional: click the puzzle-piece icon in Chrome's toolbar and pin **Fantasy Schedule Luck: League Setup** so it's always visible.

It also works in other Chromium browsers, such as Edge and Brave (use `edge://extensions` or `brave://extensions`).

## Use
1. Log in to ESPN and open your league on [fantasy.espn.com](https://fantasy.espn.com/football/). Any page with the league in its address works (league home, standings, your team).
2. Click the extension's icon. The league ID and season fill in, and you'll see:
   - **✓ Logged in to ESPN in this browser:** the login cookies were found.
   - **✓ "Your League Name" · 12 teams:** ESPN confirmed the league can be reached with these details.
3. Click **Copy as .env**, then paste it into the `.env` file in the project folder, replacing what's there.
4. Run `uv run python run_all.py`.

If the season isn't in the page address, the extension picks the most recent season. You can change the league ID or season by typing in the boxes, and the check runs again.

## Privacy and permissions
- **Your login values never leave your browser.** The extension only reads them, shows them masked, and copies them to your clipboard when you click the button. It has no server and doesn't collect anything.
- The one network request it makes goes to ESPN's own fantasy service. It's the same request your browser makes when you view your league, and it's used to confirm the league can be reached.
- Chrome describes the permissions as:
  - **"Read and change your data on espn.com"**: needed to read the ESPN login cookies and make that one request. The extension doesn't change anything.
  - Reading the current tab's address only happens when you click the extension (the `activeTab` permission), so it can't see your browsing otherwise.

Treat what you copy like a password: anyone with your `ESPN_S2` and `SWID` can use your ESPN account.

## For developers
- `lib/league.js`: pure logic (URL parsing, default season, `.env` text, ESPN response messages), shared with the popup. Kept free of `chrome.*` calls so it can be tested in Node and reused by a future in-browser report.
- `popup.html` / `popup.js` / `popup.css`: the popup.
- Tests: `cd chrome_extension && npm test` (uses Node's built-in test runner; no dependencies).
