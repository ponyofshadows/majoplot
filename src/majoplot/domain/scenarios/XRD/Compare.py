from __future__ import annotations

from copy import deepcopy

from ...base import *
from ...muti_axes_spec import StackAxesSpec


FIGSIZE = (8, 6)
STACK_FIGSIZE = (8, 4)
HEIGHT_PER_AXES = 4.0


class Compare:
    """Compare every experimental XRD scan against every CIF reference.

    For N experiments and M CIF references, produce M figures with N
    vertically stacked axes each. Each axes has an experiment curve and
    the reference's in-range peak sticks.

    When no CIF reference is supplied, retain the old behavior: a single
    figure with one experiment-only axes for each experimental scan.
    """

    data_summary_label_names = ["raw_data"]
    standard_summary_label_names = ["standard_name"]

    # experiment_id ensures even same-named experimental files get separate axes.
    axes_label_names = ("raw_data", "date", "standard_name", "experiment_id")
    figure_label_names = ("date", "standard_name")
    figure_summary_label_names = ("date", "standard_name")
    max_axes_in_one_figure = 0

    project_to_child_folder_label_names = {"date": None}
    parent_folder_name = "XRD"

    @classmethod
    def preprocess(cls, raw_datas: list[Data]) -> list[Data]:
        experiments = []
        standards = []

        for raw_data in raw_datas:
            if raw_data.labels.get("source") == "cif":
                standards.append(raw_data)
            else:
                experiments.append(raw_data)

        if not experiments:
            return []

        # Keep the original policy: all measurements in a comparison figure
        # share the last experimental scan's date.
        common_date = experiments[-1].labels["date"]

        # Give every reference a distinct display/grouping name, including
        # the rare case of multiple imported files with identical names.
        standard_entries = []
        used_standard_names = set()
        for standard in standards:
            base_name = str(standard.labels["raw_data"])
            display_name = base_name
            suffix = 2
            while display_name in used_standard_names:
                display_name = f"{base_name} ({suffix})"
                suffix += 1
            used_standard_names.add(display_name)
            standard_entries.append((standard, LabelValue(display_name)))

        if not standard_entries:
            standard_entries = [(None, experiments[0].labels["raw_data"])]

        result: list[Data] = []
        headers = ("2θ", "I")

        # Reference-first order makes each figure's axes follow the original
        # experimental-file order. Grouping into figures is done downstream.
        for standard, standard_name in standard_entries:
            standard_points = None if standard is None else standard.points[:, :2]

            for experiment_index, experiment in enumerate(experiments):
                labels = LabelDict()
                labels["instrument"] = experiment.labels["instrument"]
                labels["raw_data"] = experiment.labels["raw_data"]
                labels["date"] = common_date
                labels["standard_name"] = standard_name
                labels["experiment_id"] = LabelValue(experiment_index)

                # The experimental dataset must precede the CIF dataset:
                # the plotters assign black solid / red sticks by position.
                exp_labels = deepcopy(labels)
                exp_labels.summary_names = cls.data_summary_label_names
                result.append(
                    Data(
                        labels=exp_labels,
                        _headers=headers,
                        points=experiment.points[:, :2],
                    )
                )

                if standard_points is None:
                    continue

                xmin, xmax = experiment.xlim
                in_range = (
                    (standard_points[:, 0] >= xmin)
                    & (standard_points[:, 0] <= xmax)
                )
                clipped_points = standard_points[in_range]

                # No reference peaks within this scan's range: only the
                # experimental curve is plotted, never a fabricated peak.
                if len(clipped_points) == 0:
                    continue

                ref_labels = deepcopy(labels)
                ref_labels.summary_names = cls.standard_summary_label_names
                result.append(
                    Data(
                        labels=ref_labels,
                        _headers=headers,
                        points=clipped_points,
                    )
                )

        return result

    
    @classmethod
    def make_axes_spec(cls, axes_labels, data_pool) -> AxesSpec:
        data_pool = list(data_pool)

        # Use experimental data to define the X range.
        experiment = data_pool[0]
        xmin, xmax = experiment.xlim

        # Include all plotted data in the Y range.
        ymin = min(float(data.ylim[0]) for data in data_pool)
        ymax = max(float(data.ylim[1]) for data in data_pool)

        # CIF stick plots extend from y=0 to each peak intensity.
        if len(data_pool) > 1:
            ymin = min(ymin, 0.0)
            ymax = max(ymax, 0.0)

        return AxesSpec(
            x_axis_title="2θ",
            y_axis_title="I",
            x_left_lim=float(xmin),
            x_right_lim=float(xmax),
            y_left_lim=ymin,
            y_right_lim=ymax,
            major_grid=None,
            major_tick=TickSpec(),
            legend=LegendSpec(),
        )

    @classmethod
    def make_figure_spec(
        cls, figure_labels, axes_pool: Iterable[Axes]
    ) -> FigureSpec:
        count = len(axes_pool)
        figsize = (
            FIGSIZE
            if count < 2
            else (STACK_FIGSIZE[0], max(STACK_FIGSIZE[1], HEIGHT_PER_AXES * count))
        )
        return FigureSpec(
            name=figure_labels.brief_summary,
            title=None,
            figsize=figsize,
            linestyle_cycle=("-", "|"),
            linecolor_cycle=("black", "red"),
            linemarker_cycle=(None,),
            alpa_cycle=(1.0,),
        )

    @classmethod
    def make_muti_axes_spec(
        cls, axes_pool: list[Axes]
    ) -> MutiAxesSpec | FAIL | None:
        if len(axes_pool) < 2:
            return None
        return StackAxesSpec(nrows=len(axes_pool), ncols=1)