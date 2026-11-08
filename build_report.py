"""
Build a single, shareable HTML report for a league.

The report has interactive charts (Plotly) and a "through week N" slider.
Every slider position is simulated ahead of time here, so the page needs no
server: open it locally, email it, or host it as a static file.

Usage:
    uv run python build_report.py [--sims 10000] [--seed 42] [--offline]
"""

import argparse
import json
import math
import os
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from get_espn_league_data import league_data_paths
from simulate_schedule_permutations import (
    format_record,
    load_league_structure,
    load_scores,
    schedule_swap_matrix,
    simulator_through_week,
)

# Pinned to the plotly.js version bundled with the plotly Python package
PLOTLY_CDN = 'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@4.1.1/plotly.min.js'
MAX_GRID_COLUMNS = 7
TEMPLATE_PATH = Path(__file__).parent / 'report_template.html'


def grid_shape(n_teams: int, max_columns: int = MAX_GRID_COLUMNS) -> tuple[int, int]:
    """Rows and columns for one small panel per team (12 -> 2x6, 14 -> 2x7, 16 -> 3x6)."""
    rows = math.ceil(n_teams / max_columns)
    return rows, math.ceil(n_teams / rows)


def build_report_data(scores_df: pd.DataFrame, structure: dict,
                      num_schedules: int = 10000, seed: int = 42) -> dict:
    """
    Simulate every "through week N" cutoff and collect what the charts need.

    Without the league's schedule file only the full season can be simulated
    (actual records at earlier weeks are unknown), so the slider has one stop.
    """
    week_columns = [c for c in scores_df.columns if c.startswith('W')]
    n_weeks = len(week_columns)
    cutoffs = range(1, n_weeks + 1) if structure['actual_schedule'] else [n_weeks]

    weeks = []
    for week in cutoffs:
        sim = simulator_through_week(scores_df, structure, week)
        results = sim.run_simulation(num_schedules, seed=seed)
        seed_pct = sim.seed_counts / num_schedules * 100

        entry = {
            'week': week,
            'results': [
                {
                    'player': row['Player'],
                    'record': row['Actual Record'],
                    'points_for': round(float(row['Points For']), 2),
                    'actual': round(float(row['Actual Win %']), 2),
                    'expected': round(float(row['Expected Win %']), 2),
                    'luck': round(float(row['Luck (pp)']), 2),
                    'playoff': round(float(row['Playoff %']), 2),
                }
                for _, row in results.iterrows()
            ],
            'seeds': {team: [round(float(v), 2) for v in seed_pct.loc[team]]
                      for team in seed_pct.index},
            'swap': None,
        }
        if structure['actual_schedule']:
            matrix = schedule_swap_matrix(sim.scores_df, structure['actual_schedule'][:week])
            teams = list(matrix)
            entry['swap'] = {
                'teams': teams,
                'wins': [[matrix[x][y]['wins'] + 0.5 * matrix[x][y]['ties'] for y in teams]
                         for x in teams],
                'records': [[format_record(matrix[x][y]) for y in teams] for x in teams],
            }
        weeks.append(entry)

    generator = structure['generator']
    divisions = sorted(set(generator.slot_divisions.values()) - {''}) if generator else []
    rows, cols = grid_shape(len(scores_df))
    return {
        'league': {
            'n_teams': len(scores_df),
            'n_playoff_teams': structure['n_playoff_teams'],
            'num_schedules': num_schedules,
            'weeks_played': n_weeks,
            'divisions': divisions,
            'notes': structure['notes'],
            'grid': {'rows': rows, 'cols': cols},
        },
        'weeks': weeks,
    }


def render_html(data: dict, title: str, offline: bool = False) -> str:
    """Fill the report template with the data and the Plotly script."""
    if offline:
        from plotly.offline import get_plotlyjs
        plotly_tag = f'<script>{get_plotlyjs()}</script>'
    else:
        plotly_tag = f'<script src="{PLOTLY_CDN}"></script>'

    # Keep '</script>' inside strings from closing the data block early
    payload = json.dumps(data).replace('</', '<\\/')
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    return (template
            .replace('__TITLE__', title)
            .replace('__PLOTLY__', plotly_tag)
            .replace('__DATA__', payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sims', type=int, default=10000,
                        help='simulated schedules per week (default 10000)')
    parser.add_argument('--seed', type=int, default=42, help='random seed (default 42)')
    parser.add_argument('--offline', action='store_true',
                        help='embed Plotly in the file so it works without internet (~5 MB)')
    args = parser.parse_args()

    load_dotenv()
    league_id = os.getenv('LEAGUE_ID')
    year = os.getenv('YEAR')
    if not league_id or not year:
        raise ValueError("LEAGUE_ID and YEAR must be set in environment variables")

    paths = league_data_paths(league_id, year)
    if not paths['scores'].exists():
        raise FileNotFoundError(f"Data file not found: {paths['scores']} "
                                "(run get_espn_league_data.py first)")

    scores = load_scores(paths['scores'])
    structure = load_league_structure(scores, paths['schedule'], paths['settings'])
    for note in structure['notes']:
        print(f"Note: {note}")

    n_weeks = len([c for c in scores.columns if c.startswith('W')])
    print(f"Simulating {args.sims:,} schedules for each of {n_weeks} week cutoffs...")
    data = build_report_data(scores, structure, args.sims, args.seed)
    data['league'].update({'id': league_id, 'year': int(year),
                           'generated': date.today().isoformat()})

    output_path = paths['dir'].parent / f'league{league_id}_year{year}_report.html'
    html = render_html(data, f'Schedule Luck {year}', offline=args.offline)
    output_path.write_text(html, encoding='utf-8')
    print(f"Report saved to {output_path}")


if __name__ == '__main__':
    main()
