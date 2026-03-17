import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import win32gui
import sqlite3
import os
import shutil
import time
from collections import defaultdict, deque
import threading


# ---------------- Configuration ----------------
RECENT_MAX = 12
UPDATE_INTERVAL_MS = 1000
HISTORY_REFRESH_MS = 5000
LOG_FILENAME = "activity_log.txt"


# ---------------- GUI SETUP ----------------
root = ttk.Window(
    themename="superhero",   # themes: cyborg, darkly, superhero, morph, vapor, etc.
    title="User Activity Monitor",
    size=(950, 650)
)

mainframe = ttk.Frame(root, padding=15)
mainframe.pack(fill="both", expand=True)

mainframe.columnconfigure(0, weight=1)
mainframe.columnconfigure(1, weight=1)
mainframe.rowconfigure(2, weight=1)


# ---------------- Active Window Panel ----------------
active_frame = ttk.Labelframe(mainframe, text="Active Window", padding=10, bootstyle="info")
active_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

active_window_label = ttk.Label(active_frame, text="(waiting...)", font=("Segoe UI", 16))
active_window_label.pack(anchor="w")


# ---------------- Recent Apps Panel ----------------
recent_frame = ttk.Labelframe(mainframe, text="Recent Apps (Unique)", padding=10, bootstyle="secondary")
recent_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

recent_listbox = tk.Listbox(recent_frame, height=RECENT_MAX, font=("Segoe UI", 11))
recent_listbox.pack(fill="both", expand=True)


# ---------------- Most Used Apps Panel ----------------
stats_frame = ttk.Labelframe(mainframe, text="Most Used Apps (Time Spent)", padding=10, bootstyle="success")
stats_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=10, pady=10)

stats_tree = ttk.Treeview(stats_frame, columns=("app", "seconds"), show="headings", height=12)
stats_tree.heading("app", text="Application")
stats_tree.heading("seconds", text="Seconds")
stats_tree.column("app", width=350, anchor="w")
stats_tree.column("seconds", width=100, anchor="center")
stats_tree.pack(fill="both", expand=True)


# ---------------- Chrome History Panel ----------------
history_frame = ttk.Labelframe(mainframe, text="Recent Chrome History (All Profiles)", padding=10, bootstyle="warning")
history_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)

history_text = tk.Text(history_frame, height=12, font=("Consolas", 10))
history_text.pack(fill="both", expand=True)


# ---------------- Data Structures ----------------
recent_apps = deque(maxlen=RECENT_MAX)
time_spent = defaultdict(float)
last_active = None
last_switch_time = time.time()
history_cache = {}

lock = threading.Lock()


# ---------------- Core Functions ----------------
def get_active_window():
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        return title if title else "(no title)"
    except:
        return "(error reading window)"


def update_recent_apps_listbox():
    recent_listbox.delete(0, tk.END)
    for item in recent_apps:
        recent_listbox.insert(tk.END, item)


def refresh_stats_tree():
    sorted_items = sorted(time_spent.items(), key=lambda kv: kv[1], reverse=True)
    stats_tree.delete(*stats_tree.get_children())
    for title, secs in sorted_items[:20]:
        stats_tree.insert("", "end", values=(title, f"{int(secs)}s"))


def append_log(text):
    with open(LOG_FILENAME, "a", encoding="utf-8") as f:
        f.write(text + "\n")


# ---------------- Chrome Reader ----------------
def get_all_chrome_history():
    history_data = {}
    base = os.path.expanduser("~") + r"\AppData\Local\Google\Chrome\User Data"
    
    if not os.path.isdir(base):
        return {"Error": [("Chrome folder not found", "")]}

    profiles = ["Default"] + [p for p in os.listdir(base) if p.startswith("Profile")]

    for profile in profiles:
        try:
            hist_path = os.path.join(base, profile, "History")
            if not os.path.exists(hist_path):
                history_data[profile] = [("No history file", "")]
                continue

            temp_copy = f"history_{profile}.db"
            shutil.copy2(hist_path, temp_copy)

            conn = sqlite3.connect(temp_copy)
            cur = conn.cursor()
            cur.execute("SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 12")
            rows = cur.fetchall()
            conn.close()
            os.remove(temp_copy)

            history_data[profile] = [(title or "(no title)", url) for url, title in rows]

        except Exception as e:
            history_data[profile] = [(f"Error: {e}", "")]

    return history_data


def refresh_history_text():
    history_text.delete("1.0", tk.END)
    for profile, entries in history_cache.items():
        history_text.insert("end", f"--- {profile} ---\n")
        for title, url in entries:
            history_text.insert("end", f"{title} — {url}\n")
        history_text.insert("end", "\n")


# ---------------- Background Processes ----------------
def poll_active_window():
    global last_active, last_switch_time

    now = time.time()
    active = get_active_window()

    with lock:
        if last_active:
            time_spent[last_active] += (now - last_switch_time)

        if active != last_active:
            if active in recent_apps:
                recent_apps.remove(active)
            recent_apps.appendleft(active)
            append_log(f"{time.ctime()} | SWITCH -> {active}")

        last_active = active
        last_switch_time = now

    active_window_label.configure(text=active)
    update_recent_apps_listbox()
    refresh_stats_tree()

    root.after(UPDATE_INTERVAL_MS, poll_active_window)


def background_refresh_history():
    global history_cache
    try:
        new_data = get_all_chrome_history()
        with lock:
            history_cache = new_data

        refresh_history_text()

    except Exception as e:
        append_log(f"History refresh error: {e}")

    root.after(HISTORY_REFRESH_MS, background_refresh_history)


# ---------------- Shutdown ----------------
def on_close():
    now = time.time()
    if last_active:
        time_spent[last_active] += (now - last_switch_time)

    append_log("\n===== SESSION END =====")
    for title, secs in sorted(time_spent.items(), key=lambda x: x[1], reverse=True):
        append_log(f"{int(secs)}s | {title}")
    append_log("=======================\n")

    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_close)


# ---------------- Start Program ----------------
history_cache = get_all_chrome_history()
refresh_history_text()
poll_active_window()
root.after(HISTORY_REFRESH_MS, background_refresh_history)

root.mainloop()
