import warnings
import logging
def test_log():
    logging.info("Test Logger Information message")
    logging.warning("Test Logger Warning message")
    logging.error('eggs error')
    logging.critical('eggs critical')

def initialize_grid_with_internet():
    from src.utils import have_internet
    if not have_internet():
        warnings.warn("No internet connection deteceted, test can't be performed.")
        return None
    from src.UKGridConnection import UKGridConnection
    return UKGridConnection()

def test_call_for_co2_intensity_with_df():
    grid = initialize_grid_with_internet()
    if grid is None:
        return None
    
    from src.UKGridConnection import region_map, voltage_level_enums
    import pandas as pd
    from datetime import datetime
    sample_data = [
        {'from':datetime(2020,1,1,hour=0),'to':datetime(2020,1,1,hour=1)},
        {'from':datetime(2020,1,1,hour=1),'to':datetime(2020,1,1,hour=2)},
        {'from':datetime(2020,1,1,hour=2),'to':datetime(2020,1,1,hour=3)},
        {'from':datetime(2020,1,1,hour=3),'to':datetime(2020,1,1,hour=4)},
        {'from':datetime(2020,1,1,hour=4),'to':datetime(2020,1,1,hour=5)},
    ]
    df = pd.DataFrame(sample_data)
    regions = list(region_map.keys())
    voltage_level = list(voltage_level_enums.keys())
    df["region"]= regions[0]
    df["voltage_level"] = voltage_level[0]
    filled_data = grid.get_c02(df)

def test_call_for_price_with_df():
    from src.utils import have_internet
    if not have_internet():
        return
    
    from src.UKGridConnection import region_map, voltage_level_enums
    from src.UKGridConnection import UKGridConnection
    from copy import deepcopy
    import pandas as pd
    from datetime import datetime
    grid = UKGridConnection()

    # Simple Test: 1 Region
    sample_dataA = [
        {'from':datetime(2020,1,1,hour=0),'to':datetime(2020,1,1,hour=1)},
        {'from':datetime(2020,1,1,hour=1),'to':datetime(2020,1,1,hour=2)},
        {'from':datetime(2020,1,1,hour=2),'to':datetime(2020,1,1,hour=3)},
        {'from':datetime(2020,1,1,hour=3),'to':datetime(2020,1,1,hour=4)},
        {'from':datetime(2020,1,1,hour=4),'to':datetime(2020,1,1,hour=5)},
    ]
    dfA = pd.DataFrame(sample_dataA)
    dfA["region"]= 'North Scotland'
    dfA["voltage_level"] = 'Low Voltage: <1kV'
    dfA_empty=deepcopy(dfA)

    grid.get_price(dfA)
    logging.info('Test A Passed')

    # Complex test: 2 Regions 
    sample_dataB = [
        {'from':datetime(2020,1,5,hour=0),'to':datetime(2020,1,5,hour=1)},
        {'from':datetime(2020,1,5,hour=1),'to':datetime(2020,1,5,hour=2)},
        {'from':datetime(2020,1,5,hour=2),'to':datetime(2020,1,5,hour=3)},
        {'from':datetime(2020,1,5,hour=3),'to':datetime(2020,1,5,hour=4)},
        {'from':datetime(2020,1,5,hour=4),'to':datetime(2020,1,5,hour=5)},
    ]
    dfB2 = pd.DataFrame(sample_dataB)
    dfB2["region"]= 'South England'
    dfB2["voltage_level"] = 'LV Substation: <1kV'
    dfB = pd.concat([dfA_empty,dfB2]).reset_index(drop=True)
    grid.get_price(dfB)
    logging.info('Test B Passed')

def test_call_co2_api():
    grid = initialize_grid_with_internet()
    if grid is None:
        return None
    grid.use_cache = False # Don't want to generate extra files during testing
    from src.UKGridConnection import region_map, voltage_level_enums
    from datetime import datetime
    from_time = datetime(2020,1,1,hour=0)
    to_time = datetime(2020,1,2,hour=0)

    # Simple test only using time
    # https://api.carbonintensity.org.uk/intensity/2020-01-01T00:00Z/2020-01-02T00:00Z
    data1 =  grid.intensity_api_request(from_time,to_time)
    
    # Use time and region
    # https://api.carbonintensity.org.uk/regional/intensity/2020-01-01T00:00Z/2020-01-02T00:00Z/regionid/12
    region = "South England" # Region id: 12
    data2 =  grid.intensity_api_request(from_time,to_time,region=region)

    # Use time and postcode
    # https://api.carbonintensity.org.uk/regional/intensity/2020-01-01T00:00Z/2020-01-02T00:00Z/postcode/BS8
    postcode_prefix = "BS8" # Prefix of postoce
    data3 =  grid.intensity_api_request(from_time,to_time,postcode=postcode_prefix)

    # Call over a long time period (2 months)
    to_time = datetime(2020,2,1,hour=0)
    data4 =  grid.intensity_api_request(from_time,to_time,region=region)
    pass

def test_call_price_api():
    grid = initialize_grid_with_internet()
    if grid is None:
        return None
    grid.use_cache = False # Don't want to generate extra files during testing
    # from src.UKGridConnection import region_dno, voltage_level_enums
    from datetime import datetime
    # The dataset starts on 01-04-2017 and ends on 31-03-2025. 
    # It works on a daily basis so the hour doesn't matter here
    
    # Test short call
    # https://api.carbonintensity.org.uk/regional/intensity/2019-01-02T00:00Z/2019-01-15T00:00Z/regionid/23
    # https://odegdcpnma.execute-api.eu-west-2.amazonaws.com/development/prices?dno=23&voltage=LV&start=2019-01-02&end=2019-01-15
    from_time = datetime(2020,1,1,hour=0)
    to_time = datetime(2020,1,2,hour=0)
    volate_level = "Low Voltage: <1kV"
    region = "South England" #dno = 20
    data = grid.price_api_request(region, volate_level,from_time,to_time)

    # Test Long Call
    to_time = datetime(2020,5,2,hour=0)
    data = grid.price_api_request(region, volate_level,from_time,to_time)
    
    # Test Yorkshire monthly call
    from_time = datetime(2019,1,1,hour=0)
    to_time = datetime(2019,2,1,hour=0)
    volate_level = "Low Voltage: <1kV"
    region = "Yorkshire" #dno = 23
    data = grid.price_api_request(region, volate_level,from_time,to_time)

def test_consolidate_cache():
    """ If cache does not exist it create a cache and calls it """
    grid = initialize_grid_with_internet()
    if grid is None:
        return None
    grid.consolidate_cache(keep_latest=True)
    