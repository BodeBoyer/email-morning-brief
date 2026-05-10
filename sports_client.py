from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import requests


_TIMEOUT = 12
_HEADERS = {"User-Agent": "email-morning-brief/1.0"}

_ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports"
_ESPN_WEB = "https://site.web.api.espn.com/apis/v2/sports"
_NBA = "basketball/nba"
_NFL = "football/nfl"
_NCAAB = "basketball/mens-college-basketball"
_CFB = "football/college-football"

_HORNETS_ID = "30"
_PATRIOTS_ID = "17"
_UNC_ID = "153"

_LEAGUE_HEADLINE_KEYWORDS = (
    "playoff",
    "finals",
    "trade",
    "injury",
    "suspension",
    "record",
    "mvp",
    "draft",
    "free agent",
    "contract",
    "coach",
)
_UNC_KEYWORDS = ("unc", "north carolina", "tar heels", "tar heel", "belichick", "chapel hill")
_RECRUITING_KEYWORDS = ("recruit", "commit", "transfer", "portal", "prospect", "signs")


def _brief_item(title: str, detail: str = "", source: str = "ESPN", url: str = "") -> dict:
    return {
        "title": re.sub(r"\s+", " ", title or "").strip(),
        "detail": re.sub(r"\s+", " ", detail or "").strip(),
        "source": source,
        "url": url,
    }


def _get_json(url: str, params: Optional[dict] = None) -> dict:
    resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _get_xml(url: str) -> Optional[ET.Element]:
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _news_url(article: dict) -> str:
    links = article.get("links") or {}
    web = links.get("web") or {}
    return web.get("href") or article.get("link") or ""


def _fetch_espn_news(sport_path: str, limit: int = 12) -> list[dict]:
    try:
        data = _get_json(f"{_ESPN_SITE}/{sport_path}/news", {"limit": limit})
    except Exception:
        return []

    articles = []
    for article in data.get("articles", [])[:limit]:
        headline = article.get("headline") or article.get("title")
        if not headline:
            continue
        articles.append(
            _brief_item(
                headline,
                article.get("description", "")[:180],
                "ESPN",
                _news_url(article),
            )
        )
    return articles


def _fetch_rss(url: str, source: str, keywords: tuple[str, ...], limit: int = 4) -> list[dict]:
    try:
        root = _get_xml(url)
    except Exception:
        return []
    if root is None:
        return []

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        haystack = f"{title} {desc}".lower()
        if keywords and not any(keyword in haystack for keyword in keywords):
            continue
        items.append(_brief_item(title, desc[:180], source, link))
        if len(items) >= limit:
            break
    return items


def _team_record(sport_path: str, team_id: str) -> list[dict]:
    try:
        data = _get_json(f"{_ESPN_SITE}/{sport_path}/teams/{team_id}")
    except Exception:
        return []

    team = data.get("team") or {}
    records = []
    for record_group in (team.get("record") or {}).get("items", []):
        summary = record_group.get("summary")
        if summary:
            label = record_group.get("description") or record_group.get("type") or "Record"
            records.append(_brief_item(f"{team.get('displayName', 'Team')} {label}: {summary}"))
    return records[:2]


def _standing_entries(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("team"), dict) and isinstance(obj.get("stats"), list):
            yield obj
        for value in obj.values():
            yield from _standing_entries(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _standing_entries(value)


def _standings_item(sport_path: str, team_id: str, team_name: str) -> list[dict]:
    data = None
    for base_url in (_ESPN_SITE, _ESPN_WEB):
        try:
            data = _get_json(f"{base_url}/{sport_path}/standings")
            break
        except Exception:
            continue
    if not data:
        return []

    for entry in _standing_entries(data):
        team = entry.get("team") or {}
        if str(team.get("id")) != str(team_id):
            continue
        stats = {
            stat.get("name") or stat.get("abbreviation") or stat.get("displayName"): stat.get("displayValue")
            for stat in entry.get("stats", [])
            if stat.get("displayValue") not in (None, "")
        }
        wins = stats.get("wins") or stats.get("W")
        losses = stats.get("losses") or stats.get("L")
        seed = stats.get("playoffSeed") or stats.get("seed")
        games_back = stats.get("gamesBehind") or stats.get("GB")

        parts = []
        if wins and losses:
            parts.append(f"{wins}-{losses}")
        if seed:
            parts.append(f"seed {seed}")
        if games_back:
            parts.append(f"{games_back} GB")
        if not parts and entry.get("note"):
            parts.append(entry["note"])
        if parts:
            return [_brief_item(f"{team.get('displayName') or team_name} standings: {', '.join(parts)}")]
    return []


def _competitor_label(competitor: dict) -> str:
    team = competitor.get("team") or {}
    name = team.get("abbreviation") or team.get("shortDisplayName") or team.get("displayName") or "Team"
    score = competitor.get("score")
    return f"{name} {score}" if score not in (None, "") else name


def _event_includes_team(event: dict, team_id: str) -> bool:
    for competition in event.get("competitions", []):
        for competitor in competition.get("competitors", []):
            team = competitor.get("team") or {}
            if str(team.get("id")) == str(team_id):
                return True
    return False


def _event_item(event: dict, source_label: str = "ESPN") -> Optional[dict]:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competitors = competitions[0].get("competitors", [])
    if len(competitors) < 2:
        return None

    matchup = " vs ".join(_competitor_label(c) for c in competitors)
    status = (event.get("status") or {}).get("type") or {}
    status_text = status.get("shortDetail") or status.get("detail") or event.get("date", "")
    venue = ((competitions[0].get("venue") or {}).get("fullName") or "").strip()
    detail = status_text if not venue else f"{status_text} at {venue}"
    url = ""
    links = event.get("links") or []
    if links:
        url = links[0].get("href", "")
    return _brief_item(matchup, detail, source_label, url)


def _scoreboard_items(sport_path: str, team_id: Optional[str] = None, playoff_only: bool = False) -> list[dict]:
    try:
        data = _get_json(f"{_ESPN_SITE}/{sport_path}/scoreboard", {"limit": 100})
    except Exception:
        return []

    items = []
    for event in data.get("events", []):
        if team_id and not _event_includes_team(event, team_id):
            continue
        if playoff_only:
            season_type = (event.get("season") or {}).get("type")
            event_name = f"{event.get('name', '')} {event.get('shortName', '')}".lower()
            if season_type != 3 and "playoff" not in event_name and "finals" not in event_name:
                continue
        item = _event_item(event)
        if item:
            items.append(item)
    return items


def _schedule_items(sport_path: str, team_id: str, limit: int = 2) -> list[dict]:
    data = None
    for base_url in (_ESPN_SITE, _ESPN_WEB):
        try:
            data = _get_json(f"{base_url}/{sport_path}/teams/{team_id}/schedule")
            break
        except Exception:
            continue
    if not data:
        return []

    now = datetime.now(timezone.utc)
    items = []
    for event in data.get("events", []):
        event_date_str = event.get("date", "")
        try:
            event_date = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if event_date < now:
            continue
        item = _event_item(event)
        if item:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def _injury_items(sport_path: str, team_id: str, limit: int = 3) -> list[dict]:
    try:
        data = _get_json(f"{_ESPN_SITE}/{sport_path}/teams/{team_id}/injuries")
    except Exception:
        return []

    injuries = []
    for athlete in data.get("injuries", []) or data.get("athletes", []):
        name = athlete.get("displayName") or athlete.get("name") or athlete.get("athlete", {}).get("displayName")
        injury = athlete.get("injury") or athlete.get("status") or {}
        status = injury.get("status") if isinstance(injury, dict) else str(injury)
        detail = injury.get("detail", "") if isinstance(injury, dict) else ""
        if name and status:
            injuries.append(_brief_item(f"{name}: {status}", detail, "ESPN"))
        if len(injuries) >= limit:
            break
    return injuries


def _important_news(news: list[dict], keywords: tuple[str, ...], limit: int) -> list[dict]:
    picked = []
    seen = set()
    for item in news:
        haystack = f"{item['title']} {item['detail']}".lower()
        if any(keyword in haystack for keyword in keywords):
            key = item["title"].lower()
            if key not in seen:
                picked.append(item)
                seen.add(key)
        if len(picked) >= limit:
            break
    return picked


def _group(title: str, items: list[dict]) -> dict:
    return {"title": title, "items": [item for item in items if item.get("title")]}


def fetch_sports_brief() -> dict:
    nba_news = _fetch_espn_news(_NBA)
    nfl_news = _fetch_espn_news(_NFL)
    ncaab_news = _fetch_espn_news(_NCAAB)
    cfb_news = _fetch_espn_news(_CFB)

    hornets_keywords = ("hornets", "charlotte", "lamelo", "miller")
    patriots_keywords = ("patriots", "new england", "vrabel", "drake maye")

    nba_extra = _fetch_rss(
        "https://www.nba.com/rss/nba_rss.xml",
        "NBA.com",
        hornets_keywords + _LEAGUE_HEADLINE_KEYWORDS,
        3,
    )
    nfl_extra = _fetch_rss(
        "https://www.cbssports.com/rss/headlines/nfl/",
        "CBSSports",
        patriots_keywords + _LEAGUE_HEADLINE_KEYWORDS,
        3,
    )
    unc_extra = []
    unc_extra.extend(
        _fetch_rss(
            "https://www.cbssports.com/rss/headlines/college-basketball/",
            "CBSSports",
            _UNC_KEYWORDS + _RECRUITING_KEYWORDS,
            3,
        )
    )
    unc_extra.extend(
        _fetch_rss(
            "https://www.cbssports.com/rss/headlines/college-football/",
            "CBSSports",
            _UNC_KEYWORDS + _RECRUITING_KEYWORDS,
            3,
        )
    )

    hornets = []
    hornets.extend(_scoreboard_items(_NBA, _HORNETS_ID))
    hornets.extend(_schedule_items(_NBA, _HORNETS_ID, 2))
    hornets.extend(_standings_item(_NBA, _HORNETS_ID, "Charlotte Hornets"))
    hornets.extend(_team_record(_NBA, _HORNETS_ID))
    hornets.extend(_injury_items(_NBA, _HORNETS_ID, 3))
    hornets.extend(_important_news(nba_news + nba_extra, hornets_keywords, 3))

    nba_headlines = []
    nba_headlines.extend(_scoreboard_items(_NBA, playoff_only=True)[:4])
    nba_headlines.extend(_important_news(nba_news + nba_extra, _LEAGUE_HEADLINE_KEYWORDS, 4))

    patriots = []
    patriots.extend(_schedule_items(_NFL, _PATRIOTS_ID, 3))
    patriots.extend(_standings_item(_NFL, _PATRIOTS_ID, "New England Patriots"))
    patriots.extend(_team_record(_NFL, _PATRIOTS_ID))
    patriots.extend(_important_news(nfl_news + nfl_extra, patriots_keywords, 4))

    nfl_headlines = _important_news(nfl_news + nfl_extra, _LEAGUE_HEADLINE_KEYWORDS, 4)

    unc_keywords = _UNC_KEYWORDS + _RECRUITING_KEYWORDS
    unc = []
    unc.extend(_scoreboard_items(_NCAAB, _UNC_ID))
    unc.extend(_schedule_items(_NCAAB, _UNC_ID, 2))
    unc.extend(_scoreboard_items(_CFB, _UNC_ID))
    unc.extend(_schedule_items(_CFB, _UNC_ID, 2))
    unc.extend(_important_news(ncaab_news + cfb_news + unc_extra, unc_keywords, 5))

    return {
        "generated_at": datetime.now().isoformat(),
        "groups": [
            _group("NBA: Charlotte Hornets", hornets[:7]),
            _group("NBA League Headlines", nba_headlines[:6]),
            _group("NFL: New England Patriots", patriots[:7]),
            _group("NFL League Headlines", nfl_headlines[:5]),
            _group("UNC Basketball / Football", unc[:7]),
        ],
    }
