import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_SECTIONS: Dict[str, Dict[str, Any]] = {
    "technology": {
        "title": {"en": "Technology", "pl": "Technologia"},
        "feeds": [
            "https://feeds.arstechnica.com/arstechnica/technology-lab",
            "https://www.theverge.com/rss/index.xml",
        ],
        "keywords": ["tech", "technology", "software", "hardware", "programming", "kod", "programowanie"],
    },
    "science": {
        "title": {"en": "Science", "pl": "Nauka"},
        "feeds": [
            "https://www.sciencedaily.com/rss/top/science.xml",
            "https://www.newscientist.com/subject/science/feed/",
        ],
        "keywords": ["science", "nauka", "research", "badania", "physics", "chemistry", "biology"],
    },
    "top_stories": {
        "title": {"en": "Top Stories", "pl": "Najwazniejsze"},
        "feeds": [
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "https://feeds.bbci.co.uk/news/rss.xml",
        ],
        "keywords": ["news", "world", "global", "top", "aktualnosci", "wiadomosci"],
    },
    "weather": {
        "title": {"en": "Weather", "pl": "Pogoda"},
        "feeds": [],
        "keywords": ["weather", "pogoda", "temperature", "deszcz", "sunny"],
    },
    "ai": {
        "title": {"en": "AI", "pl": "Sztuczna inteligencja"},
        "feeds": [
            "https://www.technologyreview.com/topic/artificial-intelligence/feed",
            "https://venturebeat.com/category/ai/feed/",
        ],
        "keywords": ["ai", "ml", "llm", "sztuczna", "inteligencja", "machine learning"],
    },
    "security": {
        "title": {"en": "Security", "pl": "Bezpieczenstwo"},
        "feeds": [
            "https://krebsonsecurity.com/feed/",
            "https://www.bleepingcomputer.com/feed/",
        ],
        "keywords": ["security", "cyber", "bezpieczenstwo", "hacking", "vulnerability"],
    },
    "gaming": {
        "title": {"en": "Gaming", "pl": "Gaming"},
        "feeds": [
            "https://www.pcgamer.com/rss/",
            "https://www.ign.com/rss",
        ],
        "keywords": ["gaming", "game", "gry", "minecraft", "steam"],
    },
    "space": {
        "title": {"en": "Space", "pl": "Kosmos"},
        "feeds": [
            "https://www.nasa.gov/rss/dyn/breaking_news.rss",
            "https://www.space.com/feeds/all",
        ],
        "keywords": ["space", "kosmos", "nasa", "astronomy", "rocket"],
    },
}

FALLBACK_ORDER = ["technology", "weather", "science", "top_stories"]

WEATHER_CODE_MAP = {
    0: ("Clear", "Bezchmurnie"),
    1: ("Mostly clear", "Przewaznie pogodnie"),
    2: ("Partly cloudy", "Czesciowe zachmurzenie"),
    3: ("Overcast", "Zachmurzenie"),
    45: ("Fog", "Mgla"),
    48: ("Rime fog", "Mgla osiadajaca"),
    51: ("Light drizzle", "Slaba mzawka"),
    53: ("Drizzle", "Mzawka"),
    55: ("Dense drizzle", "Silna mzawka"),
    61: ("Light rain", "Slaby deszcz"),
    63: ("Rain", "Deszcz"),
    65: ("Heavy rain", "Silny deszcz"),
    71: ("Light snow", "Slaby snieg"),
    73: ("Snow", "Snieg"),
    75: ("Heavy snow", "Silny snieg"),
    80: ("Rain showers", "Przelotne opady"),
    81: ("Heavy showers", "Silne przelotne opady"),
    82: ("Violent showers", "Gwale przelotne opady"),
    95: ("Thunderstorm", "Burza"),
    96: ("Thunderstorm with hail", "Burza z gradem"),
    99: ("Severe thunderstorm", "Silna burza"),
}


def make_default_profile() -> Dict[str, Any]:
    return {
        "pinned_sections": ["weather"],
        "preferred_sections": [],
        "auto_slots": 3,
        "candidate_pool": list(DEFAULT_SECTIONS.keys()),
        "proposal_policy": {"enabled": True, "min_confidence": 0.65, "cooldown_hours": 12},
        "language_mode": "auto",
        "max_items_per_section": 5,
    }


def _safe_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = str(item or "").strip().lower()
        if text:
            out.append(text)
    return list(dict.fromkeys(out))


def normalize_profile(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = make_default_profile()
    if isinstance(profile, dict):
        merged.update({k: v for k, v in profile.items() if k in merged})

    merged["pinned_sections"] = [
        s for s in _safe_list(merged.get("pinned_sections")) if s in DEFAULT_SECTIONS
    ][:3]
    merged["preferred_sections"] = [
        s for s in _safe_list(merged.get("preferred_sections")) if s in DEFAULT_SECTIONS
    ][:4]
    merged["candidate_pool"] = [
        s for s in _safe_list(merged.get("candidate_pool")) if s in DEFAULT_SECTIONS
    ] or list(DEFAULT_SECTIONS.keys())

    try:
        merged["auto_slots"] = max(0, int(merged.get("auto_slots", 3)))
    except Exception:
        merged["auto_slots"] = 3

    try:
        merged["max_items_per_section"] = max(1, min(10, int(merged.get("max_items_per_section", 5))))
    except Exception:
        merged["max_items_per_section"] = 5

    policy = merged.get("proposal_policy")
    if not isinstance(policy, dict):
        policy = {}
    merged["proposal_policy"] = {
        "enabled": bool(policy.get("enabled", True)),
        "min_confidence": float(policy.get("min_confidence", 0.65)),
        "cooldown_hours": int(policy.get("cooldown_hours", 12)),
    }
    return merged


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]{2,}", (text or "").lower())


def _weather_desc(code: int, language: str) -> str:
    names = WEATHER_CODE_MAP.get(int(code), ("Unknown", "Nieznane"))
    return names[0] if language == "en" else names[1]


def fetch_weather_details(language: str = "en", days: int = 7) -> Dict[str, Any]:
    lang = "pl" if str(language).lower().startswith("pl") else "en"
    day_limit = max(1, min(10, int(days)))

    try:
        with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as url:
            loc_data = json.loads(url.read().decode("utf-8"))
        if loc_data.get("status") != "success":
            return {"summary": "", "items": [], "error": "location_unavailable"}

        lat = loc_data.get("lat")
        lon = loc_data.get("lon")
        city = str(loc_data.get("city") or "")

        w_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current_weather=true"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,surface_pressure,visibility,cloud_cover,weather_code"
            "&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max,snowfall_sum"
            f"&forecast_days={day_limit}"
            "&timezone=auto"
        )
        with urllib.request.urlopen(w_url, timeout=6) as url:
            w_data = json.loads(url.read().decode("utf-8"))

        current = w_data.get("current", {}) or {}
        current_weather = w_data.get("current_weather", {}) or {}
        current_code = int(current.get("weather_code", current_weather.get("weathercode", -1)))
        current_temp = current.get("temperature_2m", current_weather.get("temperature"))
        apparent = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        pressure = current.get("surface_pressure")
        visibility = current.get("visibility")
        cloud = current.get("cloud_cover")
        current_desc = _weather_desc(current_code, lang)
        if current_temp is None:
            summary = city or ("Weather" if lang == "en" else "Pogoda")
        else:
            if lang == "en":
                summary = f"{current_desc}, {current_temp}C in {city}".strip()
            else:
                summary = f"{current_desc}, {current_temp}C w {city}".strip()

        daily = w_data.get("daily", {}) or {}
        times = list(daily.get("time", []) or [])
        max_temps = list(daily.get("temperature_2m_max", []) or [])
        min_temps = list(daily.get("temperature_2m_min", []) or [])
        codes = list(daily.get("weathercode", []) or [])
        rain_prob = list(daily.get("precipitation_probability_max", []) or [])
        snow_sum = list(daily.get("snowfall_sum", []) or [])

        items: List[Dict[str, str]] = []
        detail_chunks = []
        if apparent is not None:
            if lang == "en":
                detail_chunks.append(f"Feels like {apparent}C")
            else:
                detail_chunks.append(f"Odczuwalna {apparent}C")
        detail_chunks.append(current_desc)
        if humidity is not None:
            detail_chunks.append(f"Humidity {humidity}%" if lang == "en" else f"Wilgotnosc {humidity}%")
        if pressure is not None:
            detail_chunks.append(f"Pressure {pressure} hPa" if lang == "en" else f"Cisnienie {pressure} hPa")
        if visibility is not None:
            vis_km = round(float(visibility) / 1000.0, 1)
            detail_chunks.append(f"Visibility {vis_km} km" if lang == "en" else f"Widocznosc {vis_km} km")
        if cloud is not None:
            detail_chunks.append(f"Cloud {cloud}%" if lang == "en" else f"Zachmurzenie {cloud}%")

        now_title = city or ("Current" if lang == "en" else "Teraz")
        if current_temp is not None:
            now_title = f"{now_title} {round(float(current_temp))}C"

        items.append({
            "title": now_title,
            "url": "",
            "summary": " - ".join(detail_chunks),
            "kind": "overview",
        })

        for idx, day in enumerate(times[:day_limit]):
            max_temp = max_temps[idx] if idx < len(max_temps) else "-"
            min_temp = min_temps[idx] if idx < len(min_temps) else "-"
            code = int(codes[idx]) if idx < len(codes) else -1
            desc = _weather_desc(code, lang)
            p_rain = rain_prob[idx] if idx < len(rain_prob) else None
            s_sum = snow_sum[idx] if idx < len(snow_sum) else None

            if lang == "en":
                extra = []
                if p_rain is not None:
                    extra.append(f"rain {p_rain}%")
                if s_sum is not None:
                    extra.append(f"snow {s_sum} mm")
                detail = f"{desc} | min {min_temp}C / max {max_temp}C"
                if extra:
                    detail += " | " + ", ".join(extra)
            else:
                extra = []
                if p_rain is not None:
                    extra.append(f"deszcz {p_rain}%")
                if s_sum is not None:
                    extra.append(f"snieg {s_sum} mm")
                detail = f"{desc} | min {min_temp}C / max {max_temp}C"
                if extra:
                    detail += " | " + ", ".join(extra)
            items.append({"title": day, "url": "", "summary": detail, "kind": "forecast"})

        return {"summary": summary, "items": items, "error": None}
    except Exception:
        return {"summary": "", "items": [], "error": "weather_unavailable"}


def build_interest_terms(memory_entries: List[Dict[str, Any]], topic_hint: str = "") -> List[str]:
    terms: List[str] = []
    for entry in memory_entries or []:
        terms.extend(_tokenize(str(entry.get("content", ""))))
        for tag in entry.get("tags", []) or []:
            terms.extend(_tokenize(str(tag)))
        for entity in entry.get("entities", []) or []:
            terms.extend(_tokenize(str(entity)))
    terms.extend(_tokenize(topic_hint or ""))
    return terms


def _score_sections(terms: List[str], candidate_pool: List[str]) -> Dict[str, float]:
    score = {section: 0.0 for section in candidate_pool}
    for section in candidate_pool:
        keywords = DEFAULT_SECTIONS.get(section, {}).get("keywords", [])
        if not keywords:
            continue
        for kw in keywords:
            kw_l = kw.lower()
            hits = sum(1 for t in terms if t == kw_l or kw_l in t)
            score[section] += hits

    for section in FALLBACK_ORDER:
        if section in score:
            score[section] += 0.2
    return score


def select_active_sections(profile: Dict[str, Any], terms: List[str], limit: int = 4) -> Tuple[List[str], Dict[str, float]]:
    pinned = [s for s in profile.get("pinned_sections", []) if s in DEFAULT_SECTIONS]
    candidate_pool = [s for s in profile.get("candidate_pool", []) if s in DEFAULT_SECTIONS]
    if not candidate_pool:
        candidate_pool = list(DEFAULT_SECTIONS.keys())

    score = _score_sections(terms, candidate_pool)
    for section in profile.get("preferred_sections", []):
        if section in score:
            score[section] += 1.5

    active: List[str] = []
    for section in pinned:
        if section not in active:
            active.append(section)

    remaining = [s for s in candidate_pool if s not in active]
    remaining.sort(key=lambda s: score.get(s, 0.0), reverse=True)

    for section in remaining:
        if len(active) >= limit:
            break
        active.append(section)

    for section in FALLBACK_ORDER:
        if len(active) >= limit:
            break
        if section not in active and section in DEFAULT_SECTIONS:
            active.append(section)

    return active[:limit], score


def _parse_rss_bytes(data: bytes) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(data)
    except Exception:
        return items

    # RSS
    for item in root.findall(".//channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        if title and link:
            items.append({"title": title, "url": link, "summary": re.sub(r"<[^>]+>", "", description)})

    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        link = ""
        link_node = entry.find("atom:link", ns)
        if link_node is not None:
            link = (link_node.attrib.get("href") or "").strip()
        if title and link:
            items.append({"title": title, "url": link, "summary": summary})

    return items


def _fetch_feed(url: str, limit: int) -> List[Dict[str, str]]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MonikAI-DailyBriefing/1.0",
            "Accept": "application/rss+xml, application/atom+xml, text/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as resp:
        raw = resp.read()
    items = _parse_rss_bytes(raw)
    return items[:limit]


def _section_title(section_id: str, language: str) -> str:
    sec = DEFAULT_SECTIONS.get(section_id, {})
    title_map = sec.get("title", {})
    return title_map.get(language, title_map.get("en", section_id))


def _weather_items(weather_summary: str, language: str, weather_details: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    details = weather_details or {}
    detail_items = details.get("items") if isinstance(details, dict) else None
    if isinstance(detail_items, list) and detail_items:
        return detail_items

    if not weather_summary:
        return []
    title = "Weather now" if language == "en" else "Pogoda teraz"
    return [{"title": title, "url": "", "summary": weather_summary}]


def build_section_items(
    section_id: str,
    language: str,
    max_items: int,
    weather_summary: str = "",
    weather_details: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    if section_id == "weather":
        items = _weather_items(weather_summary, language, weather_details=weather_details)
        err = None
        if not items:
            err = "Weather data unavailable" if language == "en" else "Dane pogodowe niedostepne"
        return items, err

    feeds = DEFAULT_SECTIONS.get(section_id, {}).get("feeds", [])
    seen_urls = set()
    merged: List[Dict[str, str]] = []

    for feed_url in feeds:
        try:
            for item in _fetch_feed(feed_url, max_items):
                url = (item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(item)
                if len(merged) >= max_items:
                    break
            if len(merged) >= max_items:
                break
        except Exception:
            continue

    if merged:
        return merged[:max_items], None

    err = "No feed data available" if language == "en" else "Brak danych z feedow"
    return [], err


def build_proposal(
    active_sections: List[str],
    pinned_sections: List[str],
    scores: Dict[str, float],
    profile: Dict[str, Any],
    language: str,
) -> Optional[Dict[str, Any]]:
    policy = profile.get("proposal_policy") or {}
    if not policy.get("enabled", True):
        return None

    min_conf = float(policy.get("min_confidence", 0.65))
    candidates = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not candidates:
        return None

    best_section, best_score = candidates[0]
    if best_section in active_sections:
        return None

    replaceable = [s for s in active_sections if s not in pinned_sections]
    if not replaceable:
        return None

    weakest = min(replaceable, key=lambda s: scores.get(s, 0.0))
    weak_score = scores.get(weakest, 0.0)
    delta = max(0.0, best_score - weak_score)

    confidence = max(0.0, min(1.0, delta / 3.0))
    if confidence < min_conf:
        return None

    reason = (
        f"Recent context aligns stronger with '{best_section}' than '{weakest}'."
        if language == "en"
        else f"Ostatni kontekst bardziej pasuje do '{best_section}' niz do '{weakest}'."
    )

    return {
        "from_section": weakest,
        "to_section": best_section,
        "reason": reason,
        "confidence": round(confidence, 2),
    }


def build_daily_briefing(
    profile: Dict[str, Any],
    language: str,
    weather_summary: str,
    weather_details: Optional[Dict[str, Any]] = None,
    memory_entries: Optional[List[Dict[str, Any]]] = None,
    topic_hint: str = "",
) -> Dict[str, Any]:
    profile = normalize_profile(profile)
    language = "pl" if str(language).lower().startswith("pl") else "en"

    terms = build_interest_terms(memory_entries or [], topic_hint=topic_hint)
    active_sections, score = select_active_sections(profile, terms, limit=4)

    max_items = int(profile.get("max_items_per_section", 5))
    section_payload: List[Dict[str, Any]] = []

    for section_id in active_sections:
        items, error = build_section_items(
            section_id=section_id,
            language=language,
            max_items=max_items,
            weather_summary=weather_summary,
            weather_details=weather_details,
        )
        section_payload.append(
            {
                "id": section_id,
                "title": _section_title(section_id, language),
                "items": items,
                "error": error,
            }
        )

    proposal = build_proposal(
        active_sections=active_sections,
        pinned_sections=profile.get("pinned_sections", []),
        scores=score,
        profile=profile,
        language=language,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": language,
        "active_sections": active_sections,
        "sections": section_payload,
        "profile": profile,
        "proposal": proposal,
    }
