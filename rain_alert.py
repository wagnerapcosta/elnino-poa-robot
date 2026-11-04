from datetime import datetime, timedelta
from decimal import Decimal
from math import isfinite
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
THRESHOLD_MM = 20


def rain_alert(payload, now=None):
    """12 hourly bins ending after the current hour, including its full forecast.

    Open-Meteo precipitation timestamps mark the END of the preceding hour.
    The displayed window is aligned down to the hour; no subhour precision is claimed.
    """
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError("now precisa de fuso horário")
    start = now.astimezone(TZ).replace(minute=0, second=0, microsecond=0)
    result = dict(status="unavailable", triggered=None, total_mm=None,
                  threshold_mm=THRESHOLD_MM, start=start.isoformat(),
                  end=(start + timedelta(hours=12)).isoformat(), error=None)
    try:
        if not isinstance(payload, dict):
            raise ValueError("Resposta da previsão inválida")
        if payload.get("timezone") != "America/Sao_Paulo":
            raise ValueError("Fuso da previsão inválido")
        if payload.get("hourly_units", {}).get("precipitation") != "mm":
            raise ValueError("Unidade de precipitação inválida")
        # API returns the model grid cell, not the airport's exact coordinates.
        lat, lon = float(payload["latitude"]), float(payload["longitude"])
        if not isfinite(lat) or not isfinite(lon) or abs(lat + 29.9939) > .3 or abs(lon + 51.1711) > .3:
            raise ValueError("Coordenadas fora da região de SBPA")
        hourly = payload.get("hourly") or {}
        times, values = hourly.get("time", []), hourly.get("precipitation", [])
        if not times or len(times) != len(values):
            raise ValueError("Série horária ausente ou inconsistente")
        series = {}
        previous = None
        for stamp, value in zip(times, values):
            dt = datetime.fromisoformat(stamp)
            dt = dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
            if dt.minute or dt.second or dt.microsecond or (previous and dt <= previous):
                raise ValueError("Horários duplicados, fora de ordem ou não horários")
            series[dt] = value
            previous = dt
        selected = [series.get(start + timedelta(hours=i)) for i in range(1, 13)]
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v) or v < 0 for v in selected):
            raise ValueError("Janela de 12h incompleta, vencida ou com valores inválidos")
        total = sum(Decimal(str(v)) for v in selected)
        result.update(status="ok", triggered=total >= Decimal(str(THRESHOLD_MM)), total_mm=float(total))
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        result["error"] = str(exc)
    return result


def alert_text(alert):
    if alert["status"] != "ok":
        return "Chuva 12h: INDISPONÍVEL — " + str(alert.get("error"))
    state = "ALERTA" if alert["triggered"] else "SEM GATILHO"
    start = datetime.fromisoformat(alert["start"]).strftime("%d/%m %H:%M")
    end = datetime.fromisoformat(alert["end"]).strftime("%d/%m %H:%M")
    return (f"Chuva 12h: {state} — {alert['total_mm']:.2f} mm; "
            f"{start} a {end} BRT (janela horária; inclui hora em curso). Limiar: >=20 mm.")
