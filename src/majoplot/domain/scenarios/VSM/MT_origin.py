from __future__ import annotations
from copy import copy

from ...base import *


FIGSIZE = (8, 6)

T = "Temperature (K)"
M = "DC Moment Free Ctr (emu)"
H = "Magnetic Field (Oe)"


class MT_origin:
    data_summary_label_names = ["mass","H","cooling_type"]
    axes_label_names = ("material","date","raw_data", "H")
    figure_label_names = ("material","date", "raw_data","H")
    figure_summary_label_names = ("raw_data","date")
    max_axes_in_one_figure = 1
    project_to_child_folder_label_names = {"material":"date","date":"material"}
    parent_folder_name = "MT"

    @classmethod
    def preprocess(cls, raw_datas:list[Data])->list[Data]:
        datas = []
        for raw_data in raw_datas:
            raw_labels = raw_data.labels
            headers = raw_data.headers
            raw_points = raw_data.points
            iT = headers[T]
            iH = headers[H]
            iM = headers[M]
            
            check_deque = []

            current_points = []
            current_cool_type = "ZFC"
            try:
                current_points.append(raw_points[0])
                H_stage = round(raw_points[0, iH])
            except KeyError:
                return []

            def append_data():
                nonlocal current_points, check_deque, datas
                nonlocal current_cool_type
                current_points.append(check_deque.pop(0))
                labels = copy(raw_labels)
                labels["H"] = LabelValue(H_stage, "Oe")
                if current_points[-1][iT] < current_points[0][iT]:
                    labels["cooling_type"] = "cooling"
                else:
                    if current_cool_type == "ZFC":
                        labels["cooling_type"] = "ZFC"
                        current_cool_type = "FC"
                    else:
                        labels["cooling_type"] = "FC"
                        current_cool_type = "ZFC"
                labels["scenario"] = "MT"
                labels.summary_names = cls.data_summary_label_names
                datas.append(
                    Data(
                        labels=labels,
                        _headers=(T,M),
                        points=np.array(current_points)[:,[iT,iM]],
                        ignore_outliers=None
                ))

            for point in raw_points[1:]:
                check_deque.append(point)
                if len(check_deque) == 2:
                    # not the same H?
                    if abs(check_deque[1][iH] - H_stage) > 1.5:
                        append_data()
                        current_points = [check_deque.pop()]
                        H_stage = round(current_points[0][iH])
                        current_cool_type = "ZFC"
                    # not the same heating curve?
                    elif (check_deque[0][iT] - current_points[0][iT])>2 and (check_deque[0][iT] - check_deque[1][iT])>2:
                        append_data()
                        current_points = [check_deque.pop()]
                    else:
                        # the same curve
                        current_points.append(check_deque.pop(0))


            else:
                while check_deque:
                    append_data()
        
        return datas


    @classmethod
    def make_axes_spec(cls,axes_labels, data_pool)->AxesSpec:
        return AxesSpec(
            x_axis_title=T,
            y_axis_title=M,
            major_grid=None,
            major_tick=TickSpec(),
            legend=LegendSpec(),
        )
            

    @classmethod
    def make_figure_spec(cls,figure_labels, axes_pool:Iterable[Axes])->FigureSpec:
        H_stages = {}
        for axes in axes_pool:
            H_stages[axes.labels["H"]] = None
        
        figure_name = f"{figure_labels.brief_summary}-{",".join(str(H_stage) for H_stage in H_stages)}"

        return FigureSpec(
            name=figure_name,
            title=None,
            figsize=FIGSIZE,
            linestyle_cycle= ("-", "--"),
            linecolor_cycle = ("black", "red"),
            linemarker_cycle = ("o","o","s","s","^","^","v","v","d","d","*","*","x","x","+","+"),
            alpa_cycle = (1.0,),
        )
    
    @classmethod
    def make_muti_axes_spec(cls, axes_pool:list[Axes])->MutiAxesSpec|FAIL|None:
        return None