from __future__ import annotations

from itertools import cycle
from typing import Iterable, Optional, Sequence, Tuple

import matplotlib.figure as mfig
import matplotlib.pyplot as plt

from ...domain.base import *
from ...domain.muti_axes_spec import *


# Inset axes should look slightly lighter/smaller than the main axes.
# Only scale what the user explicitly requested: marker, linewidth, axis-title fontsize.
INSET_STYLE_SCALE = 0.75


def _nonempty_cycle(values: Sequence, fallback: Sequence) -> Iterable:
    """Return an infinite cycle; if values is empty, cycle fallback instead."""
    if values:
        return cycle(values)
    return cycle(fallback)


def _safe_arrowstyle(value: object) -> str:
    """ArrowSpec.arrowstyle may accidentally be a 1-tuple due to a trailing comma."""
    if isinstance(value, tuple) and len(value) == 1:
        return str(value[0])
    return str(value)


def _apply_ticks(ax: plt.Axes, tick: TickSpec, labelsize: float) -> None:
    """Apply TickSpec to an Axes."""
    ax.tick_params(
        axis=tick.axis,
        direction=tick.direction,
        length=tick.length,
        width=tick.width,
        top=tick.top,
        left=tick.left,
        labelsize=labelsize,
    )


def _apply_grid(ax: plt.Axes, grid: GridSpec, which: str) -> None:
    """Apply GridSpec to an Axes."""
    ax.grid(
        True,
        which=which,
        linestyle=grid.linestyle,
        linewidth=grid.linewidth,
        color=grid.color,
    )


def _draw_axes_legend(
    ax: plt.Axes,
    handles: list,
    labels: list,
    legend: Optional[LegendSpec],
) -> None:
    """Draw a legend on an Axes using an optional LegendSpec."""
    if not handles:
        return

    if legend is None:
        ax.legend(handles, labels)
        return

    ax.legend(
        handles,
        labels,
        loc=legend.loc,
        bbox_to_anchor=(legend.anchor_x, legend.anchor_y),
        fontsize=legend.fontsize,
        frameon=legend.frameon,
    )


def _draw_figure_legend(
    matfig: mfig.Figure,
    handles: list,
    labels: list,
    legend: Optional[LegendSpec],
) -> None:
    """Draw a figure-level legend using an optional LegendSpec."""
    if not handles:
        return

    if legend is None:
        matfig.legend(handles, labels)
        return

    matfig.legend(
        handles,
        labels,
        loc=legend.loc,
        bbox_to_anchor=(legend.anchor_x, legend.anchor_y),
        fontsize=legend.fontsize,
        frameon=legend.frameon,
    )


def _maybe_set_log_scale(ax: plt.Axes, axes_obj: Axes) -> None:
    """Enable log scale when limits are positive and span exceeds thresholds."""
    xl = axes_obj.xlim[0]
    xr = axes_obj.xlim[1]
    yl = axes_obj.ylim[0]
    yr = axes_obj.ylim[1]
    x_span_min = axes_obj.spec.x_log_scale_min_span
    y_span_min = axes_obj.spec.y_log_scale_min_span

    if xl > 0 and xr > 0 and (xr / xl) >= x_span_min:
        ax.set_xscale("log")

    if yl > 0 and yr > 0 and (yr / yl) >= y_span_min:
        ax.set_yscale("log")


def plot(myfig: Figure) -> mfig.Figure:
    """
    Render a FigureSpec-driven Figure into a matplotlib Figure (OO-style).

    Guarantees:
    - All drawing-related Specs in base.py are respected
    - Global style cycles are shared across all Axes in the same Figure
    - If there are more series than cycle elements, cycles repeat automatically
    - Returns matplotlib.figure.Figure without saving
    """
    # Ensure every Data has an overall label (used for legends)
    fig_spec: FigureSpec = myfig.spec
    global_fontsize: float = getattr(fig_spec, "global_fontsize", 8.0)

    # Global style cycles (shared across the entire Figure)
    ls_cycle = _nonempty_cycle(getattr(fig_spec, "linestyle_cycle", ("-",)), ("-",))
    lc_cycle = _nonempty_cycle(getattr(fig_spec, "linecolor_cycle", ("black",)), ("black",))
    mk_cycle = _nonempty_cycle(getattr(fig_spec, "linemarker_cycle", ("o",)), ("o",))
    al_cycle = _nonempty_cycle(getattr(fig_spec, "alpa_cycle", (1.0,)), (1.0,))

    # ---------- Layout dispatch ----------
    muti_spec = myfig.muti_axes_spec
    mpl_axes: list[plt.Axes] = []

    if muti_spec is None:
        matfig, ax = plt.subplots(figsize=fig_spec.figsize, dpi=fig_spec.dpi)
        mpl_axes = [ax]

    elif isinstance(muti_spec, InsertAxesSpec):
        matfig = plt.figure(figsize=fig_spec.figsize, dpi=fig_spec.dpi)
        main_ax = matfig.add_subplot(111)
        inset_ax = main_ax.inset_axes([muti_spec.x, muti_spec.y, muti_spec.width, muti_spec.height])
        mpl_axes = [main_ax, inset_ax]

    elif isinstance(muti_spec, DualYAxesSpec):
        matfig = plt.figure(figsize=fig_spec.figsize, dpi=fig_spec.dpi)
        left_ax = matfig.add_subplot(111)
        right_ax = left_ax.twinx()
        mpl_axes = [left_ax, right_ax]

    elif isinstance(muti_spec, StackAxesSpec):
        matfig, axes = plt.subplots(
            muti_spec.nrows,
            muti_spec.ncols,
            figsize=fig_spec.figsize,
            dpi=fig_spec.dpi,
        )
        mpl_axes = [axes] if isinstance(axes, plt.Axes) else list(axes.flatten())

    else:
        raise TypeError(f"Unsupported MutiAxesSpec: {type(muti_spec)}")

    # Figure-level properties
    matfig.set_facecolor(fig_spec.facecolor)
    if getattr(fig_spec, "title", None):
        matfig.suptitle(fig_spec.title, fontsize=global_fontsize)

    per_ax_info: list[Tuple[plt.Axes, list, list, AxesSpec]] = []

    # ---------- Draw each Axes ----------
    for ax_idx, (ax, axes_obj) in enumerate(zip(mpl_axes, myfig.axes_pool)):
        axes_spec: AxesSpec = axes_obj.spec

        # for stack, every axes has its own cycle
        if isinstance(myfig.muti_axes_spec, StackAxesSpec):
            ls_cycle = _nonempty_cycle(getattr(fig_spec, "linestyle_cycle", ("-",)), ("-",))
            lc_cycle = _nonempty_cycle(getattr(fig_spec, "linecolor_cycle", ("black",)), ("black",))
            mk_cycle = _nonempty_cycle(getattr(fig_spec, "linemarker_cycle", ("o",)), ("o",))
            al_cycle = _nonempty_cycle(getattr(fig_spec, "alpa_cycle", (1.0,)), (1.0,))


        # Determine if this axes is an inset axes that should be slightly scaled down
        is_inset = isinstance(muti_spec, InsertAxesSpec) and (ax_idx == 1)
        style_scale = INSET_STYLE_SCALE if is_inset else 1.0

        # Apply per-data plotting
        for data in axes_obj.data_pool:
            if getattr(data, "ignore", False):
                continue

            points = data.points_for_plot

            # Default x/y selection: column 0 and 1
            xs = points[:,0]
            ys = points[:,1]


            ls = next(ls_cycle)
            lc = next(lc_cycle)
            mk = next(mk_cycle)      # still consume, even if not used (keeps cycles aligned)
            al = next(al_cycle)

            lw = getattr(axes_spec, "linewidth", 1.0) * style_scale
            ms = getattr(axes_spec, "marker_size", 4.0) * style_scale

            if ls == "|":
                # Stick plot: draw a vertical line at each x, from baseline to y.
                baseline = axes_spec.y_left_lim if axes_spec.y_left_lim is not None else 0.0
                ax.vlines(
                    xs,
                    baseline,
                    ys,
                    colors=lc,
                    linestyles="--",
                    linewidth=lw,
                    alpha=al,
                    label=data.labels.brief_summary,
                )
            else:
                ax.plot(
                    xs,
                    ys,
                    linestyle=ls,
                    color=lc,
                    marker=mk,
                    alpha=al,
                    linewidth=lw,
                    markersize=ms,
                    label=data.labels.brief_summary,
                )


        # Axis labels (axis-title fontsize should be slightly smaller on inset axes)
        axis_title_fs = getattr(axes_spec, "axis_title_font_size", global_fontsize) * style_scale
        ax.set_xlabel(axes_spec.x_axis_title, fontsize=axis_title_fs)
        ax.set_ylabel(axes_spec.y_axis_title, fontsize=axis_title_fs)

        # Limits
        if axes_spec.x_left_lim is not None or axes_spec.x_right_lim is not None:
            ax.set_xlim(axes_spec.x_left_lim, axes_spec.x_right_lim)
        if axes_spec.y_left_lim is not None or axes_spec.y_right_lim is not None:
            ax.set_ylim(axes_spec.y_left_lim, axes_spec.y_right_lim)

        # Log scale
        _maybe_set_log_scale(ax, axes_obj)

        # Ticks
        if getattr(axes_spec, "major_tick", None):
            _apply_ticks(ax, axes_spec.major_tick, global_fontsize)
        else:
            ax.tick_params(labelsize=global_fontsize)

        if getattr(axes_spec, "minor_tick", None):
            ax.minorticks_on()
            _apply_ticks(ax, axes_spec.minor_tick, global_fontsize)

        # Grids
        if getattr(axes_spec, "major_grid", None):
            _apply_grid(ax, axes_spec.major_grid, "major")
        if getattr(axes_spec, "minor_grid", None):
            ax.minorticks_on()
            _apply_grid(ax, axes_spec.minor_grid, "minor")

        # Annotations
        if getattr(axes_spec, "annotation", None):
            for ann in axes_spec.annotation:
                arrowprops = None
                xy = (ann.text_x, ann.text_y)

                if ann.arrow:
                    arrowprops = dict(
                        arrowstyle=_safe_arrowstyle(ann.arrow.arrowstyle),
                        color=ann.arrow.color,
                        linewidth=ann.arrow.linewidth,
                    )
                    xy = (ann.arrow.point_x, ann.arrow.point_y)

                ax.annotate(
                    ann.text,
                    xy=xy,
                    xytext=(ann.text_x, ann.text_y),
                    fontsize=ann.fontsize,
                    arrowprops=arrowprops,
                )

        # Collect legend handles/labels (legend placement is handled later)
        h, l = ax.get_legend_handles_labels()
        per_ax_info.append((ax, h, l, axes_spec))

    # ---------- Legend handling ----------
    def resolve_legend_spec(axes_spec: AxesSpec) -> Optional[LegendSpec]:
        # FigureSpec.legend is the global override/fallback (as you required earlier)
        return getattr(axes_spec, "legend", None) or getattr(fig_spec, "legend", None)

    if muti_spec is None:
        # Default: each subplot draws its own legend
        for ax, h, l, axes_spec in per_ax_info:
            _draw_axes_legend(ax, h, l, resolve_legend_spec(axes_spec))

    elif isinstance(muti_spec, StackAxesSpec):
        for ax, h, l, axes_spec in per_ax_info:
            _draw_axes_legend(ax, h, l, axes_spec.legend)

    elif isinstance(muti_spec, InsertAxesSpec):
        # InsertAxesSpec uses exactly the first two Axes for plotting (main + inset)
        holder = muti_spec.legend_holder
        if len(per_ax_info) >= 2:
            (ax0, h0, l0, spec0), (ax1, h1, l1, spec1) = per_ax_info[:2]
            handles = h0 + h1
            labels = l0 + l1

            if holder == "first axes":
                _draw_axes_legend(ax0, handles, labels, resolve_legend_spec(spec0))
            elif holder == "last axes":
                # IMPORTANT: all legends must appear on the last plotting axes (the inset axes here)
                _draw_axes_legend(ax1, handles, labels, resolve_legend_spec(spec1))
            elif holder == "figure":
                _draw_figure_legend(matfig, handles, labels, getattr(fig_spec, "legend", None))

    elif isinstance(muti_spec, DualYAxesSpec):
        # DualYAxesSpec: bind x-axis; only first two Axes are used.
        if len(per_ax_info) >= 2:
            (ax0, h0, l0, spec0), (_ax1, h1, l1, _spec1) = per_ax_info[:2]
            handles = h0 + h1
            labels = l0 + l1
            _draw_axes_legend(ax0, handles, labels, resolve_legend_spec(spec0))

    return matfig