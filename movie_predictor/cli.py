from __future__ import annotations

import argparse
import os
from datetime import date

from .tmdb import TMDbClient
from .predictor import predict_run_length_days


def cmd_now_playing(args):
    client = TMDbClient(api_key=args.api_key)
    movies = client.iterate_now_playing(max_pages=args.pages)
    movies.sort(key=lambda m: m.get("popularity", 0.0), reverse=True)
    print(f"Title | Release | Popularity | Rating | Predicted End | Days Left | Confidence")
    print("-" * 100)
    for m in movies:
        p = predict_run_length_days(m)
        title = m.get("title") or m.get("name") or "(untitled)"
        rel = m.get("release_date") or "?"
        pop = f"{float(m.get('popularity') or 0):.1f}"
        rate = f"{float(m.get('vote_average') or 0):.1f} ({int(m.get('vote_count') or 0)})"
        end = p.predicted_end_date.isoformat() if p.predicted_end_date else "N/A"
        left = str(p.days_remaining) if p.days_remaining is not None else "?"
        conf = f"{p.confidence*100:.0f}%"
        print(f"{title} | {rel} | {pop} | {rate} | {end} | {left} | {conf}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Movie Theater Length Predictor")
    parser.add_argument("--api-key", dest="api_key", default=os.getenv("TMDB_API_KEY"), help="TMDb API Key (or set TMDB_API_KEY)")
    sub = parser.add_subparsers(dest="command")

    p1 = sub.add_parser("now-playing", help="List now playing movies with predictions")
    p1.add_argument("--pages", type=int, default=3, help="How many pages to fetch (max 5)")
    p1.set_defaults(func=cmd_now_playing)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    if not args.api_key:
        print("TMDB_API_KEY missing. Pass --api-key or set env.")
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
