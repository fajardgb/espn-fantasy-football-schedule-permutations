# ESPN Fantasy Football playoff probability analysis

In my 2025 fantasy football season, I experienced a frustrating outcome: despite scoring the 2nd highest points in a 12-team league, I failed to make the playoffs (top-6 team advance). This result (shown below) prompted me to ask: How unlucky was I, really? 

![output_example](./output_example/league12345_year2025/league12345_year2025_playoff_probabilities.png)

## Understanding schedule luck
Fantasy football has inherent randomness. Your record doesn't just depend on how well your team performs - it also depends on when you face each opponent. You could have a great week but lose to the one person who had an even better week. Conversely, you could squeak by with a mediocre score because you happened to face the lowest-scoring team that week.

## The simulation approach

To quantify exactly how unlucky my season was, I created a Monte Carlo simulation that:

1. Preserves actual performance: Uses the real weekly scores each team achieved throughout the season
2. Randomizes matchups: Generates thousands of alternative schedules by randomly reassigning teams to the slots of the league's real schedule, so every simulated season keeps the league's actual format (division games, repeat matchups, byes)
3. Simulates outcomes: For each random schedule, applies the league's playoff rules to determine which teams would have made the playoffs
4. Calculates probabilities: Tracks how often each team makes the playoffs across all simulations
5. Measures expected wins: Tracks each team's average win percentage across all simulated schedules, i.e. the record a team "should" have had with a schedule-neutral draw

## League formats

The league's format and rules are read from ESPN, so the simulation adapts to:

- **Any league size, odd or even:** in odd leagues one team has a bye each week. Byes don't count as games, so they don't affect win percentage.
- **Divisions:** teams are reassigned to schedule slots completely at random, so a team can land in either division. Being placed in a tough or weak division is treated as part of the luck being measured.
- **Playoff rules:** the number of playoff teams comes from the league settings. Each division winner gets a spot, then the remaining spots go to the best records in the league. Teams are ranked by win percentage, with total points scored as the tiebreaker. This matches the playoff seeds ESPN assigns.
- **Ties:** equal weekly scores count as a tie (half a win) for both teams.
- **Seasons in progress:** only completed weeks are simulated, and playoff weeks are never counted as regular-season games.

If the schedule and settings files are missing (for example, data fetched with an older version of this tool), the simulation falls back to random round-robin schedules with no divisions and 6 playoff teams.

Not yet modeled: playoff tiebreakers other than total points scored, and matchup tie rules other than allowing ties. The simulation prints a warning if a league uses one.

## Measuring luck

Playoff odds show *what* the schedule cost me, but not *how much* luck was involved. To measure that directly, the simulation also produces a luck scatterplot:

![luck_scatterplot](./output_example/league12345_year2025/league12345_year2025_luck_scatterplot.png)

- **Expected Win % (x-axis):** a team's average win percentage across all simulated schedules (ties count as half a win)
- **Actual Win % (y-axis):** the team's real record (ties count as half a win)
- **Luck Index (color):** actual minus expected win %, in percentage points, from red (unlucky) through yellow (neutral) to green (lucky)

Teams on the dashed diagonal got exactly the record their scores earned. Teams above it (top-left, **lucky**) won more games than their scores deserved; teams below it (bottom-right, **unlucky**) won fewer.

In my case, my scores were good enough to win about 60% of the time across all possible schedules, yet I finished 5-9 (36%). That's a luck index of −24, the unluckiest team in the league.


# Installation
## Quick setup

1. Clone the repository
```
git clone https://github.com/fajardgb/espn-fantasy-football-schedule-permutations.git
cd espn-fantasy-football-schedule-permutations
```

2. Install dependencies

With [uv](https://docs.astral.sh/uv/) (recommended):
```
uv sync
```
Or with pip:
```
pip install -r requirements.txt
```

3. Configure credentials
```
cp .env_example .env
# Edit .env with your league ID, year, ESPN S2 and SWID
```
To find these credentials:
- Log into ESPN Fantasy Football in your browser
    - Your league ID will be in the URL
    - The year is the fantasy season of interest
- Open Developer Tools (F12)
- Go to Application/Storage > Cookies
- Find 'espn_s2' and 'SWID' values
# Usage
If you installed with pip, drop the `uv run` prefix from the commands below.

1. Fetch league data (weekly scores, schedule, and league settings)
```
uv run python get_espn_league_data.py
```
2. Simulate schedule permutations and generate plots
```
uv run python simulate_schedule_permutations.py
```
3. Build the shareable HTML report (optional)
```
uv run python build_report.py
```
This writes one self-contained `.html` file with interactive charts and a **"through week N"** slider that shows how the luck built up over the season. Open it in any browser, send it to your league, or host it as a static page. Options:
- `--sims 20000` sets the number of simulated schedules per week (default 10000)
- `--seed 7` changes the random seed (default 42)
- `--offline` embeds the charting library so the file works without internet (adds ~5 MB)

Add `#week=5` to the end of the report's URL to open it at a given week.

The report contains:
- **Playoff odds** for each team
- **Schedule luck**: actual vs. expected win %, colored by luck index
- **What if you had their schedule?**: a heatmap of every team's record if it had played every other team's real schedule
- **Where each team finishes**: the distribution of final seeds for each team, one small chart per team
- A table view of the numbers

## Running the tests
```
uv sync
uv run pytest
```
With pip, install pytest first (`pip install pytest`), then run `pytest`.
The tests cover league sizes from 4 to 16 teams (odd and even), different season lengths, divisions, ties, and parsing ESPN API responses. API tests use anonymized copies of real ESPN responses in `tests/fixtures/`, so no credentials or network access are needed.

## Outputs
Everything is written to `output/league<LEAGUE_ID>_year<YEAR>/`:

| File | Description |
|------|-------------|
| `league<ID>_year<YEAR>_playoff_probabilities.png` | Bar chart of each team's playoff probability |
| `league<ID>_year<YEAR>_luck_scatterplot.png` | Actual vs. expected win % scatterplot, colored by luck index |
| `league<ID>_year<YEAR>_report.html` | Shareable interactive report (from `build_report.py`) |
| `data/fantasy_scores_wide_league<ID>_y<YEAR>.csv` | Each team's ESPN team ID, division, record, and weekly scores (completed regular-season weeks only) |
| `data/schedule_league<ID>_y<YEAR>.csv` | The league's full regular-season schedule, including weeks not yet played |
| `data/league_settings_league<ID>_y<YEAR>.json` | League rules used by the simulation: playoff team count, playoff tiebreaker, season length, tie rule, and divisions |
| `data/playoff_probabilities_league<ID>_y<YEAR>.csv` | Per-team simulation results |

The results CSV contains these columns:

| Column | Description |
|--------|-------------|
| `Player` | Team owner name |
| `Actual Record` | Real W-L (or W-L-T) record |
| `Points For` | Total points scored |
| `Actual Win %` | Win percentage from the real record |
| `Expected Win %` | Average win percentage across all simulated schedules (ties count as half a win) |
| `Luck (pp)` | Actual minus expected win %, in percentage points |
| `Playoff %` | Share of simulated schedules in which the team made the playoffs |

See [`output_example/`](./output_example/league12345_year2025/) for a full set of example outputs. The example data predates the schedule and settings files, so it uses the round-robin fallback.

