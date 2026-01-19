from __future__ import annotations
from typing import NamedTuple
from dataclasses import dataclass, field
import numpy as np
from itertools import chain

from .base import * 

class InsertAxesSpec(NamedTuple):
    x:float
    y:float
    width:float
    height:float
    legend_holder:str="last axes"

    @classmethod
    def default(cls, figure_size:tuple[float], axes_pool:list[Axes])->InsertAxesSpec:
        POINT_BOX = 0.01
        MARGIN_SCALE_OFFSET = 0.05
        PIXEL_NUM = 20
        INSERT_MARGIN_SCALE = 0.8
        MARGIN_CENTER_OFFSET = 0.85
        INSERT_TOP_PIXEL_MARGEN = 0
        INSERT_RIGHT_PIXEL_MARGEN = 0
        FAIL_AREA_THRESHOLD = 0.1
        ASPECT_RATIO = 1

        if len(axes_pool) > 2:
            return fail_signal
        main = axes_pool[0]

        # collect scatters in main
        main_scatters = chain.from_iterable(data.points_for_plot for data in main.data_pool)
        
        # get the xlim, ylim of main
        xlim = main.xlim
        ylim = main.ylim
        x_span_min = main.spec.x_log_scale_min_span
        y_span_min = main.spec.y_log_scale_min_span
        if xlim[0] > 0 and xlim[1] > 0 and (xlim[1] / xlim[0]) >= x_span_min:
            xlim = (np.log10(xlim[0]), np.log10(xlim[1]))
        if ylim[0] > 0 and ylim[0] > 0 and (ylim[1] / ylim[0]) >= y_span_min:
            ylim = (np.log10(ylim[0]), np.log10(ylim[1]))

        width = xlim[1] - xlim[0]
        height = ylim[1] - ylim[0]
        x_offset = width * MARGIN_SCALE_OFFSET
        y_offset = height * MARGIN_SCALE_OFFSET
        width += x_offset * 2
        height += y_offset *2


        # Examine the occupation situation
        occ = np.zeros((PIXEL_NUM, PIXEL_NUM))
        box_t = lambda n: min(n,PIXEL_NUM-1)
        box_b = lambda n: max(n,0)
        for scatter in main_scatters:
            x,y = scatter[:2]
            x_pos = (x - xlim[0] + x_offset)/width
            y_pos = (y - ylim[0] + y_offset)/height
            xbox = (x_pos - POINT_BOX, x_pos + POINT_BOX)
            ybox = (y_pos - POINT_BOX, y_pos + POINT_BOX)
            x_pixel_box = range(box_b(np.int_(xbox[0]*PIXEL_NUM)), box_t(np.int_(xbox[1]*PIXEL_NUM)+1))
            y_pixel_box = range(box_b(np.int_(ybox[0]*PIXEL_NUM)), box_t(np.int_(ybox[1]*PIXEL_NUM)+1))
            for i in x_pixel_box:
                for j in y_pixel_box:
                    occ[j,i] = 1

        # matrix to histograms
        histograms = np.zeros((PIXEL_NUM, PIXEL_NUM))
        for x in range(PIXEL_NUM):
            for y in range(PIXEL_NUM):
                h = 0
                for i in reversed(range(y+1)):
                    if occ[i,x] == 0:
                        h+=1
                    else:
                        break
                histograms[y, x] = h
        @dataclass(slots=True)
        class Rectangle:
            x0:int|np.int_
            x1:int|np.int_
            y1:int|np.int_
            h:int|np.int_
            w:int|np.int_ = field(init=False,default=0)
            taller:bool = field(init=False,default=False)
            S:float|np.float64 = field(init=False,default=0)

            def __post_init__(self):
                self.w = self.x1 - self.x0 + 1
                self_aspect_ratio = self.h / self.w
                if self_aspect_ratio < ASPECT_RATIO:
                    self.taller = False
                    self.S = self.h ** 2 / ASPECT_RATIO
                else:
                    self.taller = True
                    self.S = self.w ** 2 * ASPECT_RATIO
                

        largest_rec = Rectangle(PIXEL_NUM-1,PIXEL_NUM-1,PIXEL_NUM-1,histograms[PIXEL_NUM-1,PIXEL_NUM-1])

        for y in reversed(range(PIXEL_NUM)):
            x_stack = []
            for x in reversed(range(-1,PIXEL_NUM)):
                cur_h = histograms[y, x] if x != -1 else 0
                while x_stack:
                    top_x = x_stack[-1]
                    h = histograms[y, top_x]

                    if cur_h >= h:
                        break

                    x_stack.pop()

                    right = x_stack[-1]-1 if x_stack else PIXEL_NUM-1
                    cur_rec = Rectangle(
                        x0=x+1,
                        x1=right,
                        y1=y,
                        h=h
                    )
                    if cur_rec.S > largest_rec.S:
                        largest_rec = cur_rec
                x_stack.append(x)                


        # calculate the final rec para (anchor on left bottom)
        p_x = (largest_rec.x0 - INSERT_RIGHT_PIXEL_MARGEN) / PIXEL_NUM
        p_y = (largest_rec.y1-largest_rec.h - INSERT_TOP_PIXEL_MARGEN) / PIXEL_NUM
        p_w = largest_rec.w / PIXEL_NUM 
        p_h = largest_rec.h / PIXEL_NUM

        margined_S = largest_rec.S / ( PIXEL_NUM ** 2 ) * ( INSERT_MARGIN_SCALE ** 2)
        if margined_S < FAIL_AREA_THRESHOLD:
            return fail_signal

        if largest_rec.taller:
            adjusted_x = p_x
            adjusted_y = p_y + p_h - p_w * ASPECT_RATIO
            margin_c_x = adjusted_x + p_w * MARGIN_CENTER_OFFSET
            margin_c_y = adjusted_y + p_w * ASPECT_RATIO * MARGIN_CENTER_OFFSET
            margined_w = p_w * INSERT_MARGIN_SCALE
            margined_h = margined_w * ASPECT_RATIO
        else:
            adjusted_x = p_x + p_w - p_h / ASPECT_RATIO
            adjusted_y = p_y
            margin_c_x = adjusted_x + p_h / ASPECT_RATIO * MARGIN_CENTER_OFFSET
            margin_c_y = adjusted_y + p_h * MARGIN_CENTER_OFFSET
            margined_h = p_h * INSERT_MARGIN_SCALE
            margined_w = margined_h / ASPECT_RATIO
        margined_x = (adjusted_x - margin_c_x) * INSERT_MARGIN_SCALE + margin_c_x
        margined_y = (adjusted_y - margin_c_y) * INSERT_MARGIN_SCALE + margin_c_y
        
        return InsertAxesSpec(
            legend_holder="last axes",
            x=margined_x,
            y=margined_y,
            width=margined_w,
            height=margined_h,
        )


        
class DualYAxesSpec(NamedTuple):
    legend_holder = "figure"

class StackAxesSpec(NamedTuple):
    legend_holder = "axes_self"
    nrows:int
    ncols:int
