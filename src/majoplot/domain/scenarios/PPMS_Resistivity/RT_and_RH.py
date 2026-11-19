from __future__ import annotations

from ...base import *


FIGSIZE = (8, 6)
MIN_POINTS = 10
SPLIT_MAGNETIC_GAP = 1000
SPLIT_TEMPERATURE_GAP = 0.3

# Candidate windows are expressed in measured points on EACH side of a cut.
WINDOWS = (8, 16, 32)
MIN_SEGMENT_POINTS = 10
# Detection sensitivity. Increase to suppress false positives.
JUMP_Z = 7.0
KINK_Z = 8.0
# Physical lower bounds prevent tiny controller fluctuations being mistaken for cuts.
H_MIN_JUMP = 30.0       # Oe
T_MIN_JUMP = 0.05       # K
H_MIN_SLOPE_CHANGE = 40.0  # Oe / point
T_MIN_SLOPE_CHANGE = 0.025 # K / point
# A kink must also be a substantial fraction of the local scan rate.
H_RELATIVE_SLOPE_CHANGE = 0.28
T_RELATIVE_SLOPE_CHANGE = 0.65

T = "Temperature (K)"
H = "Magnetic Field (Oe)"
R = "Resistance (Ohms)"
RI = {
    1: {"R": "Bridge 1 Resistance (Ohms)", "I": "Bridge 1 Excitation (uA)"},
    2: {"R": "Bridge 2 Resistance (Ohms)", "I": "Bridge 2 Excitation (uA)"},
    3: {"R": "Bridge 3 Resistance (Ohms)", "I": "Bridge 3 Excitation (uA)"},
}


def _fit_windows(y: np.ndarray, centers: np.ndarray, width: int, prefix: tuple[np.ndarray, ...]):
    """OLS line on [l, r) in O(1) per window using cumulative sums."""
    py, pyy, pxy = prefix
    n = float(width)
    # Local x-coordinate is 0,1,...,width-1 to avoid numerical cancellation.
    # Sum (x-l)*y == sum (global_x*y) - l*sum(y).
    def fit(starts):
        ends = starts + width
        sy = py[ends] - py[starts]
        syy = pyy[ends] - pyy[starts]
        sxy = (pxy[ends] - pxy[starts]) - starts * sy
        sx = n * (n - 1) / 2
        sxx = n * (n - 1) * (2 * n - 1) / 6
        cxy = sxy - sx * sy / n
        cxx = sxx - sx * sx / n
        slope = cxy / cxx
        intercept = (sy - slope * sx) / n
        rss = syy - sy * sy / n - cxy * cxy / cxx
        rss = np.maximum(rss, 0)
        return slope, intercept, rss
    left_a, left_b, left_rss = fit(centers - width)
    right_a, right_b, right_rss = fit(centers)
    # Extrapolate to the boundary x=centers.
    jump = right_b - (left_b + left_a * width)
    kink = right_a - left_a
    return jump, kink, left_a, right_a, left_rss + right_rss


def _motion_cuts(y: np.ndarray, threshold: float) -> list[int]:
    """Detect persistent changes between falling, constant, and rising scans.

    Monotone variation in ramp *speed* is deliberately kept in one sweep.
    """
    n = len(y)
    if n < 2 * MIN_SEGMENT_POINTS:
        return []
    diff = np.diff(y)
    radius = 4
    padded = np.pad(diff, (radius, radius), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * radius + 1)
    slope = np.median(windows, axis=1)
    state = np.where(slope > threshold, 1,
                     np.where(slope < -threshold, -1, 0))
    # Clean up short spurious state excursions.
    for _ in range(2):
        starts = np.r_[0, np.flatnonzero(np.diff(state) != 0) + 1]
        ends = np.r_[starts[1:], len(state)]
        for k, (l, r) in enumerate(zip(starts, ends)):
            if r - l >= MIN_SEGMENT_POINTS // 2:
                continue
            left = state[starts[k - 1]] if k else None
            right = state[starts[k + 1]] if k + 1 < len(starts) else None
            if left is not None and left == right:
                state[l:r] = left
            elif left is not None and right is not None:
                state[l:r] = left if l - starts[k - 1] >= ends[k + 1] - r else right
    starts = np.r_[0, np.flatnonzero(np.diff(state) != 0) + 1]
    ends = np.r_[starts[1:], len(state)]
    cuts = []
    for k in range(1, len(starts)):
        if (ends[k-1] - starts[k-1] >= MIN_SEGMENT_POINTS // 2 and
                ends[k] - starts[k] >= MIN_SEGMENT_POINTS // 2):
            cuts.append(int(starts[k]))
    return cuts


# Verification of a one-sample discontinuity must use the *actual* adjacent
# increment. A controller pause, a rate change or smooth curvature can give
# two independent OLS lines different extrapolated intercepts without a jump.
JUMP_STEP_RATIO = 2.2    # Require an anomalously LARGE step on an active ramp.
JUMP_NOISE_Z = 5.0       # Minimum local first-difference significance.
JUMP_NEIGHBORS = 8      # Nearby differences used to estimate normal motion.


def _verify_discontinuous_step(y: np.ndarray, cut: int, min_jump: float) -> bool:
    """Reject continuous motion (including pauses and scan-speed changes).

    A real vertical step makes the measured adjacent increment abnormally
    *larger* than ordinary increments on both sides. A pause instead makes
    it smaller. For nearly flat segments, use a robust estimate of the
    first-difference noise to admit small but statistically clear steps.

    This check is applied equally to H and T.
    """
    d = np.diff(y)
    pos = cut - 1
    n = len(d)
    radius = JUMP_NEIGHBORS
    left = d[max(0, pos - radius):pos]
    right = d[pos + 1:min(n, pos + radius + 1)]
    if len(left) < 3 or len(right) < 3:
        return False

    observed = float(d[pos])
    typical_left = float(np.median(left))
    typical_right = float(np.median(right))
    # A valid step must be anomalous relative to both adjacent scan rates.
    typical = max(abs(typical_left), abs(typical_right))
    # Allow the baseline drift estimate to differ on the two sides.
    residual = min(abs(observed - typical_left),
                   abs(observed - typical_right))

    neighbor = np.r_[left, right]
    med = float(np.median(neighbor))
    noise = 1.4826 * float(np.median(np.abs(neighbor - med)))

    if residual < min_jump:
        return False
    if typical > min_jump:
        # Discard stops, restarts, smooth ramp-rate changes and short holds.
        if abs(observed) <= JUMP_STEP_RATIO * typical:
            return False
    elif noise > 0 and residual < JUMP_NOISE_Z * noise:
        return False
    return True


def _small_jump_cuts(y: np.ndarray, min_jump: float) -> list[int]:
    """Candidate steps: robust first-difference anomaly + two-sided OLS.

    Stage 1 checks the raw adjacent increment before considering a split.
    Stage 2 tests whether separate local regression lines imply a sustained
    level change rather than a slope kink or one noisy sample.
    """
    n = len(y)
    w = 12
    if n < 2 * w + 1:
        return []
    d = np.diff(y)
    padding = np.pad(d, (w, w), mode="edge")
    local = np.median(
        np.lib.stride_tricks.sliding_window_view(padding, 2*w+1), axis=1
    )
    idx = np.flatnonzero(np.abs(d - local) >= min_jump) + 1
    idx = idx[(idx >= w) & (idx + w <= n)]
    if not len(idx):
        return []

    # Fast rejection of instrument ramps and pauses, before OLS.
    idx = np.asarray(
        [c for c in idx if _verify_discontinuous_step(y, int(c), min_jump)],
        dtype=int,
    )
    if not len(idx):
        return []

    x = np.arange(n, dtype=float)
    yy = y.astype(float)
    prefix = tuple(np.r_[0., np.cumsum(v)] for v in (yy, yy * yy, x * yy))
    jump, kink, a0, a1, rss = _fit_windows(y, idx, w, prefix)
    sigma = np.sqrt(np.maximum(rss, 0) / (2 * w - 4))
    sxx = w * (w*w - 1) / 12
    se = sigma * np.sqrt(2 * (1 / w + ((w+1)/2)**2 / sxx))
    slope_limit = 0.20 * np.maximum(np.maximum(np.abs(a0), np.abs(a1)),
                                     min_jump / w)
    ramp = np.maximum(np.abs(a0), np.abs(a1))
    ok = ((np.abs(jump) >= np.maximum(min_jump, 0.7 * ramp)) &
          (np.abs(kink) <= slope_limit) &
          (np.abs(jump) >= JUMP_Z * np.maximum(se, 1e-10)))
    return idx[ok].astype(int).tolist()


def _joint_cuts(h: np.ndarray, t: np.ndarray) -> list[int]:
    n = len(h)
    # The persistent slope-state changes capture scan starts, stops,
    # and reversals, while localized regressions capture small steps.
    cuts = set(_motion_cuts(h, threshold=12.0))
    cuts.update(_motion_cuts(t, threshold=0.008))
    cuts.update(_small_jump_cuts(h, min_jump=H_MIN_JUMP))
    cuts.update(_small_jump_cuts(t, min_jump=T_MIN_JUMP))
    # Large point-to-point increments are not necessarily jumps: on a fast
    # programmed ramp they can be completely normal. Apply the SAME physical
    # discontinuity check to these legacy threshold candidates.
    for y, gap, min_jump in (
        (h, SPLIT_MAGNETIC_GAP, H_MIN_JUMP),
        (t, SPLIT_TEMPERATURE_GAP, T_MIN_JUMP),
    ):
        for c in np.flatnonzero(np.abs(np.diff(y)) > gap) + 1:
            if _verify_discontinuous_step(y, int(c), min_jump):
                cuts.add(int(c))
    # Resolve duplicate detections near the same transition. A true
    # adjacent jump is more precisely located than a fitted change.
    candidates = sorted(c for c in cuts if MIN_SEGMENT_POINTS <= c <= n - MIN_SEGMENT_POINTS)
    clusters: list[list[int]] = []
    for c in candidates:
        if clusters and c - clusters[-1][-1] < MIN_SEGMENT_POINTS:
            clusters[-1].append(c)
        else:
            clusters.append([c])
    merged = []
    for group in clusters:
        strong = [c for c in group if (abs(h[c] - h[c-1]) > SPLIT_MAGNETIC_GAP
                                        or abs(t[c] - t[c-1]) > SPLIT_TEMPERATURE_GAP)]
        merged.append(strong[0] if strong else group[len(group) // 2])
    return [0, *merged, n]


class RT_and_RH:
    data_summary_label_names = ["H_or_T"]
    axes_label_names = ("date", "raw_data", "bridge", "sample_name", "measurement")
    figure_label_names = ("date", "raw_data", "bridge", "sample_name", "measurement")
    figure_summary_label_names = ("raw_data", "bridge", "sample_name", "measurement")
    max_axes_in_one_figure = 1
    project_to_child_folder_label_names = {"date": "sample_name"}
    parent_folder_name = "RTRH"

    @classmethod
    def preprocess(cls, raw_datas: list[Data]) -> list[Data]:
        datas = []
        for raw_data in raw_datas:
            raw_labels = raw_data.labels
            headers = raw_data.headers
            raw_points = raw_data.points
            if not len(raw_points):
                continue

            h = np.asarray([p[headers[H]] for p in raw_points], dtype=float)
            t = np.asarray([p[headers[T]] for p in raw_points], dtype=float)
            cuts = _joint_cuts(h, t)

            for start, stop in zip(cuts[:-1], cuts[1:]):
                if stop - start < MIN_POINTS:
                    continue
                points = raw_points[start:stop]
                seg_h, seg_t = h[start:stop], t[start:stop]

                # Classify by which variable is actively scanned.
                h_span = float(np.max(seg_h) - np.min(seg_h))
                t_span = float(np.max(seg_t) - np.min(seg_t))
                if h_span > SPLIT_MAGNETIC_GAP:
                    measurement = "RH"
                    h_or_t = round(float(np.median(seg_t)), 1)
                    axis = H
                else:
                    measurement = "RT"
                    h_or_t = round(float(np.median(seg_h)))
                    axis = T
                # Ignore segments in which neither H nor T is actually scanned.
                if measurement == "RT" and t_span < SPLIT_TEMPERATURE_GAP:
                    continue

                for i in range(1, 4):
                    cols = (axis, RI[i]["R"], RI[i]["I"])
                    s_points = [
                        [point[headers[col]] for col in cols]
                        for point in points
                    ]
                    # Preserve the original filtering semantics (no NaN cleanup).
                    s_points = np.asarray([p for p in s_points if p[1]], dtype=float)
                    if len(s_points) < MIN_POINTS:
                        continue
                    currents = s_points[:, 2]
                    imin, imax = float(np.min(currents)), float(np.max(currents))
                    if imax != 0 and (imax - imin) / abs(imax) < 0.03:
                        irange = f"{np.mean(currents):.1e}"
                    else:
                        irange = f"{imin:.1e}~{imax:.1e}"

                    labels = LabelDict()
                    labels["instrument"] = raw_labels["instrument"]
                    labels["raw_data"] = raw_labels["raw_data"]
                    labels["date"] = raw_labels["date"]
                    labels["bridge"] = LabelValue(i, unit="Bridge", unit_as_postfix=False)
                    labels["sample_name"] = raw_labels[f"sample{i}_name"]
                    labels["sample_units"] = raw_labels[f"sample{i}_units"]
                    labels["measurement"] = LabelValue(measurement, unit=None,
                                                       unit_as_postfix=False)
                    labels["H_or_T"] = LabelValue(h_or_t,
                                                  unit="K" if measurement == "RH" else "Oe")
                    labels["I_range"] = LabelValue(irange, unit="μA")
                    labels.summary_names = cls.data_summary_label_names
                    datas.append(Data(
                        labels=labels,
                        _headers=(axis, RI[i]["R"]),
                        points=s_points[:, :2],
                        ignore_outliers=IgnoreOutlierSpec(
                            min_gap_base=1e-4, min_gap_multiple=10
                        ),
                    ))
        return datas

    @classmethod
    def make_axes_spec(cls, axes_labels, data_pool) -> AxesSpec:
        axis = T if axes_labels["measurement"].value == "RT" else H
        return AxesSpec(
            x_axis_title=axis,
            y_axis_title=R,
            major_grid=None,
            major_tick=TickSpec(),
            legend=LegendSpec(fontsize=5),
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
                "#fdbb2d", "#fcfdbf", "#2B2E83", "#E6007A", "#00FFFF",
                "#6DFFA7", "#FDBAFD", "#FAB3d1",
            ),
            alpa_cycle=(1.0,),
        )

    @classmethod
    def make_muti_axes_spec(cls, axes_pool: list[Axes]) -> MutiAxesSpec | FAIL | None:
        return None
