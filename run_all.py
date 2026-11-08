"""
Run everything in one go: download your league from ESPN, simulate the
schedules, save the plots, and build the shareable HTML report.

Usage:
    uv run python run_all.py [--sims 100000] [--seed 42] [--offline] [--skip-download] [--no-open]

Your league details are read from the .env file (see the README).
"""

import argparse
import os
import webbrowser
from pathlib import Path

from build_report import add_report_arguments, build_report
from get_espn_league_data import fetch_league_data, load_config, run_cli
from simulate_schedule_permutations import run_league_simulation

PROJECT_DIR = Path(__file__).resolve().parent


def step(number: int, total: int, title: str) -> None:
    print(f"\n{'=' * 60}\nStep {number} of {total}: {title}\n{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_report_arguments(parser)
    parser.add_argument('--skip-download', action='store_true',
                        help='reuse the league data downloaded last time instead of fetching it again')
    parser.add_argument('--no-open', action='store_true',
                        help="don't open the report in your browser when it's done")
    args = parser.parse_args()

    # .env and output/ live in the project folder, wherever this is run from
    os.chdir(PROJECT_DIR)
    league_id, year, espn_s2, swid = load_config()

    step(1, 3, "Download league data from ESPN")
    if args.skip_download:
        print("Skipped (--skip-download): using the data downloaded last time.")
    else:
        print(f"Downloading league {league_id}, {year} season...")
        fetch_league_data(league_id, year, espn_s2, swid)

    step(2, 3, "Simulate schedules and save plots")
    run_league_simulation(league_id, year, args.sims, args.seed)

    step(3, 3, "Build the shareable report")
    report = build_report(league_id, year, args.sims, args.seed, args.offline)

    print(f"\nAll done! Your report is at:\n  {report.resolve()}")
    print("Open it in any web browser, or send the file to your league.")
    if not args.no_open:
        webbrowser.open(report.resolve().as_uri())


if __name__ == '__main__':
    run_cli(main)
