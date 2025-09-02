# MovieTheaterLengthPredictor v0.0.1

Initial preview release.

- GUI to list US "Now Playing" movies from TMDb.
- Heuristic prediction of theatrical run end dates (days remaining + confidence).
- Poster thumbnails in list; larger poster in details.
- Filter by title; double-click for details and TMDb link.
- Scrollable details window with auto-sizing.

Requirements:
- Windows 11 (x64)
- Internet connection
- TMDb API key (free): create at https://www.themoviedb.org/

How to run the EXE:
1) Download the ZIP attached to this release and extract it.
2) In the extracted folder, create a file named `.env` with your key:

   TMDB_API_KEY=your_key_here

3) Run `MovieTheaterLengthPredictor.exe`.
