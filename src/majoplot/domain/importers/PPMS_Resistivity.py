from __future__ import annotations
import numpy as np

from ..base import *
from ..utils import skip_lines_then_readline

ROW_FILEOPENTIME  = 3
ROW_SAMPLE1_NAME  = 6
ROW_SAMPLE1_UNITS = 9
ROW_SAMPLE2_NAME  = 10
ROW_SAMPLE2_UNITS = 13
ROW_SAMPLE3_NAME  = 14
ROW_SAMPLE3_UNITS = 17
ROW_HEADERS       = 32

T = "Temperature (K)"
H = "Magnetic Field (Oe)"
R1, I1 = "Bridge 1 Resistivity (Ohm-m)", "Bridge 1 Excitation (uA)"
R2, I2 = "Bridge 2 Resistivity (Ohm-m)", "Bridge 2 Excitation (uA)"
R3, I3 = "Bridge 3 Resistivity (Ohm-m)", "Bridge 3 Excitation (uA)"

class PPMS_Resistivity:
    instrument = "PPMS"
    
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

        # S1 Name
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE1_NAME - ROW_FILEOPENTIME -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "Sample1 Name":
                return fail_signal
            s1_name = info[1]
        except IndexError:
            return fail_signal
        labels["sample1_name"] = LabelValue(s1_name)

        # S1 Units
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE1_UNITS - ROW_SAMPLE1_NAME -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "Sample1 Units":
                return fail_signal
            s1_units = info[1]
        except IndexError:
            return fail_signal
        labels["sample1_units"] = LabelValue(s1_units)

        # S2 Name
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE2_NAME - ROW_SAMPLE1_UNITS -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "Sample2 Name":
                return fail_signal
            s2_name = info[1]
        except IndexError:
            return fail_signal
        labels["sample2_name"] = LabelValue(s2_name)

        # S2 Units
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE2_UNITS - ROW_SAMPLE2_NAME -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "Sample2 Units":
                return fail_signal
            s2_units = info[1]
        except IndexError:
            return fail_signal
        labels["sample2_units"] = LabelValue(s2_units)

        # S3 Name
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE3_NAME - ROW_SAMPLE2_UNITS -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "Sample3 Name":
                return fail_signal
            s3_name = info[1]
        except IndexError:
            return fail_signal
        labels["sample3_name"] = LabelValue(s3_name)

        # S3 Units
        line = skip_lines_then_readline(raw_data_file, ROW_SAMPLE3_UNITS - ROW_SAMPLE3_NAME -1)
        info = line.split(",")
        try:
            if info[-1].strip() != "Sample3 Units":
                return fail_signal
            s3_units = info[1]
        except IndexError:
            return fail_signal
        labels["sample3_units"] = LabelValue(s3_units)

        # Headers
        line = skip_lines_then_readline(raw_data_file,ROW_HEADERS - ROW_SAMPLE3_UNITS -1)
        all_headers = dict((header,i) for (i,header) in enumerate(line.split(",")))
        headers = (T, H, R1, I1, R2, I2, R3, I3)
        try:
            indexs = tuple(all_headers[header] for header in headers)
        except KeyError:
            return fail_signal

        # read data
        points = []
        for line in raw_data_file:
            cells = line.split(",")
            points.append([np.float64(cells[i]) if cells[i] else np.nan for i in indexs])

        return Data(
            labels=labels,
            _headers=headers,
            points=np.array(points),
            )