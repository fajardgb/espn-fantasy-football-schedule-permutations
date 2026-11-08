"""
Tests for setup help: reading league details from .env (IDs or pasted URLs)
and turning ESPN errors into plain-language messages.
"""

import pytest
import requests

import get_espn_league_data as espn
from get_espn_league_data import (
    ESPNFantasyFootball,
    SetupError,
    load_config,
    load_league_and_year,
    parse_league_input,
)


@pytest.fixture
def env(monkeypatch):
    """Control the settings directly; never read the real .env file."""
    monkeypatch.setattr(espn, 'load_dotenv', lambda: None)
    for name in ('LEAGUE_ID', 'YEAR', 'ESPN_S2', 'SWID'):
        monkeypatch.delenv(name, raising=False)

    def set_env(**values):
        for name, value in values.items():
            monkeypatch.setenv(name, value)
    return set_env


# ------------------------------------------------------------ league input

@pytest.mark.parametrize('value,expected', [
    ('12345678', (12345678, None)),
    (' 12345678 ', (12345678, None)),
    ('"12345678"', (12345678, None)),
    ('https://fantasy.espn.com/football/league?leagueId=12345678&seasonId=2025', (12345678, 2025)),
    ('https://fantasy.espn.com/football/team?leagueId=42&teamId=4&seasonId=2024', (42, 2024)),
    ('fantasy.espn.com/football/league?leagueId=42', (42, None)),
])
def test_parse_league_input(value, expected):
    assert parse_league_input(value) == expected


def test_parse_league_input_rejects_nonsense():
    with pytest.raises(SetupError, match='should be a number'):
        parse_league_input('my league')


def test_year_comes_from_url_when_missing(env):
    env(LEAGUE_ID='https://fantasy.espn.com/football/league?leagueId=7&seasonId=2025')
    assert load_league_and_year() == (7, 2025)


def test_explicit_year_wins_over_url(env):
    env(LEAGUE_ID='https://fantasy.espn.com/football/league?leagueId=7&seasonId=2025', YEAR='2024')
    assert load_league_and_year() == (7, 2024)


def test_missing_league_id(env):
    with pytest.raises(SetupError, match='LEAGUE_ID'):
        load_league_and_year()


def test_example_values_count_as_missing(env):
    env(LEAGUE_ID='your_league_id_here', YEAR='2025')
    with pytest.raises(SetupError, match="LEAGUE_ID isn't set"):
        load_league_and_year()


def test_missing_year(env):
    env(LEAGUE_ID='7')
    with pytest.raises(SetupError, match='YEAR'):
        load_league_and_year()


def test_bad_year(env):
    env(LEAGUE_ID='7', YEAR='25')
    with pytest.raises(SetupError, match='4-digit'):
        load_league_and_year()


# ------------------------------------------------------------- cookies

def test_public_league_needs_no_cookies(env):
    env(LEAGUE_ID='7', YEAR='2025', ESPN_S2='', SWID='')
    assert load_config() == (7, 2025, None, None)


def test_one_cookie_alone_is_ignored_with_warning(env, capsys):
    env(LEAGUE_ID='7', YEAR='2025', ESPN_S2='abc')
    assert load_config() == (7, 2025, None, None)
    assert 'SWID is empty' in capsys.readouterr().out


def test_both_cookies_are_passed_through(env):
    env(LEAGUE_ID='7', YEAR='2025', ESPN_S2='abc', SWID='{1A2B}')
    assert load_config() == (7, 2025, 'abc', '{1A2B}')


# --------------------------------------------------------- ESPN errors

class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return {}


def respond_with(monkeypatch, status=None, error=None):
    def fake_get(*args, **kwargs):
        if error:
            raise error
        return FakeResponse(status)
    monkeypatch.setattr(espn.requests, 'get', fake_get)


def test_private_league_without_cookies(monkeypatch):
    respond_with(monkeypatch, 401)
    with pytest.raises(SetupError, match='private'):
        ESPNFantasyFootball(7, 2025).fetch()


def test_bad_cookies(monkeypatch):
    respond_with(monkeypatch, 401)
    with pytest.raises(SetupError, match='wrong or expired'):
        ESPNFantasyFootball(7, 2025, 'abc', '{x}').fetch()


def test_league_not_found(monkeypatch):
    respond_with(monkeypatch, 404)
    with pytest.raises(SetupError, match='couldn.t find league 7 for the 2025'):
        ESPNFantasyFootball(7, 2025).fetch()


def test_no_internet(monkeypatch):
    respond_with(monkeypatch, error=requests.ConnectionError())
    with pytest.raises(SetupError, match='internet'):
        ESPNFantasyFootball(7, 2025).fetch()


def test_run_cli_prints_message_without_traceback(capsys):
    def broken():
        raise SetupError('Fix your .env')
    with pytest.raises(SystemExit) as exit_info:
        espn.run_cli(broken)
    assert exit_info.value.code == 1
    assert 'Error: Fix your .env' in capsys.readouterr().err


@pytest.mark.parametrize('status,message', [(400, 'error 400'), (403, 'error 403'),
                                            (503, "ESPN's servers")])
def test_other_http_errors(monkeypatch, status, message):
    respond_with(monkeypatch, status)
    with pytest.raises(SetupError, match=message):
        ESPNFantasyFootball(7, 2025).fetch()
