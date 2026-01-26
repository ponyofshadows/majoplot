from __future__ import annotations

from ...base import *


FIGSIZE = (8, 6)

T = "Temperature (K)"
H = "Magnetic Field (Oe)"
R = "Resistivity (Ohm-m)"
RI ={
    1: {"R":"Bridge 1 Resistivity (Ohm-m)", "I":"Bridge 1 Excitation (uA)"},
    2: {"R":"Bridge 2 Resistivity (Ohm-m)", "I":"Bridge 2 Excitation (uA)"},
    3: {"R":"Bridge 3 Resistivity (Ohm-m)", "I":"Bridge 3 Excitation (uA)"},
}

class RT:
    data_summary_label_names = ["H"]
    axes_label_names = ("date", "raw_data", "bridge", "sample_name")
    figure_label_names = ("date", "raw_data", "bridge", "sample_name")
    figure_summary_label_names = ("raw_data","bridge","sample_name")
    max_axes_in_one_figure = 1
    project_to_child_folder_label_names = {"date":"sample_name"}
    parent_folder_name = "RT"

    @classmethod
    def preprocess(cls, raw_datas:list[Data])->list[Data]:
        datas = []
        for raw_data in raw_datas:
            raw_labels = raw_data.labels
            headers = raw_data.headers
            raw_points = raw_data.points
            
            # Split by H
            split_datas = []

            last_H_stage = round(raw_points[0][headers[H]])
            current_points = [ last_H_stage, [ raw_points[0] ] ]

            for point in raw_points[1:]:
                cur_H_stage = round(point[headers[H]])
                if cur_H_stage != last_H_stage:
                    split_datas.append(current_points)
                    last_H_stage = cur_H_stage
                    current_points = [ last_H_stage, [ point ] ]
                else:
                    current_points[1].append(point)
            else:
                split_datas.append(current_points)

            # 3 bridges
            for H_stage, points in split_datas:
                for i in range(1,4):
                    _headerTRI = (T,RI[i]["R"],RI[i]["I"])
                    _headers = (T,RI[i]["R"])
                    s_points = [ [point[headers[x]] for x in _headerTRI] for point in points]
                    # clear null R points
                    s_points = np.array([point for point in s_points if point[1]])
                    # record
                    Imin = np.min(s_points[:,1])
                    Imax = np.max(s_points[:,1])
                    if (Imax - Imin) / Imax < 0.03:
                        Irange = f"{np.mean(s_points[:,1]):.1e}"
                    else:
                        Irange = f"{Imin:.1e}~{Imax:.1e}"
                    labels = LabelDict()
                    labels["instrument"] = raw_labels["instrument"]
                    labels["raw_data"] = raw_labels["raw_data"]
                    labels["date"] = raw_labels["date"]
                    labels["bridge"] = LabelValue(i,unit="Bridge",unit_as_postfix=False)
                    labels["sample_name"] = raw_labels[f"sample{i}_name"]
                    labels["sample_units"] = raw_labels[f"sample{i}_units"]
                    labels["H"] = LabelValue(H_stage, unit="Oe")
                    labels["I_range"] = LabelValue(Irange,unit="μA")
                    labels.summary_names = cls.data_summary_label_names
                    datas.append(Data(
                        labels=labels,
                        _headers=_headers,
                        points=s_points[:,0:2],
                        ignore_outliers=IgnoreOutlierSpec(min_gap_base=1e-6,min_gap_multiple=10),
                    ))
            
        return datas
            
            

    @classmethod
    def make_axes_spec(cls, axes_labels, data_pool)->AxesSpec:
        return AxesSpec(
            x_axis_title=T,
            y_axis_title=R,
            major_grid=None,
            major_tick=TickSpec(),
            legend=LegendSpec(fontsize=5),
        )
            

    @classmethod
    def make_figure_spec(cls,figure_labels, axes_pool:Iterable[Axes])->FigureSpec:
        figure_name = figure_labels.brief_summary

        return FigureSpec(
            name=figure_name,
            title=None,
            figsize=FIGSIZE,
            linestyle_cycle= ("-",),
            linecolor_cycle = (
                "#2d0b59", "#3b0f6f", "#4a136e", "#5a176e", "#6a1c6e",
                "#7a216f", "#8b2770", "#9b2d71", "#ac3372", "#bd3973",
                "#ce4074", "#df4775", "#f04f76", "#f86a5a", "#fb8c3c",
                "#fdbb2d", "#fcfdbf",
                ),
            linemarker_cycle = ("o","s","^","v","d","*","x","+"),
            alpa_cycle = (1.0,),
        )
    
    @classmethod
    def make_muti_axes_spec(cls, axes_pool:list[Axes])->MutiAxesSpec|FAIL|None:
        return None