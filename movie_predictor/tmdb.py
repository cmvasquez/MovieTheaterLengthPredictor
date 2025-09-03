from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

from .config import get_settings
from datetime import date, datetime


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

    def get_run_start_date(self, movie_id: int, region: Optional[str] = None, today: Optional[date] = None) -> Optional[date]:
        """Pick the start date for the current theatrical run.

        Heuristic: choose the most recent Theatrical (type 3) or Theatrical (limited) (type 2)
        release date in the given region that is not in the future. If none found in region,
        fall back to any region. Returns a date or None.
        """
        data = self.movie_release_dates(movie_id)
        region = (region or self.region) or "US"
        today = today or date.today()

        def parse_tmdb_dt(s: str) -> Optional[date]:
            # Examples: 2022-09-02T00:00:00.000Z
            if not s:
                return None
            try:
                # Trim Z if present
                if s.endswith("Z"):
                    s2 = s[:-1]
                    try:
                        dt = datetime.strptime(s2, "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        dt = datetime.strptime(s2, "%Y-%m-%dT%H:%M:%S")
                else:
                    try:
                        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
                    except ValueError:
                        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
                return dt.date()
            except Exception:
                try:
                    return datetime.strptime(s[:10], "%Y-%m-%d").date()
                except Exception:
                    return None

        def pick(results_list: List[Dict[str, Any]]) -> Optional[date]:
            theatrical_types = {2, 3}
            candidates: List[date] = []
            for entry in results_list or []:
                rds = entry.get("release_dates") or []
                for rd in rds:
                    t = rd.get("type")
                    if t not in theatrical_types:
                        continue
                    d = parse_tmdb_dt(rd.get("release_date"))
                    if not d or d > today:
                        continue
                    candidates.append(d)
            if not candidates:
                return None
            return sorted(candidates, reverse=True)[0]

        results = data.get("results") or []
        # Try region first
        region_block = next((x for x in results if (x.get("iso_3166_1") or "").upper() == region.upper()), None)
        if region_block:
            dt = pick([region_block])
            if dt:
                return dt
        # Fallback any region
        return pick(results)
