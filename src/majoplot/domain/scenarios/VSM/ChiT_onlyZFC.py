from __future__ import annotations
from copy import copy

from ...base import *


FIGSIZE = (8, 6)

T = "Temperature (K)"
M = "DC Moment Free Ctr (emu)"
H = "Magnetic Field (Oe)"
chi = "χ ( cm³ / g )"


class ChiT_onlyZFC:
    data_summary_label_names = ["H","cooling_type"]
    axes_label_names = ("material","date","raw_data")
    figure_label_names = ("material","date", "raw_data")
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
                    unused = True
                    labels["cooling_type"] = "cooling"
                else:
                    if current_cool_type == "ZFC":
                        unused = False
                        labels["cooling_type"] = "ZFC"
                        current_cool_type = "FC"
                    else:
                        unused = True
                        labels["cooling_type"] = "FC"
                        current_cool_type = "ZFC"
                labels["scenario"] = "MT"
                labels.summary_names = cls.data_summary_label_names
                a_points=np.array(current_points)[:,[iT,iM]]
                try:
                    mass = np.float64(labels["mass"].value)
                except ValueError:
                    mass = np.nan
                if mass == 0:
                    mass = np.nan
                safe_H_stage = np.nan if H_stage == 0 else H_stage
                chi_points = np.column_stack([a_points[:,0], a_points[:,1] / safe_H_stage * 1e3 / mass])
                datas.append(
                    Data(
                        labels=labels,
                        _headers=(T,chi),
                        points=chi_points,
                        ignore_outliers=IgnoreOutlierSpec(
                            min_gap_base=5e-9,
                            min_gap_multiple=10
                        ),
                        unused=unused,
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
    def make_axes_spec(cls,axes_labels,data_pool:Iterable[Data])->AxesSpec:
        if data_pool:
            x_min, x_max = data_pool[0].xlim
            for data in data_pool[1:]:
                data_x_min, data_x_max = data.xlim
                if data_x_min > x_min:
                    x_min = data_x_min
                if data_x_max < x_max:
                    x_max = data_x_max
            
            y_min, y_max = None, None
            for data in data_pool:
                mask = (data.points_for_plot[:, 0] >= x_min) & (data.points_for_plot[:, 0] <= x_max)
                y = data.points_for_plot[mask, 1]
                data_y_min = y.min()
                data_y_max = y.max()
                if y_min:
                    if data_y_min < y_min:
                        y_min = data_y_min
                else:
                    y_min = data_y_min

                if y_max:
                    if data_y_max > y_max:
                        y_max = data_y_max
                else:
                    y_max = data_y_max
            
            x_magin = (x_max - x_min) * 0.05
            y_magin = (y_max - y_min) * 0.05
            
            x_min, x_max = x_min - x_magin, x_max + x_magin
            y_min, y_max = y_min - y_magin, y_max + y_magin


        else:
            x_min, x_max = None, None
            y_min, y_max = None, None


        return AxesSpec(
            x_axis_title=T,
            y_axis_title=chi,
            x_left_lim=x_min,
            x_right_lim=x_max,
            y_left_lim=y_min,
            y_right_lim=y_max,
            major_grid=None,
            major_tick=TickSpec(),
            legend=LegendSpec(),
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
                "#1f77b4",  # blue (best first color)
                "#ff7f0e",  # orange
                "#2ca02c",  # green
                "#d62728",  # red
                "#9467bd",  # purple
                "#8c564b",  # brown
                "#17becf",  # cyan
                "#e377c2",  # pink
            ),
            linemarker_cycle = ("o","s","^","v","d","*","x","+"),
            alpa_cycle = (1.0,),
        )
    
    @classmethod
    def make_muti_axes_spec(cls, axes_pool:list[Axes])->MutiAxesSpec|FAIL|None:
        return None