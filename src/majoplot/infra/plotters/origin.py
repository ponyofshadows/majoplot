from __future__ import annotations

from pathlib import WindowsPath, Path
from typing import Optional, Any, Union
_ColorLike = Union[str, tuple[int, int, int], list[int]]

import numpy as np
from win32com.client import Dispatch

from ...domain.base import *
from ...domain.muti_axes_spec import *
from .origin_utils.originlab_type_library import constants


# --- Unit/scale mapping ---
# Origin uses its own point-like units for font size, line width, and symbol size in LabTalk.
# FONT_PT_SCALE is a rough conversion factor used throughout style setters.
# INSET_SCALE / MAIN_SCALE are intended to scale styles between main vs inset layers,
# but note that curve_scale is computed later and is NOT used inside _apply_curve_style() in this file.
FONT_PT_SCALE = 2.3
INSET_SCALE = 2.5  # inset linewidth/marker/title a bit smaller
MAIN_SCALE = 1.5  # inset linewidth/marker/title a bit smaller
# -------------------------
# COM Resourse
# -------------------------
## How to get help:
## Run:
##  python -m win32com.client.makepy
## choose "OriginLab Type Library"
## Find APIs in generated py file. (maybe under C:\Users\user_name\AppData\Local\Temp\gen_py/)

## tested with OriginPro 2021


# -------------------------
# Origin COM bootstrap (COM = Component Object Model)
# -------------------------
# OriginCOM is a context manager that creates/controls an Origin instance.
# Typical usage:
#   with OriginCOM(visible=True) as og:
#       plot(project, name, og, proj_dir=..., overwrite=...)
# Behavior notes:
# - __enter__ calls BeginSession() and returns the Application COM object.
# - __exit__ tries to Exit() Origin (closing the application).
# - If you need Origin to remain open for interactive debugging, modify *caller* behavior,
#   not this class; this annotated file must keep logic unchanged.
class OriginCOM:
    """
    OriginCOM
    create a ApplicationCMOSI instance of Origin. See https://www.originlab.com/doc/en/COM/Classes/ApplicationCOMSI.
    """
    def __init__(self,visible:bool):
        self.visible = visible
        app = None

    def __enter__(self):
        # Acquire COM automation entry point: Origin.ApplicationCOMSI
        # Most actions below happen through LabTalk commands (og.Execute).
        # Dispatch() attaches to Origin via COM.
        self.app = Dispatch("Origin.ApplicationCOMSI")
        if self.visible:
            self.app.Visible = constants.MAINWND_SHOW
        else:
            self.app.Visible = constants.MAINWND_HIDE
        # Reduce UI noise / command window chatter
        # doc -mc 1: suppress some UI/command-window chatter during batch automation.
        self.app.Execute("doc -mc 1;")
        # BeginSession(): recommended by Origin for COM automation batches.
        self.app.BeginSession()
        return self.app

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.app.Execute("doc -mc 0;")
        except Exception:
            pass
        try:
            if self.app is not None:
                self.app.Exit()
        except Exception:
            pass
        self.app = None

# =========================
# LabTalk helpers
# =========================


# -------------------------
# LabTalk command execution helper
# -------------------------
# This wrapper intentionally swallows failures after printing.
# Consequence: style commands can fail silently, leaving defaults in place,
# which may look like "random" styles. Consider temporarily making this stricter
# during debugging (but NOT in this annotated file).
def _try_exec(og: Any, lt: str) -> None:
    """
    execute Labtalk commands
    """
    try:
        og.Execute(lt)
    except Exception as e:
        print(f"LabTalk command '{lt}' failed: {e}")
        pass

# ==========================
# OPJU Manager
# ==========================

# -------------------------
# Project open/create (.opju)
# -------------------------
# This function enforces suffix and ensures the directory exists.
# It does NOT create folders/pages inside the project; it only manages the project file itself.
def open_or_create_project(
    og,
    project_path: Union[str, Path],
    *,
    readonly: bool = False,
) -> None:
    """
    Open an existing Origin project, or create a new one and save to path.

    Parameters
    ----------
    og : COM object
        Origin.ApplicationCOMSI instance
    project_path : str | Path
        Full path to .opju or .opj
    readonly : bool
        Open project in read-only mode if exists
    """
    path = Path(project_path).expanduser().resolve()

    # ---- sanity checks ----
    if path.suffix.lower() not in {".opju", ".opj"}:
        raise ValueError("Origin project must end with .opju or .opj")

    # Ensure parent directory exists (for create case)
    path.parent.mkdir(parents=True, exist_ok=True)

    # If project already exists: load it.
    if path.exists():
        # ===== open existing project =====
        # Origin COM exposes Open() directly
        og.Load(str(path), int(bool(readonly)))
    else:
        # ===== create new project =====
        try:
            og.NewProject()
        except Exception:
            # fallback (older builds / edge cases)
            og.Execute("doc -n;")

        # Save immediately to bind project path
        og.Save(str(path))




# -------------------------
# LabTalk string escaping
# -------------------------
# Origin LabTalk uses "..." string literals. Backslashes and quotes need escaping.
def _lt_quote(s: str) -> str:
    """Escape string for LabTalk "..." literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')

def _lt_quote_keep_backslash(s: str) -> str:
    # Only escape double quotes for LabTalk "...".
    return s.replace('"', r'\"')



# Color helpers
# - _lt_color_expr outputs color(name) or color(r,g,b) for #RRGGBB
# - _lt_color_rgb always forces RGB form to avoid name-resolution surprises
def _lt_color_expr(color: str) -> str:
    """Return LabTalk color() expression supporting '#RRGGBB' and names."""
    c = (color or "").strip()
    if c.startswith("#") and len(c) in (7, 9):
        r = int(c[1:3], 16)
        g = int(c[3:5], 16)
        b = int(c[5:7], 16)
        return f"color({r},{g},{b})"
    if not c:
        c = "black"
    return f"color({c})"

def _lt_color_rgb(color: _ColorLike, *, fallback=(250, 179, 209)) -> str:
    """
    Convert a color literal to LabTalk-safe RGB expression: color(R,G,B).

    Intended for Axis / Grid / Tick / Border colors in Origin.
    Avoids silent fallback caused by color(name).

    Supported inputs:
    - color names: "grey", "gray", "black", "red", ...
    - hex strings: "#RRGGBB", "#RGB"
    - RGB tuple/list: (r, g, b)
    - None -> fallback

    Returns:
        str: 'color(R,G,B)'
    """
    if color is None:
        r, g, b = fallback
        return f"color({r},{g},{b})"

    # --- RGB tuple/list ---
    if isinstance(color, (tuple, list)) and len(color) == 3:
        r, g, b = (int(c) for c in color)
        return f"color({r},{g},{b})"

    if not isinstance(color, str):
        r, g, b = fallback
        return f"color({r},{g},{b})"

    c = color.strip().lower()

    # --- Hex formats ---
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 6:
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            return f"color({r},{g},{b})"
        if len(h) == 3:
            r = int(h[0] * 2, 16)
            g = int(h[1] * 2, 16)
            b = int(h[2] * 2, 16)
            return f"color({r},{g},{b})"

    # --- Named colors (minimal but sufficient for grids) ---
    NAMED_RGB = {
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "red": (255, 0, 0),
        "green": (0, 128, 0),
        "blue": (0, 0, 255),
        "grey": (128, 128, 128),
        "gray": (128, 128, 128),
        "lightgrey": (200, 200, 200),
        "lightgray": (200, 200, 200),
        "darkgrey": (96, 96, 96),
        "darkgray": (96, 96, 96),
        "pinkie_pie": (250,179,209)
    }

    if c in NAMED_RGB:
        r, g, b = NAMED_RGB[c]
        return f"color({r},{g},{b})"

    # --- Fallback ---
    r, g, b = fallback
    return f"color({r},{g},{b})"


# Origin plot style code maps
# These integers are consumed by `set %C -d <code>` or similar LabTalk.
_LINESTYLE_CODE = {
    "-": 0,     # solid
    "--": 2,    # dash
    ":": 3,     # dot
    "-.": 4,    # dash-dot
}
_GRID_LINESTYLE_CODE = {
    "-": 1,   # solid
    "--": 2,  # dash
    ":": 3,   # dot
    "-.": 4,  # dash-dot
}

_MARKER_CODE = {
    "s": 1,   # square
    "o": 2,   # circle
    "^": 3,   # up triangle
    "v": 4,   # down triangle
    "D": 5,   # diamond
    "d": 5,
    "+": 6,   # plus
    "x": 7,   # x
    "*": 8,   # star
}



# IMPORTANT: plotxy plot code selection
# In this file, _choose_plot_code ALWAYS returns 202 (line+symbol).
# That means even if a series should be "line only" or "scatter only",
# Origin still creates a line+symbol plot, and later style setters try to disable/alter pieces.
# This can contribute to confusing marker/line behavior.
def _choose_plot_code(linestyle: str, marker: str) -> int:
    """plotxy plot codes: 200=line, 201=scatter, 202=line+symbol"""
    # has_line = bool(linestyle) and linestyle != "None"
    # has_marker = bool(marker) and marker != "None"
    # if has_line and has_marker:
    #     return 202
    # if has_marker and not has_line:
    #     return 201
    # return 200
    return 202


def _graph_sanitize_name(name: str, fallback: str = "MajoGraph") -> str:
    """
    Origin Graph Page Short Name Limit: <= 24 Characters
    """
    if not name:
        return fallback
    out = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out).strip("_")
    if not s:
        return fallback
    if not s[0].isalpha():
        s = "G_" + s
    if len(s) > 24:
        s = f"{s[:10]}__{s[-10:]}"
    return s

def _workbook_sanitize_name(name: str, fallback: str = "MajoGraph") -> str:
    """
    Origin WorkBook Short Name Limit: <= 13 Characters
    """
    if not name:
        return fallback
    out = []
    for ch in name:
        if ch.isalnum():
            out.append(ch)
    s = "".join(out)
    if not s:
        return fallback
    if not s[0].isalpha():
        s = "W" + s
    if len(s) > 13:
        s = f"{s[:6]}{s[-6:]}"
    return s

# =========================
# Figure-level style cycle
# =========================


# -------------------------
# Figure-level style cycle (shared across ALL layers)
# -------------------------
# This generator advances a single index i each time next() is called.
# In plot(), a single iterator is created per Figure and is consumed for every curve
# across all layers. There is NO per-axes reset here, even for StackAxesSpec.
def iter_cycles(figspec: FigureSpec) -> Iterator[dict[str, Any]]:
    """Yield per-line styles. Each new line advances ALL cycles once."""
    i = 0
    while True:
        yield {
            "color": figspec.linecolor_cycle[i % len(figspec.linecolor_cycle)],
            "linestyle": figspec.linestyle_cycle[i % len(figspec.linestyle_cycle)],
            "marker": figspec.linemarker_cycle[i % len(figspec.linemarker_cycle)],
            "alpha": figspec.alpa_cycle[i % len(figspec.alpa_cycle)],
        }
        i += 1


# =========================
# Spec application helpers
# =========================

# Log-scale heuristic
# If limits are positive AND span ratio exceeds threshold, enable log10 axis in Origin.
# Note: the code later writes layer.x.from/to and layer.y.from/to using numeric values;
# their interpretation depends on layer.x.type / layer.y.type (linear vs log).
def _should_set_log_scale(axes_obj: Axes) -> tuple[bool,bool]:
    """Enable log scale when limits are positive and span exceeds thresholds."""
    xl = axes_obj.xlim[0]
    xr = axes_obj.xlim[1]
    yl = axes_obj.ylim[0]
    yr = axes_obj.ylim[1]
    x_span_min = axes_obj.spec.x_log_scale_min_span
    y_span_min = axes_obj.spec.y_log_scale_min_span

    should_x, should_y = False, False
    if xl > 0 and xr > 0 and (xr / xl) >= x_span_min:
        should_x = True

    if yl > 0 and yr > 0 and (yr / yl) >= y_span_min:
        should_y = True
    return should_x, should_y


def _apply_full_frame_axes(og: Any) -> None:
    """Force full-frame axes (top/right show line & ticks) at UI/OPJU level."""
    # Caller should have selected layer: layer -s N;
    _try_exec(og, "layer.border=0;")

    # Axis display: 0=None, 1=First, 2=Second, 3=Both
    # For X: First=Bottom, Second=Top; For Y: First=Left, Second=Right
    _try_exec(og, "axis -ps X A 3;")  # show bottom+top axis line & ticks
    _try_exec(og, "axis -ps Y A 3;")  # show left+right axis line & ticks

    # Tick label display (optional):
    # Keep labels only on Bottom/Left (typical matplotlib look).
    _try_exec(og, "axis -ps X L 1;")
    _try_exec(og, "axis -ps Y L 1;")

    # Keep secondary axes linked to primary if your version supports it
    _try_exec(og, "layer.x2.link=1;")
    _try_exec(og, "layer.y2.link=1;")




def _ticks_mask(direction: str, include_minor: bool) -> int:
    # ticks bitmask: major in=1, major out=2, minor in=4, minor out=8
    d = (direction or "in").lower()
    if d == "in":
        return (1 | (4 if include_minor else 0))
    return (2 | (8 if include_minor else 0))



# Tick application (best-effort)
# Many tick/grid properties in Origin depend on version; failed commands fall back silently via _try_exec.
def _apply_tick_spec(og: Any, major: Optional[TickSpec], minor: Optional[TickSpec], global_fontsize: float, scale: float) -> None:
    """Apply major/minor ticks (best-effort) to x/y axes."""
    include_minor = minor is not None

    # tick label fontsize (Origin uses layer.x.label.fsize etc)
    _try_exec(og, f"layer.x.label.fsize={global_fontsize * FONT_PT_SCALE * scale};")
    _try_exec(og, f"layer.y.label.fsize={global_fontsize * FONT_PT_SCALE * scale};")
    _try_exec(og, f"layer.x2.label.fsize={global_fontsize * FONT_PT_SCALE *scale};")
    _try_exec(og, f"layer.y2.label.fsize={global_fontsize * FONT_PT_SCALE * scale};")

    # Direction
    direction = major.direction if major is not None else ("in" if minor is None else minor.direction)
    mask = _ticks_mask(direction, include_minor)
    _try_exec(og, f"layer.x.ticks={mask}; layer.y.ticks={mask};")
    _try_exec(og, f"layer.x2.ticks={mask}; layer.y2.ticks={mask};")

    # Length/width
    if major is not None:
        _try_exec(og, f"layer.x.ticklength={major.length * scale}; layer.y.ticklength={major.length * scale};")
        _try_exec(og, f"layer.x2.ticklength={major.length * scale}; layer.y2.ticklength={major.length * scale};")
        _try_exec(og, f"layer.x.tickthickness={major.width}; layer.y.tickthickness={major.width};")
        _try_exec(og, f"layer.x2.tickthickness={major.width}; layer.y2.tickthickness={major.width};")

        # Which sides show ticks (best-effort)
        if not major.top:
            _try_exec(og, "layer.x2.show=0;")
        if not major.left:
            _try_exec(og, "layer.y.show=0;")  # left Y axis; risky, but matches intent

    if minor is not None:
        _try_exec(og, f"layer.x.mticklength={minor.length * scale}; layer.y.mticklength={minor.length * scale};")
        _try_exec(og, f"layer.x2.mticklength={minor.length * scale}; layer.y2.mticklength={minor.length * scale};")
        _try_exec(og, f"layer.x.mtickthickness={minor.width}; layer.y.mtickthickness={minor.width};")
        _try_exec(og, f"layer.x2.mtickthickness={minor.width}; layer.y2.mtickthickness={minor.width};")



# Grid application (best-effort)
# If these properties mismatch your Origin version, commands may fail and grids remain default/unchanged.
def _apply_grid_spec(og: Any, major: Optional[GridSpec], minor: Optional[GridSpec]) -> None:
    """Apply major/minor grids (best-effort)."""
    major_on = major is not None
    minor_on = minor is not None

    # Show flags: 0 none, 1 major, 2 minor, 3 both
    show = (1 if major_on else 0) | (2 if minor_on else 0)

    # Turn on/off grid display (documented)
    _try_exec(og, f"layer.x.grid.show={show}; layer.y.grid.show={show};")

    # Some scripts / versions also use showGrids; setting both is harmless and increases robustness
    _try_exec(og, f"layer.x.showGrids={show}; layer.y.showGrids={show};")

    # Must use RGB here.
    if major is not None:
        lt = _GRID_LINESTYLE_CODE.get(major.linestyle, 1)
        # Use documented properties (width in points)
        _try_exec(og, f"layer.x.grid.majorType={lt}; layer.y.grid.majorType={lt};")
        _try_exec(og, f"layer.x.grid.majorWidth={float(major.linewidth)}; layer.y.grid.majorWidth={float(major.linewidth)};")
        _try_exec(og, f"layer.x.grid.majorColor={_lt_color_rgb(major.color)}; layer.y.grid.majorColor={_lt_color_rgb(major.color)};")

    if minor is not None:
        lt = _GRID_LINESTYLE_CODE.get(minor.linestyle, 1)
        _try_exec(og, f"layer.x.grid.minorType={lt}; layer.y.grid.minorType={lt};")
        _try_exec(og, f"layer.x.grid.minorWidth={float(minor.linewidth)}; layer.y.grid.minorWidth={float(minor.linewidth)};")
        _try_exec(og, f"layer.x.grid.minorColor={_lt_color_rgb(minor.color)}; layer.y.grid.minorColor={_lt_color_rgb(minor.color)};")

def _apply_annotations(og: Any, ann: Optional[list[AnnotationSpec]], scale: float) -> None:
    if not ann:
        return
    for a in ann:
        text = _lt_quote(a.text)
        x, y = a.xy
        _try_exec(og, f'label -a {float(x)} {float(y)} "{text}";')
        _try_exec(og, f"label.fsize={a.fontsize  * FONT_PT_SCALE * scale};")



# -------------------------
# AxesSpec -> Origin layer properties
# -------------------------
# Workflow: select layer -> enforce full-frame -> set titles -> set scale types -> set limits -> ticks/grids -> annotations
# Important detail: this is applied AFTER curves are plotted (in plot()).
def _apply_axes_spec(
    og: Any,
    layer_idx: int,
    axes_obj: Axes,
    *,
    ignore_grid: bool,
    figspec: FigureSpec,
    x_is_log: bool,
    y_is_log: bool,
    scale: float,
    force_show_titles: bool = False
) -> None:
    """Apply AxesSpec to selected layer."""
    spec = axes_obj.spec
    _try_exec(og, f"layer -s {layer_idx};")

    _apply_full_frame_axes(og)

    # Titles
    if force_show_titles:
        # Titles: use label -n to ensure special objects (XB/YL) are created for every layer
        _try_exec(og, f'label -n XB "{_lt_quote(spec.x_axis_title)}";')
        _try_exec(og, f'label -n YL "{_lt_quote(spec.y_axis_title)}";')

        # After creation, setting properties via XB/YL works reliably
        _try_exec(og, f"XB.fsize={spec.axis_title_font_size * FONT_PT_SCALE * 2 * scale};")
        _try_exec(og, f"YL.fsize={spec.axis_title_font_size * FONT_PT_SCALE * 2 * scale};")
        _try_exec(og, "YL.rotate=90;")   # rotate Y axis title to 90 degrees

    # Scale type: 0=linear, 2=log10
    _try_exec(og, f"layer.x.type={2 if x_is_log else 0};")
    _try_exec(og, f"layer.y.type={2 if y_is_log else 0};")

    # Limits
    # Disable auto scaling before setting from/to.
    _try_exec(og,f"layer.x.auto=0")
    _try_exec(og,f"layer.x.rescale_margin=5")
    _try_exec(og,f"layer.y.auto=0")
    _try_exec(og,f"layer.y.rescale_margin=5")
    xl, xr = axes_obj.xlim
    yl, yr = axes_obj.ylim
    # Add 5% padding based on data-driven xlim/ylim if explicit limits are missing.
    xl_margin = xl - (xr - xl) * 0.05
    xr_margin = xr + (xr - xl) * 0.05
    yl_margin = yl - (yr - yl) * 0.05
    yr_margin = yr + (yr - yl) * 0.05
    if spec.x_left_lim is not None:
        _try_exec(og, f"layer.x.from={float(spec.x_left_lim)};")
    else:
        _try_exec(og, f"layer.x.from={float(xl_margin)};")
    if spec.x_right_lim is not None:
        _try_exec(og, f"layer.x.to={float(spec.x_right_lim)};")
    else:
        _try_exec(og, f"layer.x.to={float(xr_margin)};")

    if spec.y_left_lim is not None:
        _try_exec(og, f"layer.y.from={float(spec.y_left_lim)};")
    else:
        _try_exec(og, f"layer.y.from={float(yl_margin)};")
    if spec.y_right_lim is not None:
        _try_exec(og, f"layer.y.to={float(spec.y_right_lim)};")
    else:
        _try_exec(og, f"layer.y.to={float(yr_margin)};")

    # Ticks & grids
    _apply_tick_spec(og, spec.major_tick, spec.minor_tick, figspec.global_fontsize, scale)
    if not ignore_grid:
        _apply_grid_spec(og, spec.major_grid, spec.minor_grid)

    # Annotations
    _apply_annotations(og, spec.annotation, scale)


def _legend_anchor_xy(leg: LegendSpec) -> tuple[float, float]:
    """Use explicit anchor_x/y if user set them; else map loc to a sane default."""
    # In your LegendSpec, anchor defaults to (1,1). We'll interpret as "relative top-right".
    if leg.anchor_x != 1 or leg.anchor_y != 1:
        return float(leg.anchor_x) * 100.0, float(leg.anchor_y) * 100.0

    loc = (leg.loc or "upper right").lower().replace("_", " ")
    table = {
        "upper right": (85.0, 90.0),
        "upper left": (10.0, 90.0),
        "lower left": (10.0, 10.0),
        "lower right": (85.0, 10.0),
        "center": (50.0, 50.0),
    }
    return table.get(loc, (85.0, 90.0))


def _apply_legend_text(og: Any, layer_idx: int, legend_spec: LegendSpec, legend_text: str, scale: float) -> None:
    _try_exec(og, f"layer -s {layer_idx};")

    # Ensure the legend object exists (template may not have one)
    _try_exec(og, "legend;")
    _try_exec(og, "legend -r;")

    # Set legend text
    _try_exec(og, f'string __py_lg$="{_lt_quote_keep_backslash(legend_text)}";')
    _try_exec(og, "legend.text$=__py_lg$;")

    # Font and frame
    _try_exec(og, f"legend.fsize={legend_spec.fontsize * FONT_PT_SCALE * scale};")
    _try_exec(og, f"legend.frame={1 if legend_spec.frameon else 0};")

    # Place legend: interpret your (x,y) as percent of axis range -> convert to axis units
    px, py = _legend_anchor_xy(legend_spec)  # 0..100
    fx = float(px) / 100.0
    fy = float(py) / 100.0
    _try_exec(
        og,
        f"double __x=layer.x.from+(layer.x.to-layer.x.from)*{fx:.8f};"
        f"double __y=layer.y.from+(layer.y.to-layer.y.from)*{fy:.8f};"
        "legend.x=__x; legend.y=__y;"
    )

    _try_exec(og, "legend.update=1;")



def _set_layer_position_percent(og: Any, layer_idx: int, width: float, height: float, xoff: float, yoff: float) -> None:
    _try_exec(og, f"layer -s {layer_idx};")
    _try_exec(og, f"layer {width:.4f} {height:.4f} {xoff:.4f} {yoff:.4f};")


def _apply_multi_axes_layout(og: Any, multi_spec: MutiAxesSpec, n_layers: int) -> None:
    if isinstance(multi_spec, InsertAxesSpec) and n_layers >= 2:
        main_w, main_h, main_x, main_y = 78.0, 72.0, 15.0, 15.0
        _set_layer_position_percent(og, 1, main_w, main_h, main_x, main_y)

        insert_w = main_w * float(multi_spec.width)
        insert_h = main_h * float(multi_spec.height)
        insert_x = main_x + main_w * float(multi_spec.x)
        insert_y = main_y + main_h * float(multi_spec.y)
        insert_y = 100 - (insert_y + insert_h)
        _set_layer_position_percent(og, 2, insert_w, insert_h, insert_x, insert_y)

        _try_exec(og, "layer -s 2; layer.link=0;")
    
    if isinstance(multi_spec, StackAxesSpec):
        # Grid layout: nrows x ncols
        nrows = int(multi_spec.nrows)
        ncols = int(multi_spec.ncols)

        # Safety: if mismatched, do best-effort with min(n_layers, nrows*ncols)
        total = nrows * ncols
        use_layers = min(n_layers, total)

        # Layout parameters in percent (tweak if you want tighter spacing)
        left = 15.0
        right = 10.0
        bottom = 12.0
        top = 10.0
        hgap = 6.0     # horizontal gap between cells
        vgap = 6.0     # vertical gap between cells

        avail_w = 100.0 - left - right - (ncols - 1) * hgap
        avail_h = 100.0 - bottom - top - (nrows - 1) * vgap
        cell_w = avail_w / ncols
        cell_h = avail_h / nrows

        for idx in range(1, use_layers + 1):
            k = idx - 1
            r = k // ncols
            c = k % ncols

            # Origin layer positioning is easier to reason in "bottom-left" coordinates.
            # We want row 0 at the top, so map it to highest yoff.
            xoff = left + c * (cell_w + hgap)
            yoff = bottom + r * (cell_h + vgap)


            _set_layer_position_percent(og, idx, cell_w, cell_h, xoff, yoff)

        # Optional: unlink axes among layers
        for idx in range(1, use_layers + 1):
            _try_exec(og, f"layer -s {idx}; layer.link=0;")

        return



# -------------------------
# Curve styling via LabTalk `set`
# -------------------------
# Styles are applied to plot_ref (default "%C" = current plot).
# If Origin does not update %C to the newly-created plot after plotxy,
# style commands may apply to the wrong curve ("off-by-one" or cross-layer).
# That can produce complex, nontrivial mismatches (not just a simple swap).
def _apply_curve_style(og, axes_spec, cyc, *, plot_ref="%C") -> None:
    color = str(cyc.get("color", "black"))
    linestyle = str(cyc.get("linestyle", "-"))
    marker = str(cyc.get("marker", "o"))
    alpha = float(cyc.get("alpha", 1.0))

    lw = float(axes_spec.linewidth) * FONT_PT_SCALE
    ms = float(axes_spec.marker_size) * FONT_PT_SCALE

    # Always apply base color/alpha first
    _try_exec(og, f"set {plot_ref} -c {_lt_color_expr(color)};")
    _try_exec(og, f"set {plot_ref} -t {int(alpha * 100)};")

    if linestyle == "|":
        # --- Special case: "stick" style implemented via Drop Lines ---
        # 1) No connecting line (Connect: No Line)
        _try_exec(og, f"set {plot_ref} -l 0;")  # 0 = scatter/no line :contentReference[oaicite:4]{index=4}

        # 2) Hide symbols (we only want droplines)
        _try_exec(og, f"set {plot_ref} -z 0;")  # symbol size -> 0 (your code uses -z for size)

        # 3) Enable vertical drop lines
        _try_exec(og, f"set {plot_ref} -lv 1;")  # show vertical drop lines :contentReference[oaicite:5]{index=5}

        # 4) Vertical drop line style: dashed
        _try_exec(og, f"set {plot_ref} -lvs 1;")  # 1 = dash :contentReference[oaicite:6]{index=6}

        # 5) Vertical drop line width
        _try_exec(og, f"set {plot_ref} -lvw {int(lw)};")

        # 6) Optional: try to set dropline color by palette index (only works for simple named colors)
        # Origin docs say -lvc follows palette index (1 black, 2 red, 3 green, 4 blue, ...). :contentReference[oaicite:8]{index=8}
        _COLOR_INDEX = {"black": 1, "red": 2, "green": 3, "blue": 4, "white": 0}
        ci = _COLOR_INDEX.get(color.strip().lower()) if isinstance(color, str) else None
        if ci is not None:
            _try_exec(og, f"set {plot_ref} -lvc {ci};")

        return  # IMPORTANT: do not fall through to normal line/marker logic

    # --- Normal path (your existing logic) ---
    _try_exec(og, f"set {plot_ref} -wp {lw};")
    _try_exec(og, f"set {plot_ref} -z {ms};")

    ls_code = _LINESTYLE_CODE.get(linestyle)
    if ls_code is not None:
        _try_exec(og, f"set {plot_ref} -d {int(ls_code)};")

    mk_code = _MARKER_CODE.get(marker)
    if mk_code is not None:
        _try_exec(og, f"set {plot_ref} -k {int(mk_code)};")
    else:
        _try_exec(og, f"set {plot_ref} -z 0;")





def _save_project(og: Any, proj_name: str, opju_dir: str) -> None:
    out_dir = WindowsPath(opju_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    opju_path = out_dir / f"{proj_name}.opju"
    og.Save(str(opju_path.absolute()))



# -------------------------
# Legend text templates
# -------------------------
# Origin legend uses escape sequences like: \l(1) meaning "sample of plot #1".
# If plot order is changed (e.g., `layer -r`), the mapping from index -> curve changes.
# This is a high-priority suspect when legend labels and line samples appear mismatched.
def _legend_text_single_layer(labels: list[str]) -> str:
    return "\n".join([f"\\l({i}) {lab}" for i, lab in enumerate(labels, start=1)])


def _legend_text_all_layers(layer_labels: list[list[str]]) -> str:
    lines: list[str] = []
    for L, labels in enumerate(layer_labels, start=1):
        for P, lab in enumerate(labels, start=1):
            lines.append(f"\\l({L}.{P}) {lab}") 
    return "\n".join(lines)

def _apply_layer_background_from_figure(
    og: Any,
    facecolor,
    *,
    layer_idx: int | None = None,
) -> None:
    """
    Apply FigureSpec.facecolor to layer background and FORCE it opaque.
    This works for both main layer and inset layers.
    """
    cexpr = _lt_color_rgb(facecolor, fallback=(255, 255, 255))

    if layer_idx is None:
        # Assume current layer is selected
        _try_exec(og, "layer.fill=1;")          # REQUIRED for inset
        _try_exec(og, f"layer.color={cexpr};")  # background color
        _try_exec(og, "layer.transparency=0;")  # 0 = opaque
    else:
        _try_exec(og, f"layer -s {layer_idx};")
        _try_exec(og, f"layer{layer_idx}.fill=1;")
        _try_exec(og, f"layer{layer_idx}.color={cexpr};")
        _try_exec(og, f"layer{layer_idx}.transparency=0;")


# -------------------------
# Core plotting
# -------------------------

# =====================================================================
# Main pipeline: domain Project -> Origin workbook(s) + graph page(s)
# =====================================================================
# High-level runtime structure per Figure:
# 1) Ensure project opened/created
# 2) Create a workbook named after figure_name
#    - One worksheet per Axes (layer)
#    - Each Data contributes two columns (X then Y)
# 3) Create a graph page (template "Origin"), fallback via plotxy if CreatePage fails
# 4) Ensure layer count == number of Axes
# 5) Plot curves for each layer, consuming a SINGLE figure-level style cycle
#    - After each layer, run `layer -r` (reverse plot order within the layer)
# 6) Apply AxesSpec formatting (titles/limits/log/ticks/grids/annotations)
# 7) Build legend text and write legend.text$
# 8) Save project if requested
#
# Debugging suspects for style chaos (non-exhaustive):
# - _choose_plot_code always returns 202 (line+symbol)
# - %C reference may not point to the intended curve when styling
# - `layer -r` changes plot indices used by legend \l(...)
# - CreatePage fallback may create an extra initial plot before the main loop plots again
# - curve_scale computed but not used inside _apply_curve_style
def plot(proj: Project, proj_name: str, og: Any, /, proj_dir: Optional[str] = None, overwrite=False) -> None:
    """Plot FigureSpec into Origin and optionally save OPJU.
    """
    if overwrite:
        # Start fresh
        try:
            og.NewProject()
        except Exception:
            _try_exec(og, "doc -n;")
    else:
        open_or_create_project(og, Path(proj_dir) / f"{proj_name}.opju")

    for folder_name, folder in proj.items():
        for figure_name, figure in folder.items():
            _try_exec(og, "pe_cd /")
            _try_exec(og, f"pe_mkdir {folder_name} chk:=1 cd:=1")

            axes_pool = figure.axes_pool
            figspec: FigureSpec = figure.spec
            multi_spec: MutiAxesSpec = figure.muti_axes_spec

            if not axes_pool:
                break

            # ===== Workbook + data =====
            # A New workbook
            wb = og.WorksheetPages.Add("Origin")
            wb.Name = _workbook_sanitize_name(figure_name)
            og.Execute(f'page.longname$ = "{figure_name}";')
            # create worksheets
            wks_layer_names = [wb.Layers(0).Name]
            for _ in range(len(axes_pool)-1):
                wks_layer_names.append(wb.Layers.Add().Name)
            wks_pool = [f"[{wb.Name}]{name}" for name in wks_layer_names]
            # Put datas into worksheets, set axis titles(longnames) and legends(comments).
            for wks_name,axes in zip(wks_pool, axes_pool):
                datas = axes.data_pool
                wks = og.FindWorksheet(wks_name)
                for i,data in enumerate(datas):
                    og.PutWorksheet(wks_name,data.points_for_plot[:,0:2].tolist(),0,-1) # 0:first_row -1:append_col
                    id1 = i * 2
                    id2 = id1 + 1
                    wks.Columns(id1).Type = constants.COLTYPE_X
                    wks.Columns(id2).Type = constants.COLTYPE_Y
                    
                    # --- Robust column long names: data.headers may be missing/short ---
                    headers = list(getattr(data, "headers", []) or [])
                    # Prefer user-provided headers; otherwise fallback to deterministic defaults.
                    x_name = headers[0] if len(headers) >= 1 and headers[0] else f"X{i+1}"
                    y_name = headers[1] if len(headers) >= 2 and headers[1] else f"Y{i+1}"
                    wks.Columns(id1).LongName = x_name
                    wks.Columns(id2).LongName = y_name
                    wks.Columns(id2).Comments = data.labels.brief_summary

            

            # ===== Create graph page =====
            graph_name = _graph_sanitize_name(figure_name)
            try:
                gr_page = str(og.CreatePage(constants.OPT_GRAPH, graph_name, "Origin"))
                og.Execute(f'page.longname$ = "{figure_name}";')
            except Exception:
                # FALLBACK PATH: create graph via plotxy <new ...>.
                # IMPORTANT: this may create the first plot immediately.
                # Later, the main plotting loop may plot the same series again,
                # which can duplicate curves and scramble plot indices/styles.
                # fallback: create via plotxy new
                first_sheet = wks_pool[0]
                cyc0 = next(iter_cycles(figspec))
                code0 = _choose_plot_code(str(cyc0["linestyle"]), str(cyc0["marker"]))
                _try_exec(og, f'plotxy iy:=({first_sheet}!col(1),col(2)) plot:={code0} ogl:=<new name:={graph_name}>;')
                try:
                    gr_page = str(og.GetLTStr("%H")).strip()
                except Exception:
                    gr_page = graph_name

            _try_exec(og, f'win -a "{_lt_quote(gr_page)}";')

            # Ensure layer count
            for _ in range(2, len(axes_pool) + 1):
                _try_exec(og, "layer -n;")

            # Muti Layout if needed
            _apply_multi_axes_layout(og, multi_spec, len(axes_pool))

            # ===== Plot curves with figure-level cycles =====
            global_cycle_iter = iter_cycles(figspec)

            for layer_idx, (axes, sheet_name) in enumerate(zip(axes_pool, wks_pool), start=1):
                _try_exec(og, f"layer -s {layer_idx};")
                # for stack, each layer has its own cycle
                if isinstance(multi_spec, StackAxesSpec):
                    cycle_iter = iter_cycles(figspec)     # reset per layer
                else:
                    cycle_iter = global_cycle_iter        # share across figure

                is_inset = isinstance(multi_spec, InsertAxesSpec) and layer_idx == 2
                curve_scale = INSET_SCALE if is_inset else MAIN_SCALE

                for j, data in enumerate(axes.data_pool):
                    cyc = next(cycle_iter)
                    code = _choose_plot_code(str(cyc["linestyle"]), str(cyc["marker"]))

                    xcol = j * 2 + 1
                    ycol = xcol + 1

                    _try_exec(
                        og,
                        f"plotxy iy:=({sheet_name}!col({xcol}),{sheet_name}!col({ycol})) "
                        f"plot:={code} ogl:={layer_idx} rescale:=0 legend:=0;"
                    )
                    _try_exec(og, f"layer -s {layer_idx}; layer -c;")  # count plots in active layer -> count, %Z  :contentReference[oaicite:2]{index=2}
                    _try_exec(og, "layer.plot = count;")               # set active plot index to the last one :contentReference[oaicite:3]{index=3}    
                    _apply_curve_style(og, axes.spec, cyc, plot_ref="%C")
                _try_exec(og, f"layer -s {layer_idx};")

            # ===== Axes formatting =====
            for layer_idx, axes in enumerate(axes_pool, start=1):
                is_inset = isinstance(multi_spec, InsertAxesSpec) and layer_idx == 2
                scale = INSET_SCALE if is_inset else 1.0

                x_is_log, y_is_log = _should_set_log_scale(axes)

                if isinstance(figure.muti_axes_spec, StackAxesSpec):
                    force_show_titles = True
                else:
                    force_show_titles = False

                _apply_axes_spec(
                    og,
                    layer_idx,
                    axes,
                    figspec=figspec,
                    ignore_grid=is_inset,
                    x_is_log=x_is_log,
                    y_is_log=y_is_log,
                    scale=scale,
                    force_show_titles=force_show_titles
                )

                # If no explicit limits, rescale
                # NOTE: This condition uses OR across the four limits.
                # If ANY one limit is None, Rescale runs and may override from/to values set earlier.
                if axes.spec.x_left_lim is None or axes.spec.x_right_lim is None or axes.spec.y_left_lim is None or axes.spec.y_right_lim is None:
                    _try_exec(og, f"layer -s {layer_idx}; Rescale;")
                
                if figspec.facecolor is not None:
                    _try_exec(og, f"layer -s {layer_idx};")
                    _apply_layer_background_from_figure(og, figspec.facecolor)

            # ===== Legends =====
            # Build labels
            per_layer_labels: list[list[str]] = []
            for axes in axes_pool:
                per_layer_labels.append([d.labels.brief_summary for d in axes.data_pool])

            if isinstance(multi_spec, InsertAxesSpec) and getattr(multi_spec, "legend_holder", "") == "last axes":
                holder_idx = len(axes_pool)
                legend_spec = axes_pool[-1].spec.legend or figspec.legend
                if legend_spec is not None:
                    txt = _legend_text_all_layers(per_layer_labels)
                    _apply_legend_text(og, holder_idx, legend_spec, txt, scale=INSET_SCALE if holder_idx == 2 else MAIN_SCALE)
                    for i in range(1, holder_idx):
                        _try_exec(og, f"layer -s {i}; legend.text$=\"\";")
            else:
                for layer_idx, axes in enumerate(axes_pool, start=1):
                    legend_spec = axes.spec.legend or figspec.legend
                    if legend_spec is None:
                        continue
                    txt = _legend_text_single_layer(per_layer_labels[layer_idx - 1])
                    _apply_legend_text(og, layer_idx, legend_spec, txt, scale=MAIN_SCALE)

    if proj_dir and proj_name:
       _save_project(og, proj_name, proj_dir)
