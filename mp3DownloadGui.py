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
            tracks.append({"url": mp3, "title": title, "artist": artist})
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
            artists.append({"name": title, "url": href})
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
                all_tracks.append({"url": mp3, "title": title, "artist": artist})
        next_link = soup.select_one(".paginate a.next_page")
        if next_link and next_link.get("href"):
            page_url = urljoin(BASE, next_link["href"])
        else:
            break
    return all_tracks

def download_file(url, path, progress_callback=None):
    with requests.get(url, headers=HEADERS, stream=True) as r:
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

# ===================== GUI Приложение =====================

class MP3DownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3Party Downloader")
        self.root.geometry("750x500")

        self.mode_var = tk.StringVar(value="search")
        self.query_var = tk.StringVar()
        self.folder_var = tk.StringVar()

        self.tracks = []
        self.check_vars = []

        self.create_widgets()

    def create_widgets(self):
        # Режим
        frame_mode = ttk.LabelFrame(self.root, text="Режим")
        frame_mode.pack(fill="x", padx=10, pady=5)
        ttk.Radiobutton(frame_mode, text="Поиск песен", variable=self.mode_var, value="search").pack(side="left", padx=5)
        ttk.Radiobutton(frame_mode, text="Все песни артиста", variable=self.mode_var, value="artist").pack(side="left", padx=5)

        # Запрос
        frame_query = ttk.Frame(self.root)
        frame_query.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_query, text="Запрос / URL:").pack(side="left")
        ttk.Entry(frame_query, textvariable=self.query_var, width=50).pack(side="left", padx=5)
        ttk.Button(frame_query, text="Найти", command=self.search_tracks).pack(side="left", padx=5)

        # Папка
        frame_folder = ttk.Frame(self.root)
        frame_folder.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame_folder, text="Папка:").pack(side="left")
        ttk.Entry(frame_folder, textvariable=self.folder_var, width=50).pack(side="left", padx=5)
        ttk.Button(frame_folder, text="Выбрать", command=self.choose_folder).pack(side="left", padx=5)

        # Таблица треков
        self.frame_tracks = ttk.Frame(self.root)
        self.frame_tracks.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(self.frame_tracks)
        self.scrollbar = ttk.Scrollbar(self.frame_tracks, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Кнопка скачивания
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=5)
        ttk.Button(self.root, text="Скачать", command=self.start_download).pack(pady=5)

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)

    def search_tracks(self):
        query = self.query_var.get().strip()
        if not query:
            messagebox.showerror("Ошибка", "Введите запрос или ссылку")
            return

        def worker():
            try:
                if self.mode_var.get() == "search":
                    # tracks = find_first_track_from_search(query)
                    tracks = find_tracks_from_search(query, limit=40)
                    self.root.after(0, lambda: self.show_tracks(tracks, default_checked=False))
                else:
                    # поиск артиста
                    if not query.startswith("http") and not query.isdigit():
                        artists = find_all_artists_by_name(query)
                        if not artists:
                            messagebox.showerror("Ошибка", "Артист не найден")
                            return
                        if len(artists) > 1:
                            self.root.after(0, lambda: self.show_artist_selection(artists))
                            return
                        else:
                            tracks = collect_tracks_from_artist(artists[0]["url"])
                            self.root.after(0, lambda: self.show_tracks(tracks))
                    else:
                        tracks = collect_tracks_from_artist(query)
                        self.root.after(0, lambda: self.show_tracks(tracks))
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def show_artist_selection(self, artists):
        top = tk.Toplevel(self.root)
        top.title("Выберите артиста")

        lb = tk.Listbox(top, width=50, height=10)
        for art in artists:
            lb.insert(tk.END, art["name"])
        lb.pack(padx=10, pady=10)

        def select_artist():
            idx = lb.curselection()
            if idx:
                url = artists[idx[0]]["url"]
                top.destroy()
                threading.Thread(target=lambda: self.show_tracks(collect_tracks_from_artist(url)), daemon=True).start()

        ttk.Button(top, text="Выбрать", command=select_artist).pack(pady=5)

    def show_tracks(self, tracks, default_checked=True):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.tracks = tracks
        self.check_vars = []

        for track in tracks:
            var = tk.BooleanVar(value=default_checked)
            self.check_vars.append(var)
            chk = ttk.Checkbutton(self.scroll_frame, text=f"{track['artist']} - {track['title']}", variable=var)
            chk.pack(anchor="w")

    def start_download(self):
        folder = self.folder_var.get()
        if not folder:
            messagebox.showerror("Ошибка", "Выберите папку для сохранения")
            return

        selected_tracks = [t for t, v in zip(self.tracks, self.check_vars) if v.get()]
        if not selected_tracks:
            messagebox.showinfo("Инфо", "Нет выбранных треков для скачивания")
            return

        def worker():
            session = requests.Session()
            for track in selected_tracks:
                filename = safe_filename(f"{track['artist']} - {track['title']}.mp3")
                path = os.path.join(folder, filename)
                try:
                    def prog(p):
                        self.root.after(0, lambda: self.progress.configure(value=p*100))
                    download_file(track["url"], path, progress_callback=prog)
                except Exception as e:
                    print(f"Ошибка скачивания {track['url']}: {e}")
                self.root.after(0, lambda: self.progress.configure(value=0))
            messagebox.showinfo("Готово", "Скачивание завершено!")

        threading.Thread(target=worker, daemon=True).start()

# ===================== Запуск =====================

if __name__ == "__main__":
    root = tk.Tk()
    app = MP3DownloaderApp(root)
    root.mainloop()