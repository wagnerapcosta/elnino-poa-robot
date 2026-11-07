"""Check for a successful real consultation in the current UTC hour."""

import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def covering_run(get, hour_prefix):
    hour_start = hour_prefix + "00:00Z"
    runs = get("workflows/rain-alert.yml/runs?branch=main&status=success&per_page=20")
    for run in runs["workflow_runs"]:
        if run["updated_at"] < hour_start:
            continue
        run_id = run["id"]
        jobs = get(f"runs/{run_id}/jobs")["jobs"]
        for job in jobs:
            for step in job["steps"]:
                if (
                    step["name"] == "Consultar previsao e avaliar alertas"
                    and step["conclusion"] == "success"
                    and step["started_at"].startswith(hour_prefix)
                ):
                    return run_id
    return None


def get_actions_json(path):
    api = os.environ["GITHUB_API_URL"]
    repo = os.environ["GITHUB_REPOSITORY"]
    request = Request(
        f"{api}/repos/{repo}/actions/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        },
    )
    with urlopen(request, timeout=8) as response:
        return json.load(response)


def main():
    hour_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:")
    run_id = covering_run(get_actions_json, hour_prefix)
    if run_id is None:
        print(f"Hora UTC {hour_prefix}00 ainda sem consulta concluída. Executando.")
        return

    print(f"Hora UTC {hour_prefix}00 já consultada com sucesso na execução {run_id}.")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("covered=true\n")


if __name__ == "__main__":
    main()
