# MovieTheaterLengthPredictor v0.0.2

What's new:
- Added Help > About dialog with author, version, and a link to the GitHub repo.
- Improved release date logic to show the start date of the current theatrical run (handles re-releases).
- Do not show a past predicted end date for movies still in theaters; display "TBD" instead and "?" for days left.
- Menu-based poster zoom (Poster zoom + / -). Slider removed for reliability.
- Dark Mode toggle (Edit menu) with better Treeview styling.

Notes:
- Predictions remain heuristic; use as rough guidance only.

Requirements:
- Windows 11 (x64)
- Internet connection
- TMDb API key (free): create at https://www.themoviedb.org/

How to run the EXE:
1) Download the v0.0.2 ZIP and extract it.
2) In the extracted folder, create a file named `.env` with your key:

   TMDB_API_KEY=your_key_here

3) Run `MovieTheaterLengthPredictor.exe`.
