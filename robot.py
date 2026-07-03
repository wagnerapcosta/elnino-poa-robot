import os
import re
import requests
import pandas as pd
import matplotlib.pyplot as plt

from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path


# ============================================================
# VERSÃO
# ============================================================

ROBOT_VERSION = "1.2"


# ============================================================
# CONFIGURAÇÃO PRINCIPAL
# ============================================================

AIRPORT = {
    "icao": "SBPA",
    "name": "Porto Alegre Airport",
    "lat": -29.9939,
    "lon": -51.1711,
    "timezone": "America/Sao_Paulo",
}

# layer:
# - tactical: pode elevar risco diário se houver gatilho regionalizado
# - strategic: entra como contexto ENOS/climático, mas não eleva readiness diário sozinho
SOURCES = [
    {
        "name": "NOAA CPC ENSO Diagnostic Discussion",
        "url": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml",
        "layer": "strategic",
        "regional_scope": False,
    },
    {
        "name": "IRI Columbia ENSO Forecast",
        "url": "https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/",
        "layer": "strategic",
        "regional_scope": False,
    },
    {
        "name": "INMET Portal",
        "url": "https://portal.inmet.gov.br/",
        "layer": "strategic",
        "regional_scope": False,
    },
    {
        "name": "INPE Gov",
        "url": "https://www.gov.br/inpe/pt-br",
        "layer": "strategic",
        "regional_scope": False,
    },
    {
        "name": "CEMADEN Gov",
        "url": "https://www.gov.br/cemaden/pt-br",
        "layer": "strategic",
        "regional_scope": False,
    },
    {
        "name": "Defesa Civil RS",
        "url": "https://www.defesacivil.rs.gov.br/avisos-e-alertas",
        "layer": "tactical",
        "regional_scope": True,
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
}

TACTICAL_KEYWORDS = {
    "yellow": [
        "chuva intensa",
        "tempestade",
        "raios",
        "descargas elétricas",
        "rajadas",
        "instabilidade",
        "perigo potencial",
        "risco de alagamento",
    ],
    "orange": [
        "vendaval",
        "granizo",
        "temporal severo",
        "alerta laranja",
        "alagamento",
    ],
    "red": [
        "grande perigo",
        "alerta vermelho",
        "inundação severa",
        "evento extremo",
        "emergência",
        "evacuação",
        "bloqueio",
    ],
}

STRATEGIC_KEYWORDS = {
    "yellow": [
        "el niño",
        "enos",
        "anomalia positiva",
        "aquecimento do pacífico",
    ],
    "orange": [
        "el niño forte",
        "el niño muito forte",
        "intensificação",
        "persistência do el niño",
        "probabilidade elevada",
        "risco hidrometeorológico",
    ],
    "red": [
        "el niño extremo",
        "impactos severos",
        "risco hidrometeorológico elevado",
        "evento extremo",
    ],
}

REGIONAL_TERMS = [
    "porto alegre",
    "região metropolitana",
    "regiao metropolitana",
    "rio grande do sul",
    "rs",
    "guaíba",
    "guaiba",
    "lago guaíba",
    "lago guaiba",
    "bacia do guaíba",
    "bacia do guaiba",
    "delta do jacuí",
    "delta do jacui",
    "sinos",
    "caí",
    "cai",
    "gravataí",
    "gravatai",
    "taquari",
]

HEADERS = {
    "User-Agent": f"POA-ElNino-SMS-Radar/{ROBOT_VERSION}"
}


# ============================================================
# UTILITÁRIOS
# ============================================================

def now_brt():
    return datetime.now(ZoneInfo("America/Sao_Paulo"))


def ensure_dirs():
    Path("data").mkdir(parents=True, exist_ok=True)
    Path("reports").mkdir(parents=True, exist_ok=True)


def level_order(level: str) -> int:
    return {
        "verde": 0,
        "amarelo": 1,
        "laranja": 2,
        "vermelho": 3,
    }.get(level, 0)


def highest_level(levels: list[str]) -> str:
    if not levels:
        return "verde"
    return max(levels, key=level_order)


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return " ".join(soup.get_text(" ").split())


def has_regional_relevance(text: str, source: dict) -> bool:
    if source.get("regional_scope"):
        return True

    text_lower = normalize_text(text)
    return any(term in text_lower for term in REGIONAL_TERMS)


# ============================================================
# COLETA
# ============================================================

def collect_html_source(source: dict) -> dict:
    try:
        response = requests.get(source["url"], headers=HEADERS, timeout=30)
        response.raise_for_status()
        text = clean_html(response.text)

        return {
            "source": source["name"],
            "url": source["url"],
            "layer": source["layer"],
            "regional_scope": source.get("regional_scope", False),
            "status": "ok",
            "text": text[:20000],
            "error": None,
            "collected_at": now_brt().isoformat(),
        }

    except Exception as exc:
        return {
            "source": source["name"],
            "url": source["url"],
            "layer": source["layer"],
            "regional_scope": source.get("regional_scope", False),
            "status": "error",
            "text": "",
            "error": str(exc),
            "collected_at": now_brt().isoformat(),
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
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        return {
            "source": "Open-Meteo POA Forecast",
            "url": url,
            "status": "ok",
            "json": response.json(),
            "error": None,
            "collected_at": now_brt().isoformat(),
        }

    except Exception as exc:
        return {
            "source": "Open-Meteo POA Forecast",
            "url": url,
            "status": "error",
            "json": {},
            "error": str(exc),
            "collected_at": now_brt().isoformat(),
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
        "collected_at": now_brt().isoformat(),
    }

    try:
        metar_response = requests.get(metar_url, headers=HEADERS, timeout=30)
        metar_response.raise_for_status()
        result["metar"] = metar_response.json()
    except Exception as exc:
        result["status"] = "partial_error"
        result["errors"].append(f"METAR: {exc}")

    try:
        taf_response = requests.get(taf_url, headers=HEADERS, timeout=30)
        taf_response.raise_for_status()
        result["taf"] = taf_response.json()
    except Exception as exc:
        result["status"] = "partial_error"
        result["errors"].append(f"TAF: {exc}")

    return result


# ============================================================
# ANÁLISE
# ============================================================

def classify_keywords(text: str, source: dict) -> dict:
    layer = source.get("layer", "strategic")
    text_lower = normalize_text(text)

    keyword_set = TACTICAL_KEYWORDS if layer == "tactical" else STRATEGIC_KEYWORDS

    hits = {
        "yellow": [],
        "orange": [],
        "red": [],
    }

    for level in hits:
        for word in keyword_set[level]:
            if word.lower() in text_lower:
                hits[level].append(word)

    regional_relevance = has_regional_relevance(text, source)

    if hits["red"]:
        level = "vermelho"
    elif hits["orange"]:
        level = "laranja"
    elif hits["yellow"]:
        level = "amarelo"
    else:
        level = "verde"

    # Proteção contra falso positivo:
    # fonte tática só pode elevar risco se for regionalmente relevante.
    if layer == "tactical" and not regional_relevance:
        level = "verde"

    return {
        "level": level,
        "hits": hits,
        "regional_relevance": regional_relevance,
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
        "precipitation": precipitation,
        "gusts": gusts,
        "p24_max_mm": p24_max,
        "p72_max_mm": p72_max,
        "gust_max_kmh": gust_max,
        "reasons": reasons,
    }


def determine_collection_reliability(web_results: list, open_meteo: dict, aviation: dict) -> dict:
    failed_sources = [
        item.get("source")
        for item in web_results
        if item.get("status") != "ok"
    ]

    critical_failures = []

    if open_meteo.get("status") != "ok":
        critical_failures.append("Open-Meteo Forecast")

    if aviation.get("status") not in ["ok", "partial_error"]:
        critical_failures.append("AviationWeather")

    if critical_failures:
        reliability = "insuficiente"
    elif failed_sources:
        reliability = "parcial"
    else:
        reliability = "confiavel"

    return {
        "reliability": reliability,
        "failed_sources": failed_sources,
        "critical_failures": critical_failures,
    }


def build_tactical_drivers(forecast: dict, web_results: list) -> list[str]:
    drivers = []

    for reason in forecast.get("reasons", []):
        drivers.append(f"Previsão quantitativa: {reason}")

    for item in web_results:
        if item.get("layer") != "tactical":
            continue
        if item.get("status") != "ok":
            continue

        analysis = item.get("analysis", {})
        level = analysis.get("level", "verde")

        if level == "verde":
            continue

        hits = analysis.get("hits", {})
        hit_words = []
        for words in hits.values():
            hit_words.extend(words)

        drivers.append(
            f"{item.get('source')}: gatilho textual {level} "
            f"({', '.join(hit_words[:5])})"
        )

    if not drivers:
        drivers.append("Sem gatilho tático relevante identificado.")

    return drivers


def build_strategic_drivers(web_results: list) -> list[str]:
    drivers = []

    for item in web_results:
        if item.get("layer") != "strategic":
            continue
        if item.get("status") != "ok":
            continue

        analysis = item.get("analysis", {})
        level = analysis.get("level", "verde")

        if level == "verde":
            continue

        hits = analysis.get("hits", {})
        hit_words = []
        for words in hits.values():
            hit_words.extend(words)

        drivers.append(
            f"{item.get('source')}: contexto {level} "
            f"({', '.join(hit_words[:5])})"
        )

    if not drivers:
        drivers.append("Sem gatilho estratégico relevante identificado.")

    return drivers


def actions_by_level(level: str, reliability: str, tactical_drivers: list[str]) -> list[str]:
    no_tactical_trigger = tactical_drivers == ["Sem gatilho tático relevante identificado."]

    if reliability == "insuficiente":
        return [
            "Validar manualmente fontes oficiais antes de qualquer conclusão operacional.",
            "Não assumir ausência de risco enquanto a coleta crítica estiver insuficiente.",
            "Reexecutar o workflow ou consultar fontes oficiais diretamente.",
        ]

    if no_tactical_trigger:
        return [
            "Manter monitoramento. Sem readiness requerido neste momento.",
            "Registrar lacunas de coleta, se houver.",
            "Aguardar próxima atualização automática ou boletim contratado.",
        ]

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


def decision_required(level: str, reliability: str, tactical_drivers: list[str]) -> str:
    if reliability == "insuficiente":
        return "Sim. Validar fontes manualmente antes de concluir risco."

    if tactical_drivers == ["Sem gatilho tático relevante identificado."]:
        return "Não. Sem readiness requerido neste momento."

    if level == "vermelho":
        return "Sim. Escalonamento imediato."

    if level == "laranja":
        return "Sim. Readiness preventivo no mesmo dia."

    if level == "amarelo":
        return "Não imediata. Monitoramento reforçado."

    return "Não. Monitoramento normal."


# ============================================================
# RELATÓRIO
# ============================================================

def format_hits(hits: dict) -> str:
    parts = []

    for level_name, words in hits.items():
        if words:
            parts.append(f"{level_name}: {', '.join(words[:8])}")

    return " | ".join(parts) if parts else "Sem gatilho textual relevante"


def build_mobile_summary(
    tactical_level: str,
    strategic_level: str,
    forecast: dict,
    reliability_info: dict,
    aviation: dict,
    actions: list,
    tactical_drivers: list[str],
) -> str:
    failed_sources = reliability_info.get("failed_sources", [])
    reliability = reliability_info.get("reliability", "indefinida")

    main_driver = tactical_drivers[0] if tactical_drivers else "Sem gatilho tático relevante identificado."

    lines = []
    lines.append(f"Radar El Nino POA - {tactical_level.upper()}")
    lines.append("")
    lines.append(f"Risco tatico: {tactical_level.upper()}")
    lines.append(f"Contexto ENOS: {strategic_level.upper()}")
    lines.append(f"Confiabilidade: {reliability.upper()}")
    lines.append("")
    lines.append(f"Chuva 24h: {forecast.get('p24_max_mm', 0):.1f} mm")
    lines.append(f"Chuva 72h: {forecast.get('p72_max_mm', 0):.1f} mm")
    lines.append(f"Rajada max.: {forecast.get('gust_max_kmh', 0):.1f} km/h")
    lines.append(f"METAR/TAF: {aviation.get('status')}")
    lines.append("")
    lines.append(f"Motivo: {main_driver}")

    if failed_sources:
        lines.append(f"Fontes com erro: {', '.join(failed_sources)}")
    else:
        lines.append("Fontes web: ok")

    lines.append("")
    lines.append(f"Acao principal: {actions[0]}")

    return "\n".join(lines)


def build_full_report(
    mode: str,
    tactical_level: str,
    strategic_level: str,
    forecast: dict,
    web_results: list,
    aviation: dict,
    reliability_info: dict,
    actions: list,
    tactical_drivers: list[str],
    strategic_drivers: list[str],
    chart_path: str,
) -> str:
    date_label = now_brt().strftime("%d/%m/%Y %H:%M")

    lines = []
    lines.append(f"# Radar El Nino POA - {mode.upper()}")
    lines.append("")
    lines.append(f"**Versão:** {ROBOT_VERSION}")
    lines.append(f"**Data/hora:** {date_label}")
    lines.append(f"**Aeroporto:** {AIRPORT['name']} / {AIRPORT['icao']}")
    lines.append(f"**Risco tático:** {tactical_level.upper()}")
    lines.append(f"**Contexto estratégico ENOS:** {strategic_level.upper()}")
    lines.append(f"**Confiabilidade da coleta:** {reliability_info.get('reliability', 'indefinida').upper()}")
    lines.append(f"**Decisão requerida:** {decision_required(tactical_level, reliability_info.get('reliability', 'indefinida'), tactical_drivers)}")
    lines.append("")

    lines.append("## 1. Síntese operacional")
    lines.append("")
    lines.append(
        "Monitoramento automático de sinais climáticos, meteorológicos e operacionais "
        "com foco em potenciais impactos ao Porto Alegre Airport: chuva acumulada, temporais, vento, raios, "
        "drenagem, energia, acessos, pista, pátio, terminal, APOC, SCI, FOD e continuidade operacional."
    )
    lines.append("")

    lines.append("## 2. Previsão quantitativa POA - próximos 7 dias")
    lines.append("")
    lines.append(f"- Máxima chuva em 24h: **{forecast.get('p24_max_mm', 0):.1f} mm**")
    lines.append(f"- Máxima chuva acumulada em 72h: **{forecast.get('p72_max_mm', 0):.1f} mm**")
    lines.append(f"- Máxima rajada prevista: **{forecast.get('gust_max_kmh', 0):.1f} km/h**")
    lines.append("")

    lines.append("## 3. Gatilhos táticos")
    lines.append("")
    for driver in tactical_drivers:
        lines.append(f"- {driver}")
    lines.append("")

    lines.append("## 4. Contexto estratégico ENOS")
    lines.append("")
    for driver in strategic_drivers:
        lines.append(f"- {driver}")
    lines.append("")

    lines.append("## 5. Gráfico")
    lines.append("")
    lines.append(f"Arquivo gerado no artifact: `{chart_path}`")
    lines.append("")

    lines.append("## 6. Fontes web monitoradas")
    lines.append("")
    lines.append("| Fonte | Camada | Regional | Coleta | Nível | Achados |")
    lines.append("|---|---|---|---|---|---|")

    for item in web_results:
        analysis = item.get("analysis", {})
        lines.append(
            f"| {item.get('source')} | {item.get('layer')} | "
            f"{analysis.get('regional_relevance', False)} | {item.get('status')} | "
            f"{analysis.get('level', 'n/a')} | {format_hits(analysis.get('hits', {}))} |"
        )

    lines.append("")

    lines.append("## 7. Lacunas de coleta")
    lines.append("")

    failed_sources = reliability_info.get("failed_sources", [])
    critical_failures = reliability_info.get("critical_failures", [])

    if failed_sources or critical_failures:
        if failed_sources:
            lines.append(f"- Fontes web com erro: {', '.join(failed_sources)}")
        if critical_failures:
            lines.append(f"- Fontes críticas com erro: {', '.join(critical_failures)}")
    else:
        lines.append("- Sem lacunas relevantes de coleta nesta execução.")

    lines.append("")

    lines.append("## 8. Meteorologia aeronáutica SBPA")
    lines.append("")
    lines.append(f"- AviationWeather status: **{aviation.get('status')}**")
    lines.append(f"- METAR URL: {aviation.get('metar_url')}")
    lines.append(f"- TAF URL: {aviation.get('taf_url')}")

    if aviation.get("errors"):
        for error in aviation["errors"]:
            lines.append(f"- Erro: {error}")

    lines.append("")

    lines.append("## 9. Ações recomendadas")
    lines.append("")
    for action in actions:
        lines.append(f"- {action}")

    lines.append("")
    lines.append("## 10. Observação SMS")
    lines.append("")
    lines.append(
        "Este radar é uma camada de Safety Intelligence. Não substitui boletim meteorológico contratado, "
        "avaliação operacional local, decisão formal, validação regulatória, validação jurídica ou plano de contingência. "
        "Em caso de divergência entre fontes, prevalecerá a avaliação técnica especializada e a decisão operacional formal."
    )
    lines.append("")

    return "\n".join(lines)


# ============================================================
# GRÁFICO
# ============================================================

def create_forecast_chart(forecast: dict, mode: str) -> str:
    report_dir = Path("reports") / mode
    report_dir.mkdir(parents=True, exist_ok=True)

    dates = forecast.get("dates", [])
    precipitation = forecast.get("precipitation", [])
    gusts = forecast.get("gusts", [])

    if not dates or not precipitation:
        return "grafico_nao_gerado_sem_dados"

    labels = [d[5:] for d in dates]

    filename = now_brt().strftime("forecast_chart_%Y%m%d_%H%M.png")
    path = report_dir / filename

    plt.figure(figsize=(10, 5))
    plt.plot(labels, precipitation, marker="o", label="Chuva diária prevista (mm)")

    if gusts:
        plt.plot(labels, gusts, marker="o", label="Rajada máxima prevista (km/h)")

    plt.axhline(30, linestyle="--", linewidth=1, label="Chuva 24h amarelo: 30 mm")
    plt.axhline(50, linestyle="--", linewidth=1, label="Chuva 24h laranja: 50 mm")
    plt.axhline(80, linestyle="--", linewidth=1, label="Chuva 24h vermelho: 80 mm")

    plt.title("Radar El Nino POA - Previsão 7 dias")
    plt.xlabel("Data")
    plt.ylabel("Valor")
    plt.legend()
    plt.grid(True, linewidth=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()

    return str(path)


# ============================================================
# NOTIFICAÇÃO
# ============================================================

def notify_ntfy(title: str, message: str, tactical_level: str):
    topic = os.getenv("NTFY_TOPIC")

    if not topic:
        print("NTFY_TOPIC não configurado. Pulando notificação ntfy.")
        return

    url = f"https://ntfy.sh/{topic}"

    priority = "default"
    tags = "information_source"

    if tactical_level == "amarelo":
        priority = "default"
        tags = "warning"
    elif tactical_level == "laranja":
        priority = "high"
        tags = "rotating_light"
    elif tactical_level == "vermelho":
        priority = "urgent"
        tags = "rotating_light,warning"

    headers = {
        "Title": title,
        "Priority": priority,
        "Tags": tags,
    }

    response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=30)
    response.raise_for_status()


# ============================================================
# HISTÓRICO E ARQUIVOS
# ============================================================

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


def save_report(report: str, mode: str) -> str:
    report_dir = Path("reports") / mode
    report_dir.mkdir(parents=True, exist_ok=True)

    filename = now_brt().strftime("radar_elnino_poa_%Y%m%d_%H%M.md")
    path = report_dir / filename
    path.write_text(report, encoding="utf-8")

    return str(path)


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_dirs()

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
        result["analysis"] = classify_keywords(result.get("text", ""), result)
        web_results.append(result)

    reliability_info = determine_collection_reliability(web_results, open_meteo, aviation)

    tactical_levels = [forecast_analysis["level"]]
    tactical_levels += [
        item["analysis"]["level"]
        for item in web_results
        if item.get("layer") == "tactical" and item.get("status") == "ok"
    ]

    strategic_levels = [
        item["analysis"]["level"]
        for item in web_results
        if item.get("layer") == "strategic" and item.get("status") == "ok"
    ]

    tactical_level = highest_level(tactical_levels)
    strategic_level = highest_level(strategic_levels)

    if reliability_info.get("reliability") == "insuficiente" and level_order(tactical_level) < level_order("amarelo"):
        tactical_level = "amarelo"

    tactical_drivers = build_tactical_drivers(forecast_analysis, web_results)
    strategic_drivers = build_strategic_drivers(web_results)

    actions = actions_by_level(
        tactical_level,
        reliability_info.get("reliability", "indefinida"),
        tactical_drivers,
    )

    chart_path = create_forecast_chart(forecast_analysis, mode)

    full_report = build_full_report(
        mode=mode,
        tactical_level=tactical_level,
        strategic_level=strategic_level,
        forecast=forecast_analysis,
        web_results=web_results,
        aviation=aviation,
        reliability_info=reliability_info,
        actions=actions,
        tactical_drivers=tactical_drivers,
        strategic_drivers=strategic_drivers,
        chart_path=chart_path,
    )

    report_path = save_report(full_report, mode)

    mobile_summary = build_mobile_summary(
        tactical_level=tactical_level,
        strategic_level=strategic_level,
        forecast=forecast_analysis,
        reliability_info=reliability_info,
        aviation=aviation,
        actions=actions,
        tactical_drivers=tactical_drivers,
    )

    title = f"Radar El Nino POA - {tactical_level.upper()}"
    notify_ntfy(title, mobile_summary, tactical_level)

    save_history({
        "timestamp": now_brt().isoformat(),
        "version": ROBOT_VERSION,
        "mode": mode,
        "tactical_level": tactical_level,
        "strategic_level": strategic_level,
        "collection_reliability": reliability_info.get("reliability"),
        "failed_sources": " | ".join(reliability_info.get("failed_sources", [])),
        "critical_failures": " | ".join(reliability_info.get("critical_failures", [])),
        "tactical_drivers": " | ".join(tactical_drivers),
        "strategic_drivers": " | ".join(strategic_drivers),
        "p24_max_mm": forecast_analysis.get("p24_max_mm"),
        "p72_max_mm": forecast_analysis.get("p72_max_mm"),
        "gust_max_kmh": forecast_analysis.get("gust_max_kmh"),
        "report_path": report_path,
        "chart_path": chart_path,
        "main_action": actions[0] if actions else "",
    })

    print(full_report)
    print(f"\nRelatório salvo em: {report_path}")
    print(f"Gráfico salvo em: {chart_path}")


if __name__ == "__main__":
    main()
