from __future__ import annotations
from copy import deepcopy

from ...base import *
from ...muti_axes_spec import StackAxesSpec


FIGSIZE = (8, 6)
STACK_FIGSIZE = (8,4)

class Compare:
    """
        EXP_RAW1, EXP_RAW2, CIF_RAW1, EXP_RAW3 CIF_RAW2
        ->
        StackFigure(
            Axes1( EXP_DATA1, CIF_DATA1 ),
            Axes2( EXP_DATA2, CIF_DATA1 ),
            Axes3( EXP_DATA3, CIF_DATA1 ),
        )
    """
    data_summary_label_names = ["raw_data"]
    standard_summary_label_names = ["standard_name"]
    axes_label_names = ("raw_data","date","standard_name")
    figure_label_names = ("date","standard_name")
    figure_summary_label_names = ("date","standard_name")
    max_axes_in_one_figure = 0
    project_to_child_folder_label_names = {"date":None}
    parent_folder_name = "XRD"

    @classmethod
    def preprocess(cls, raw_datas:list[Data])->list[Data]:
        _headers = ("2θ","I")
        standard_raw_data = None
        raw_experiment_datas = []
        for raw_data in raw_datas:
            if raw_data.labels["source"] == "cif":
                if standard_raw_data == None:
                    standard_labels = raw_data.labels
                    standard_points = raw_data.points[:,0:2]
                    standard_raw_data = Data(labels=standard_labels, _headers=_headers,points=standard_points)
            else:
                raw_experiment_datas.append(raw_data)
        
        _headers = ()
        if raw_experiment_datas:
            com_date = raw_experiment_datas[-1].labels["date"]
            substitute_standard_name = raw_experiment_datas[0].labels["raw_data"]
        
        datas = []
        for raw_data in raw_experiment_datas:
            labels = LabelDict()
            labels["instrument"] = raw_data.labels["instrument"]
            labels["raw_data"] = raw_data.labels["raw_data"]
            labels["date"] = com_date
            if standard_raw_data:
                labels["standard_name"] = standard_raw_data.labels["raw_data"]
            else:
                labels["standard_name"] = substitute_standard_name
            experiment_labels = deepcopy(labels)
            experiment_labels.summary_names = cls.data_summary_label_names
            datas.append(
                Data(labels=experiment_labels, _headers=_headers, points=raw_data.points)
            )
            if standard_raw_data:
                standard_labels = deepcopy(labels)
                standard_labels.summary_names = cls.standard_summary_label_names
                xmin, xmax = raw_data.xlim
                mask = (standard_raw_data.points[:,0] >= xmin) & (standard_raw_data.points[:, 0] <= xmax)
                datas.append(
                    Data(labels=standard_labels, _headers=_headers, points=standard_raw_data.points[mask])
                )
        return datas

    @classmethod
    def make_axes_spec(cls, axes_labels, data_pool)->AxesSpec:
        return AxesSpec(
            x_axis_title="2θ",
            y_axis_title="I",
            major_grid=None,
            major_tick=TickSpec(),
            legend=LegendSpec(),
        )
            

    @classmethod
    def make_figure_spec(cls,figure_labels, axes_pool:Iterable[Axes])->FigureSpec:
        figure_name = figure_labels.brief_summary
        figsize = FIGSIZE if len(axes_pool)<2 else STACK_FIGSIZE

        return FigureSpec(
            name=figure_name,
            title=None,
            figsize=figsize,
            linestyle_cycle= ("-","|"),
            linecolor_cycle = ("black","red"),
            linemarker_cycle = (None,),
            alpa_cycle = (1.0,),
        )
    
    @classmethod
    def make_muti_axes_spec(cls, axes_pool:list[Axes])->MutiAxesSpec|FAIL|None:
        count = len(axes_pool)
        if count < 2:
            return None
        else:
            return StackAxesSpec(nrows=count, ncols=1)