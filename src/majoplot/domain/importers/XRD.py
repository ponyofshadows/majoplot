from __future__ import annotations
import numpy as np

from ..base import *

class XRD:
    instrument = "XRD"
    prefs_scenario = "Compare"
    
    @classmethod
    def fetch_raw_data(cls, raw_data_file:TextIO, raw_data_name:str)->Data|FAIL:
        labels = LabelDict(
            initital={"instrument":cls.instrument ,"raw_data": LabelValue(raw_data_name)},
            )

        # read
        initial_pos = raw_data_file.tell()          # remember current position
        first_line = raw_data_file.readline().strip()
        match first_line:
            case "<?xml version=\"1.0\" encoding=\"UTF-8\"?>":
                # xrdml from XRD
                import xml.etree.ElementTree as ET
                from datetime import datetime
                raw_data_file.seek(initial_pos)             # rewind to original position
                _headers = ("2θ","I")
                tree = ET.parse(raw_data_file)
                root = tree.getroot()
                # Get the default namespace URI from the root tag: "{uri}xrdMeasurements"
                ns_uri = root.tag.split("}")[0].lstrip("{")
                ns = {"x": ns_uri}
                start = float(root.find(".//x:positions[@axis='2Theta']/x:startPosition", ns).text)
                end   = float(root.find(".//x:positions[@axis='2Theta']/x:endPosition", ns).text)
                ts_elem = root.find(".//x:startTimeStamp", ns)
                ts = ts_elem.text.strip()
                # Parse ISO 8601 with timezone offset
                dt = datetime.fromisoformat(ts)

                # Format date as YYYYMMDD
                labels["date"] = dt.strftime("%Y%m%d")

                intensities_text = root.find(".//x:intensities", ns).text
                I = np.fromstring(intensities_text, sep=" ")
                base = np.max(I) / 100
                I = I / base
                two_theta = np.linspace(start, end, I.size)
                points = np.column_stack([two_theta, I])
                labels["source"] = "experiment"
                return Data(labels=labels, _headers=_headers, points=points)
                

            case "h    k    l      d (Å)      F(real)      F(imag)          |F|         2θ          I    M ID(λ) Phase":
                # Refraction table from CIF by VESTA
                _headers = ("2θ","I","h","k","l")
                indexs = {"2θ":7,"I":8,"h":0,"k":1,"l":2}
                points = []
                for line in raw_data_file:
                    cells = line.split()
                    points.append([float(cells[indexs[head]]) for head in _headers])
                labels["source"] = "cif"
                return Data(labels=labels,_headers=_headers,points=np.array(points))

            case _:
                return fail_signal