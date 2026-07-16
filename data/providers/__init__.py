"""Provider registry. Add new vendors here and they become available to the
DataService by name (matching the names in config.SOURCES)."""
from .base import DataProvider, DataType, ProviderError, NotSupported
from .yfinance_provider import YFinanceProvider
from .alpha_vantage_provider import AlphaVantageProvider
from .polygon_provider import PolygonProvider

# name -> provider class
PROVIDER_REGISTRY: dict[str, type[DataProvider]] = {
    YFinanceProvider.name: YFinanceProvider,
    AlphaVantageProvider.name: AlphaVantageProvider,
    PolygonProvider.name: PolygonProvider,
}


def build_provider(name: str, config: dict | None = None) -> DataProvider | None:
    cls = PROVIDER_REGISTRY.get(name)
    return cls(config) if cls else None


__all__ = [
    "DataProvider", "DataType", "ProviderError", "NotSupported",
    "YFinanceProvider", "AlphaVantageProvider", "PolygonProvider",
    "PROVIDER_REGISTRY", "build_provider",
]
