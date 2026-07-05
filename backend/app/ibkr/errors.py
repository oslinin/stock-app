class IBKRUnavailable(Exception):
    """IB Gateway/TWS is not connected (or IBKR is disabled in settings)."""


class DataUnavailable(Exception):
    """Connected, but IB returned no usable data (entitlements, empty chain...)."""
