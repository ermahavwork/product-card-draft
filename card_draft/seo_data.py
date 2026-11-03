"""Необязательные данные Яндекса: частотность из Вордстата и поисковые фразы страницы из Метрики."""

import os

import httpx

WORDSTAT_URL = "https://searchapi.api.cloud.yandex.net/v2/wordstat/topRequests"
METRIKA_URL = "https://api-metrika.yandex.net/stat/v1/data"
TIMEOUT_SECONDS = 20
RUSSIA_REGION = "225"


def add_seo_data(result: dict, product, env=os.environ, transport=None) -> dict:
    warnings = list(result["warnings"])
    with httpx.Client(transport=transport, timeout=TIMEOUT_SECONDS) as http:
        stats = _query_stats(result["search_queries"], env, http, warnings)
        phrases = _metrika_phrases(product, env, http, warnings)
    return result | {"query_stats": stats, "metrika_phrases": phrases, "warnings": warnings}


def _query_stats(queries: list[str], env, http: httpx.Client, warnings: list[str]) -> list[dict]:
    stats = [{"query": query, "frequency": None} for query in queries]
    key, folder = env.get("YANDEX_SEARCH_API_KEY"), env.get("YANDEX_FOLDER_ID")
    if not key or not folder:
        return stats
    try:
        for item in stats:
            response = http.post(
                WORDSTAT_URL,
                headers={"Authorization": f"Api-Key {key}"},
                json={"phrase": item["query"], "numPhrases": 1, "regions": [RUSSIA_REGION], "folderId": folder},
            )
            response.raise_for_status()
            item["frequency"] = int(response.json().get("totalCount", 0))
            if item["frequency"] == 0:
                warnings.append(f"Запрос «{item['query']}»: в Вордстате нет показов, замените его.")
    except (httpx.HTTPError, ValueError, TypeError):
        warnings.append("Вордстат недоступен: частотность проверена не полностью.")
    return stats


def _metrika_phrases(product, env, http: httpx.Client, warnings: list[str]) -> list[dict]:
    token, counter = env.get("YANDEX_METRIKA_TOKEN"), env.get("YANDEX_METRIKA_COUNTER")
    if not token or not counter:
        return []
    if not product.url:
        warnings.append("Метрика подключена, но во входе нет поля url: фразы страницы не получены.")
        return []
    try:
        response = http.get(
            METRIKA_URL,
            headers={"Authorization": f"OAuth {token}"},
            params={
                "ids": counter,
                "metrics": "ym:s:visits",
                "dimensions": "ym:s:lastSearchPhrase",
                "filters": f"ym:s:startURL=='{product.url}'",
                "date1": "30daysAgo",
                "limit": 20,
            },
        )
        response.raise_for_status()
        return [
            {"phrase": row["dimensions"][0]["name"], "visits": int(row["metrics"][0])}
            for row in response.json()["data"]
            if row["dimensions"][0].get("name")
        ]
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        warnings.append("Метрика недоступна: поисковые фразы страницы не получены.")
        return []
