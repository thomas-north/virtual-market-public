class VMarketError(Exception):
    """Base error for all vmarket application errors."""


class InsufficientCashError(VMarketError):
    pass


class InsufficientHoldingsError(VMarketError):
    pass


class NoPriceError(VMarketError):
    pass


class InstrumentNotFoundError(VMarketError):
    pass


class ProviderError(VMarketError):
    pass
