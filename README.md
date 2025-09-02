# MovieTheaterLengthPredictor

Predict and browse how long movies will likely stay in US theaters.

Features:
- Fetches "Now Playing" movies in the US from TMDb.
- Heuristic predictions for theatrical run end date (days remaining, confidence, rationale).
- Simple GUI and a minimal CLI.

## Setup

1) Create a TMDb API key (free) at https://www.themoviedb.org/ and verify your account.
2) In this folder, install dependencies:

```pwsh
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

3) Provide your API key via environment or a `.env` file:

```
TMDB_API_KEY=your_key_here
```

## Run the GUI

```pwsh
python -m movie_predictor.gui_app
```

Enter your API key (if not in `.env`) and click "Fetch Now Playing".

## CLI examples

```pwsh
python -m movie_predictor.cli now-playing --pages 3 --api-key $env:TMDB_API_KEY
```

## Notes & Limitations

- Predictions are heuristic only and may be inaccurate; consider them rough guidance.
- If a public end date is available via distributors or exhibitors, prefer that source.
- Region defaults to `US`; you can adapt `movie_predictor/config.py` if needed.

## Next steps

- Add a historical mode to search any movie and estimate original theatrical run length.
- Incorporate weekend box office data to improve signals.


##Plans
- Need to fix the poster styles on the main screen
- Fix the scrolling
- Fix the logic for end date
- Fix the logic for the predictor
- Fix the gui make it pretty
- Literally fix everything ig damn