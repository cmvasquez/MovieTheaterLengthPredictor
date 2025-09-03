from __future__ import annotations

import threading
import webbrowser
from io import BytesIO
from datetime import date
from tkinter import BOTH, END, HORIZONTAL, LEFT, RIGHT, StringVar, BooleanVar, IntVar, Tk, Toplevel, VERTICAL, Canvas, Menu, ttk, messagebox

import requests
from PIL import Image, ImageTk

from .config import get_settings
from .predictor import Prediction, predict_run_length_days
from .tmdb import TMDbClient
from . import __version__


class App(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Movie Theater Run Predictor (US)")
        self.geometry("1280x760")

        # Styles and theme
        self.style = ttk.Style(self)
        self._original_theme = self.style.theme_use()

        # Tree/List poster display sizing
        self._list_poster_size_key = "w185"  # TMDb size bucket for list thumbnails
        self._base_thumb_max = (185, 278)     # base width, height for scaling
        self._list_poster_max = (185, 278)    # current target width, height
        self._tree_row_height = 300           # fit whole poster (a bit of padding)
        self._min_thumb = (60, 90)
        self._max_thumb = (360, 540)

        # In-memory caches for posters (init early so callbacks can use them)
        self._all_rows = []  # store (movie, prediction) for filtering
        self._item_map = {}  # tree item id -> (movie, prediction)
        self._thumb_cache = {}  # size:path -> PhotoImage
        self._poster_bytes = {}  # size:path -> bytes

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

        # Menubar with Edit options
        self.show_posters_var = BooleanVar(value=True)
        self.dark_mode_var = BooleanVar(value=False)
        menubar = Menu(self)
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        edit_menu = Menu(menubar, tearoff=0)
        edit_menu.add_checkbutton(label="Show Posters", variable=self.show_posters_var, command=self._toggle_posters)
        edit_menu.add_checkbutton(label="Dark Mode", variable=self.dark_mode_var, command=self._toggle_dark_mode)
        edit_menu.add_separator()
        edit_menu.add_command(label="Poster zoom +", command=lambda: self._zoom_step(+10))
        edit_menu.add_command(label="Poster zoom -", command=lambda: self._zoom_step(-10))
        menubar.add_cascade(label="Edit", menu=edit_menu)
        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

        # Treeview (with poster thumbnails in #0 tree column)
        cols = ("title", "release", "pop", "vote", "pred_end", "left", "conf")
        self.tree = ttk.Treeview(self, columns=cols, show="tree headings")
        self.tree.heading("#0", text="Poster")
        self.tree.column("#0", width=210, anchor="center")
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
        ttk.Style(self).configure("Treeview", rowheight=self._tree_row_height)
        self.tree.pack(fill=BOTH, expand=True, padx=8, pady=4)
        self.tree.bind("<Double-1>", self._open_details)

        # Bottom bar: only status (poster slider temporarily disabled)
        self.status = StringVar(value="Idle")
        self.thumb_scale_var = IntVar(value=100)  # keep scale value for menu zoom
        self.bottom = ttk.Frame(self)
        self.bottom.pack(fill="x", padx=8, pady=(0, 6))
        self.status_label = ttk.Label(self.bottom, textvariable=self.status, anchor="w")
        self.status_label.pack(side=LEFT, fill="x", expand=True)

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
                    # Resolve current run start date (may be a re-release)
                    run_start = client.get_run_start_date(int(m.get("id"))) if m.get("id") else None
                    p = predict_run_length_days({**m, "release_date": run_start.isoformat() if run_start else m.get("release_date")})
                    rows.append(({**m, "_run_start": run_start and run_start.isoformat()}, p))
                # Download poster thumbnails in background (use list size for cache)
                poster_bytes = {}
                base = f"https://image.tmdb.org/t/p/{self._list_poster_size_key}"
                session = requests.Session()
                for m, _ in rows:
                    path = m.get("poster_path")
                    if not path:
                        continue
                    key = f"{self._list_poster_size_key}:{path}"
                    if key in poster_bytes or key in self._poster_bytes:
                        continue
                    url = f"{base}{path}"
                    try:
                        r = session.get(url, timeout=10)
                        if r.ok:
                            poster_bytes[key] = r.content
                    except Exception:
                        pass
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Error", str(e)))
                self.after(0, lambda: self.status.set("Error"))
                return

            def update_ui():
                self._all_rows = rows
                # merge newly fetched poster bytes into cache
                self._poster_bytes.update(poster_bytes)
                self._item_map.clear()
                for m, p in rows:
                    title = m.get("title") or m.get("name") or "(untitled)"
                    # Show the run-start date if available
                    release = (m.get("_run_start") or m.get("release_date") or "?")
                    pop = f"{float(m.get('popularity') or 0):.1f}"
                    vote = f"{float(m.get('vote_average') or 0):.1f} ({int(m.get('vote_count') or 0)})"
                    # For ongoing runs, do not show an end date in the past
                    if p.predicted_end_date and p.predicted_end_date < date.today():
                        pred_end = "TBD"
                    else:
                        pred_end = p.predicted_end_date.isoformat() if p.predicted_end_date else "N/A"
                    left = str(p.days_remaining) if (p.days_remaining is not None and p.predicted_end_date and p.predicted_end_date >= date.today()) else "?"
                    conf = f"{p.confidence*100:.0f}%"
                    image = self._get_thumb_image(m.get("poster_path"))
                    if image is not None:
                        iid = self.tree.insert("", END, text="", image=image, values=(title, release, pop, vote, pred_end, left, conf))
                    else:
                        iid = self.tree.insert("", END, text="", values=(title, release, pop, vote, pred_end, left, conf))
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
            release = (m.get("_run_start") or m.get("release_date") or "?")
            pop = f"{float(m.get('popularity') or 0):.1f}"
            vote = f"{float(m.get('vote_average') or 0):.1f} ({int(m.get('vote_count') or 0)})"
            if p.predicted_end_date and p.predicted_end_date < date.today():
                pred_end = "TBD"
            else:
                pred_end = p.predicted_end_date.isoformat() if p.predicted_end_date else "N/A"
            left = str(p.days_remaining) if (p.days_remaining is not None and p.predicted_end_date and p.predicted_end_date >= date.today()) else "?"
            conf = f"{p.confidence*100:.0f}%"
            image = self._get_thumb_image(m.get("poster_path"))
            if self.show_posters_var.get() and image is not None:
                iid = self.tree.insert("", END, text="", image=image, values=(m.get("title") or m.get("name") or "(untitled)", release, pop, vote, pred_end, left, conf))
            else:
                iid = self.tree.insert("", END, text="", values=(m.get("title") or m.get("name") or "(untitled)", release, pop, vote, pred_end, left, conf))
            self._item_map[iid] = (m, p)

    def _toggle_posters(self):
        # Toggle between showing the tree (poster column) and headings-only
        if self.show_posters_var.get():
            self.tree.configure(show="tree headings")
            # Restore row height and poster column width based on current scale
            _, h, wcol = self._current_thumb_dims()
            ttk.Style(self).configure("Treeview", rowheight=h)
            self.tree.column("#0", width=wcol, anchor="center")
        else:
            self.tree.configure(show="headings")
            ttk.Style(self).configure("Treeview", rowheight=28)
        # Bottom bar no-op; slider hidden for now
        # Rebuild the rows so images are attached/detached accordingly
        self._apply_filter()

    def _zoom_step(self, delta: int):
        # Adjust zoom percent by delta and apply
        try:
            current = int(self.thumb_scale_var.get())
        except Exception:
            current = 100
        new_pct = max(50, min(200, current + int(delta)))
        self._on_thumb_scale(float(new_pct))

    def _current_thumb_dims(self):
        # Returns (thumb_w, row_height, poster_col_width)
        tw, th = self._list_poster_max
        th = max(self._min_thumb[1], min(self._max_thumb[1], th))
        tw = max(self._min_thumb[0], min(self._max_thumb[0], tw))
        row_h = th + 22
        col_w = tw + 25
        return tw, row_h, col_w

    def _on_thumb_scale(self, value: float):
        # Scale in percent from 50..200
        try:
            pct = max(50.0, min(200.0, float(value)))
        except Exception:
            pct = 100.0
        self.thumb_scale_var.set(int(pct))
        try:
            self.scale_value_lbl.configure(text=f"{int(pct)}%")
        except Exception:
            pass
        factor = pct / 100.0
        bw, bh = self._base_thumb_max
        new_w = int(bw * factor)
        new_h = int(bh * factor)
        # Clamp
        new_w = max(self._min_thumb[0], min(self._max_thumb[0], new_w))
        new_h = max(self._min_thumb[1], min(self._max_thumb[1], new_h))
        self._list_poster_max = (new_w, new_h)
        # Update layout if posters are visible
        if self.show_posters_var.get():
            _, row_h, col_w = self._current_thumb_dims()
            ttk.Style(self).configure("Treeview", rowheight=row_h)
            self.tree.column("#0", width=col_w, anchor="center")
        else:
            ttk.Style(self).configure("Treeview", rowheight=28)
        # Re-render rows with new thumbnail sizes
        self._apply_filter()

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
        add_row("Release:", movie.get("_run_start") or movie.get("release_date") or "?")
        add_row("Popularity:", f"{float(movie.get('popularity') or 0):.1f}")
        add_row("Rating:", f"{float(movie.get('vote_average') or 0):.1f} ({int(movie.get('vote_count') or 0)})")

        if pred.predicted_end_date:
            if pred.predicted_end_date < date.today():
                add_row("Predicted End:", "TBD")
                add_row("Days Remaining:", "?")
            else:
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
        # Cache key includes the target pixel size so different slider sizes cache separately
        cache_key = f"{self._list_poster_size_key}:{self._list_poster_max[0]}x{self._list_poster_max[1]}:{poster_path}"
        if cache_key in self._thumb_cache:
            return self._thumb_cache[cache_key]
        data_key = f"{self._list_poster_size_key}:{poster_path}"
        data = self._poster_bytes.get(data_key)
        if not data:
            return None
        try:
            img = Image.open(BytesIO(data))
            # Resize to fit our list poster target size
            img.thumbnail(self._list_poster_max, Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self._thumb_cache[cache_key] = tk_img
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

    def _toggle_dark_mode(self):
        dark = self.dark_mode_var.get()
        style = self.style
        if dark:
            # Prefer 'clam' for better customization
            try:
                style.theme_use("clam")
            except Exception:
                pass
            bg = "#1e1e1e"
            bg2 = "#2a2a2a"
            fg = "#e6e6e6"
            tree_bg = "#252526"
            sel_bg = "#094771"
            self.configure(bg=bg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TButton", background=bg, foreground=fg)
            # keep current rowheight
            _, row_h, _ = self._current_thumb_dims()
            if not self.show_posters_var.get():
                row_h = 28
            style.configure("Treeview", background=tree_bg, fieldbackground=tree_bg, foreground=fg, rowheight=row_h)
            style.configure("Treeview.Heading", background=bg2, foreground=fg)
            style.map("Treeview", background=[("selected", sel_bg)])
        else:
            # Revert to original theme-ish colors
            try:
                style.theme_use(self._original_theme)
            except Exception:
                pass
            bg = "SystemButtonFace"
            fg = "black"
            tree_bg = "white"
            sel_bg = "#0078d7"  # Windows accent blue
            self.configure(bg=bg)
            style.configure("TFrame", background=bg)
            style.configure("TLabel", background=bg, foreground=fg)
            style.configure("TButton", background=bg, foreground=fg)
            _, row_h, _ = self._current_thumb_dims()
            if not self.show_posters_var.get():
                row_h = 28
            style.configure("Treeview", background=tree_bg, fieldbackground=tree_bg, foreground=fg, rowheight=row_h)
            style.configure("Treeview.Heading", background=bg, foreground=fg)
            style.map("Treeview", background=[("selected", sel_bg)])

    def _show_about(self):
        win = Toplevel(self)
        win.title("About")
        win.resizable(False, False)
        pad = 12
        frame = ttk.Frame(win, padding=pad)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Movie Theater Run Predictor", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frame, text=f"Version v{__version__}").pack(anchor="w", pady=(4,0))
        ttk.Label(frame, text="Created by Christian Vasquez").pack(anchor="w")

        link = "https://github.com/cmvasquez/MovieTheaterLengthPredictor"
        link_lbl = ttk.Label(frame, text=link, foreground="#0066cc", cursor="hand2")
        link_lbl.pack(anchor="w", pady=(6,0))
        link_lbl.bind("<Button-1>", lambda e: webbrowser.open(link))

        btn = ttk.Button(frame, text="OK", command=win.destroy)
        btn.pack(anchor="e", pady=(8,0))


def run():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    run()
