from __future__ import annotations

from ..base import *
from ..utils import skip_lines_then_readline

ROW_FILEOPENTIME = 5
ROW_SAMPLE_MATERIAL = 18
ROW_SAMPLE_COMMENT = 19
ROW_SAMPLE_MASS = 20
ROW_SAMPLE_HOLDER = 25
ROW_HEADERS = 36

T = "Temperature (K)"
H = "Magnetic Field (Oe)"
M = "DC Moment Free Ctr (emu)"

Mfit = "DC Free Fit"
Mfix = "DC Moment Fixed Ctr (emu)"
SD = "DC Squid Drift"
CP = "Center Position (mm)"
DCC = "DC Calculated Center (mm)"


headers = (T, H, M, Mfix, Mfit, SD, CP, DCC)

class VSM:
    instrument = "VSM"
    
    @classmethod
    def fetch_raw_data(cls, raw_data_file:TextIO, raw_data_name:str)->Data|FAIL:
        labels = LabelDict(
            initital={"instrument":cls.instrument ,"raw_data": LabelValue(raw_data_name)},
            )

        # Date
        line = skip_lines_then_readline(raw_data_file, ROW_FILEOPENTIME-1)
        info = line.split(",")
        try:
            if info[0].strip() != "FILEOPENTIME":
                return fail_signal
            dateMM_DD_YYYY = info[2].split("/")
            dateYYYYMMDD = f"{dateMM_DD_YYYY[2]}{dateMM_DD_YYYY[0].zfill(2)}{dateMM_DD_YYYY[1].zfill(2)}"
        except IndexError:
            return fail_signal
        labels["date"] = LabelValue(dateYYYYMMDD)

        # Material
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE_MATERIAL - ROW_FILEOPENTIME -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "SAMPLE_MATERIAL":
                return fail_signal
            material = info[1]
        except IndexError:
            return fail_signal
        labels["material"] = LabelValue(material)

        # COMMENT
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE_COMMENT - ROW_SAMPLE_MATERIAL -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "SAMPLE_COMMENT":
                return fail_signal
            comment = info[1]
        except IndexError:
            return fail_signal
        labels["comment"] = LabelValue(comment)

        # Mass
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE_MASS - ROW_SAMPLE_COMMENT -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "SAMPLE_MASS":
                return fail_signal
            mass = info[1]
        except IndexError:
            return fail_signal
        labels["mass"] = LabelValue(mass,"mg")

        # Sample Holder
        line = skip_lines_then_readline(raw_data_file,ROW_SAMPLE_HOLDER - ROW_SAMPLE_MASS -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "SAMPLE_HOLDER":
                return fail_signal
            sample_holder = info[1]
        except IndexError:
            return None
        labels["sample_holder"] = LabelValue(sample_holder)

        # Headers
        line = skip_lines_then_readline(raw_data_file,ROW_HEADERS - ROW_SAMPLE_HOLDER -1)
        all_headers = dict((header,i) for (i,header) in enumerate(line.split(",")))
        try:
            indexs = tuple(all_headers[header] for header in headers)
        except KeyError:
            return fail_signal

        # read data
        points = []
        for line in raw_data_file:
            cells = line.split(",")
            points.append(tuple(float(cells[i]) for i in indexs))

        return Data(
            labels=labels,
            _headers=headers,
            points=np.array(points),
            )