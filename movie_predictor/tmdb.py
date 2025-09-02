from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

from .config import get_settings


class TMDbClient:
    """Lightweight TMDb v3 API client using an API key.

    Docs: https://developer.themoviedb.org/reference/intro/getting-started
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, language: Optional[str] = None, region: Optional[str] = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.tmdb_api_key or os.getenv("TMDB_API_KEY")
        self.base_url = (base_url or settings.tmdb_base_url).rstrip("/")
        self.language = language or settings.language
        self.region = region or settings.region
        if not self.api_key:
            raise RuntimeError("TMDB_API_KEY is not set. Provide it via environment or .env file.")
        self._session = requests.Session()
        self._session.params = {"api_key": self.api_key}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None, retries: int = 2) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        merged = {"language": self.language}
        if params:
            merged.update(params)
        for attempt in range(retries + 1):
            resp = self._session.get(url, params=merged, timeout=20)
            if resp.status_code == 429 and attempt < retries:
                # rate limited
                retry_after = int(resp.headers.get("Retry-After", "1"))
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp.json()
        # Should never reach here due to raise_for_status
        return {}

    def now_playing(self, page: int = 1, region: Optional[str] = None) -> Dict[str, Any]:
        region = region or self.region
        return self._get("movie/now_playing", {"page": page, "region": region})

    def iterate_now_playing(self, region: Optional[str] = None, max_pages: int = 5) -> List[Dict[str, Any]]:
        movies: List[Dict[str, Any]] = []
        first = self.now_playing(page=1, region=region)
        total_pages = min(first.get("total_pages", 1), max_pages)
        movies.extend(first.get("results", []))
        for p in range(2, total_pages + 1):
            data = self.now_playing(page=p, region=region)
            movies.extend(data.get("results", []))
        return movies

    def movie_details(self, movie_id: int, append: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if append:
            params["append_to_response"] = append
        return self._get(f"movie/{movie_id}", params)

    def movie_release_dates(self, movie_id: int) -> Dict[str, Any]:
        return self._get(f"movie/{movie_id}/release_dates")

    def search_movie(self, query: str, year: Optional[int] = None, page: int = 1, include_adult: bool = False) -> Dict[str, Any]:
        params: Dict[str, Any] = {"query": query, "page": page, "include_adult": include_adult}
        if year:
            params["year"] = year
        return self._get("search/movie", params)
