from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    tmdb_api_key: Optional[str]
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    region: str = "US"
    language: str = "en-US"


def get_settings() -> Settings:
    return Settings(
        tmdb_api_key=os.getenv("TMDB_API_KEY"),
    )
