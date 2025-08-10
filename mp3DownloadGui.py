import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
from bs4 import BeautifulSoup
import threading
import os
import re
from urllib.parse import quote_plus, urljoin

BASE = "https://mp3party.net"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ===================== Вспомогательные функции =====================

def safe_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r'\s+', " ", name)
    return name

def get_soup(url: str):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def find_tracks_from_search(query_or_url, limit=40):
    if query_or_url.startswith("http"):
        url = query_or_url
    else:
        q = quote_plus(query_or_url)
        url = f"{BASE}/search?q={q}"
    soup = get_soup(url)

    tracks = []
    for panel in soup.select(".track__user-panel")[:limit]:
        mp3 = panel.get("data-js-url")
        title = panel.get("data-js-song-title")
        artist = panel.get("data-js-artist-name")
        if mp3:
            tracks.append({"url": mp3, "title": title or "Unknown Title", "artist": artist or "Unknown Artist"})
    return tracks

def find_all_artists_by_name(name):
    q = quote_plus(name)
    url = f"{BASE}/search?q={q}"
    soup = get_soup(url)
    artists = []
    for a in soup.select("a[href*='/artist/']"):
        href = urljoin(BASE, a["href"])
        title = a.get_text(strip=True)
        if href not in [ar['url'] for ar in artists]:
            artists.append({"name": title or "Unknown", "url": href})
    return artists

def collect_tracks_from_artist(artist_url):
    all_tracks = []
    page_url = artist_url
    while page_url:
        soup = get_soup(page_url)
        panels = soup.select(".track__user-panel")
        for p in panels:
            mp3 = p.get("data-js-url")
            title = p.get("data-js-song-title")
            artist = p.get("data-js-artist-name")
            if mp3:
                all_tracks.append({"url": mp3, "title": title or "Unknown Title", "artist": artist or "Unknown Artist"})
        next_link = soup.select_one(".paginate a.next_page")
        if next_link and next_link.get("href"):
            page_url = urljoin(BASE, next_link["href"])
        else:
            break
    return all_tracks

def download_file(url, path, progress_callback=None, session=None):
    sess = session or requests
    with sess.get(url, headers=HEADERS, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        with open(path, "wb") as f:
            downloaded = 0
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(downloaded / total)

# ===================== UI / Приложение =====================

class MP3DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3Party Downloader")
        self.root.geometry("820x560")
        self.root.minsize(700, 480)

        # Состояние
        self.mode_var = tk.StringVar(value="search")
        self.query_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.limit_var = tk.IntVar(value=20)

        self.tracks = []          # list of track dicts
        self.check_vars = []      # list of BooleanVar

        self._build_style()
        self.create_widgets()

    def _build_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("TFrame", padding=6)
        style.configure("Card.TLabelframe", background="#f7f7f7")
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 11, "bold"))
        style.map("Danger.TButton", foreground=[('active', 'white')], background=[('active', '#c0392b')])

    def create_widgets(self):
        # Header
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(header, text="MP3Party Downloader", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="— удобная загрузка треков с mp3party.net", anchor="e").pack(side="right")

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: controls
        left = ttk.Frame(main)
        left.pack(side="left", fill="y", padx=(0,10))

        # Mode card
        mode_card = ttk.Labelframe(left, text="Режим", padding=(10,8), style="Card.TLabelframe")
        mode_card.pack(fill="x", pady=4)
        ttk.Radiobutton(mode_card, text="Поиск песен", variable=self.mode_var, value="search").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(mode_card, text="Все песни артиста", variable=self.mode_var, value="artist").grid(row=0, column=1, sticky="w", padx=2, pady=2)

        # Query card
        query_card = ttk.Labelframe(left, text="Запрос / URL", padding=(10,8), style="Card.TLabelframe")
        query_card.pack(fill="x", pady=6)
        q_entry = ttk.Entry(query_card, textvariable=self.query_var, width=36)
        q_entry.grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
        search_btn = ttk.Button(query_card, text="Найти", command=self.search_tracks)
        search_btn.grid(row=0, column=2, padx=6)

        # Limit selector
        ttk.Label(query_card, text="Макс результатов:").grid(row=1, column=0, sticky="w", pady=(6,0))
        limit_spin = ttk.Spinbox(query_card, from_=1, to=40, textvariable=self.limit_var, width=6)
        limit_spin.grid(row=1, column=1, sticky="w", pady=(6,0))

        # Folder card
        folder_card = ttk.Labelframe(left, text="Папка для сохранения", padding=(10,8), style="Card.TLabelframe")
        folder_card.pack(fill="x", pady=6)
        f_entry = ttk.Entry(folder_card, textvariable=self.folder_var, width=36)
        f_entry.grid(row=0, column=0, pady=4)
        ttk.Button(folder_card, text="Выбрать...", command=self.choose_folder).grid(row=0, column=1, padx=6)

        # Action buttons
        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=6)
        self.btn_select_all = ttk.Button(actions, text="Выбрать всё", command=self.select_all)
        self.btn_select_all.pack(side="left", expand=True, fill="x", padx=(0,4))
        self.btn_select_none = ttk.Button(actions, text="Снять всё", command=self.select_none)
        self.btn_select_none.pack(side="left", expand=True, fill="x", padx=(4,0))

        # Download button & status
        dl_card = ttk.Frame(left)
        dl_card.pack(fill="x", pady=(10,0))
        self.progress = ttk.Progressbar(dl_card, orient="horizontal", length=240, mode="determinate")
        self.progress.pack(pady=(0,6))
        self.lbl_status = ttk.Label(dl_card, text="Готов", anchor="center")
        self.lbl_status.pack(fill="x", pady=(0,6))

        self.btn_download = ttk.Button(dl_card, text="Скачать выбранные", command=self.start_download)
        self.btn_download.pack(fill="x")

        # Right: track list
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        tracks_card = ttk.Labelframe(right, text="Список треков", padding=(8,8), style="Card.TLabelframe")
        tracks_card.pack(fill="both", expand=True)

        # Scrollable area for checkboxes
        self.canvas = tk.Canvas(tracks_card, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(tracks_card, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)

        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0,0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Footer: counts & credits
        footer = ttk.Frame(self.root)
        footer.pack(fill="x", padx=10, pady=(0,10))
        self.lbl_count = ttk.Label(footer, text="Треков: 0")
        self.lbl_count.pack(side="left")
        ttk.Label(footer, text=" | ").pack(side="left")
        ttk.Label(footer, text="Скрипт для личного использования.").pack(side="left")
        ttk.Label(footer, text=" ").pack(side="right")

    # ----------------- утилиты UI -----------------
    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)

    def select_all(self):
        for v in self.check_vars:
            v.set(True)

    def select_none(self):
        for v in self.check_vars:
            v.set(False)

    def _set_status(self, text):
        self.lbl_status.config(text=text)

    def _show_error(self, title, text):
        # call from main thread
        messagebox.showerror(title, text)

    # ----------------- поиск -----------------
    def search_tracks(self):
        query = self.query_var.get().strip()
        if not query:
            messagebox.showerror("Ошибка", "Введите запрос или ссылку")
            return

        self._set_status("Поиск...")
        self.progress.configure(value=0)
        self.clear_tracks()

        def worker():
            try:
                if self.mode_var.get() == "search":
                    tracks = find_tracks_from_search(query, limit=self.limit_var.get())
                    self.root.after(0, lambda: self.show_tracks(tracks, default_checked=False))
                else:
                    # режим "artist"
                    if not query.startswith("http") and not query.isdigit():
                        artists = find_all_artists_by_name(query)
                        if not artists:
                            self.root.after(0, lambda: self._show_error("Ошибка", "Артист не найден"))
                            self.root.after(0, lambda: self._set_status("Готов"))
                            return
                        if len(artists) > 1:
                            self.root.after(0, lambda: self.show_artist_selection(artists))
                            self.root.after(0, lambda: self._set_status("Ожидание выбора артиста"))
                            return
                        else:
                            tracks = collect_tracks_from_artist(artists[0]["url"])
                            self.root.after(0, lambda: self.show_tracks(tracks))
                    else:
                        tracks = collect_tracks_from_artist(query)
                        self.root.after(0, lambda: self.show_tracks(tracks))
                self.root.after(0, lambda: self._set_status("Готов"))
            except Exception as e:
                self.root.after(0, lambda: self._show_error("Ошибка", str(e)))
                self.root.after(0, lambda: self._set_status("Готов"))

        threading.Thread(target=worker, daemon=True).start()

    def show_artist_selection(self, artists):
        top = tk.Toplevel(self.root)
        top.title("Выберите артиста")
        top.geometry("480x320")
        ttk.Label(top, text="Найдено несколько артистов. Выберите один:").pack(anchor="w", padx=10, pady=(8,0))

        lb = tk.Listbox(top, width=60, height=12)
        for art in artists:
            lb.insert(tk.END, art["name"])
        lb.pack(padx=10, pady=8, fill="both", expand=True)

        def select_artist():
            idx = lb.curselection()
            if idx:
                url = artists[idx[0]]["url"]
                top.destroy()
                self._set_status("Сбор треков артиста...")
                threading.Thread(target=lambda: self._collect_and_show_artist(url), daemon=True).start()

        btn = ttk.Button(top, text="Выбрать", command=select_artist)
        btn.pack(pady=(0,10))

    def _collect_and_show_artist(self, url):
        try:
            tracks = collect_tracks_from_artist(url)
            self.root.after(0, lambda: self.show_tracks(tracks))
            self.root.after(0, lambda: self._set_status("Готов"))
        except Exception as e:
            self.root.after(0, lambda: self._show_error("Ошибка", str(e)))
            self.root.after(0, lambda: self._set_status("Готов"))

    def clear_tracks(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.tracks = []
        self.check_vars = []
        self.lbl_count.config(text="Треков: 0")

    def show_tracks(self, tracks, default_checked=True):
        # Очищаем
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.tracks = tracks
        self.check_vars = []

        # Заполняем
        for idx, track in enumerate(tracks):
            var = tk.BooleanVar(value=default_checked)
            self.check_vars.append(var)
            row = ttk.Frame(self.scroll_frame)
            row.pack(fill="x", anchor="w", pady=1, padx=2)

            chk = ttk.Checkbutton(row, variable=var)
            chk.pack(side="left", padx=(0,6))
            # compact label with artist - title and small url hover
            lbl_text = f"{track.get('artist', '')} — {track.get('title', '')}"
            lbl = ttk.Label(row, text=lbl_text, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)

            # save the url as an attribute for convenience
            lbl.url = track.get("url", "")

            # add a small 'preview' button that opens URL in browser if needed
            def open_url(u=track.get("url", "")):
                import webbrowser
                if u:
                    webbrowser.open(u)
            btn_preview = ttk.Button(row, text="Открыть", width=8, command=open_url)
            btn_preview.pack(side="right", padx=(6,0))

        self.lbl_count.config(text=f"Треков: {len(tracks)}")
        # reset progress
        self.progress.configure(value=0)

    # ----------------- скачивание -----------------
    def start_download(self):
        folder = self.folder_var.get()
        if not folder:
            messagebox.showerror("Ошибка", "Выберите папку для сохранения")
            return

        selected_tracks = [t for t, v in zip(self.tracks, self.check_vars) if v.get()]
        if not selected_tracks:
            messagebox.showinfo("Инфо", "Нет выбранных треков для скачивания")
            return

        # disable UI actions while качаем
        self._set_status("Скачивание...")
        self.btn_download.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_select_none.config(state="disabled")

        def worker():
            session = requests.Session()
            total_tracks = len(selected_tracks)
            for i, track in enumerate(selected_tracks, start=1):
                filename = safe_filename(f"{track['artist']} - {track['title']}.mp3")
                path = os.path.join(folder, filename)
                try:
                    def prog(p, idx=i, total=total_tracks):
                        # p - 0..1 for current file; we map to overall progress roughly:
                        base = (idx - 1) / total
                        overall = base + (p / total)
                        self.root.after(0, lambda: self.progress.configure(value=overall * 100))
                    download_file(track["url"], path, progress_callback=prog, session=session)
                except Exception as e:
                    print(f"Ошибка скачивания {track.get('url')}: {e}")
                # after each file reset per-file progress (keeps overall)
                self.root.after(0, lambda: self.progress.configure(value=(i / total_tracks) * 100))
            # done
            self.root.after(0, lambda: messagebox.showinfo("Готово", "Скачивание завершено!"))
            self.root.after(0, lambda: self._set_status("Готов"))
            self.root.after(0, lambda: self.progress.configure(value=0))
            self.root.after(0, lambda: self.btn_download.config(state="normal"))
            self.root.after(0, lambda: self.btn_select_all.config(state="normal"))
            self.root.after(0, lambda: self.btn_select_none.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()


# ===================== Запуск =====================

if __name__ == "__main__":
    root = tk.Tk()
    app = MP3DownloaderApp(root)
    root.mainloop()
