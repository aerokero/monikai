import json
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_SECTIONS: Dict[str, Dict[str, Any]] = {
    "weather": {
        "title": {"en": "Weather", "pl": "Pogoda", "zh": "天气", "ja": "天気"},
        "keywords": ["weather", "pogoda", "temperature", "deszcz", "sunny"],
    },
}


WEATHER_CODE_MAP = {
    0: {"en": "Clear", "pl": "Bezchmurnie", "zh": "晴朗", "ja": "晴れ"},
    1: {"en": "Mostly clear", "pl": "Przewaznie pogodnie", "zh": "大多晴朗", "ja": "主に晴れている"},
    2: {"en": "Partly cloudy", "pl": "Czesciowe zachmurzenie", "zh": "局部多云", "ja": "曇りがち"},
    3: {"en": "Overcast", "pl": "Zachmurzenie", "zh": "阴天", "ja": "曇り"},
    45: {"en": "Fog", "pl": "Mgla", "zh": "雾", "ja": "霧"},
    48: {"en": "Rime fog", "pl": "Mgla osiadajaca", "zh": "冰霜雾", "ja": "霧氷"},
    51: {"en": "Light drizzle", "pl": "Slaba mzawka", "zh": "细雨", "ja": "軽い霧雨"},
    53: {"en": "Drizzle", "pl": "Mzawka", "zh": "毛毛雨", "ja": "霧雨"},
    55: {"en": "Dense drizzle", "pl": "Silna mzawka", "zh": "浓雾", "ja": "激しい霧雨"},
    61: {"en": "Light rain", "pl": "Slaby deszcz", "zh": "小雨", "ja": "小雨"},
    63: {"en": "Rain", "pl": "Deszcz", "zh": "雨", "ja": "雨"},
    65: {"en": "Heavy rain", "pl": "Silny deszcz", "zh": "大雨", "ja": "大雨"},
    71: {"en": "Light snow", "pl": "Slaby snieg", "zh": "小雪", "ja": "小雪"},
    73: {"en": "Snow", "pl": "Snieg", "zh": "雪", "ja": "雪"},
    75: {"en": "Heavy snow", "pl": "Silny snieg", "zh": "大雪", "ja": "大雪"},
    80: {"en": "Rain showers", "pl": "Przelotne opady", "zh": "阵雨", "ja": "にわか雨"},
    81: {"en": "Heavy showers", "pl": "Silne przelotne opady", "zh": "强阵雨", "ja": "激しいにわか雨"},
    82: {"en": "Violent showers", "pl": "Gwalte przelotne opady", "zh": "暴雨", "ja": "激しい雨"},
    95: {"en": "Thunderstorm", "pl": "Burza", "zh": "雷暴", "ja": "雷嵐"},
    96: {"en": "Thunderstorm with hail", "pl": "Burza z gradem", "zh": "伴有冰雹的雷暴", "ja": "ひょうを伴う雷嵐"},
    99: {"en": "Severe thunderstorm", "pl": "Silna burza", "zh": "严重雷暴", "ja": "激しい雷嵐"},
}


def _language(raw: str = "en") -> str:
    raw_lower = str(raw or "en").lower()
    if raw_lower.startswith("pl"):
        return "pl"
    if raw_lower.startswith("zh"):
        return "zh"
    if raw_lower.startswith("ja"):
        return "ja"
    return "en"


def make_default_profile() -> Dict[str, Any]:
    return {
        "pinned_sections": ["weather"],
        "preferred_sections": [],
        "auto_slots": 1,
        "candidate_pool": ["weather"],
        "language_mode": "auto",
        "max_items_per_section": 7,
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
    ] or ["weather"]
    merged["preferred_sections"] = []
    merged["candidate_pool"] = ["weather"]
    merged["auto_slots"] = 1

    try:
        merged["max_items_per_section"] = max(1, min(10, int(merged.get("max_items_per_section", 7))))
    except Exception:
        merged["max_items_per_section"] = 7

    return merged


def _weather_desc(code: int, language: str) -> str:
    names = WEATHER_CODE_MAP.get(int(code), {"en": "Unknown", "pl": "Nieznane", "zh": "未知", "ja": "不明"})
    lang = _language(language)
    return names.get(lang, names.get("en", "Unknown"))


def fetch_weather_details(language: str = "en", days: int = 7) -> Dict[str, Any]:
    lang = _language(language)
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
            summary = city or {"en": "Weather", "pl": "Pogoda", "zh": "天气", "ja": "天気"}[lang]
        elif lang == "pl":
            summary = f"{current_desc}, {current_temp}C w {city}".strip()
        elif lang == "zh":
            summary = f"{current_desc}, {current_temp}C 在 {city}".strip()
        else:
            summary = f"{current_desc}, {current_temp}C in {city}".strip()

        daily = w_data.get("daily", {}) or {}
        times = list(daily.get("time", []) or [])
        max_temps = list(daily.get("temperature_2m_max", []) or [])
        min_temps = list(daily.get("temperature_2m_min", []) or [])
        codes = list(daily.get("weathercode", []) or [])
        rain_prob = list(daily.get("precipitation_probability_max", []) or [])
        snow_sum = list(daily.get("snowfall_sum", []) or [])

        detail_chunks = []
        if apparent is not None:
            detail_chunks.append({
                "en": f"Feels like {apparent}C",
                "pl": f"Odczuwalna {apparent}C",
                "zh": f"体感温度 {apparent}C",
                "ja": f"Feels like {apparent}C",
            }[lang])
        detail_chunks.append(current_desc)
        if humidity is not None:
            detail_chunks.append({
                "en": f"Humidity {humidity}%",
                "pl": f"Wilgotnosc {humidity}%",
                "zh": f"湿度 {humidity}%",
                "ja": f"Humidity {humidity}%",
            }[lang])
        if pressure is not None:
            detail_chunks.append({
                "en": f"Pressure {pressure} hPa",
                "pl": f"Cisnienie {pressure} hPa",
                "zh": f"气压 {pressure} hPa",
                "ja": f"Pressure {pressure} hPa",
            }[lang])
        if visibility is not None:
            vis_km = round(float(visibility) / 1000.0, 1)
            detail_chunks.append({
                "en": f"Visibility {vis_km} km",
                "pl": f"Widocznosc {vis_km} km",
                "zh": f"能见度 {vis_km} 公里",
                "ja": f"Visibility {vis_km} km",
            }[lang])
        if cloud is not None:
            detail_chunks.append({
                "en": f"Cloud {cloud}%",
                "pl": f"Zachmurzenie {cloud}%",
                "zh": f"云层 {cloud}%",
                "ja": f"Cloud {cloud}%",
            }[lang])

        now_title = city or {"en": "Current", "pl": "Teraz", "zh": "现在", "ja": "現在"}[lang]
        if current_temp is not None:
            now_title = f"{now_title} {round(float(current_temp))}C"

        items: List[Dict[str, str]] = [{
            "title": now_title,
            "url": "",
            "summary": " - ".join(detail_chunks),
            "kind": "overview",
        }]

        for idx, day in enumerate(times[:day_limit]):
            max_temp = max_temps[idx] if idx < len(max_temps) else "-"
            min_temp = min_temps[idx] if idx < len(min_temps) else "-"
            code = int(codes[idx]) if idx < len(codes) else -1
            desc = _weather_desc(code, lang)
            p_rain = rain_prob[idx] if idx < len(rain_prob) else None
            s_sum = snow_sum[idx] if idx < len(snow_sum) else None

            extra = []
            if p_rain is not None:
                extra.append(f"rain {p_rain}%" if lang == "en" else f"deszcz {p_rain}%")
            if s_sum is not None:
                extra.append(f"snow {s_sum} mm" if lang == "en" else f"snieg {s_sum} mm")
            detail = f"{desc} | min {min_temp}C / max {max_temp}C"
            if extra:
                detail += " | " + ", ".join(extra)
            items.append({"title": day, "url": "", "summary": detail, "kind": "forecast"})

        return {"summary": summary, "items": items, "error": None}
    except Exception:
        return {"summary": "", "items": [], "error": "weather_unavailable"}


def _section_title(section_id: str, language: str) -> str:
    sec = DEFAULT_SECTIONS.get(section_id, {})
    title_map = sec.get("title", {})
    lang = _language(language)
    return title_map.get(lang, title_map.get("en", section_id))


def _weather_items(weather_summary: str, language: str, weather_details: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    details = weather_details or {}
    detail_items = details.get("items") if isinstance(details, dict) else None
    if isinstance(detail_items, list) and detail_items:
        return detail_items

    if not weather_summary:
        return []
    title = "Weather now" if _language(language) == "en" else "Pogoda teraz"
    return [{"title": title, "url": "", "summary": weather_summary, "kind": "overview"}]


def build_section_items(
    section_id: str,
    language: str,
    max_items: int,
    weather_summary: str = "",
    weather_details: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    if section_id != "weather":
        return [], None

    items = _weather_items(weather_summary, language, weather_details=weather_details)
    if max_items:
        items = items[:max_items]
    err = None
    if not items:
        err = "Weather data unavailable" if _language(language) == "en" else "Dane pogodowe niedostepne"
    return items, err


def build_daily_briefing(
    profile: Dict[str, Any],
    language: str,
    weather_summary: str,
    weather_details: Optional[Dict[str, Any]] = None,
    memory_entries: Optional[List[Dict[str, Any]]] = None,
    topic_hint: str = "",
) -> Dict[str, Any]:
    profile = normalize_profile(profile)
    lang = _language(language)
    max_items = int(profile.get("max_items_per_section", 7))
    items, error = build_section_items(
        section_id="weather",
        language=lang,
        max_items=max_items,
        weather_summary=weather_summary,
        weather_details=weather_details,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "language": lang,
        "active_sections": ["weather"],
        "sections": [{
            "id": "weather",
            "title": _section_title("weather", lang),
            "items": items,
            "error": error,
        }],
        "profile": profile,
    }
