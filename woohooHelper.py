from typing import List
from datetime import datetime, timedelta

class Utils():
    class StatesValues:
        def __init__(self, name: str, color: List[float], isTc: bool, length: float, type : str, description : str):
            self.name = name
            self.color = color
            self.isTc = isTc
            self.length = length
            self.type = type
            self.description = description

    error_response = {"Error": "FILTER UNDEFINED", "filter": {"year": "int(2025)", "month": "int(5)", "day": "int(30)"}}

    def unix_time_range_ms(year, month, day, start_am_pm, end_am_pm):
        datum_str = f"{year:04d}-{month:02d}-{day:02d}"  # YYYY-MM-DD
        
        start_dt = datetime.strptime(f"{datum_str} {start_am_pm}", "%Y-%m-%d %I:%M %p") # "08:30 PM"
        end_dt   = datetime.strptime(f"{datum_str} {end_am_pm}", "%Y-%m-%d %I:%M %p") # "04:45 AM"
        
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        start_unix_ms = int(start_dt.timestamp() * 1000)
        end_unix_ms   = int(end_dt.timestamp() * 1000)
        
        return start_unix_ms, end_unix_ms