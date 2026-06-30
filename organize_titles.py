"""
Gettel Title Organizer
Reads the CSV exported by the Gettel Title Scraper and organizes downloaded
PDFs into two folders inside your Downloads directory:
  - Property Sheets/   renamed from "Property XXXXX.pdf" → "XXXXX.pdf"
  - Title Documents/   renamed from site filename → "PID_filename.pdf"
"""

import csv
import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_default_downloads():
    return str(Path.home() / "Downloads")


def find_file(folder, name):
    """Case-insensitive file search in a flat folder."""
    target = name.lower()
    for f in os.listdir(folder):
        if f.lower() == target:
            return os.path.join(folder, f)
    return None


def organize(csv_path, downloads_path, log):
    prop_folder  = os.path.join(downloads_path, "Property Sheets")
    title_folder = os.path.join(downloads_path, "Title Documents")
    os.makedirs(prop_folder,  exist_ok=True)
    os.makedirs(title_folder, exist_ok=True)

    moved       = 0
    skipped     = 0
    not_found   = 0

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        log("CSV is empty — nothing to do.")
        return

    for row in rows:
        pid      = (row.get('PID') or '').strip()
        status   = (row.get('Status') or '').strip().lower()
        filename = (row.get('Filename') or '').strip()

        if not pid:
            continue

        # ── Property sheet: "Property XXXXX.pdf" → "Property Sheets/XXXXX.pdf" ──
        prop_src_name = f"Property {pid}.pdf"
        prop_src      = find_file(downloads_path, prop_src_name)
        if prop_src:
            dest = os.path.join(prop_folder, f"{pid}.pdf")
            if os.path.exists(dest):
                log(f"[SKIP]  {prop_src_name} → already exists as {pid}.pdf")
                skipped += 1
            else:
                shutil.move(prop_src, dest)
                log(f"[OK]    {prop_src_name} → Property Sheets/{pid}.pdf")
                moved += 1

        # ── Title / LINC: site filename → "Title Documents/PID_filename.pdf" ──
        if status == 'downloaded' and filename:
            title_src = find_file(downloads_path, filename)
            if title_src:
                new_name = f"{pid}_{filename}" if not filename.startswith(f"{pid}_") else filename
                dest     = os.path.join(title_folder, new_name)
                if os.path.exists(dest):
                    log(f"[SKIP]  {filename} → already exists as {new_name}")
                    skipped += 1
                else:
                    shutil.move(title_src, dest)
                    log(f"[OK]    {filename} → Title Documents/{new_name}")
                    moved += 1
            else:
                log(f"[MISS]  {filename} (PID {pid}) — not found in Downloads")
                not_found += 1

    log("")
    log(f"Done.  Moved: {moved}  |  Already existed: {skipped}  |  Not found: {not_found}")
    if not_found:
        log("Files marked [MISS] may still be downloading or may have been moved already.")


# ── GUI ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gettel Title Organizer")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e", padx=16, pady=16)

        label_style  = dict(bg="#1a1a2e", fg="#e0e0e0", font=("Segoe UI", 9))
        entry_style  = dict(bg="#0d0d1a", fg="#e0e0e0", insertbackground="#e0e0e0",
                            relief="flat", bd=4, font=("Consolas", 9))
        btn_style    = dict(relief="flat", bd=0, padx=10, pady=4,
                            font=("Segoe UI", 9, "bold"), cursor="hand2")

        # CSV row
        tk.Label(self, text="CSV file exported by the scraper:", **label_style).grid(
            row=0, column=0, sticky="w", pady=(0, 2))
        csv_frame = tk.Frame(self, bg="#1a1a2e")
        csv_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.csv_var = tk.StringVar()
        tk.Entry(csv_frame, textvariable=self.csv_var, width=52, **entry_style).pack(
            side="left", fill="x", expand=True)
        tk.Button(csv_frame, text="Browse…", bg="#2a6496", fg="white",
                  command=self.browse_csv, **btn_style).pack(side="left", padx=(6, 0))

        # Downloads row
        tk.Label(self, text="Downloads folder:", **label_style).grid(
            row=2, column=0, sticky="w", pady=(0, 2))
        dl_frame = tk.Frame(self, bg="#1a1a2e")
        dl_frame.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        self.dl_var = tk.StringVar(value=get_default_downloads())
        tk.Entry(dl_frame, textvariable=self.dl_var, width=52, **entry_style).pack(
            side="left", fill="x", expand=True)
        tk.Button(dl_frame, text="Browse…", bg="#2a6496", fg="white",
                  command=self.browse_dl, **btn_style).pack(side="left", padx=(6, 0))

        # Run button
        tk.Button(self, text="Organize Files", bg="#28783a", fg="white",
                  command=self.run, **btn_style).grid(row=4, column=0, sticky="w", pady=(0, 10))

        # Log
        self.log_box = scrolledtext.ScrolledText(
            self, width=70, height=16, state="disabled",
            bg="#0d0d1a", fg="#aaaaaa", font=("Consolas", 9),
            relief="flat", bd=4, insertbackground="#e0e0e0")
        self.log_box.grid(row=5, column=0, pady=(0, 0))

        self.columnconfigure(0, weight=1)

    def browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select scraper CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=get_default_downloads())
        if path:
            self.csv_var.set(path)

    def browse_dl(self):
        path = filedialog.askdirectory(title="Select Downloads folder",
                                       initialdir=self.dl_var.get())
        if path:
            self.dl_var.set(path)

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.update_idletasks()

    def run(self):
        csv_path  = self.csv_var.get().strip()
        dl_path   = self.dl_var.get().strip()

        if not csv_path or not os.path.isfile(csv_path):
            messagebox.showerror("Error", "Please select a valid CSV file.")
            return
        if not dl_path or not os.path.isdir(dl_path):
            messagebox.showerror("Error", "Please select a valid Downloads folder.")
            return

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.log(f"CSV:       {csv_path}")
        self.log(f"Downloads: {dl_path}")
        self.log("")

        try:
            organize(csv_path, dl_path, self.log)
        except Exception as e:
            self.log(f"[ERROR] {e}")
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    app = App()
    app.mainloop()
