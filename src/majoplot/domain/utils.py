from __future__ import annotations
from typing import Iterator
from .base import *

# ========= Axes and Figures ========
def group_into_axes(all_datas:Iterable[Data], scenario:Scenario)->list[Axes]:
    axes_label_names = scenario.axes_label_names
    make_axes_spec = scenario.make_axes_spec

    axes_labels_and_data_pools, _ = LabelDict.group(
        ((data.labels, data) for data in all_datas if ( (not data.unused) and (data.points.size > 0) )),
        group_label_names=axes_label_names,
    )
    axes_pool = []
    for axes_labels, data_pool in axes_labels_and_data_pools:  
        spec = make_axes_spec(axes_labels)
        axes_pool.append(Axes(spec, axes_labels, data_pool))
    return axes_pool


def group_into_figure(all_axes:Iterable[Axes], scenario:Scenario)->list[Figure]:
    figure_label_names = scenario.figure_label_names
    make_figure_spec = scenario.make_figure_spec
    make_muti_axes_spec = scenario.make_muti_axes_spec
    summary_label_names = scenario.figure_summary_label_names
    max_axes_in_one_figure = scenario.max_axes_in_one_figure

    labels_and_axes_pools, _ = LabelDict.group(
        ((axes.labels, axes) for axes in all_axes),
        group_label_names=figure_label_names,
        summary_label_names= summary_label_names,
        group_member_limit=max_axes_in_one_figure
    )

    figure_pool = []
    for labels, axes_pool in labels_and_axes_pools:
        spec = make_figure_spec(labels, axes_pool)
        muti_axes_spec = make_muti_axes_spec(axes_pool)
        
        proj_folder = {}
        for proj_label_name, child_folder_label_name in scenario.project_to_child_folder_label_names.items():
            p_name = str(labels.get(proj_label_name, ""))
            if not p_name:
                p_name = "UNTITLED"
            f_name = str(labels.get(child_folder_label_name, ""))
            proj_folder[p_name] = f"{scenario.parent_folder_name}/{f_name}"

        if muti_axes_spec is fail_signal:
            for i, axes in enumerate(axes_pool):
                figure_pool.append(
                    Figure(
                        axes_pool=[axes],
                        spec=spec._replace(name=f"{spec.name}_{i}"),
                        muti_axes_spec=None,
                        labels=labels,
                        proj_folder= proj_folder
                        )
                )
            continue

        figure_pool.append(
            Figure(
                axes_pool=axes_pool,
                spec=spec,
                muti_axes_spec=muti_axes_spec,
                labels=labels,
                proj_folder= proj_folder
                )
            )
            

    return figure_pool

# ======== Project ========
def pack_into_project(all_figures:Iterable[Figure])->dict[str,Project]:
    projs = {}
    for figure in all_figures:
        figure_name = figure.spec.name
        for proj_name,folder_name in figure.proj_folder.items():
            projs.setdefault(proj_name, Project()).setdefault(folder_name, folder())[figure_name] = figure
    return projs

# ======== Importers ========
def skip_lines_then_readline(fp:TextIO, skip_lines: int)->str:
    for _ in range(skip_lines):
        fp.readline()
    return fp.readline()
