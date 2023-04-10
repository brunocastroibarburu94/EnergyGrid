import requests
import json
import pandas as pd
from datetime import timedelta, timezone
from pathlib import Path
import logging
import time
from src.utils import to_float, to_int

utc = timezone.utc
co2_data_cols = [
    # Metadata
    "id",
    "created",
    "from",
    "to",
    "region",
    "postcode",
    "source",
    # Data from Source (if available)
    "regionid",
    "dnoregion",
    "shortname",
    "source_postcode",
    # Actual data
    "intensity_forecast",
    "intensity_index",  # CO2 Grams per kWh
    "intensity_actual",  # CO2 Grams per kWh
    "generationmix",  # If available % of total Power generated by source
]
price_data_cols = [
    "id",
    "created",
    "region",
    "voltageLevel",
    "from",
    "to",
    "voltage",
    "dnoRegion",
    "pennies_per_kwh",
]
region_map = {  # Used for CO2 intensity data
    "North Scotland": 1,
    "South Scotland": 2,
    "North West England": 3,
    "North East England": 4,
    "Yorkshire": 5,
    "North Wales": 6,
    "South Wales": 7,
    "West Midlands": 8,
    "East Midlands": 9,
    "East England": 10,
    "South West England": 11,
    "South England": 12,
    "London": 13,
    "South East England": 14,
    "England": 15,
    "Scotland": 16,
    "Wales": 17,
}

region_dno = {  # Used for energy price data
    "East England": 10,  # Eastern England
    "East Midlands": 11,
    "London": 12,
    "North Wales": 13,  # North Wales & Mersey
    "West Midlands": 14,  # Midlands
    "North East England": 15,  # North East
    "North West England": 16,  # North West
    "North Scotland": 17,  # Northern Scotland
    "South Scotland": 18,  # Southern Scotland
    "South East England": 19,  # South East
    "South England": 20,  # Southern
    "South Wales": 21,
    "South West England": 22,  # South Western
    "Yorkshire": 23,
    # Unspecified Regions (Regions we offer in the UI as options but are not defined by our source of data)
    "England": 20,  # England is considered the same as South England (Southern)
    "Scotland": 16,  # Scotland is considered the same as South Scotland
    "Wales": 21,  # Wales is considered the same as South Wales
}

voltage_level_enums = {  # Used for energy price data
    "Low Voltage: <1kV": "LV",
    "LV Substation: <1kV": "LV-Sub",
    "High Voltage: <22kV": "HV",
}

ci_base_url = "https://api.carbonintensity.org.uk"

ci_headers = {"Accept": "application/json"}


class UKGridConnection:
    """
    This class models the connection to the grid in the UK.
    """

    def consolidate_cache(self, keep_latest: bool = False, clear_rest: bool = True):
        # It groups all the caches into a single consolidated file. (that can be committed in git)
        # This is more memory efficient than several files

        # Extract all the data from cache
        logging.info("Consolidating Cache")
        consolidated_cache_co2 = pd.read_parquet(self.co2_cache_path)
        consolidated_cache_price = pd.read_parquet(self.price_cache_path)

        if keep_latest:
            co2_latest_data = (
                consolidated_cache_co2.groupby("id")["created"].rank(
                    "first", ascending=False
                )
                == 1
            )
            consolidated_cache_co2 = consolidated_cache_co2.loc[co2_latest_data, :]
            price_latest_data = (
                consolidated_cache_price.groupby("id")["created"].rank(
                    "first", ascending=False
                )
                == 1
            )
            consolidated_cache_price = consolidated_cache_price.loc[
                price_latest_data, :
            ]
            assert len(consolidated_cache_price.id.unique()) == len(
                consolidated_cache_price
            )
            assert len(consolidated_cache_co2.id.unique()) == len(
                consolidated_cache_co2
            )

        # Sort by id (region-voltage-timestamp)
        consolidated_cache_co2.sort_values(by="id", inplace=True)
        consolidated_cache_price.sort_values(by="id", inplace=True)

        # Reset index
        consolidated_cache_co2.reset_index(drop=True, inplace=True)
        consolidated_cache_price.reset_index(drop=True, inplace=True)

        # Store all
        consolidated_cache_co2.to_parquet(
            self.co2_cache_path / ("Consolidated_CO2_Cache.parquet.snappy"),
            engine="pyarrow",
            compression="snappy",
        )
        consolidated_cache_price.to_parquet(
            self.price_cache_path / ("Consolidated_Price_Cache.parquet.snappy"),
            engine="pyarrow",
            compression="snappy",
        )

    # def fill_price_cache_gaps(self,region = None,voltage_level=None):
    #   TODO: Make function that inspects the data in the cache and fills data gaps

    # def update_price_cache(self,from_time = datetime(2019,1,1),to_time=datetime.today()):
    #     # TODO: Make a function that automatically fetchs new data and stores it in the cache.
    #     self.refresh_price_cache(keep_latest=True)

    def refresh_price_cache(self, keep_latest: bool = True):
        """
        Checks in local storage for data and refresh the cache in memory.
        Cache columns
        region_price_cache:
        id            - string
        created       - timestamp
        date          - timestamp
        region        - string
        voltage_level - string
        price_per_kwh - float (Pounds)

        (Ideally if implemented for database management the following columns would be ideal
        updated       - timestamp
        version       - integer
        )
        """
        logging.info("Refresing Price Cache...")
        self.price_cache = pd.read_parquet(self.price_cache_path)
        if len(self.price_cache) == 0:
            self.price_cache = pd.DataFrame(columns=price_data_cols)
            return
        if keep_latest:
            price_latest_data = (
                self.price_cache.groupby("id")["created"].rank("first", ascending=False)
                == 1
            )
            self.price_cache = self.price_cache.loc[price_latest_data, :]
            assert len(self.price_cache.id.unique()) == len(self.price_cache)
        self.price_cache["pennies_per_kwh"] = self.price_cache.pennies_per_kwh.map(
            to_float
        )
        self.price_cache["from"] = pd.to_datetime(self.price_cache["from"], utc=True)
        self.price_cache["to"] = pd.to_datetime(self.price_cache["to"], utc=True)
        self.price_cache["created"] = self.price_cache.created.map(to_int)
        self.price_cache.sort_values(by="id", inplace=True)
        self.price_cache.reset_index(drop=True, inplace=True)

    def refresh_co2_cache(self, keep_latest: bool = True):
        """
        Checks in local storage for data and refresh the cache in memory.

        Cache columns
        region_price_cache:
        id              - string
        created         - timestamp
        from            - timestamp
        to              - timestamp
        region          - string
        co2_g_per_kwh   - float [g/kWh]

        (Ideally if implemented for database management the following columns would be ideal
        updated       - timestamp
        version       - integer
        )
        """
        logging.info("Refresing CO2 Cache...")
        self.co2_cache = pd.read_parquet(self.co2_cache_path)
        if keep_latest:
            co2_latest_data = (
                self.co2_cache.groupby("id")["created"].rank("first", ascending=False)
                == 1
            )
            self.co2_cache = self.co2_cache.loc[co2_latest_data, :]
            assert len(self.co2_cache.id.unique()) == len(self.co2_cache)

        # Data is stored as text, transform into right format
        self.co2_cache["generationmix"] = self.co2_cache.generationmix.apply(
            lambda x: json.loads(x)
        )
        self.co2_cache["intensity_actual"] = self.co2_cache.intensity_actual.map(
            to_float
        )
        self.co2_cache["intensity_forecast"] = self.co2_cache.intensity_forecast.map(
            to_float
        )
        self.co2_cache["created"] = self.co2_cache.created.map(to_int)
        self.co2_cache["from"] = pd.to_datetime(self.co2_cache["from"], utc=True)
        self.co2_cache["to"] = pd.to_datetime(self.co2_cache["to"], utc=True)
        self.co2_cache.sort_values(by="id", inplace=True)
        self.co2_cache.reset_index(drop=True, inplace=True)

    def __init__(self):
        self.max_power: float
        self.use_cache: float = True
        # , price_data : pd.DataFrame = None, co2_intesity_data : pd.DataFrame = None
        self.co2_cache_path: Path = Path(
            "/root/project/data/.GridConnection_cache/co2/"
        )
        self.price_cache_path: Path = Path(
            "/root/project/data/.GridConnection_cache/price/"
        )
        self.co2_cache_path.mkdir(
            parents=True, exist_ok=True
        )  # Create Path if doesn't exist
        self.price_cache_path.mkdir(
            parents=True, exist_ok=True
        )  # Create Path if doesn't exist

        self.co2_cache: pd.DataFrame = pd.DataFrame()
        self.price_cache: pd.DataFrame = pd.DataFrame()
        self.refresh_co2_cache()  # Load Data
        self.refresh_price_cache()  # Load Data

    def get_price(self, df):
        """Get total estimated energy costs given an energy profile

            df columns:
                - from
                - to
                - region (Optional)
                - postcode (Optional)
                - average_power (Optional)

        Args:
            df (pandas.DataFrame): DataFrame with profile

        Raises:
            Exception: _description_

        Returns:
            pandas.DataFrame:  DataFrame with energy costs
        """
        if not "from_utc" in df.columns:
            df["from_utc"] = pd.to_datetime(df["from"], utc=True)  # Enforce UTC
        if not "to_utc" in df.columns:
            df["to_utc"] = pd.to_datetime(df["to"], utc=True)  # Enforce UTC
        region = list(df.region.unique())
        voltage_level = list(df.voltage_level.unique())
        logging.info(f"Extractiong for {region}-{voltage_level}")
        region_voltage_combinations = (
            df[["region", "voltage_level"]].drop_duplicates().reset_index(drop=True)
        )
        for i in range(len(region_voltage_combinations)):
            # Iterate for each unique combination of region and voltage_level.
            region = region_voltage_combinations.loc[i, "region"]
            voltage_level = region_voltage_combinations.loc[i, "voltage_level"]
            # Check cache for data
            ixs = (df["region"] == region) & (df["voltage_level"] == voltage_level)
            from_time = min(df.loc[ixs, "from_utc"])
            to_time = max(df.loc[ixs, "to_utc"])
            # Test completeness of data and fill if necessary
            for attempt in range(4):
                cache_ixs = (self.price_cache["region"] == region) & (
                    self.price_cache["voltage"] == voltage_level
                )
                if not any(cache_ixs):
                    logging.info(
                        "No data for region and voltage level is stored, collecting data via API."
                    )
                    self.price_api_request(region, voltage_level, from_time, to_time)
                    self.refresh_price_cache(keep_latest=True)
                    continue  # Start loop again this test shouldn't be triggered

                first_available_date = min(self.price_cache.loc[cache_ixs, "from"])
                last_available_date = max(self.price_cache.loc[cache_ixs, "to"])

                if from_time < first_available_date:
                    logging.info(
                        "No data for beggining of time period, collecting data via API."
                    )
                    self.price_api_request(
                        region, voltage_level, from_time, first_available_date
                    )
                    self.refresh_price_cache(keep_latest=True)
                    cache_ixs = (self.price_cache["region"] == region) & (
                        self.price_cache["voltage"] == voltage_level
                    )
                    continue
                if to_time > last_available_date:
                    logging.info(
                        "No data for end of time period, collecting data via API."
                    )
                    self.price_api_request(
                        region, voltage_level, last_available_date, to_time
                    )
                    self.refresh_price_cache(keep_latest=True)
                    continue
                focused_cache_ixs = (
                    (self.price_cache["region"] == region)
                    & (self.price_cache["voltage"] == voltage_level)
                    & (self.price_cache["from"] >= from_time)
                    & (self.price_cache["to"] <= to_time)
                )
                focused_cached_data = self.price_cache[focused_cache_ixs]
                if not len(focused_cached_data) == int(
                    (to_time - from_time).total_seconds() / 1800
                ):
                    # Check if data is missing between from_time and to_time if there is just fill the gap
                    logging.warning(
                        f"Gaps in cache detected between {from_time}/{to_time} filling gap [have: {len(focused_cached_data)}, expected: {int((to_time-from_time).seconds/1800)} ] , this may take several minutes, please be patient..."
                    )
                    self.price_api_request(region, voltage_level, from_time, to_time)
                    self.refresh_price_cache(keep_latest=True)
                    continue
                break

            # Insert data into dataframe
            df.loc[ixs, "pennies_per_kwh"] = pd.merge(
                df.loc[ixs, "from_utc"],
                focused_cached_data[["from", "pennies_per_kwh"]],
                left_on="from_utc",
                right_on="from",
                suffixes=("", "_ci"),
                how="left",
            ).set_index(df[ixs].index)["pennies_per_kwh"]

            # df.drop(columns='pennies_per_kwh',inplace=True)

    # def try_fill_from_cache_simple_df_price(self,region,voltage_level,from_time,to_time):

    def price_api_request(
        self, region, voltage, from_time, to_time, skipstore: bool = False
    ):
        """Retrieves energy price data via API
             Source: https://electricitycosts.org.uk/api-documentation/

            Making a request to the API, you can access half-hourly (HH) electricity costs datasets for each DNO region and voltage level.
            The dataset starts on 01-04-2017 and ends on 31-03-2025. Due to electricity bill components, the financial year is considered
            from the beginning of April to the end of March. All times are provided in UTC format.

            A maximum of 31 days of data can be downloaded at a time using the download button.

            DNO: Used to select the DNO region, the parameter should be added as a string in the format “dno=XX”, where XX is an
                integer from 10 to 23. Regions:
                - 10 : Eastern England
                - 11 : East Midlands
                - 12 : London
                - 13 : North Wales & Mersey
                - 14 : Midlands
                - 15 : North East
                - 16 : North West
                - 17 : Northern Scotland
                - 18 : Southern Scotland
                - 19 : South East
                - 20 : Southern
                - 21 : South Wales
                - 22 : South Western
                - 23 : Yorkshire
            Voltage: Used to select the voltage level, the parameter should be added as a string in the format “voltage=XX”,
                where XX can be “HV”, “LV” or “LV-Sub”. It is important to add these letter exactly as presented for the API
                request to work correctly.
                - Low voltage (LV) : voltage level below 1 kV. SMEs usually are connected to LV levels.
                - Low voltage substation (LV-Sub) : connected to a substation with a supply point voltage level below 1 kV.
                - High voltage (HV) : voltage level of at least 1kV and less than 22kV. (London Power Networks, 2011)

            Start: Used to define the start date, the parameter should be added as a string in the format “start=DD-MM-YYYY”.
                It is important to add the “-” in-between the numbers.

            End: Used to define the end date, the parameter should be added as a string in the format “end=DD-MM-YYYY”.
                It is important to add the “-” in-between the numbers.
        Args:
            dno (_type_): _description_
            voltage (_type_): _description_
            start (_type_): _description_
            end (_type_): _description_

        Returns:
            pandas.DataFrame: response from API call
        """

        fetch_nanosec = time.time_ns()
        fetch_id = str(fetch_nanosec)

        if to_time - from_time > timedelta(days=31):
            # Recursive behaviour
            data_chunks = []
            next_t = from_time
            while next_t < to_time:
                next_t = min(from_time + timedelta(days=30), to_time)
                data_chunks.append(
                    self.price_api_request(
                        region,
                        voltage,
                        from_time=from_time,
                        to_time=next_t,
                        skipstore=True,
                    )
                )
                from_time = next_t
                # Could add a pause not to overwhelm their servers
            data = pd.concat(data_chunks)
            data.reset_index(inplace=True, drop=True)
        else:
            dno = region_dno[region]
            voltage_level = voltage_level_enums[voltage]
            from_txt = from_time.strftime("%d-%m-%Y")  # datetime in format YYYY-MM-DD
            to_txt = (to_time + timedelta(days=1)).strftime(
                "%d-%m-%Y"
            )  # datetime in format YYYY-MM-DD / Truncates at the beggining of the day
            url = f"https://odegdcpnma.execute-api.eu-west-2.amazonaws.com/development/prices?dno={dno}&voltage={voltage_level}&start={from_txt}&end={to_txt}"
            r = requests.get(url, params={}, headers=ci_headers)
            # Response {"status":~ , "data":{"dno":, "region":,  "data":[{"Overall":~, "Timestamp":}] }}
            # “data”: a list with the “Overall” price in p/kWh, the “unixTimestamp”, and “Timestamp” with the specific time and date.
            json_data = json.loads(r.text)

            data = pd.DataFrame(json_data["data"]["data"])
            data.rename(
                columns={"Overall": "pennies_per_kwh", "Timestamp": "from"},
                inplace=True,
            )
            data = data[["pennies_per_kwh", "from"]]
            data["from"] = pd.to_datetime(
                data["from"], format="%H:%M %d-%m-%Y", utc=True
            )
            data["to"] = data["from"] + timedelta(minutes=30)
            data["region"] = region if region else "NA"
            data["voltage"] = voltage if voltage else "NA"
            data["dnoRegion"] = json_data["data"]["dnoRegion"]
            data["voltageLevel"] = json_data["data"]["voltageLevel"]
            data["id"] = data.apply(
                lambda x: "_".join(
                    [x["region"], x["voltageLevel"], str(int(x["from"].timestamp()))]
                )
                .replace(" ", "_")
                .upper(),
                axis=1,
            )
            data["created"] = fetch_id
            data = data[price_data_cols]
        # Export data to cache
        # Need to create ID & timestamps

        if self.use_cache and not skipstore:  # Store data (default behaviour)
            filename = "price_" + fetch_id + ".parquet.snappy"
            logging.info(f"Storing {filename}")
            data = data.applymap(str).astype(
                pd.StringDtype()
            )  # Convert all to string for storing
            data.to_parquet(
                self.price_cache_path / filename, engine="pyarrow", compression="snappy"
            )
        return data

    def get_c02(self, df):
        """Given an energy profile and region it returns the total CO2 consumed from the grid
            df columns:
                - from
                - to
                - region (Optional)
                - postcode (Optional)
                - average_power (Optional)

        Args:
            df (pandas.DataFrame): DataFrame with energy profile

        Returns:
            pandas.DataFrame: DataFrame with CO2 generated
        """

        # TODO: Enable Cache for improved performance
        # Check cache dataframe

        # If cache dataframe does not have all data then:
        # 1. Refresh cache (from local storage) if this still does not have all data then
        # 2. Make an API request to fetch missing data and update local storage cache.

        raw_df = self.intensity_api_request(min(df["from"]), max(df.to))
        raw_df["from"] = pd.to_datetime(raw_df["from"], utc=True)
        raw_df["to"] = pd.to_datetime(raw_df["to"], utc=True)
        df["from"] = pd.to_datetime(df["from"], utc=True)

        # TODO: Enable smart assignement of intensity (using pandas SQL)
        # Logic:
        #   1. Join by: From_requested>to_response && To_requested<From_response,
        #   2. Do aggregations: Between From_requested and To_requested

        out = pd.merge(df, raw_df, on="from", suffixes=("", "_ci"))
        if "average_power" in out.columns:
            # TODO: When change to variable time windows, change the code below (assumes intervals are half an hour long)
            out["total_emmissions_actual"] = (
                out.average_power * out.intensity_actual / 10**6
            ) / 2
            out["total_emmissions_forecast"] = (
                out.average_power * out.intensity_forecast / 10**6
            ) / 2

        return out

    def intensity_api_request(
        self,
        from_time,
        to_time,
        region: str = None,
        postcode: str = None,
        skipstore: bool = False,
    ):
        """Makes API request to CarbonIntensity to retrieve intensity data

        Args:
            from_time (_type_): _description_
            to_time (_type_): _description_
            region (_type_, optional): _description_. Defaults to None.
            postcode (_type_, optional): _description_. Defaults to None.


        Returns:
            pandas.DataFrame: Results of CO2 intensity [g/kWh]
             - from
             - to
             - region_id
             - region SS0
             - intensity_forecast
             - intensity_index
             - intensity_actual
             - geneartionmix

        """

        fetch_nanosec = time.time_ns()
        fetch_id = str(fetch_nanosec)
        logging.info(
            f"FetchID: {fetch_id}"
        )  # Maybe time definition is not enoughly accurate

        # Times should be all UTC. Timezone parsing should be handled here.
        if to_time - from_time > timedelta(days=14):
            # Recursive behaviour
            data_chunks = []
            next_t = from_time
            while next_t < to_time:
                next_t = min(from_time + timedelta(days=13), to_time)
                data_chunks.append(
                    self.intensity_api_request(
                        from_time=from_time,
                        to_time=next_t,
                        region=region,
                        postcode=postcode,
                        skipstore=True,
                    )
                )
                from_time = next_t
                # Could add a pause not to overwhelm their servers
            data = pd.concat(data_chunks)
            data.reset_index(inplace=True, drop=True)
        else:
            # Prepare URL for API call
            from_txt = from_time.strftime(
                "%Y-%m-%dT%H:%MZ"
            )  # datetime in ISO8601 format YYYY-MM-DDThh:mmZ
            to_txt = to_time.strftime("%Y-%m-%dT%H:%MZ")

            if postcode:
                template = (
                    f"/regional/intensity/{from_txt}/{to_txt}/postcode/{postcode}"
                )
            elif region:
                region_id = region_map[region]
                template = (
                    f"/regional/intensity/{from_txt}/{to_txt}/regionid/{region_id}"
                )
            else:
                template = f"/intensity/{from_txt}/{to_txt}"  # The maximum date range is limited to 14 days

            url = ci_base_url + template
            # Fetch data
            logging.info(f"Calling {url}")
            r = requests.get(url, params={}, headers=ci_headers)

            # Process data
            json_data = json.loads(r.text)

            if postcode:
                # data_summary = pd.json_normalize(json_data["data"],sep="_")[['regionid','dnoregion','shortname']]
                data = pd.json_normalize(json_data["data"], record_path="data", sep="_")
                data["regionid"] = json_data["data"]["regionid"]
                data["shortname"] = json_data["data"]["shortname"]
                data["source_postcode"] = json_data["data"]["postcode"]
            elif region:
                # Does not have actual but has generation mix
                data = pd.json_normalize(json_data["data"], record_path="data", sep="_")
                data["regionid"] = json_data["data"]["regionid"]
                data["dnoregion"] = json_data["data"]["dnoregion"]
                data["shortname"] = json_data["data"]["shortname"]
            else:
                data = pd.json_normalize(json_data["data"], sep="_")
            data["source"] = "CarbonIntensity"
            data["created"] = fetch_id
            data["region"] = region if region else "NA"
            data["postcode"] = postcode if postcode else "NA"
            data["from"] = pd.to_datetime(data["from"], utc=True)
            data["to"] = pd.to_datetime(data["to"], utc=True)
            data["id"] = data.apply(
                lambda x: "_".join(
                    [x["region"], x["postcode"], str(int(x["from"].timestamp()))]
                )
                .replace(" ", "_")
                .upper(),
                axis=1,
            )
            if not "generationmix" in data.columns:
                data["generationmix"] = json.dumps({})
            else:
                data["generationmix"] = data.generationmix.apply(
                    lambda x: json.dumps(x)
                )

            if not "intensity_actual" in data.columns:
                data["intensity_actual"] = None
            #  Fill missing columns with pd.NA.
            missing_cols = [col for col in co2_data_cols if col not in data.columns]
            data[missing_cols] = "NA"
            data = data[co2_data_cols]  # Sort Columns
        if self.use_cache and not skipstore:  # Store data (default behaviour)
            filename = "CO2_" + fetch_id + ".parquet.snappy"
            logging.info(f"Storing {filename}")
            data = data.applymap(str).astype(
                pd.StringDtype()
            )  # Convert all to string for storing
            data.to_parquet(
                self.co2_cache_path / filename, engine="pyarrow", compression="snappy"
            )

        return data

    # pd.read_parquet(self.co2_cache_path/'CO2_1680361107217428600.parquet.snappy')
    # pd.read_parquet(self.co2_cache_path/'CO2_1680361107532143900.parquet.snappy')
    # def mix_api_request(self,from_txt,to_txt):
    # Indicates in percentage how much contribution to the grid came from wind, solar, gas, nuclear power,...
    # Generation Mix
    # https://api.carbonintensity.org.uk/generation/{from}/{to}
    # r = { "data": [{"name_of_resource":value}] }

    # def intensity_factors_api_request(self):
    # Indicates per kWh how much gCO2 is released from wind, solar, gas, nuclear power,...
    # https://api.carbonintensity.org.uk/intensity/factors
    # Format:
    # r = { "data": [{"name_of_resource":value}] }