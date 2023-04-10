if __name__ == "__main__":
    # Example: retrieve from cache (or download and then retrieve if not in cache)
    # data of energy price the whole UK for January 2019

    from src.UKGridConnection import UKGridConnection
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    import pandas as pd

    price_regions = {
        "Yorkshire": 23,
        "London": 12,
        "East England": 10,  # Eastern England
        "East Midlands": 11,
        "North Wales": 13,  # North Wales & Mersey
        "West Midlands": 14,  # Midlands
        "North Scotland": 17,  # Northern Scotland
        "South Scotland": 18,  # Southern Scotland
        "South England": 20,  # Southern
        "South Wales": 21,
        "South West England": 22,  # South Western
        "South East England": 19,  # South East
        "North East England": 15,  # North East
        "North West England": 16,  # North West
    }

    # # Unspecified Regions (Regions we offer in the UI as options but are not defined by our source of data)
    # "England" : 20,  # England is considered the same as South England (Southern)
    # "Scotland" : 16, # Scotland is considered the same as South Scotland
    # "Wales" : 21,    # Wales is considered the same as South Wales

    voltage_levels = {  # Used for energy price data
        "Low Voltage: <1kV": "LV",
        "LV Substation: <1kV": "LV-Sub",
        "High Voltage: <22kV": "HV",
    }
    grid = UKGridConnection()

    # Do monthly batches from Jan-2019 till last month on all categories
    from_time = datetime(2019, 1, 1)
    to_time = from_time + relativedelta(months=1)

    # 41 combinations per month.
    # We have forecasts up to end of next year. (if we are in April 2023, the last day we can query is Dec-2024)
    sample_data = [
        {
            "from": from_time,
            "to": to_time,
            "region": region,
            "voltage_level": voltage_level,
        }
        for region in price_regions.keys()
        for voltage_level in voltage_levels.keys()
    ]
    df = pd.DataFrame(sample_data)
    grid.get_price(df)
