import os
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

AIRPORT = {
    "icao": "SBPA",
    "name": "Porto Alegre Airport",
    "lat": -29.9939,
    "lon": -51.1711,
    "timezone": "America/Sao_Paulo",
}

SOURCES = [
    {
        "name": "NOAA CPC ENSO Diagnostic Discussion",
        "url": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml",
        "type": "html",
    },
    {
        "name": "IRI Columbia ENSO Forecast",
        "url": "https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/",
        "type": "html",
    },
    {
        "name": "INMET",
        "url": "https://portal.inmet.gov.br/",
        "type": "html",
    },
    {
        "name": "Defesa Civil RS",
        "url": "https://www.defesacivil.rs.gov.br/avisos-e-alertas",
        "type": "html",
    },
]

THRESHOLDS = {
    "precipitation": {
        "yellow_24h_mm": 30,
        "orange_24h_mm": 50,
        "red_24h_mm": 80,
        "yellow_72h_mm": 60,
        "orange_72h_mm": 100,
        "red_72h_mm": 150,
    },
    "wind": {
        "yellow_gust_kmh": 50,
        "orange_gust_kmh": 70,
        "red_gust_kmh": 90,
    },
    "keywords": {
        "yellow": [
            "chuva intensa",
            "tempestade",
            "raios",
            "rajadas",
            "instabilidade",
            "El Niño",
            "atenção",
            "perigo potencial",
        ],
        "orange": [
            "alerta",
            "perigo",
            "vendaval",
            "granizo",
            "cheia",
            "inundação",
            "forte",
            "muito forte",
            "laranja",
        ],
        "red": [
            "grande perigo",
            "emergência",
            "inundação severa",
            "evento extremo",
            "crítico",
            "vermelho",
            "evacuação",
            "bloqueio",
        ],
    },
}

HEADERS = {
    "User-Agent": "Fraport-SMS-ElNino-POA-Robot/1.0"
}


def now_brt():
    return datetime.now(ZoneInfo("America/Sao_Paulo"))


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def collect_html_source(source: dict) -> dict:
    try:
        response = requests.get(source["url"], headers=HEADERS, timeout=25)
        response.raise_for_status()
        text = clean_html(response.text)

        return {
            "source": source["name"],
            "url": source["url"],
            "status": "ok",
            "text": text[:15000],
            "error": None,
        }

    except Exception as exc:
        return {
            "source": source["name"],
            "url": source["url"],
            "status": "error",
            "text": "",
            "error": str(exc),
        }


def collect_open_meteo() -> dict:
    lat = AIRPORT["lat"]
    lon = AIRPORT["lon"]

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=precipitation_sum,wind_gusts_10m_max"
        "&hourly=precipitation,wind_gusts_10m"
        "&forecast_days=7"
        "&timezone=America%2FSao_Paulo"
    )

    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        response.raise_for_status()
        return {
            "source": "Open-Meteo POA Forecast",
            "url": url,
            "status": "ok",
            "json": response.json(),
            "error": None,
        }

    except Exception as exc:
        return {
            "source": "Open-Meteo POA Forecast",
            "url": url,
            "status": "error",
            "json": {},
            "error": str(exc),
        }


def collect_aviation_weather() -> dict:
    icao = AIRPORT["icao"]

    metar_url = f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json"
    taf_url = f"https://aviationweather.gov/api/data/taf?ids={icao}&format=json"

    result = {
        "source": f"AviationWeather {icao}",
        "status": "ok",
        "metar_url": metar_url,
        "taf_url": taf_url,
        "metar": None,
        "taf": None,
        "errors": [],
    }

    try:
        metar_response = requests.get(metar_url, headers=HEADERS, timeout=25)
        metar_response.raise_for_status()
        result["metar"] = metar_response.json()
    except Exception as exc:
        result["status"] = "partial_error"
        result["errors"].append(f"METAR: {exc}")

    try:
        taf_response = requests.get(taf_url, headers=HEADERS, timeout=25)
        taf_response.raise_for_status()
        result["taf"] = taf_response.json()
    except Exception as exc:
        result["status"] = "partial_error"
        result["errors"].append(f"TAF: {exc}")

    return result


def classify_keywords(text: str) -> dict:
    text_lower = text.lower()

    hits = {
        "yellow": [],
        "orange": [],
        "red": [],
    }

    for level in hits:
        for word in THRESHOLDS["keywords"][level]:
            if word.lower() in text_lower:
                hits[level].append(word)

    if hits["red"]:
        level = "vermelho"
    elif hits["orange"]:
        level = "laranja"
    elif hits["yellow"]:
        level = "amarelo"
    else:
        level = "verde"

    return {
        "level": level,
        "hits": hits,
    }


def classify_forecast(open_meteo_json: dict) -> dict:
    daily = open_meteo_json.get("daily", {})
    dates = daily.get("time", [])
    precipitation = daily.get("precipitation_sum", []) or []
    gusts = daily.get("wind_gusts_10m_max", []) or []

    p24_max = max(precipitation) if precipitation else 0

    p72_values = []
    for i in range(len(precipitation)):
        p72_values.append(sum(precipitation[i:i + 3]))

    p72_max = max(p72_values) if p72_values else 0
    gust_max = max(gusts) if gusts else 0

    level = "verde"
    reasons = []

    p = THRESHOLDS["precipitation"]
    w = THRESHOLDS["wind"]

    if p24_max >= p["red_24h_mm"] or p72_max >= p["red_72h_mm"]:
        level = "vermelho"
        reasons.append(f"Chuva prevista em nível vermelho: 24h={p24_max:.1f} mm; 72h={p72_max:.1f} mm.")
    elif p24_max >= p["orange_24h_mm"] or p72_max >= p["orange_72h_mm"]:
        level = "laranja"
        reasons.append(f"Chuva prevista em nível laranja: 24h={p24_max:.1f} mm; 72h={p72_max:.1f} mm.")
    elif p24_max >= p["yellow_24h_mm"] or p72_max >= p["yellow_72h_mm"]:
        level = "amarelo"
        reasons.append(f"Chuva prevista em nível amarelo: 24h={p24_max:.1f} mm; 72h={p72_max:.1f} mm.")

    if gust_max >= w["red_gust_kmh"]:
        level = "vermelho"
        reasons.append(f"Rajada prevista em nível vermelho: {gust_max:.1f} km/h.")
    elif gust_max >= w["orange_gust_kmh"] and level != "vermelho":
        level = "laranja"
        reasons.append(f"Rajada prevista em nível laranja: {gust_max:.1f} km/h.")
    elif gust_max >= w["yellow_gust_kmh"] and level not in ["vermelho", "laranja"]:
        level = "amarelo"
        reasons.append(f"Rajada prevista em nível amarelo: {gust_max:.1f} km/h.")

    return {
        "level": level,
        "dates": dates,
        "p24_max_mm": p24_max,
        "p72_max_mm": p72_max,
        "gust_max_kmh": gust_max,
        "reasons": reasons,
    }


def highest_level(levels: list[str]) -> str:
    order = {
        "verde": 0,
        "amarelo": 1,
        "laranja": 2,
        "vermelho": 3,
    }
    return max(levels, key=lambda item: order.get(item, 0))


def actions_by_level(level: str) -> list[str]:
    if level == "vermelho":
        return [
            "Acionar reunião imediata de readiness/crise com SMS, Operações, APOC, Manutenção, SCI e áreas críticas.",
            "Confirmar status de drenagem, bombas, energia, geradores, acessos, escala operacional, SCI e fornecedores críticos.",
            "Avaliar necessidade de comunicação executiva, plano de contingência, MOC ou registro formal de risco temporário.",
            "Registrar evidências de prontidão e decisões tomadas.",
        ]

    if level == "laranja":
        return [
            "Realizar alinhamento preventivo no mesmo dia com SMS, Operações, APOC e Manutenção.",
            "Checar drenagem, pontos sensíveis, energia, geradores, FOD pós-temporal, SCI e equipes de resposta.",
            "Preparar briefing para Diretoria se houver piora de tendência ou persistência dos alertas.",
            "Definir responsável por nova verificação em até 24 horas.",
        ]

    if level == "amarelo":
        return [
            "Manter monitoramento reforçado nas próximas 72 horas.",
            "Confirmar contatos, escalas e recursos críticos.",
            "Registrar tendência no histórico do radar.",
        ]

    return [
        "Manter monitoramento diário.",
        "Sem ação operacional adicional neste momento.",
    ]


def format_hits(hits: dict) -> str:
    parts = []
    for level, words in hits.items():
        if words:
            parts.append(f"{level}: {', '.join(words[:8])}")
    return " | ".join(parts) if parts else "Sem gatilho textual relevante"


def build_report(mode: str, overall_level: str, forecast: dict, web_results: list, aviation: dict, actions: list) -> str:
    date_label = now_brt().strftime("%d/%m/%Y %H:%M")

    lines = []
    lines.append(f"Radar El Niño POA - {mode.upper()}")
    lines.append(f"Data/hora: {date_label}")
    lines.append(f"Status geral: {overall_level.upper()}")
    lines.append("")
    lines.append("1. Síntese operacional")
    lines.append(
        "Monitoramento automático de sinais climáticos, meteorológicos e operacionais "
        "com foco em potenciais impactos ao Porto Alegre Airport: chuva acumulada, temporais, vento, raios, "
        "drenagem, energia, acessos, pista, pátio, terminal, APOC, SCI, FOD e continuidade operacional."
    )
    lines.append("")
    lines.append("2. Previsão quantitativa POA - próximos 7 dias")
    lines.append(f"- Máxima chuva em 24h: {forecast.get('p24_max_mm', 0):.1f} mm")
    lines.append(f"- Máxima chuva acumulada em 72h: {forecast.get('p72_max_mm', 0):.1f} mm")
    lines.append(f"- Máxima rajada prevista: {forecast.get('gust_max_kmh', 0):.1f} km/h")

    if forecast.get("reasons"):
        lines.append("")
        lines.append("3. Gatilhos quantitativos")
        for reason in forecast["reasons"]:
            lines.append(f"- {reason}")

    lines.append("")
    lines.append("4. Fontes web monitoradas")
    for item in web_results:
        analysis = item.get("analysis", {})
        lines.append(f"- {item.get('source')}: coleta={item.get('status')}; nível={analysis.get('level')}; achados={format_hits(analysis.get('hits', {}))}")

    lines.append("")
    lines.append("5. Meteorologia aeronáutica SBPA")
    lines.append(f"- AviationWeather status: {aviation.get('status')}")
    if aviation.get("errors"):
        for error in aviation["errors"]:
            lines.append(f"- Erro: {error}")

    lines.append("")
    lines.append("6. Ações recomendadas")
    for action in actions:
        lines.append(f"- {action}")

    lines.append("")
    lines.append("7. Observação SMS")
    lines.append(
        "Este radar é uma camada de Safety Intelligence. Não substitui boletim meteorológico contratado, "
        "avaliação operacional local, decisão formal, validação regulatória, validação jurídica ou plano de contingência."
    )

    return "\n".join(lines)


def notify_ntfy(title: str, message: str, level: str):
    topic = os.getenv("NTFY_TOPIC")

    if not topic:
        print("NTFY_TOPIC não configurado. Pulando notificação ntfy.")
        return

    url = f"https://ntfy.sh/{topic}"

    priority = "default"
    tags = "information_source"

    if level == "amarelo":
        priority = "default"
        tags = "warning"
    elif level == "laranja":
        priority = "high"
        tags = "rotating_light"
    elif level == "vermelho":
        priority = "urgent"
        tags = "rotating_light,warning"

    headers = {
        "Title": title,
        "Priority": priority,
        "Tags": tags,
    }

    response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=25)
    response.raise_for_status()


def save_history(row: dict):
    path = Path("data/history.csv")
    path.parent.mkdir(parents=True, exist_ok=True)

    new_df = pd.DataFrame([row])

    if path.exists():
        old_df = pd.read_csv(path)
        df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        df = new_df

    df.to_csv(path, index=False)


def save_report(report: str, mode: str):
    report_dir = Path("reports") / mode
    report_dir.mkdir(parents=True, exist_ok=True)

    filename = now_brt().strftime("radar_elnino_poa_%Y%m%d_%H%M.txt")
    path = report_dir / filename
    path.write_text(report, encoding="utf-8")


def main():
    mode = os.getenv("RUN_MODE", "daily")

    print("Coletando previsão Open-Meteo...")
    open_meteo = collect_open_meteo()
    forecast_analysis = classify_forecast(open_meteo.get("json", {}))

    print("Coletando AviationWeather...")
    aviation = collect_aviation_weather()

    print("Coletando fontes web...")
    web_results = []
    for source in SOURCES:
        result = collect_html_source(source)
        result["analysis"] = classify_keywords(result.get("text", ""))
        web_results.append(result)

    levels = [forecast_analysis["level"]]
    levels += [item["analysis"]["level"] for item in web_results]

    overall_level = highest_level(levels)
    actions = actions_by_level(overall_level)

    report = build_report(
        mode=mode,
        overall_level=overall_level,
        forecast=forecast_analysis,
        web_results=web_results,
        aviation=aviation,
        actions=actions,
    )

    title = f"Radar El Niño POA - {overall_level.upper()}"
    notify_ntfy(title, report[:3500], overall_level)

    save_report(report, mode)

    save_history({
        "timestamp": now_brt().isoformat(),
        "mode": mode,
        "overall_level": overall_level,
        "p24_max_mm": forecast_analysis.get("p24_max_mm"),
        "p72_max_mm": forecast_analysis.get("p72_max_mm"),
        "gust_max_kmh": forecast_analysis.get("gust_max_kmh"),
        "actions": " | ".join(actions),
    })

    print(report)


if __name__ == "__main__":
    main()
