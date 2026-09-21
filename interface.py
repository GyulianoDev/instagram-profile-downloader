from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from download_profile import (
    PROJECT_DIR,
    Configuration,
    session_file,
    run,
    normalize_login,
    normalize_profile,
)


class DownloaderInterface:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.queue_: queue.Queue[tuple[str, object]] = queue.Queue()
        self.downloading = False

        self.profile = tk.StringVar()
        self.output = tk.StringVar(value=str(PROJECT_DIR / "downloads"))
        self.use_login = tk.BooleanVar(value=False)
        self.use_browser = tk.BooleanVar(value=False)
        self.browser = tk.StringVar(value="Brave")
        self.user = tk.StringVar()
        self.password = tk.StringVar()
        self.show_password = tk.BooleanVar(value=False)
        self.full = tk.BooleanVar(value=False)
        self.update = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready to download")
        self.session_notice = tk.StringVar(value="")
        self.last_error = ""
        self.checkpoint_shown = False

        self._configure_window()
        self._build_ui()
        self._toggle_login(select_full=False)
        self.root.after(100, self._process_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_window(self) -> None:
        self.root.title("Instagram Profile Downloader")
        self.root.geometry("760x760")
        self.root.minsize(640, 620)
        self.root.configure(background="#f4f5f7")

        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Tela.TFrame", background="#f4f5f7")
        style.configure(
            "Titulo.TLabel",
            background="#f4f5f7",
            foreground="#171717",
            font=("Segoe UI", 20, "bold"),
        )
        style.configure(
            "Subtitulo.TLabel",
            background="#f4f5f7",
            foreground="#565b65",
            font=("Segoe UI", 10),
        )
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1)
        style.configure(
            "Card.TLabelframe.Label",
            background="#ffffff",
            foreground="#252525",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", background="#ffffff", foreground="#252525")
        style.configure("Dica.TLabel", background="#ffffff", foreground="#68707c")
        style.configure("Acao.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 10))

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding=24, style="Tela.TFrame")
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)

        ttk.Label(main_frame, text="Instagram Profile Downloader", style="Titulo.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            main_frame,
            text="Choose a profile, sign in to your account if necessary, and monitor the download.",
            style="Subtitulo.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 18))

        destination = ttk.LabelFrame(
            main_frame, text="Profile and destination", padding=16, style="Card.TLabelframe"
        )
        destination.grid(row=2, column=0, sticky="ew")
        destination.columnconfigure(0, weight=1)

        ttk.Label(destination, text="Profile to download", style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.profile_entry = ttk.Entry(destination, textvariable=self.profile, font=("Segoe UI", 11))
        self.profile_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 12))
        ttk.Label(
            destination,
            text="Accepts a username, @username, or full profile URL.",
            style="Dica.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(0, 12))

        ttk.Label(destination, text="Save to", style="Card.TLabel").grid(
            row=3, column=0, sticky="w"
        )
        self.output_entry = ttk.Entry(destination, textvariable=self.output)
        self.output_entry.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        self.choose_folder_button = ttk.Button(
            destination, text="Choose folder", command=self._choose_folder
        )
        self.choose_folder_button.grid(row=4, column=1, padx=(8, 0), pady=(5, 0))

        login = ttk.LabelFrame(
            main_frame, text="Login and options", padding=16, style="Card.TLabelframe"
        )
        login.grid(row=3, column=0, sticky="ew", pady=(14, 14))
        login.columnconfigure(1, weight=1)

        self.use_login_check = ttk.Checkbutton(
            login,
            text="Use login (required for private profiles, stories, and highlights)",
            variable=self.use_login,
            command=self._toggle_login,
        )
        self.use_login_check.grid(row=0, column=0, columnspan=3, sticky="w")

        self.use_browser_check = ttk.Checkbutton(
            login,
            text="Sign in using the browser (recommended)",
            variable=self.use_browser,
            command=self._toggle_login_method,
        )
        self.use_browser_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(login, text="Browser", style="Card.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        self.browser_combo = ttk.Combobox(
            login,
            textvariable=self.browser,
            values=("Brave", "Chrome", "Edge", "Firefox"),
            state="readonly",
            width=16,
        )
        self.browser_combo.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(8, 0))

        ttk.Label(login, text="Username or email", style="Card.TLabel").grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )
        self.user_entry = ttk.Entry(login, textvariable=self.user)
        self.user_entry.grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(8, 0))
        self.user_entry.bind("<FocusOut>", lambda _evento: self._check_session())

        ttk.Label(login, text="Password", style="Card.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )
        self.password_entry = ttk.Entry(login, textvariable=self.password, show="*")
        self.password_entry.grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=(8, 0))
        self.show_button = ttk.Checkbutton(
            login,
            text="Show",
            variable=self.show_password,
            command=self._toggle_password_visibility,
        )
        self.show_button.grid(row=4, column=2, sticky="w", padx=(8, 0), pady=(8, 0))

        ttk.Label(login, textvariable=self.session_notice, style="Dica.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(6, 4)
        )

        self.full_check = ttk.Checkbutton(
            login,
            text="Also download Reels, current stories, highlights, tagged posts, and IGTV",
            variable=self.full,
        )
        self.full_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.update_check = ttk.Checkbutton(
            login,
            text="Fast update (stop when already downloaded content is found)",
            variable=self.update,
        )
        self.update_check.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))
        progress = ttk.LabelFrame(
            main_frame, text="Progress", padding=12, style="Card.TLabelframe"
        )
        progress.grid(row=4, column=0, sticky="nsew")
        progress.columnconfigure(0, weight=1)
        progress.rowconfigure(2, weight=1)

        ttk.Label(progress, textvariable=self.status, style="Card.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.progress_bar = ttk.Progressbar(progress, mode="indeterminate")
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(7, 10))

        self.log_text = tk.Text(
            progress,
            height=9,
            wrap="word",
            state="disabled",
            background="#111827",
            foreground="#e5e7eb",
            insertbackground="#ffffff",
            relief="flat",
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        self.log_text.grid(row=2, column=0, sticky="nsew")

        self.download_button = ttk.Button(
            main_frame,
            text="Download profile",
            command=self._start_download,
            style="Acao.TButton",
        )
        self.download_button.grid(row=5, column=0, sticky="ew", pady=(14, 0))

        self.profile_entry.focus_set()

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.root,
            title="Choose where to save the profiles",
            initialdir=self.output.get() or str(PROJECT_DIR),
        )
        if folder:
            self.output.set(folder)

    def _toggle_login(self, select_full: bool = True) -> None:
        enabled = self.use_login.get()
        self.use_browser_check.configure(state="normal" if enabled else "disabled")
        self.full_check.configure(state="normal" if enabled else "disabled")

        if enabled:
            if select_full:
                self.full.set(True)
        else:
            self.use_browser.set(False)
            self.password.set("")
            self.full.set(False)
            self.session_notice.set("")
        self._toggle_login_method()

    def _toggle_login_method(self) -> None:
        enabled = self.use_login.get()
        via_browser = enabled and self.use_browser.get()
        credentials_state = "disabled" if via_browser or not enabled else "normal"
        self.user_entry.configure(state=credentials_state)
        self.password_entry.configure(state=credentials_state)
        self.show_button.configure(state=credentials_state)
        self.browser_combo.configure(state="readonly" if via_browser else "disabled")

        if via_browser:
            self.password.set("")
            if self.browser.get().lower() == "brave":
                self.session_notice.set(
                    "An isolated window will open; the Brave instance you already use can remain open."
                )
            else:
                self.session_notice.set(
                    "Log in to instagram.com in that browser before starting the download."
                )
        elif enabled:
            self._check_session()
            self.user_entry.focus_set()

    def _toggle_password_visibility(self) -> None:
        self.password_entry.configure(show="" if self.show_password.get() else "*")

    def _check_session(self) -> None:
        if not self.use_login.get() or self.use_browser.get():
            return
        try:
            user = normalize_login(self.user.get())
        except argparse.ArgumentTypeError:
            self.session_notice.set("")
            return

        file = session_file(user)
        if file.exists():
            self.session_notice.set("Saved session found; the password can be left blank.")
        else:
            self.session_notice.set("First login: enter the password; it will not be saved.")

    def _start_download(self) -> None:
        try:
            profile = normalize_profile(self.profile.get())
        except argparse.ArgumentTypeError as error:
            messagebox.showerror("Invalid profile", str(error), parent=self.root)
            self.profile_entry.focus_set()
            return

        texto_saida = self.output.get().strip()
        if not texto_saida:
            messagebox.showerror("Folder required", "Choose a destination folder.", parent=self.root)
            return

        login: str | None = None
        browser: str | None = None
        if self.use_login.get():
            if self.use_browser.get():
                browser = self.browser.get().lower()
            else:
                try:
                    login = normalize_login(self.user.get())
                except argparse.ArgumentTypeError as error:
                    messagebox.showerror("Invalid login", str(error), parent=self.root)
                    self.user_entry.focus_set()
                    return

                file = session_file(login)
                if not file.exists() and not self.password.get():
                    messagebox.showerror(
                        "Password required",
                        "Enter the password on the first login. It will be used only in memory.",
                        parent=self.root,
                    )
                    self.password_entry.focus_set()
                    return

        configuration = Configuration(
            profiles=(profile,),
            output=Path(texto_saida).expanduser().resolve(),
            login=login,
            browser=browser,
            full=self.full.get(),
            update=self.update.get(),
        )
        password = self.password.get() if login else None
        self.password.set("")
        self._clear_log()
        self.last_error = ""
        self.checkpoint_shown = False
        self._set_busy(True)
        self._log("Starting download...")

        threading.Thread(
            target=self._run_in_background,
            args=(configuration, password),
            daemon=True,
            name="download-instagram",
        ).start()

    def _run_in_background(self, configuration: Configuration, password: str | None) -> None:
        code = run(
            configuration,
            password=password,
            get_password=lambda: "",
            get_2fa_code=self._ask_2fa_code,
            on_checkpoint=lambda url: self.queue_.put(("checkpoint", url)),
            logger=self._log,
        )
        password = None
        self.queue_.put(("completed", code))

    def _ask_2fa_code(self) -> str:
        event = threading.Event()
        response: list[str] = []

        def ask() -> None:
            code = simpledialog.askstring(
                "Two-factor authentication",
                "Enter the code sent by Instagram:",
                parent=self.root,
            )
            response.append(code or "")
            event.set()

        self.root.after(0, ask)
        event.wait()
        return response[0]

    def _log(self, message: str) -> None:
        self.queue_.put(("log", message))

    def _process_queue(self) -> None:
        try:
            while True:
                event_type, value = self.queue_.get_nowait()
                if event_type == "log":
                    message = str(value)
                    self._append_log(message)
                    self.status.set(message.splitlines()[-1][:90])
                    if any(
                        marker in message.lower()
                        for marker in ("error:", "unauthorized", "login required", "could not")
                    ):
                        self.last_error = message.splitlines()[-1]
                elif event_type == "completed":
                    self._finish_download(int(value))
                elif event_type == "checkpoint":
                    self._show_checkpoint(str(value))
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._process_queue)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _show_checkpoint(self, url: str) -> None:
        self.checkpoint_shown = True
        open_page = messagebox.askyesno(
            "Confirmation required by Instagram",
            "Instagram blocked the login until you confirm it was you.\n\n"
            "Do you want to open the official confirmation page in the browser?\n\n"
            "If only the home page opens, log in to your account and use the option "
            "'session already open in the browser' in the application.",
            parent=self.root,
        )
        if open_page:
            webbrowser.open(url, new=2)

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self.downloading = busy
        self.download_button.configure(state="disabled" if busy else "normal")
        self.profile_entry.configure(state="disabled" if busy else "normal")
        self.output_entry.configure(state="disabled" if busy else "normal")
        self.choose_folder_button.configure(state="disabled" if busy else "normal")
        self.use_login_check.configure(state="disabled" if busy else "normal")
        self.update_check.configure(state="disabled" if busy else "normal")
        if busy:
            for control in (
                self.user_entry,
                self.password_entry,
                self.show_button,
                self.use_browser_check,
                self.browser_combo,
                self.full_check,
            ):
                control.configure(state="disabled")
            self.status.set("Downloading...")
            self.progress_bar.start(12)
        else:
            self.progress_bar.stop()
            self._toggle_login(select_full=False)

    def _finish_download(self, code: int) -> None:
        self._set_busy(False)
        if code == 0:
            self.status.set("Download completed")
            messagebox.showinfo(
                "Completed",
                f"Files saved in:\n{self.output.get()}",
                parent=self.root,
            )
        elif code == 3:
            self.status.set("Confirm the login in the browser and try again")
            if not self.checkpoint_shown:
                messagebox.showwarning(
                    "Confirmation required",
                    "Confirm access on Instagram and try the download again.",
                    parent=self.root,
                )
        else:
            self.status.set("Download not completed")
            detail = self.last_error or "Check the messages in the progress area."
            messagebox.showerror(
                "Could not complete",
                f"{detail}\n\nAlso check the messages in the progress area.",
                parent=self.root,
            )

    def _close(self) -> None:
        if self.downloading and not messagebox.askyesno(
            "Interrupt download?",
            "A download is in progress. Closing the window will interrupt the process.",
            parent=self.root,
        ):
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DownloaderInterface(root)
    root.mainloop()


if __name__ == "__main__":
    main()
