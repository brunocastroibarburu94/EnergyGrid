import numpy as np
import http.client as httplib


def to_int(x):
    try:
        return int(x)
    except:
        return np.nan


def to_float(x):
    try:
        return float(x)
    except:
        return np.nan


def have_internet() -> bool:
    """Checks if google server 8.8.8.8 is reachable if it is, then this is an indication that there is
    internet connection.

    Returns:
        bool: A variable representing if google's server is reachable
    """
    conn = httplib.HTTPSConnection("8.8.8.8", timeout=5)
    try:
        conn.request("HEAD", "/")
        return True
    except Exception:
        return False
    finally:
        conn.close()
