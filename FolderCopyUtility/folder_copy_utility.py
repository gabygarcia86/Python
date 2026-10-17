import os
import shutil
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path


APP_TITLE = "Folder Copy Utility"


class FolderCopyApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x650")
        self.root.minsize(700, 560)

        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a source and destination to begin.")
        self.events = queue.Queue()
        self.copying = False

        self._build_ui()
        self.root.after(100, self._process_events)

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Folder Copy Utility",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            outer,
            text="Copy a file or folder into every immediate subfolder of a destination.",
        ).pack(anchor="w", pady=(2, 14))

        source_frame = ttk.LabelFrame(outer, text="1. Source file or folder", padding=10)
        source_frame.pack(fill="x", pady=(0, 10))
        source_frame.columnconfigure(0, weight=1)
        ttk.Entry(source_frame, textvariable=self.source_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(source_frame, text="Choose File…", command=self.choose_file).grid(
            row=0, column=1, padx=(0, 6)
        )
        ttk.Button(source_frame, text="Choose Folder…", command=self.choose_source_folder).grid(
            row=0, column=2
        )

        destination_frame = ttk.LabelFrame(
            outer, text="2. Destination parent folder", padding=10
        )
        destination_frame.pack(fill="x", pady=(0, 10))
        destination_frame.columnconfigure(0, weight=1)
        ttk.Entry(destination_frame, textvariable=self.destination_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(destination_frame, text="Browse…", command=self.choose_destination).grid(
            row=0, column=1
        )

        preview_frame = ttk.LabelFrame(
            outer, text="3. Target subfolders (immediate children only)", padding=10
        )
        preview_frame.pack(fill="both", expand=True, pady=(0, 10))
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        self.targets = ttk.Treeview(
            preview_frame, columns=("path",), show="tree headings", height=7
        )
        self.targets.heading("#0", text="Target folder")
        self.targets.heading("path", text="Full path")
        self.targets.column("#0", width=190, stretch=False)
        self.targets.column("path", width=460, stretch=True)
        yscroll = ttk.Scrollbar(
            preview_frame, orient="vertical", command=self.targets.yview
        )
        xscroll = ttk.Scrollbar(
            preview_frame, orient="horizontal", command=self.targets.xview
        )
        self.targets.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.targets.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 10))
        ttk.Button(controls, text="Refresh Preview", command=self.refresh_preview).pack(
            side="left"
        )
        self.copy_button = ttk.Button(
            controls, text="Copy to All Targets", command=self.start_copy
        )
        self.copy_button.pack(side="right")

        results_frame = ttk.LabelFrame(outer, text="Activity log", padding=8)
        results_frame.pack(fill="both", expand=True)
        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(results_frame, height=6, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(
            fill="x", pady=(8, 0)
        )

    def choose_file(self):
        path = filedialog.askopenfilename(title="Choose a file to copy")
        if path:
            self.source_var.set(path)
            self.refresh_preview()

    def choose_source_folder(self):
        path = filedialog.askdirectory(title="Choose a folder to copy")
        if path:
            self.source_var.set(path)
            self.refresh_preview()

    def choose_destination(self):
        path = filedialog.askdirectory(title="Choose the destination parent folder")
        if path:
            self.destination_var.set(path)
            self.refresh_preview()

    def _get_source_and_targets(self):
        source_text = self.source_var.get().strip().strip('"')
        destination_text = self.destination_var.get().strip().strip('"')
        if not source_text:
            raise ValueError("Choose a source file or folder first.")
        if not destination_text:
            raise ValueError("Choose a destination parent folder first.")

        source = Path(source_text).expanduser().resolve()
        destination = Path(destination_text).expanduser().resolve()

        if not source.exists():
            raise ValueError("The selected source does not exist.")
        if not (source.is_file() or source.is_dir()):
            raise ValueError("The source must be a regular file or folder.")
        if not destination.is_dir():
            raise ValueError("The destination must be an existing folder.")

        # Avoid copying a folder into itself or into one of its own descendants.
        if source.is_dir():
            try:
                destination.relative_to(source)
                raise ValueError(
                    "The destination is inside the source folder. Choose a destination "
                    "outside the source folder to avoid recursive copying."
                )
            except ValueError as exc:
                if "inside the source folder" in str(exc):
                    raise

        targets = sorted(
            (p for p in destination.iterdir() if p.is_dir()),
            key=lambda p: p.name.casefold(),
        )

        # Avoid copying a source folder into itself or one of its descendants.
        if source.is_dir():
            safe_targets = []
            for target in targets:
                try:
                    target.resolve().relative_to(source)
                    continue
                except ValueError:
                    pass
                safe_targets.append(target)
            targets = safe_targets

        return source, destination, targets

    def refresh_preview(self):
        self.targets.delete(*self.targets.get_children())
        try:
            source, destination, targets = self._get_source_and_targets()
        except (ValueError, OSError) as exc:
            self.status_var.set(str(exc))
            return

        if not targets:
            self.status_var.set("No immediate subfolders were found in the destination.")
            return

        for target in targets:
            self.targets.insert("", "end", text=target.name, values=(str(target),))
        self.status_var.set(
            f"Ready: {len(targets)} target folder(s). Source: {source.name}"
        )

    def _write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start_copy(self):
        if self.copying:
            return

        try:
            source, destination, targets = self._get_source_and_targets()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Cannot start copy", str(exc), parent=self.root)
            return

        if not targets:
            messagebox.showinfo(
                "No target folders",
                "The destination does not contain any immediate subfolders.",
                parent=self.root,
            )
            return

        preview = (
            f"Source:\n{source}\n\n"
            f"Destination parent:\n{destination}\n\n"
            f"Target folders: {len(targets)}\n\n"
            "Continue with the copy?"
        )
        if not messagebox.askyesno("Confirm copy", preview, parent=self.root):
            return

        # Ask once how to handle existing destination items.
        conflict_mode = "ask"
        existing_targets = [
            target / source.name
            for target in targets
            if (target / source.name).exists()
        ]
        if existing_targets:
            choice = messagebox.askyesnocancel(
                "Items already exist",
                f"{len(existing_targets)} target(s) already contain an item named "
                f"'{source.name}'.\n\n"
                "Yes = replace existing items\n"
                "No = skip existing items\n"
                "Cancel = stop without copying",
                parent=self.root,
            )
            if choice is None:
                return
            conflict_mode = "replace" if choice else "skip"

        self.copying = True
        self.copy_button.configure(state="disabled")
        self.status_var.set("Copying…")
        self._write_log(f"Starting copy: {source} -> {len(targets)} target(s)")

        worker = threading.Thread(
            target=self._copy_worker,
            args=(source, targets, conflict_mode),
            daemon=True,
        )
        worker.start()

    def _copy_worker(self, source, targets, conflict_mode):
        success = 0
        skipped = 0
        failures = 0

        for target in targets:
            destination_item = target / source.name
            try:
                if destination_item.exists() or destination_item.is_symlink():
                    if conflict_mode == "skip":
                        skipped += 1
                        self.events.put(("log", f"SKIPPED: {destination_item}"))
                        continue
                    if conflict_mode != "replace":
                        failures += 1
                        self.events.put(
                            ("log", f"FAILED: {destination_item} already exists.")
                        )
                        continue
                    self._remove_existing(destination_item)

                if source.is_dir():
                    shutil.copytree(source, destination_item, symlinks=True)
                else:
                    shutil.copy2(source, destination_item)

                success += 1
                self.events.put(("log", f"COPIED: {destination_item}"))
            except Exception as exc:
                failures += 1
                self.events.put(("log", f"FAILED: {destination_item} — {exc}"))

        self.events.put(
            ("done", (success, skipped, failures))
        )

    @staticmethod
    def _remove_existing(path):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    def _process_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._write_log(payload)
                elif kind == "done":
                    success, skipped, failures = payload
                    self.copying = False
                    self.copy_button.configure(state="normal")
                    summary = (
                        f"Finished. Copied: {success} | Skipped: {skipped} "
                        f"| Failed: {failures}"
                    )
                    self.status_var.set(summary)
                    self._write_log(summary)
                    messagebox.showinfo("Copy complete", summary, parent=self.root)
                    self.refresh_preview()
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)


def main():
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass

    FolderCopyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
