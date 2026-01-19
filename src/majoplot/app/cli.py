from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import importlib
import pkgutil
from types import ModuleType
from typing import Any

from ..domain.base import *
from ..domain.utils import group_into_axes, group_into_figure, pack_into_project
from ..infra.plotters.origin import OriginCOM
from ..infra.plotters.origin import plot as oplot

def load_named_objects(package: str) -> dict[str, Any]:
    """
    Import all submodules under `package`, and extract the attribute
    that has the same name as the module.

    Example:
        domain.importers.csv -> object named `csv`
    """
    result: dict[str, Any] = {}

    pkg = importlib.import_module(package)

    if not hasattr(pkg, "__path__"):
        raise ValueError(f"{package!r} is not a package")

    for module_info in pkgutil.iter_modules(pkg.__path__):
        module_name = module_info.name
        full_name = f"{package}.{module_name}"

        module = importlib.import_module(full_name)

        if hasattr(module, module_name):
            result[module_name] = getattr(module, module_name)
        else:
            raise AttributeError(
                f"Module {full_name} does not define `{module_name}`"
            )

    return result




def pick_multiple_files(
    *,
    title: str = "Select files",
    initial_dir: str | Path | None = None,
    filetypes: list[tuple[str, str]] | None = None,
) -> list[Path]:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        filenames = filedialog.askopenfilenames(
            title=title,
            initialdir=str(Path(initial_dir).resolve()) if initial_dir else None,
            filetypes=filetypes or [("All files", "*.*")],
        )
        return [Path(x).resolve() for x in filenames]  # empty list if cancelled
    finally:
        root.destroy()

def pick_directory(
    *,
    title: str = "Select directory",
    initial_dir: str | Path | None = None,
) -> Path | None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        dirname = filedialog.askdirectory(
            title=title,
            initialdir=str(Path(initial_dir).resolve()) if initial_dir else None,
            mustexist=True,
        )
        if not dirname:
            return None  # user cancelled
        return Path(dirname).resolve()
    finally:
        root.destroy()

def run_cli():
    """
    cli is just for test in early and middle development stage
    """
    print("################")
    print("# MAJOPLOT CLI #")
    print("################")
    importers = load_named_objects("majoplot.domain.importers")
    figures = []
    print("======== Step 1 ========")
    while True:
        print("[Majo]: Now we try to import some raw datas.")
        while True:
            print("[Majo]: Please choose one Importer:")
            print("\n".join(f"\t- {importer}" for importer in importers))
            try:
                chosed_importer_name = input("[You]:").strip()
                chosed_importer = importers[chosed_importer_name]
            except KeyError:
                print(f"[Majo]: Importer '{chosed_importer_name}' not founded. Please try another.")
                continue
            break
        scenarios = load_named_objects(f"majoplot.domain.scenarios.{chosed_importer_name}")
        while True:
            print("[Majo]: Please choose one Scenario:")
            print("\n".join(f"\t- {scenario}" for scenario in scenarios))
            try:
                chosed_scenario_name = input("[You]:").strip()
                chosed_scenario = scenarios[chosed_scenario_name]
            except KeyError:
                print(f"[Majo]: Scenario '{chosed_scenario_name}' not founded. Please try another.")
                continue
            break
        
        print("[Majo]: Please choose some raw data files.")
        raw_data_paths = pick_multiple_files(title="Select Raw data files", initial_dir=".")
        print(f"[You]:")
        print("\n".join(f"\t+ {raw_data_path}" for raw_data_path in raw_data_paths))
        
        
        # make figures
        raw_datas = []
        for path in raw_data_paths:
            with open(path, encoding="utf-8") as fp:
                raw_data = chosed_importer.fetch_raw_data(fp, path.stem)
                if raw_data is not fail_signal:
                    raw_datas.append(raw_data)
        datas = chosed_scenario.preprocess(raw_datas)

        
        axes_pool = group_into_axes(datas, chosed_scenario)
        figures.extend(group_into_figure(axes_pool, chosed_scenario))


        print("[Majo]: Ok. Shall we proceed to the next step?")
        print("\t- (Y) Yes.")
        print("\t- (N) No, I want to import more datas.")
        choice = input("[You]:")
        if choice.upper() == "Y":
            break
    
    print("======== Step 2 ========")
    while True:
        print("[Majo]: We got these figures:")
        print("\n".join(f"\t ({i}) {figure.spec.name}" for i,figure in enumerate(figures)))
        print("[Majo]: You can choose one figure to manipulate. Or you can input:")
        print("\t- (Y) to get to the next step.")
        print("\t- (W) to write and apply a project_name:folder_path pair to all the figures")
        print("\t- (O) to overwrite and apply a project_name:folder_path pair to all the figures")

        answer = input("[You]:").upper()
        if answer == "Y":
            break
        elif answer == "W" or answer == "O":
            print("[Majo]: Please input a 'proj_name:folder_path' pair. For example: '20260115:MT/LNO'.")
            try:
                pair = input("[You]:").split(":")
                proj_name, folder_path = pair[0:2]
                if answer == "W":
                    for figure in figures:
                        figure.proj_folder[proj_name] = folder_path
                else:
                    for figure in figures:
                        figure.proj_folder = {}
                        figure.proj_folder[proj_name] = folder_path
                print("[Majo]: Project name and folder Paths applied.")
            except ValueError:
                print("[Majo]: Wrong Input.")
            continue
                

        try:
            index = int(answer)
        except ValueError:
            print("[Majo]: Wrong Input.")
            continue
        try:
            chosed_figure = figures[index]
        except IndexError:
            print("[Majo]: You chosed a figure that doesn't exist.")
            continue
            
        while True:
            print(f"[Majo]: This figure is chosed: ({index}) {chosed_figure.spec.name}")
            print("[Majo]: What do you want to do now?")
            print("\t- (D) Delete this figure.")
            print("\t- (P) Preview this figure.")
            print("\t- (S) Show current project_name:folder_path pairs.")
            print("\t- (W) to write and apply a project_name:folder_path pair to all the figures")
            print("\t- (O) to overwrite and apply a project_name:folder_path pair to all the figures")
            print("\t- (C) Cancel and come back.")
            choice = input("[You]:")
            match choice.upper():
                case "D":
                    del figures[index]
                    break
                case "P":
                    import matplotlib.pyplot as plt
                    from ..infra.plotters.matplot import plot as mplot
                    mfigure = mplot(chosed_figure)
                    plt.figure(mfigure)
                    plt.show()
                case "C":
                    break
                case "S":
                    print(f"[Majo]: proj_name:folder_path pairs of {chosed_figure.spec.name}:")
                    print("\n".join(f"\t- {proj_name}: {folder_path}" for proj_name, folder_path in chosed_figure.proj_folder.items()))
                case "W" | "O":
                    print("[Majo]: Please input a 'proj_name:folder_path' pair. For example: '20260115:MT/LNO'.")
                    try:
                        pair = input("[You]:").split(":")
                        proj_name, folder_path = pair[0:2]
                        if choice == "W":
                                chosed_figure.proj_folder[proj_name] = folder_path
                        else:
                                chosed_figure.proj_folder = {}
                                chosed_figure.proj_folder[proj_name] = folder_path
                        print("[Majo]: Project name and folder Paths applied.")
                    except ValueError:
                        print("[Majo]: Wrong Input.")
            

    print("======== Step 3 ========")
    print("[Majo]: Please pick a directory to save opju")
    proj_dir = pick_directory(title="Select the directory of OPJU", initial_dir=".")
    while True:
        print("[Majo]: [A] Attach or [O] Overwrite?")
        choice = input("[You]:")
        match choice.upper():
            case "A":
                overwrite = False
                break
            case "O":
                overwrite = True
                break
            case _:
                print("[Majo]: Wrong Input.")

    projs = pack_into_project(figures)
    print("[Majo]: Launching OriginCOM...")
    with OriginCOM(visible=False) as og:
        for proj_name, proj in projs.items():
            print(f"[Majo]: ploting in the project {proj_name}...")
            oplot(proj, proj_name, og, proj_dir=proj_dir,overwrite=overwrite)
            for folder_name, folder in proj.items():
                for figure_name in folder:
                    print(f"\tPlotted: Figure {figure_name} in folder {folder_name}.")
            print("[Majo]: Done.")


    
