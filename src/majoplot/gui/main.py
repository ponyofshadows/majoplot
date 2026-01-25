from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from collections import OrderedDict
from typing import Any

from ..app.cli import load_named_objects  # reuse discovery helper
from ..domain.base import fail_signal, Figure
from ..domain.utils import pack_into_project, group_into_axes, group_into_figure
from ..infra.plotters.origin import OriginCOM, plot as oplot
from ..infra.plotters.matplot import plot as mplot


class _LRUCache:
    """A tiny LRU cache for rendered matplotlib Figure previews."""

    def __init__(self, maxsize: int = 3) -> None:
        self.maxsize = maxsize
        self._d: OrderedDict[int, Any] = OrderedDict()

    def get(self, key: int) -> Any | None:
        if key not in self._d:
            return None
        self._d.move_to_end(key)
        return self._d[key]

    def put(self, key: int, value: Any) -> None:
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = value
        while len(self._d) > self.maxsize:
            _, victim = self._d.popitem(last=False)
            try:
                import matplotlib.pyplot as plt
                plt.close(victim)
            except Exception:
                pass


    def clear(self) -> None:
        try:
            import matplotlib.pyplot as plt
            for v in self._d.values():
                plt.close(v)
        except Exception:
            pass
        self._d.clear()



class MainWindow(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master)
        self.master = master

        # State
        self.importers: dict[str, Any] = {}
        self.scenarios: dict[str, Any] = {}
        self.figures: list[Figure] = []
        self.raw_files_to_import: list[Path] = []

        self._preview_cache = _LRUCache(maxsize=3)
        self._current_preview_canvas = None  # FigureCanvasTkAgg

        # UI variables
        self.importer_var = tk.StringVar(value="")
        self.scenario_var = tk.StringVar(value="")
        self.proj_dir_var = tk.StringVar(value=str(Path.cwd()))
        self.save_mode_var = tk.StringVar(value="attach")  # attach|overwrite

        # Global archive inputs
        self.global_proj_name_var = tk.StringVar(value="")
        self.global_folder_path_var = tk.StringVar(value="")

        # Per-figure archive editor
        self.edit_proj_name_var = tk.StringVar(value="")
        self.edit_folder_path_var = tk.StringVar(value="")

        self._build_ui()
        self._load_importers()

    # ---------------- UI construction ----------------
    def _build_ui(self) -> None:
        self.master.title("Majoplot")
        self.master.geometry("1400x720")

        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=8)

        ttk.Label(top, text="Importer").pack(side=tk.LEFT)
        self.importer_cb = ttk.Combobox(top, textvariable=self.importer_var, state="readonly", width=20)
        self.importer_cb.pack(side=tk.LEFT, padx=(6, 12))
        self.importer_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_importer_selected())

        ttk.Label(top, text="Scenario").pack(side=tk.LEFT)
        self.scenario_cb = ttk.Combobox(top, textvariable=self.scenario_var, state="readonly", width=30)
        self.scenario_cb.pack(side=tk.LEFT, padx=(6, 12))

        ttk.Button(top, text="Select raw files...", command=self._pick_raw_files).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Raw files → Figures", command=self._import_figures).pack(side=tk.LEFT, padx=(0, 24))
        ttk.Button(top, text="Delete all figures", command=self._delete_all_figures).pack(side=tk.RIGHT)

        # Main body: left raw files / middle preview / right save
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Left: raw files
        left = ttk.Frame(body)
        body.add(left, weight=2)
        ttk.Label(left, text="Raw files").pack(anchor="w")
        self.raw_file_list = tk.Listbox(left, height=10)
        self.raw_file_list.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # Middle: figure list + preview
        mid = ttk.PanedWindow(body, orient=tk.HORIZONTAL)
        body.add(mid, weight=12)

        mid_left = ttk.Frame(mid)
        mid.add(mid_left, weight=2)
        ttk.Label(mid_left, text="Figures").pack(anchor="w")
        self.figure_list = tk.Listbox(mid_left)
        self.figure_list.pack(fill=tk.BOTH, expand=True, pady=(4, 6))
        self.figure_list.bind("<<ListboxSelect>>", lambda _e: self._on_figure_selected())

        # Per-figure actions
        action = ttk.LabelFrame(mid_left, text="Selected Figure")
        action.pack(fill=tk.X)

        row1 = ttk.Frame(action)
        row1.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(row1, text="Delete", command=self._delete_selected_figure).pack(side=tk.LEFT)
        ttk.Button(row1, text="Save this...", command=self._save_selected_figure).pack(side=tk.LEFT, padx=(6, 0))

        row2 = ttk.Frame(action)
        row2.pack(fill=tk.X, padx=6, pady=(4, 2))
        ttk.Label(row2, text="proj_name").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.edit_proj_name_var, width=10).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(row2, text="folder_path").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.edit_folder_path_var, width=16).pack(side=tk.LEFT, padx=(6, 0))

        row3 = ttk.Frame(action)
        row3.pack(fill=tk.X, padx=6, pady=(2, 6))
        ttk.Button(row3, text="Apply (append)", command=lambda: self._apply_archive_to_selected(overwrite=False)).pack(side=tk.LEFT)
        ttk.Button(row3, text="Apply (overwrite)", command=lambda: self._apply_archive_to_selected(overwrite=True)).pack(side=tk.LEFT, padx=(6, 0))

        mid_right = ttk.Frame(mid)
        mid.add(mid_right, weight=8)
        ttk.Label(mid_right, text="Matplotlib preview").pack(anchor="w")
        self.preview_host = ttk.Frame(mid_right)
        self.preview_host.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # Right: save all
        right = ttk.Frame(body)
        body.add(right, weight=2)

        save_box = ttk.LabelFrame(right, text="Save all to OPJU")
        save_box.pack(fill=tk.BOTH, expand=True)

        g1 = ttk.Frame(save_box)
        g1.pack(fill=tk.X, padx=8, pady=(8, 4))
        ttk.Label(g1, text="proj_name").pack(side=tk.LEFT)
        ttk.Entry(g1, textvariable=self.global_proj_name_var, width=18).pack(side=tk.LEFT, padx=(6, 0))

        g2 = ttk.Frame(save_box)
        g2.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(g2, text="folder_path").pack(side=tk.LEFT)
        ttk.Entry(g2, textvariable=self.global_folder_path_var, width=18).pack(side=tk.LEFT, padx=(6, 0))

        g3 = ttk.Frame(save_box)
        g3.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(g3, text="Append to all", command=lambda: self._apply_archive_to_all(overwrite=False)).pack(side=tk.LEFT)
        ttk.Button(g3, text="Overwrite all", command=lambda: self._apply_archive_to_all(overwrite=True)).pack(side=tk.LEFT, padx=(6, 0))

        g4 = ttk.Frame(save_box)
        g4.pack(fill=tk.X, padx=8, pady=(10, 4))
        ttk.Label(g4, text="OPJU directory").pack(side=tk.LEFT)
        proj_entry = ttk.Entry(g4, textvariable=self.proj_dir_var, state="readonly")
        proj_entry.pack(side=tk.TOP, padx=(6, 6), fill=tk.X, expand=True)
        proj_entry.bind("<Button-1>", lambda _e: self._pick_proj_dir())

        ttk.Button(g4, text="Choose...", command=self._pick_proj_dir).pack(side=tk.LEFT)


        g5 = ttk.Frame(save_box)
        g5.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(g5, text="Mode").pack(side=tk.LEFT)
        ttk.Radiobutton(g5, text="Attach", variable=self.save_mode_var, value="attach").pack(side=tk.LEFT, padx=(6, 0))
        ttk.Radiobutton(g5, text="Overwrite", variable=self.save_mode_var, value="overwrite").pack(side=tk.LEFT, padx=(6, 0))

        ttk.Button(save_box, text="Save ALL", command=self._save_all).pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)

        self.pack(fill=tk.BOTH, expand=True)

    # ---------------- Data discovery ----------------
    def _load_importers(self) -> None:
        self.importers = load_named_objects("majoplot.domain.importers")
        names = sorted(self.importers.keys())
        self.importer_cb["values"] = names
        if names:
            self.importer_var.set(names[0])
            self._on_importer_selected()

    def _on_importer_selected(self) -> None:
        name = self.importer_var.get()
        if not name or name not in self.importers:
            return
        self.scenarios = load_named_objects(f"majoplot.domain.scenarios.{name}")
        snames = sorted(self.scenarios.keys())
        self.scenario_cb["values"] = snames
        if snames:
            try:
                self.scenario_var.set(self.importers[name].prefs_scenario)
            except AttributeError:
                self.scenario_var.set(snames[0])

    # ---------------- Import flow ----------------
    def _pick_raw_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select raw data files",
            initialdir=str(Path.cwd()),
            filetypes=[("All files", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            pp = Path(p).resolve()
            self.raw_files_to_import.append(pp)
            self.raw_file_list.insert(tk.END, str(pp))

    def _import_figures(self) -> None:
        importer_name = self.importer_var.get()
        scenario_name = self.scenario_var.get()
        if not importer_name or importer_name not in self.importers:
            messagebox.showerror("Error", "Please choose an importer.")
            return
        if not scenario_name or scenario_name not in self.scenarios:
            messagebox.showerror("Error", "Please choose a scenario.")
            return
        if not self.raw_files_to_import:
            messagebox.showwarning("No files", "Please select raw files first.")
            return

        importer = self.importers[importer_name]
        scenario = self.scenarios[scenario_name]

        # Only import files not yet imported into figures in this session
        new_paths = self.raw_files_to_import
        self.raw_files_to_import = []
        self.raw_file_list.delete(0, tk.END)

        raw_datas = []
        for path in new_paths:
            try:
                with open(path, encoding="utf-8") as fp:
                    raw = importer.fetch_raw_data(fp, path.stem)
                if raw is not fail_signal:
                    raw_datas.append(raw)
            except Exception as e:
                messagebox.showerror("Import error", f"Failed to read {path}:\n{e}")
                return

        try:
            datas = scenario.preprocess(raw_datas)
        except Exception as e:
            messagebox.showerror("Preprocess error", f"Scenario preprocess failed:\n{e}")
            return

        
        # Match CLI logic: Data -> Axes -> Figure
        try:
            axes_pool = group_into_axes(datas, scenario)
            figures = group_into_figure(axes_pool, scenario)
        except Exception as e:
            messagebox.showerror(
                "Grouping error",
                "Failed to group Data into Figures.\n"
                f"{e}",
            )
            return

        added = 0
        for fig in figures:
            if not isinstance(fig, Figure):
                continue
            self.figures.append(fig)
            self.figure_list.insert(tk.END, fig.spec.name)
            added += 1

        if added == 0:
            messagebox.showinfo("No figures", "No figures were produced from the selected files.")
            return

        self._preview_cache.clear()

    # ---------------- Figure selection & preview ----------------
    def _selected_index(self) -> int | None:
        sel = self.figure_list.curselection()
        if not sel:
            return None
        return int(sel[0])

    def _on_figure_selected(self) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self.figures):
            return
        fig = self.figures[idx]

        # Populate editor with a single pair if exists, else blank.
        if fig.proj_folder:
            # choose the first (stable ordering not guaranteed)
            proj_name, folder = next(iter(fig.proj_folder.items()))
            self.edit_proj_name_var.set(proj_name)
            self.edit_folder_path_var.set(folder)
        else:
            self.edit_proj_name_var.set("")
            self.edit_folder_path_var.set("")

        self._show_preview(fig)

    def _show_preview(self, myfig: Figure) -> None:
        # Render with caching
        key = id(myfig)
        matfig = self._preview_cache.get(key)
        if matfig is None:
            try:
                matfig = mplot(myfig)
            except Exception as e:
                messagebox.showerror("Preview error", f"Failed to render preview:\n{e}")
                return
            matfig.set_constrained_layout(True)
            self._preview_cache.put(key, matfig)

        # Close previous figure bound to old canvas to avoid leaking GUI event sources
        try:
            import matplotlib.pyplot as plt
            if self._current_preview_canvas is not None:
                old_fig = self._current_preview_canvas.figure
                plt.close(old_fig)
        except Exception:
            pass
        self._current_preview_canvas = None

        # Replace preview canvas
        for child in self.preview_host.winfo_children():
            child.destroy()

        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

        canvas = FigureCanvasTkAgg(matfig, master=self.preview_host)
        canvas.draw()

        # Add toolbar (pan/zoom/home/save)
        toolbar = NavigationToolbar2Tk(canvas, self.preview_host)
        toolbar.update()

        # Pack order matters: toolbar first, then canvas widget fills the rest
        toolbar.pack(side=tk.TOP, fill=tk.X)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._current_preview_canvas = canvas


    # ---------------- Figure operations ----------------
    def _delete_selected_figure(self) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self.figures):
            return
        fig = self.figures.pop(idx)
        self.figure_list.delete(idx)
        self._preview_cache.clear()
        # Clear preview if nothing selected
        for child in self.preview_host.winfo_children():
            child.destroy()
    
    def _delete_all_figures(self) -> None:
        # 0) If there is an active preview canvas, close the bound matplotlib Figure
        # to avoid leaking GUI event sources.
        try:
            import matplotlib.pyplot as plt
            if self._current_preview_canvas is not None:
                try:
                    old_fig = self._current_preview_canvas.figure
                    plt.close(old_fig)
                except Exception:
                    pass
        except Exception:
            pass
        self._current_preview_canvas = None

        # 1) Clear the in-memory model
        self.figures.clear()

        # 2) Clear the listbox UI and selection highlight
        try:
            self.figure_list.selection_clear(0, tk.END)
        except Exception:
            pass
        self.figure_list.delete(0, tk.END)

        # 3) Clear per-figure archive editor fields
        self.edit_proj_name_var.set("")
        self.edit_folder_path_var.set("")

        # 4) Clear preview cache (LRUCache.clear() closes cached figures)
        self._preview_cache.clear()

        # 5) Remove any preview widgets from the host frame
        for child in self.preview_host.winfo_children():
            child.destroy()


    def _apply_archive_to_selected(self, overwrite: bool) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self.figures):
            messagebox.showwarning("No selection", "Please select a figure.")
            return
        proj = self.edit_proj_name_var.get().strip()
        folder = self.edit_folder_path_var.get().strip()
        if not proj or not folder:
            messagebox.showwarning("Invalid", "proj_name and folder_path are required.")
            return
        fig = self.figures[idx]
        if overwrite:
            fig.proj_folder = {proj: folder}
        else:
            fig.proj_folder[proj] = folder
        messagebox.showinfo("Applied", "Archive info applied to selected figure.")

    def _apply_archive_to_all(self, overwrite: bool) -> None:
        proj = self.global_proj_name_var.get().strip()
        folder = self.global_folder_path_var.get().strip()
        if not proj or not folder:
            messagebox.showwarning("Invalid", "proj_name and folder_path are required.")
            return
        for fig in self.figures:
            if overwrite:
                fig.proj_folder = {proj: folder}
            else:
                fig.proj_folder[proj] = folder
        messagebox.showinfo("Applied", "Archive info applied to all figures.")

    # ---------------- Save operations ----------------
    def _pick_proj_dir(self) -> None:
        d = filedialog.askdirectory(title="Select OPJU directory",initialdir=".", mustexist=True)
        if d:
            self.proj_dir_var.set(str(Path(d).resolve()))

    def _save_selected_figure(self) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self.figures):
            messagebox.showwarning("No selection", "Please select a figure.")
            return
        if not self.figures[idx].proj_folder:
            messagebox.showwarning("Missing archive", "Selected figure has no proj_name:folder_path mapping.")
            return
        target = filedialog.askdirectory(title="Select save directory", mustexist=True)
        if not target:
            return
        proj_dir = Path(target).resolve()
        overwrite = self.save_mode_var.get() == "overwrite"

        projs = pack_into_project([self.figures[idx]])

        try:
            with OriginCOM(visible=False) as og:
                for proj_name, proj in projs.items():
                    oplot(proj, proj_name, og, proj_dir=proj_dir, overwrite=overwrite)
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save to OPJU:\n{e}")
            return

        messagebox.showinfo("Saved", "Selected figure saved.")

    def _save_all(self) -> None:
        if not self.figures:
            messagebox.showwarning("No figures", "Nothing to save.")
            return
        raw = self.proj_dir_var.get().strip()
        if not raw:
            messagebox.showwarning("Missing directory", "Please choose an OPJU directory first.")
            return

        proj_dir = Path(raw).expanduser().resolve()
        if not proj_dir.exists():
            messagebox.showwarning("Invalid directory", "Please choose a valid OPJU directory.")
            return
        overwrite = self.save_mode_var.get() == "overwrite"

        projs = pack_into_project(self.figures)

        try:
            with OriginCOM(visible=False) as og:
                for proj_name, proj in projs.items():
                    oplot(proj, proj_name, og, proj_dir=proj_dir, overwrite=overwrite)
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save to OPJU:\n{e}")
            return

        messagebox.showinfo("Saved", "All figures saved.")


def main() -> None:
    root = tk.Tk()
    root.attributes("-topmost", False)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    app = MainWindow(root)

    def _on_close():
        # 1) Close all matplotlib figures (previews)
        try:
            import matplotlib.pyplot as plt
            plt.close("all")
        except Exception:
            pass

        # 2) Destroy tkinter root
        try:
            root.quit()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()