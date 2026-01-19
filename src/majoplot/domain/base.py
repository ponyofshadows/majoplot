from __future__ import annotations
from typing import Protocol, runtime_checkable, NamedTuple, TextIO, Iterable, Optional, Callable, Iterator, Any
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from numpy.typing import NDArray
import numpy as np
from numbers import Real
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")

class FAIL:
    __slots__ = ()
fail_signal = FAIL()
# ========= Data ========

class LabelValue(NamedTuple):
    """
    value: int | float | str
    Note:
        bool is not a supported value type.
        Passing bool leads to undefined ordering behavior.
    """
    value: int|float|str|tuple[int|float|str]
    unit: Optional[str] = None
    unit_as_postfix: bool = True
    def __lt__(self, other:LabelValue):
        if not isinstance(other, LabelValue):
            return NotImplemented
        
        if isinstance(self.value, Real):
            if isinstance(other.value, Real):
                if self.unit == other.unit:
                    return self.value < other.value
                elif self.unit is None:
                    return True
                elif other.unit is None:
                    return False
                else:
                    return self.unit < other.unit
            else:
                return True
        elif isinstance(other.value, Real):
            return False
        else:
            return str(self.value) < str(other.value)
    def __str__(self):
        if self.unit:
            if self.unit_as_postfix:
                return f"{self.value}{self.unit}"
            else:
                return f"{self.unit}{self.value}"
        else:
            return str(self.value)


class LabelDict(MutableMapping):
    __slots__ = ("_items","summary_names","subgroup")
    def __init__(self,initital:Optional[dict[str,LabelValue]]=None, summary_names:Optional[Iterable[str]]=None, subgroup:int=0):
        self._items = dict(initital) if initital else {}
        self.summary_names = list(summary_names) if summary_names else []
        self.subgroup = subgroup
    def __getitem__(self, key):
        return self._items[key]
    def __setitem__(self, key, value):
        self._items[key] = value
    def __delitem__(self, key):
        del self._items[key]
    def __iter__(self):
        return iter(self._items)
    def __len__(self):
        return len(self._items)
    def __str__(self):
        return ", ".join(f"{name}:{value}" for (name, value) in self._items.items()).strip().strip(",")
    def __copy__(self):
        return LabelDict(
            initital=dict(self._items),
            summary_names=list(self.summary_names),
            subgroup=self.subgroup
        )
    
    @property
    def full_summary(self):
        if self.summary_names:
            return ", ".join(f"{name}:{self._items[name]}" for name in self.summary_names)
        else:
            return ", ".join(f"{name}:{value}" for (name, value) in self._items.items()).strip().strip(",")
    @property
    def brief_summary(self):
        if self.summary_names:
            return ",".join(f"{self._items[name]}" for name in self.summary_names if self._items[name]).strip().strip(",")
        else:
            return ",".join(f"{value}" for value in self._items.values() if value).strip().strip(",")
    
    @classmethod
    def group(cls,label_dict_element_pairs:Iterable[tuple[LabelDict,Any]],
              /,
              group_label_names:Iterable[str],
              group_member_limit:int=0,
              summary_label_names:Optional[Iterable[str]]=None,
              sort_label_names:Optional[tuple[str]]=None,
            )->tuple[list[tuple[LabelDict,list[Any]]], list[Any]]:
        groups = {}
        remains = []
        group_label_names = list(group_label_names)
        summary_label_names = list(summary_label_names) if summary_label_names else []
        for label_dict, element in label_dict_element_pairs:
            try:
                group_label_values=tuple(label_dict[name] for name in group_label_names)
            except KeyError:
                remains.append(element)
                continue
            groups.setdefault(group_label_values,[]).append((label_dict, element))
        
        if sort_label_names:
            for label_dict_member_pairs in groups.values():
                for sort_label_name in sort_label_names:
                    label_dict_member_pairs.sort(key=lambda x: x[0][sort_label_name])

        if group_member_limit < 1:
            return (list(
                    (
                        LabelDict(
                            initital = dict((name,value) for (name,value) in zip(group_label_names, group_label_values)),
                            summary_names=summary_label_names
                        ),
                        [label_dict_member_pair[1] for label_dict_member_pair in label_dict_member_pairs]
                ) 
                        for (group_label_values, label_dict_member_pairs) in groups.items()
            ), remains)
        else:
            subgroups = []
            group_member_limit = int(group_member_limit)
            for group_label_values, label_dict_member_pairs in groups.items():
                group_dict = dict((name,value) for (name,value) in zip(group_label_names, group_label_values))
                cur_subgroup = []
                subgroup_end_i = group_member_limit-1
                last_member_i = len(label_dict_member_pairs) - 1
                for i,(_, member) in enumerate(label_dict_member_pairs):
                    subgroup_id = i // group_member_limit
                    subgroup_label_dict = LabelDict(initital=group_dict, summary_names=summary_label_names, subgroup=subgroup_id)
                    cur_subgroup.append(member)
                    if i == subgroup_end_i or i == last_member_i:
                        subgroups.append((subgroup_label_dict, cur_subgroup))
                        cur_subgroup = []
            return subgroups, remains
                

@dataclass(slots=True)
class Data:
    labels: LabelDict
    _headers: tuple[str]
    points:NDArray[np.floating]
    ignore_outliers: Optional[IgnoreOutlierSpec] = None
    unused: bool = False

    headers: dict[str,int] = field(init=False, default=None)
    _ignore_outliers_spec_cache:Optional[IgnoreOutlierSpec] = field(init=False, default=None)
    _points_for_plot:Optional[NDArray[np.floating]] = field(init=False,default=None)
    _x_for_plot:NDArray[np.floating] = field(init=False, default=None)
    _y_for_plot:NDArray[np.floating] = field(init=False, default=None)
    _xlim:tuple[np.floating,np.floating] = field(init=False, default=None)
    _ylim:tuple[np.floating,np.floating] = field(init=False, default=None)

    def __post_init__(self):
        self.headers = dict((header, index) for (index, header) in enumerate(self._headers))

    def __repr__(self):
        return f"\nData({self.labels}\tShape: {self.points.shape})\n"
    
    def _set_ignore_outliers(self):
        min_gap_base = self.ignore_outliers.min_gap_base
        min_gap_mutiple = self.ignore_outliers.min_gap_multiple
        i = 1

        def points_without_outliers():
            cache_deque = []
            for point in self.points:
                cache_deque.append(point)
                if len(cache_deque) == 3:
                    gap0to1 = abs(cache_deque[1][i] - cache_deque[0][i]) 
                    gap0to2 = abs(cache_deque[2][i] - cache_deque[0][i]) 
                    if gap0to2 < min_gap_base:
                        gap0to2 = min_gap_base
                    if gap0to1 > gap0to2 * min_gap_mutiple:
                        cache_deque.pop(1)
                    else:
                        yield cache_deque.pop(0)
            yield from cache_deque

        self._points_for_plot = np.array(list(points_without_outliers()))

    @property
    def points_for_plot(self)->NDArray[np.floating]:
        if self.ignore_outliers is None:
            return self.points
        else:
            if self._ignore_outliers_spec_cache != self.ignore_outliers:
                self._set_ignore_outliers()
                self._ignore_outliers_spec_cache = self.ignore_outliers
            return self._points_for_plot
            

    @property
    def x_for_plot(self)->NDArray[np.floating]:
        if self._x_for_plot is None:
            self._x_for_plot = self.points_for_plot[:,0]
        return self._x_for_plot

    @property
    def xlim(self)->tuple[np.float64,np.float64]:
        if self._xlim is None:
            self._xlim = (np.min(self.x_for_plot), np.max(self.x_for_plot))
        return self._xlim

    @property
    def y_for_plot(self)->NDArray[np.floating]:
        if self._y_for_plot is None:
            self._y_for_plot = self.points_for_plot[:,1]
        return self._y_for_plot

    @property
    def ylim(self)->tuple[np.float64,np.float64]:
        if self._ylim is None:
            self._ylim = (min(self.y_for_plot), max(self.y_for_plot))
        return self._ylim
    
    @property
    def label_for_plot(self)->str:
        if self.labels:
            return self.labels.brief_summary
        else:
            return ""
        

   
# ======== Plot Object ========
@dataclass(slots=True)
class Axes:
    spec: AxesSpec
    labels: LabelDict
    data_pool: list[Data] = field(default_factory=list)

    _xlim:tuple[np.float64,np.float64] = field(init=False, default=None)
    _ylim:tuple[np.float64,np.float64] = field(init=False, default=None)

    @property
    def xlim(self)->tuple[np.float64,np.float64]:
        if self._xlim is None:
            xlims = (np.array([data.xlim for data in self.data_pool]))
            self._xlim = np.min(xlims[:,0]), np.max(xlims[:,1])
        return self._xlim

    @property
    def ylim(self)->tuple[np.float64,np.float64]:
        if self._ylim is None:
            ylims = np.array([data.ylim for data in self.data_pool])
            self._ylim = (np.min(ylims[:,0]), np.max(ylims[:,1]))
        return self._ylim


@dataclass(slots=True)
class Figure:
    axes_pool: list[Axes]
    spec: FigureSpec
    muti_axes_spec: MutiAxesSpec
    labels: LabelDict
    proj_folder: dict[str,str] # Mapping from proj_name to folder_path_in_proj

# ======== Plot Spec ========
class AxesSpec(NamedTuple):
    # Alaways has full Frame
    x_axis_title: str
    y_axis_title: str
    axis_title_font_size:float = 8
    x_left_lim: Optional[float] = None
    x_right_lim: Optional[float] = None
    y_left_lim: Optional[float] = None
    y_right_lim: Optional[float] = None
    x_log_scale_min_span:float = 1e12
    y_log_scale_min_span:float = 1e12
    linewidth:float = 1.0
    marker_size:float = 4
    major_tick: Optional[TickSpec] = None
    minor_tick: Optional[TickSpec] = None
    major_grid: Optional[GridSpec] = None
    minor_grid: Optional[GridSpec] = None
    legend: Optional[LegendSpec] = None
    annotation: Optional[list[AnnotationSpec]] = None

class TickSpec(NamedTuple):
    axis:str = "both"
    direction:str = "in"
    length:float = 6
    width:float = 1.2
    top:bool = True
    left:bool = True


class GridSpec(NamedTuple):
    linestyle:str = "--"
    linewidth:float = 0.5
    color:str = "grey"

class LegendSpec(NamedTuple):
    loc:str = "upper right"
    anchor_x:float = 1
    anchor_y:float = 1
    fontsize:float = 8
    frameon:bool = True

class AnnotationSpec(NamedTuple):
    text:str
    text_x:float
    text_y:float
    fontsize:float = 8
    arrow:Optional[ArrowSpec] = None

class ArrowSpec(NamedTuple):
    point_x:float
    point_y:float
    arrowstyle:str = "->"
    color:str = "black"
    linewidth:float = 1.0

class IgnoreOutlierSpec(NamedTuple):
    min_gap_base:float
    min_gap_multiple:float = 20


class FigureSpec(NamedTuple):
    name:str
    title:str = None
    figsize:tuple[float] = (3.4,2.6)
    dpi:int = 300
    global_fontsize:float = 8
    facecolor:str = "white"
    linestyle_cycle:tuple[str] = ("-", "--")
    linecolor_cycle:tuple[str] = ("black", "red")
    linemarker_cycle:tuple[str] = ("o","o","s","s","^","^","v","v","d","d","*","*","x","x","+","+")
    alpa_cycle:tuple[float] = (1.0,)
    legend:Optional[LegendSpec] = None


class MutiAxesSpec(Protocol):
    legend_holder:str
    @classmethod
    def default(cls, figuresize:tuple[float], axes_pool:list[Axes]):
        ...

# ======== Proj & folder ========
class folder(dict[str,Figure]):
    pass

class Project(dict[str,folder]):
    pass

# ======== Scenario ========
class Importer(Protocol):
    instrument: str

    @classmethod
    def fetch_raw_data(cls, raw_data_file:TextIO, raw_data_name:str)->Data|FAIL:
        ...
    

class Scenario(Protocol):
    data_summary_label_names:list[str]
    axes_label_names:tuple[str]
    figure_label_names:tuple[str]
    figure_summary_label_names:list[str]
    max_axes_in_one_figure:int
    project_to_child_folder_label_names: str
    parent_folder_name: str

    @classmethod
    def preprocess(cls, raw_datas:list[Data])->list[Data]:
        ...
    
    @classmethod
    def make_axes_spec(cls, axes_labels:LabelDict)->AxesSpec:
        ...

    @classmethod
    def make_figure_spec(cls,figure_labels:LabelDict, axes_pool:Iterable[Axes])->FigureSpec:
        ...
    
    @classmethod
    def make_muti_axes_spec(cls, axes_pool:list[Axes])->MutiAxesSpec|FAIL:
        ...

#======== Fit ========
# @dataclass(slots=True)
# class FitData:
#     labels: LabelDict
#     x: NDArray
#     y: NDArray

# class FitScenario(Scenario, Protocol):
#     @classmethod
#     def fit(cls, data:FitData, modelstrategy:ModelStrategy, optimizer:Callable)->NDArray:
#         ...
    
# class ModelStrategy(Protocol):
#     fit_figure_spec: FigureSpec
#     @staticmethod
#     def prepare_data_for_fit(all_datas:Iterable[Data])->list[FitData]:
#         ...
#     @staticmethod
#     def model(self, x)->Callable:
#         ...
#     def residual(self, x):
#         ...

# @runtime_checkable
# class HasJacobian(Protocol):
#     def jacobian(self, x):
#         ...

# @runtime_checkable
# class HasInitialGuess(Protocol):
#     def initial_guess(self):
#         ...

# @runtime_checkable
# class HasTransfrom(Protocol):
#     @staticmethod
#     def from_physics(x):
#         ...
#     @staticmethod
#     def to_physics(x):
#         ...