from __future__ import annotations

from collections import Counter, defaultdict
from copy import copy

from ...base import *


# ---------------------------------------------------------------------------
# MT / MH preprocessing for Quantum Design MPMS3 measurements.
#
# - Retains the acquisition order (important for hysteresis curves).
# - Distinguishes independent temperature scans without assigning ZFC / FC.
# - Does not split a sweep merely because its rate, field step or sampling
#   frequency changes.
# - Uses only H and T for segmentation, never magnetic moment (the specimen
#   may show a genuine phase transition or a discontinuity in M).
# ---------------------------------------------------------------------------

FIGSIZE = (8, 6)
MIN_POINTS = 10

T = "Temperature (K)"
H = "Magnetic Field (Oe)"
M_VSM = "Moment (emu)"
M_FREE = "DC Moment Free Ctr (emu)"
M_FIXED = "DC Moment Fixed Ctr (emu)"

# Minimum total change required to regard a piece as an active H / T scan.
# Small controller fluctuations around a fixed setpoint are not a new sweep.
H_ACTIVE_SPAN = 5.0       # Oe
T_ACTIVE_SPAN = 0.12      # K

# Average change per acquired point used for detecting a PERSISTENT trend.
# Repeated MH measurements at the same field are supported.
H_TREND = 0.10            # Oe / point
T_TREND = 0.018          # K / point
TREND_HALF_WINDOW = 4
MIN_TREND_RUN = 6

# Minimum single-point discontinuities. The step must ALSO be anomalous
# relative to the measured increments on both sides of the proposed cut.
H_MIN_JUMP = 5.0          # Oe
T_MIN_JUMP = 0.20         # K
JUMP_NEIGHBORS = 9
JUMP_STEP_RATIO = 2.4
JUMP_NOISE_Z = 6.0

# Suppress nearly coincident detections, and avoid very short output fragments.
CUT_MERGE_DISTANCE = 5


def _significant_jumps(y: np.ndarray, min_jump: float, nonzero_eps: float) -> list[int]:
    """Find genuine acquisition discontinuities; ignore scan-step changes.

    A scheduled ramp can change from, e.g., 1 Oe steps to 50 Oe steps.
    Even though the immediate difference becomes large, the following steps
    share that size and should NOT be treated as a new MH sweep.
    """
    n = len(y)
    if n < 7:
        return []

    dy = np.diff(y)
    candidates = np.flatnonzero(np.abs(dy) >= min_jump)
    cuts = []

    for p in candidates:
        left = dy[max(0, p - JUMP_NEIGHBORS):p]
        right = dy[p + 1:min(len(dy), p + JUMP_NEIGHBORS + 1)]
        if len(left) < 2 or len(right) < 2:
            continue

        # Do not let the duplicated measurements in an MH scan make the
        # normal increment look like zero. Compare *nonzero* increments.
        left_nz = np.abs(left[np.abs(left) > nonzero_eps])
        right_nz = np.abs(right[np.abs(right) > nonzero_eps])
        typical_left = float(np.median(left_nz)) if len(left_nz) else 0.0
        typical_right = float(np.median(right_nz)) if len(right_nz) else 0.0
        typical = max(typical_left, typical_right)
        observed = abs(float(dy[p]))

        if typical > nonzero_eps and observed < JUMP_STEP_RATIO * typical:
            continue

        # Robust local noise check; a truly flat controller gives zero MAD.
        neighbors = np.r_[left, right]
        center = float(np.median(neighbors))
        mad = float(np.median(np.abs(neighbors - center)))
        noise = 1.4826 * mad
        if noise > nonzero_eps and abs(dy[p] - center) < JUMP_NOISE_Z * noise:
            continue

        cuts.append(int(p + 1))
    return cuts


def _trend_states(y: np.ndarray, slope_threshold: float) -> np.ndarray:
    """Robust local signs (-1, 0, +1), including repeated scan setpoints."""
    n = len(y)
    if n < 3:
        return np.zeros(n, dtype=np.int8)

    # A median first removes short excursions and sub-step controller noise.
    radius = 2
    padded = np.pad(y, (radius, radius), mode="edge")
    median = np.median(
        np.lib.stride_tricks.sliding_window_view(padded, 2 * radius + 1),
        axis=1,
    )
    step = TREND_HALF_WINDOW
    ix = np.arange(n)
    before = np.maximum(ix - step, 0)
    after = np.minimum(ix + step, n - 1)
    slope = (median[after] - median[before]) / np.maximum(after - before, 1)
    return np.where(slope > slope_threshold, 1,
                    np.where(slope < -slope_threshold, -1, 0)).astype(np.int8)


def _trend_runs(state: np.ndarray) -> list[tuple[int, int, int]]:
    """Only long, stable nonzero-direction runs are meaningful."""
    starts = np.r_[0, np.flatnonzero(np.diff(state) != 0) + 1]
    ends = np.r_[starts[1:], len(state)]
    return [(int(l), int(r), int(state[l]))
            for l, r in zip(starts, ends)
            if state[l] != 0 and r - l >= MIN_TREND_RUN]


def _reversal_cuts(y: np.ndarray, state: np.ndarray) -> list[int]:
    """Split true sweep reversals, not pauses or changes of scan speed."""
    runs = _trend_runs(state)
    cuts = []
    for (_, end0, direction0), (start1, _, direction1) in zip(runs, runs[1:]):
        if direction0 == direction1:
            continue
        lo = max(0, end0 - TREND_HALF_WINDOW)
        hi = min(len(y), start1 + TREND_HALF_WINDOW + 1)
        if hi <= lo:
            continue
        window = y[lo:hi]
        if direction0 > 0:
            # Last maximum in a flat plateau: second half starts on reversal.
            peak = np.flatnonzero(window == np.max(window))[-1]
        else:
            peak = np.flatnonzero(window == np.min(window))[-1]
        cuts.append(int(lo + peak + 1))
    return cuts


def _mode_switch_cuts(h_state: np.ndarray, t_state: np.ndarray) -> list[int]:
    """Detect a switch between an H scan and a T scan in the same file.

    Intermittent holds (state 0) never cause a cut by themselves.
    """
    mode = np.where((h_state != 0) & (t_state == 0), 1,
                    np.where((t_state != 0) & (h_state == 0), 2, 0))
    starts = np.r_[0, np.flatnonzero(np.diff(mode) != 0) + 1]
    ends = np.r_[starts[1:], len(mode)]
    runs = [(int(l), int(r), int(mode[l]))
            for l, r in zip(starts, ends)
            if mode[l] != 0 and r - l >= MIN_TREND_RUN]
    cuts = []
    for (_, last, old), (first, _, new) in zip(runs, runs[1:]):
        if old != new:
            cuts.append(int((last + first) // 2))
    return cuts


def _joint_cuts(h: np.ndarray, t: np.ndarray) -> list[int]:
    """Candidate positions in acquisition order; output includes 0 and n."""
    n = len(h)
    if n < 2:
        return [0, n]

    # Strong changes in physical setpoints can split even if the sweep
    # direction before and after the step is the same.
    jumps_h = _significant_jumps(h, H_MIN_JUMP, nonzero_eps=0.05)
    jumps_t = _significant_jumps(t, T_MIN_JUMP, nonzero_eps=0.002)
    strong = set(jumps_h + jumps_t)

    hs = _trend_states(h, H_TREND)
    ts = _trend_states(t, T_TREND)
    other = (_reversal_cuts(h, hs) + _reversal_cuts(t, ts) +
             _mode_switch_cuts(hs, ts))
    candidates = sorted(set(other) | strong)
    candidates = [p for p in candidates if 0 < p < n]

    # Group detections of the same physical transition; exact measured jumps
    # take precedence over approximate trend-transition positions.
    clusters: list[list[int]] = []
    for p in candidates:
        if clusters and p - clusters[-1][-1] <= CUT_MERGE_DISTANCE:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    merged = []
    for group in clusters:
        exact = [p for p in group if p in strong]
        cut = exact[0] if exact else group[len(group) // 2]
        merged.append(cut)

    # Avoid keeping a tiny tail created by controller noise. Only substantial
    # discontinuities get to bypass the minimum fragment size.
    final = [0]
    for p in merged:
        if p - final[-1] < MIN_POINTS:
            continue
        if n - p < MIN_POINTS:
            continue
        final.append(p)
    final.append(n)
    return final


def _classify(h: np.ndarray, t: np.ndarray) -> str | None:
    """Return MH for active field scans, MT for active temperature scans."""
    if len(h) < MIN_POINTS:
        return None
    # Percentile spans are robust to a single imperfect stabilization point.
    h_span = float(np.percentile(h, 95) - np.percentile(h, 5))
    t_span = float(np.percentile(t, 95) - np.percentile(t, 5))

    h_score = h_span / H_ACTIVE_SPAN
    t_score = t_span / T_ACTIVE_SPAN
    if h_score < 1 and t_score < 1:
        return None
    return "MH" if h_score >= t_score else "MT"


def _moment_column(headers: dict[str, int], points: np.ndarray) -> str | None:
    """Respect the existing Majoplot VSM importer (free-center DC data).

    If a future importer also exposes direct VSM Moment (emu), prefer it
    when it contains values; do not modify the raw importer's headers.
    """
    for name in (M_VSM, M_FREE, M_FIXED):
        if name in headers:
            col = np.asarray(points[:, headers[name]], dtype=float)
            if np.isfinite(col).any():
                return name
    return None


class MT_and_MH:
    data_summary_label_names = ["H_or_T"]
    axes_label_names = ("material", "date", "raw_data", "measurement")
    figure_label_names = ("material", "date", "raw_data", "measurement")
    figure_summary_label_names = ("raw_data", "measurement")
    max_axes_in_one_figure = 1
    project_to_child_folder_label_names = {"material": "date", "date": "material"}
    parent_folder_name = "MTMH"

    @classmethod
    def preprocess(cls, raw_datas: list[Data]) -> list[Data]:
        datas = []
        for raw_data in raw_datas:
            headers = raw_data.headers
            points = np.asarray(raw_data.points)
            if len(points) < MIN_POINTS or T not in headers or H not in headers:
                continue
            m_name = _moment_column(headers, points)
            if m_name is None:
                continue

            h = np.asarray(points[:, headers[H]], dtype=float)
            t = np.asarray(points[:, headers[T]], dtype=float)
            cuts = _joint_cuts(h, t)

            segments = []
            for start, stop in zip(cuts[:-1], cuts[1:]):
                measurement = _classify(h[start:stop], t[start:stop])
                if measurement is None:
                    continue
                if measurement == "MH":
                    # Representative constant T; never use the first point
                    # alone because it may be undergoing stabilization.
                    stage = round(float(np.median(t[start:stop])), 1)
                    x_name = H
                else:
                    stage = round(float(np.median(h[start:stop])))
                    x_name = T
                segments.append((start, stop, measurement, stage, x_name))

            # At identical H, separate independently recorded MT scans; do
            # not call them ZFC/FC or guess from temperature direction.
            total_per_stage = Counter((mode, stage) for _, _, mode, stage, _ in segments)
            sequence = defaultdict(int)

            for start, stop, measurement, stage, x_name in segments:
                sequence[(measurement, stage)] += 1
                serial = sequence[(measurement, stage)]
                labels = copy(raw_data.labels)
                labels["measurement"] = LabelValue(measurement, unit_as_postfix=False)
                labels["scenario"] = LabelValue(measurement, unit_as_postfix=False)
                labels["H_or_T"] = LabelValue(stage,
                                                  unit="K" if measurement == "MH" else "Oe")
                labels["H" if measurement == "MT" else "T"] = labels["H_or_T"]
                if total_per_stage[(measurement, stage)] > 1:
                    labels["scan"] = LabelValue(serial, unit_as_postfix=False)
                    labels.summary_names = ["H_or_T", "scan"]
                else:
                    labels.summary_names = cls.data_summary_label_names

                datas.append(Data(
                    labels=labels,
                    _headers=(x_name, m_name),
                    points=np.asarray(points[start:stop,
                                              [headers[x_name], headers[m_name]]],
                                      dtype=float),
                    ignore_outliers=IgnoreOutlierSpec(
                        min_gap_base=5e-7, min_gap_multiple=10,
                    ),
                ))
        return datas

    @classmethod
    def make_axes_spec(cls, axes_labels, data_pool) -> AxesSpec:
        measurement = axes_labels["measurement"].value
        # In the current importer this is M_FREE. Preserve the actual y-column
        # name if a future importer supplies direct VSM or fixed-center data.
        y_name = next((data._headers[1] for data in data_pool), M_FREE)
        return AxesSpec(
            x_axis_title=T if measurement == "MT" else H,
            y_axis_title=y_name,
            major_grid=None,
            major_tick=TickSpec(),
            legend=LegendSpec(fontsize=7),
            linewidth=1,
            marker_size=2,
        )

    @classmethod
    def make_figure_spec(cls, figure_labels, axes_pool: Iterable[Axes]) -> FigureSpec:
        return FigureSpec(
            name=figure_labels.brief_summary,
            title=None,
            figsize=FIGSIZE,
            linestyle_cycle=("-",),
            linemarker_cycle=("o",),
            linecolor_cycle=(
                "#515151", "#F14040", "#1A6FDF", "#37AD6B", "#B177DE",
                "#CC9900", "#00CBCC", "#7D4E4E", "#8E8E00", "#FB6501",
                "#6699CC", "#6FB802", "#FD0000FF", "#15ff00", "#FF9447",
            ),
            alpa_cycle=(1.0,),
        )

    @classmethod
    def make_muti_axes_spec(cls, axes_pool: list[Axes]) -> MutiAxesSpec | FAIL | None:
        return None