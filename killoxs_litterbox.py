import os
import time
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import urllib.request
import urllib.error
import ssl

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


BG         = "#0d0f14"
BG_PANEL   = "#13161e"
BG_CARD    = "#1a1e28"
BG_INPUT   = "#10121a"
ACCENT     = "#00d4aa"
ACCENT_DIM = "#009e7e"
FG         = "#e8eaf0"
SUBTEXT    = "#6b7280"
BORDER     = "#252a38"
RED        = "#f87171"
GREEN      = "#4ade80"
YELLOW     = "#fbbf24"

F_UI   = "Segoe UI"
F_MONO = "Consolas"

EXPIRY_OPTIONS = {
    "1h":  "1h",
    "12h": "12h",
    "24h": "24h",
    "72h": "72h",
}

IMAGE_EXT     = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
USER_AGENT    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _dark_titlebar(hwnd):
    try:
        import ctypes
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
        )
    except Exception:
        pass


def _build_multipart(fields, file_path):
    boundary = b"----KilloxsBoundary7MA4YWxkTrZu0gW"
    body = b""
    for name, value in fields.items():
        body += b"--" + boundary + b"\r\n"
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += value.encode() + b"\r\n"
    file_name = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        file_bytes = fh.read()
    body += b"--" + boundary + b"\r\n"
    body += f'Content-Disposition: form-data; name="fileToUpload"; filename="{file_name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
    body += file_bytes + b"\r\n"
    body += b"--" + boundary + b"--\r\n"
    ctype = "multipart/form-data; boundary=" + boundary.decode()
    return body, ctype


class ImageUploadHandler(FileSystemEventHandler):
    def __init__(self, upload_queue):
        super().__init__()
        self.upload_queue = upload_queue

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(IMAGE_EXT):
            self.upload_queue.put(event.src_path)


class UploadWorker(threading.Thread):
    SENTINEL = None

    def __init__(self, upload_queue, log_cb, copy_cb, expiry_cb, counter_cb):
        super().__init__(daemon=True)
        self.upload_queue = upload_queue
        self.log     = log_cb
        self.copy    = copy_cb
        self.expiry  = expiry_cb
        self.counter = counter_cb

    def run(self):
        while True:
            path = self.upload_queue.get()
            if path is self.SENTINEL:
                break
            try:
                self._process(path)
            except Exception as exc:
                self.log(f"ERR  {exc}", "error")
            finally:
                self.upload_queue.task_done()

    def _process(self, file_path):
        name = os.path.basename(file_path)
        self.log(f"SCAN {name}", "info")
        if not self._wait_for_file(file_path):
            self.log(f"TOUT write timeout — skipping {name}", "warn")
            return
        self._upload(file_path)

    def _wait_for_file(self, path, timeout=30):
        prev = -1
        for _ in range(timeout):
            try:
                size = os.path.getsize(path)
            except OSError:
                time.sleep(1)
                continue
            if size == prev and size > 0:
                return True
            prev = size
            time.sleep(1)
        return False

    def _upload(self, file_path, retries=5):
        name   = os.path.basename(file_path)
        expiry = self.expiry()
        self.log(f"UP   {name}  [{expiry}]", "info")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE

        for attempt in range(1, retries + 1):
            try:
                body, ctype = _build_multipart({"reqtype": "fileupload", "time": expiry}, file_path)
                req = urllib.request.Request(LITTERBOX_URL, data=body)
                req.add_header("Content-Type", ctype)
                req.add_header("User-Agent",   USER_AGENT)
                req.add_header("Origin",       "https://litterbox.catbox.moe")
                req.add_header("Referer",      "https://litterbox.catbox.moe/")

                with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                    link = resp.read().decode().strip()

                if link.startswith("https://"):
                    self.log(f"OK   {link}", "success")
                    self.copy(link)
                    self.counter(True)
                    return

                if "BunkerWeb" in link or "Generating" in link:
                    wait = 5 * attempt
                    self.log(f"WAF  challenge {attempt}/{retries} — waiting {wait}s", "warn")
                    time.sleep(wait)
                    continue

                self.log(f"FAIL attempt {attempt}/{retries}: {link[:120]}", "warn")

            except urllib.error.URLError as exc:
                self.log(f"ERR  attempt {attempt}/{retries}: {exc.reason}", "error")
            except Exception as exc:
                self.log(f"ERR  attempt {attempt}/{retries}: {exc}", "error")

            if attempt < retries:
                wait = 3 * attempt
                self.log(f"WAIT retrying in {wait}s", "muted")
                time.sleep(wait)

        self.log(f"DEAD all {retries} attempts failed for {name}", "error")
        self.counter(False)


class App:
    def __init__(self, master):
        self.master = master
        master.title("Killoxs x Litterbox")
        master.configure(bg=BG)
        master.resizable(False, False)
        master.protocol("WM_DELETE_WINDOW", self._on_close)
        master.update_idletasks()
        _dark_titlebar(master.winfo_id())

        self.monitoring_path = tk.StringVar()
        self.expiry_var      = tk.StringVar(value="72h")
        self.observer        = None
        self.upload_queue    = queue.Queue()
        self.worker          = None
        self._ok_count       = 0
        self._fail_count     = 0

        self._build_ui()

        if not WATCHDOG_AVAILABLE:
            self._log("watchdog not installed — pip install watchdog", "warn")

    def _build_ui(self):
        top = tk.Frame(self.master, bg=BG)
        top.pack(fill=tk.X, padx=28, pady=(20, 0))

        tk.Label(top, text="KILLOXS", font=("Segoe UI Black", 26, "bold"),
                 bg=BG, fg=ACCENT).pack(side=tk.LEFT)
        tk.Label(top, text=" × LITTERBOX", font=(F_UI, 26),
                 bg=BG, fg=FG).pack(side=tk.LEFT)

        self._dot = tk.Label(top, text="●", font=(F_MONO, 13), bg=BG, fg=SUBTEXT)
        self._dot.pack(side=tk.RIGHT)
        self._status_lbl = tk.Label(top, text="IDLE", font=(F_MONO, 8), bg=BG, fg=SUBTEXT)
        self._status_lbl.pack(side=tk.RIGHT, padx=(0, 5))

        tk.Frame(self.master, bg=BORDER, height=1).pack(fill=tk.X, padx=28, pady=(12, 16))

        self._section("WATCH FOLDER")
        fc = self._card()
        fr = tk.Frame(fc, bg=BG_CARD)
        fr.pack(fill=tk.X)
        tk.Entry(fr, textvariable=self.monitoring_path,
                 bg=BG_INPUT, fg=FG, insertbackground=ACCENT,
                 relief=tk.FLAT, font=(F_MONO, 9),
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT, width=44
                 ).pack(side=tk.LEFT, ipady=6, padx=(0, 8))
        self._btn(fr, "BROWSE", self._browse, style="ghost").pack(side=tk.LEFT)

        self._section("EXPIRY")
        ec = self._card()
        er = tk.Frame(ec, bg=BG_CARD)
        er.pack(fill=tk.X)
        for label in EXPIRY_OPTIONS:
            self._radio(er, label, label, self.expiry_var)

        br = tk.Frame(self.master, bg=BG)
        br.pack(fill=tk.X, padx=28, pady=(10, 0))
        self.btn_start = self._btn(br, "▶  START", self._start, style="primary", width=18)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_stop = self._btn(br, "■  STOP", self._stop, style="ghost", width=10)
        self.btn_stop.pack(side=tk.LEFT)
        self.btn_stop.config(state=tk.DISABLED)

        sr = tk.Frame(self.master, bg=BG)
        sr.pack(fill=tk.X, padx=28, pady=(12, 0))
        self._lbl_ok    = self._badge(sr, "OK",     "0", GREEN)
        self._lbl_fail  = self._badge(sr, "FAIL",   "0", RED)
        self._lbl_queue = self._badge(sr, "QUEUED", "0", YELLOW)

        self._section("LOG")
        lf = tk.Frame(self.master, bg=BG_PANEL,
                      highlightthickness=1, highlightbackground=BORDER)
        lf.pack(fill=tk.BOTH, padx=28, pady=(0, 6))
        sb = tk.Scrollbar(lf, bg=BG_PANEL, troughcolor=BG_PANEL, relief=tk.FLAT, width=7)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_box = tk.Text(
            lf, height=13, width=70,
            bg=BG_PANEL, fg=FG, font=(F_MONO, 9),
            relief=tk.FLAT, yscrollcommand=sb.set,
            state=tk.DISABLED, padx=10, pady=8,
            selectbackground=ACCENT_DIM, wrap=tk.NONE, cursor="arrow",
        )
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH)
        sb.config(command=self.log_box.yview)

        self.log_box.tag_config("success", foreground=GREEN)
        self.log_box.tag_config("error",   foreground=RED)
        self.log_box.tag_config("warn",    foreground=YELLOW)
        self.log_box.tag_config("info",    foreground=FG)
        self.log_box.tag_config("muted",   foreground=SUBTEXT)
        self.log_box.tag_config("ts",      foreground=SUBTEXT)
        self.log_box.tag_config("accent",  foreground=ACCENT)

        ft = tk.Frame(self.master, bg=BG)
        ft.pack(fill=tk.X, padx=28, pady=(4, 14))
        tk.Label(ft, text="killoxs.com  -  hello@killoxs.com  -  2026 Killoxs",
                 font=(F_UI, 9), bg=BG, fg=SUBTEXT).pack(side=tk.LEFT)
        self._btn(ft, "CLEAR", self._clear_log, style="ghost", width=8).pack(side=tk.RIGHT)

        self._tick()

    def _section(self, text):
        r = tk.Frame(self.master, bg=BG)
        r.pack(fill=tk.X, padx=28, pady=(8, 4))
        tk.Label(r, text=text, font=(F_MONO, 8, "bold"),
                 bg=BG, fg=SUBTEXT).pack(side=tk.LEFT)
        tk.Frame(r, bg=BORDER, height=1).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

    def _card(self):
        f = tk.Frame(self.master, bg=BG_CARD,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill=tk.X, padx=28, pady=(0, 4))
        inner = tk.Frame(f, bg=BG_CARD)
        inner.pack(fill=tk.X, padx=12, pady=10)
        return inner

    def _btn(self, parent, text, cmd, style="primary", width=None):
        kw = dict(text=text, command=cmd, font=(F_MONO, 9, "bold"),
                  relief=tk.FLAT, cursor="hand2", bd=0,
                  padx=14, pady=6, activeforeground=FG)
        if width:
            kw["width"] = width
        if style == "primary":
            kw.update(bg=ACCENT, fg=BG, activebackground=ACCENT_DIM)
        else:
            kw.update(bg=BG_CARD, fg=SUBTEXT, activebackground=BORDER,
                      highlightthickness=1, highlightbackground=BORDER)
        b = tk.Button(parent, **kw)
        if style == "primary":
            b.bind("<Enter>", lambda e: b.config(bg=ACCENT_DIM))
            b.bind("<Leave>", lambda e: b.config(bg=ACCENT))
        return b

    def _radio(self, parent, text, value, variable):
        rb = tk.Radiobutton(
            parent, text=text, variable=variable, value=value,
            bg=BG_CARD, fg=SUBTEXT, selectcolor=BG_CARD,
            activebackground=BG_CARD, activeforeground=ACCENT,
            font=(F_MONO, 9), indicatoron=0, relief=tk.FLAT,
            padx=12, pady=5, cursor="hand2", bd=1,
        )
        rb.pack(side=tk.LEFT, padx=(0, 4))

        def _refresh(*_):
            if variable.get() == value:
                rb.config(fg=ACCENT, highlightbackground=ACCENT,
                          highlightthickness=1, highlightcolor=ACCENT)
            else:
                rb.config(fg=SUBTEXT, highlightbackground=BORDER,
                          highlightthickness=1, highlightcolor=BORDER)

        variable.trace_add("write", _refresh)
        _refresh()

    def _badge(self, parent, label, value, color):
        f = tk.Frame(parent, bg=BG_CARD,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(side=tk.LEFT, padx=(0, 8), pady=2, ipadx=8, ipady=4)
        tk.Label(f, text=label, font=(F_MONO, 8),
                 bg=BG_CARD, fg=SUBTEXT).pack(side=tk.LEFT, padx=(0, 6))
        lbl = tk.Label(f, text=value, font=(F_MONO, 9, "bold"), bg=BG_CARD, fg=color)
        lbl.pack(side=tk.LEFT)
        return lbl

    def _log(self, message, tag="info"):
        self.master.after(0, self._append, message, tag)

    def _append(self, message, tag):
        self.log_box.config(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] ", "ts")
        self.log_box.insert(tk.END, f"{message}\n", tag)
        self.log_box.see(tk.END)
        self.log_box.config(state=tk.DISABLED)

    def _clear_log(self):
        self.log_box.config(state=tk.NORMAL)
        self.log_box.delete(1.0, tk.END)
        self.log_box.config(state=tk.DISABLED)

    def _copy_to_clipboard(self, text):
        self.master.after(0, self._do_copy, text)

    def _do_copy(self, text):
        if CLIPBOARD_AVAILABLE:
            try:
                pyperclip.copy(text)
                self._append("CLIP link copied", "accent")
            except Exception as exc:
                self._append(f"CLIP error: {exc}", "warn")
        else:
            self.master.clipboard_clear()
            self.master.clipboard_append(text)
            self._append("CLIP copied", "accent")

    def _update_counter(self, success):
        def _do():
            if success:
                self._ok_count += 1
                self._lbl_ok.config(text=str(self._ok_count))
            else:
                self._fail_count += 1
                self._lbl_fail.config(text=str(self._fail_count))
        self.master.after(0, _do)

    def _tick(self):
        self._lbl_queue.config(text=str(self.upload_queue.qsize()))
        self.master.after(500, self._tick)

    def _set_status(self, live):
        if live:
            self._dot.config(fg=GREEN)
            self._status_lbl.config(fg=GREEN, text="LIVE")
        else:
            self._dot.config(fg=SUBTEXT)
            self._status_lbl.config(fg=SUBTEXT, text="IDLE")

    def _browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.monitoring_path.set(folder)

    def _get_expiry(self):
        return EXPIRY_OPTIONS.get(self.expiry_var.get(), "72h")

    def _start(self):
        if not WATCHDOG_AVAILABLE:
            messagebox.showerror("Error", "watchdog not installed.\npip install watchdog")
            return
        path = self.monitoring_path.get()
        if not os.path.isdir(path):
            messagebox.showerror("Error", "Select a valid folder first.")
            return

        while not self.upload_queue.empty():
            try:
                self.upload_queue.get_nowait()
            except queue.Empty:
                break

        self._ok_count = self._fail_count = 0
        self._lbl_ok.config(text="0")
        self._lbl_fail.config(text="0")

        self.worker = UploadWorker(
            self.upload_queue,
            log_cb=self._log,
            copy_cb=self._copy_to_clipboard,
            expiry_cb=self._get_expiry,
            counter_cb=self._update_counter,
        )
        self.worker.start()

        handler = ImageUploadHandler(self.upload_queue)
        self.observer = Observer()
        self.observer.schedule(handler, path, recursive=False)
        self.observer.start()

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self._set_status(True)
        self._log(f"INIT {path}", "accent")
        self._log(f"CONF expiry={self._get_expiry()}", "muted")

    def _stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        if self.worker and self.worker.is_alive():
            self.upload_queue.put(UploadWorker.SENTINEL)
            self.worker.join(timeout=5)
            self.worker = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self._set_status(False)
        self._log("STOP", "muted")

    def _on_close(self):
        self._stop()
        self.master.destroy()


def main():
    root = tk.Tk()
    root.configure(bg=BG)
    try:
        root.wm_iconbitmap("")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
