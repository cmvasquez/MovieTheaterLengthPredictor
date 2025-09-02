from __future__ import annotations

import threading
import webbrowser
from io import BytesIO
from datetime import date
from tkinter import BOTH, END, HORIZONTAL, LEFT, RIGHT, StringVar, Tk, Toplevel, VERTICAL, Canvas, ttk, messagebox

import requests
from PIL import Image, ImageTk

from .config import get_settings
from .predictor import Prediction, predict_run_length_days
from .tmdb import TMDbClient


class App(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Movie Theater Run Predictor (US)")
        self.geometry("1120x640")

        settings = get_settings()
        self.api_key_var = StringVar(value=settings.tmdb_api_key or "")
        self.search_var = StringVar(value="")

        # Top controls
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(top, text="TMDb API Key:").pack(side=LEFT)
        self.api_entry = ttk.Entry(top, textvariable=self.api_key_var, width=45)
        self.api_entry.pack(side=LEFT, padx=4)
        ttk.Button(top, text="Fetch Now Playing", command=self.fetch_now_playing).pack(side=LEFT, padx=4)

        ttk.Label(top, text="Filter:").pack(side=LEFT, padx=(16, 4))
        self.filter_entry = ttk.Entry(top, textvariable=self.search_var, width=30)
        self.filter_entry.pack(side=LEFT)
        self.filter_entry.bind("<KeyRelease>", lambda e: self._apply_filter())

        # Treeview (with poster thumbnails in #0 tree column)
        cols = ("title", "release", "pop", "vote", "pred_end", "left", "conf")
        self.tree = ttk.Treeview(self, columns=cols, show="tree headings")
        self.tree.heading("#0", text="Poster")
        self.tree.column("#0", width=80, anchor="center")
        self.tree.heading("title", text="Title")
        self.tree.heading("release", text="Release")
        self.tree.heading("pop", text="Popularity")
        self.tree.heading("vote", text="Rating")
        self.tree.heading("pred_end", text="Predicted End")
        self.tree.heading("left", text="Days Left")
        self.tree.heading("conf", text="Confidence")
        self.tree.column("title", width=380)
        self.tree.column("release", width=90)
        self.tree.column("pop", width=90, anchor="center")
        self.tree.column("vote", width=80, anchor="center")
        self.tree.column("pred_end", width=120, anchor="center")
        self.tree.column("left", width=90, anchor="center")
        self.tree.column("conf", width=100, anchor="center")
        self.tree.pack(fill=BOTH, expand=True, padx=8, pady=4)
        self.tree.bind("<Double-1>", self._open_details)

        # Status
        self.status = StringVar(value="Idle")
        status_bar = ttk.Label(self, textvariable=self.status, anchor="w")
        status_bar.pack(fill="x", padx=8, pady=(0, 6))

        # In-memory caches for posters
        self._all_rows = []  # store (movie, prediction) for filtering
        self._item_map = {}  # tree item id -> (movie, prediction)
        self._thumb_cache = {}  # poster_path -> PhotoImage
        self._poster_bytes = {}  # poster_path -> bytes

    def fetch_now_playing(self) -> None:
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("TMDb API Key", "Please enter your TMDb API key. Create one at themoviedb.org.")
            return
        self.status.set("Fetching now playing…")
        self.tree.delete(*self.tree.get_children())
        self._all_rows.clear()

        def worker():
            try:
                client = TMDbClient(api_key=api_key)
                movies = client.iterate_now_playing(max_pages=5)
                # Sort by popularity desc
                movies.sort(key=lambda m: m.get("popularity", 0.0), reverse=True)
                rows = []
                for m in movies:
                    p = predict_run_length_days(m)
                    rows.append((m, p))
                # Download poster thumbnails (w92) in background
                poster_bytes = {}
                base = "https://image.tmdb.org/t/p/w92"
                session = requests.Session()
                for m, _ in rows:
                    path = m.get("poster_path")
                    if not path or path in poster_bytes or path in self._poster_bytes:
                        continue
                    url = f"{base}{path}"
                    try:
                        r = session.get(url, timeout=10)
                        if r.ok:
                            poster_bytes[path] = r.content
                    except Exception:
                        pass
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.after(0, lambda: self.status.set("Error"))
                return

            def update_ui():
                self._all_rows = rows
                # merge newly fetched poster bytes into cache
                self._poster_bytes.update(poster_bytes)
                self._item_map.clear()
                for m, p in rows:
                    title = m.get("title") or m.get("name") or "(untitled)"
                    release = (m.get("release_date") or "?")
                    pop = f"{float(m.get('popularity') or 0):.1f}"
                    vote = f"{float(m.get('vote_average') or 0):.1f} ({int(m.get('vote_count') or 0)})"
                    pred_end = p.predicted_end_date.isoformat() if p.predicted_end_date else "N/A"
                    left = str(p.days_remaining) if p.days_remaining is not None else "?"
                    conf = f"{p.confidence*100:.0f}%"
                    image = self._get_thumb_image(m.get("poster_path"))
                    iid = self.tree.insert("", END, text="", image=image, values=(title, release, pop, vote, pred_end, left, conf))
                    self._item_map[iid] = (m, p)
                self.status.set(f"Loaded {len(rows)} movies. Double-click for details.")

            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_filter(self):
        q = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        self._item_map.clear()
        for m, p in self._all_rows:
            title = (m.get("title") or m.get("name") or "").lower()
            if q and q not in title:
                continue
            release = (m.get("release_date") or "?")
            pop = f"{float(m.get('popularity') or 0):.1f}"
            vote = f"{float(m.get('vote_average') or 0):.1f} ({int(m.get('vote_count') or 0)})"
            pred_end = p.predicted_end_date.isoformat() if p.predicted_end_date else "N/A"
            left = str(p.days_remaining) if p.days_remaining is not None else "?"
            conf = f"{p.confidence*100:.0f}%"
            image = self._get_thumb_image(m.get("poster_path"))
            iid = self.tree.insert("", END, text="", image=image, values=(m.get("title") or m.get("name") or "(untitled)", release, pop, vote, pred_end, left, conf))
            self._item_map[iid] = (m, p)

    def _open_details(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid not in self._item_map:
            return
        movie, pred = self._item_map[iid]
        win = Toplevel(self)
        win.title(movie.get("title") or movie.get("name") or "Movie Details")
        # Scrollable content container
        container = ttk.Frame(win)
        container.pack(fill=BOTH, expand=True)
        canvas = Canvas(container, borderwidth=0, highlightthickness=0)
        scroll_y = ttk.Scrollbar(container, orient=VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scroll_y.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scroll_y.pack(side=RIGHT, fill="y")

        def add_row(label, value):
            row = ttk.Frame(win)
            row.pack(fill="x", padx=8, pady=2)
            ttk.Label(row, text=label, width=16).pack(side=LEFT)
            ttk.Label(row, text=value).pack(side=LEFT)

        # Poster on top
        poster_label = ttk.Label(content)
        poster_label.pack(pady=(8, 4))
        self._load_detail_poster_async(movie.get("poster_path"), poster_label)

        def add_row(label, value, wrap=None):
            row = ttk.Frame(content)
            row.pack(fill="x", padx=8, pady=2)
            ttk.Label(row, text=label, width=16).pack(side=LEFT)
            lbl = ttk.Label(row, text=value)
            if wrap:
                lbl.configure(wraplength=wrap, justify="left")
            lbl.pack(side=LEFT, fill="x", expand=True)

        add_row("Title:", movie.get("title") or movie.get("name") or "")
        add_row("Release:", movie.get("release_date") or "?")
        add_row("Popularity:", f"{float(movie.get('popularity') or 0):.1f}")
        add_row("Rating:", f"{float(movie.get('vote_average') or 0):.1f} ({int(movie.get('vote_count') or 0)})")

        if pred.predicted_end_date:
            add_row("Predicted End:", pred.predicted_end_date.isoformat())
            add_row("Days Remaining:", str(pred.days_remaining))
        add_row("Confidence:", f"{pred.confidence*100:.0f}%")
        # Wrap rationale for readability
        add_row("Rationale:", pred.rationale, wrap=700)

        tmdb_id = movie.get("id")
        if tmdb_id:
            def open_tmdb():
                webbrowser.open(f"https://www.themoviedb.org/movie/{tmdb_id}")
            btn = ttk.Button(content, text="Open on TMDb", command=open_tmdb)
            btn.pack(pady=8)

        # Auto-size to content up to a max, then allow scrolling
        win.update_idletasks()
        req_w = min(max(content.winfo_reqwidth() + 24, 640), 900)
        req_h = min(max(content.winfo_reqheight() + 24, 420), 720)
        win.geometry(f"{req_w}x{req_h}")

    def _get_thumb_image(self, poster_path):
        if not poster_path:
            return None
        if poster_path in self._thumb_cache:
            return self._thumb_cache[poster_path]
        data = self._poster_bytes.get(poster_path)
        if not data:
            return None
        try:
            img = Image.open(BytesIO(data))
            # Limit to ~60-90px height
            img.thumbnail((60, 90), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self._thumb_cache[poster_path] = tk_img
            return tk_img
        except Exception:
            return None

    def _load_detail_poster_async(self, poster_path, label_widget):
        if not poster_path:
            return
        base = "https://image.tmdb.org/t/p/w342"
        url = f"{base}{poster_path}"

        def work():
            try:
                r = requests.get(url, timeout=15)
                if not r.ok:
                    return
                data = r.content
            except Exception:
                return

            def set_img():
                try:
                    img = Image.open(BytesIO(data))
                    img.thumbnail((360, 540), Image.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    label_widget.configure(image=tk_img)
                    label_widget.image = tk_img  # keep ref
                except Exception:
                    pass

            self.after(0, set_img)

        threading.Thread(target=work, daemon=True).start()


def run():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    run()
