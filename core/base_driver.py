from abc import ABC, abstractmethod
from typing import List, Any
from core.models import ProductOffer

class AbstractSupermarketDriver(ABC):
    """
    Abstract base class defining the standard interface for supermarket scrapers.
    Follows the Strategy Pattern to decouple parsing strategies from execution.
    """

    @abstractmethod
    def fetch_promotions(self, store_id: str) -> Any:
        """
        Fetches the raw promotion data (JSON, HTML, PDF content, etc.) from the source.
        
        Args:
            store_id: The identifier for the specific supermarket store.
            
        Returns:
            The raw data structure or file pointer, or None if fetching failed.
        """
        pass

    @abstractmethod
    def parse_promotions(self, raw_data: Any, store_id: str) -> List[ProductOffer]:
        """
        Parses raw promotion data into a list of normalized ProductOffer objects.
        
        Args:
            raw_data: The raw data retrieved from fetch_promotions.
            store_id: The identifier for the specific supermarket store.
            
        Returns:
            A list of validated ProductOffer objects.
        """
        pass

    def run_etl(self, store_id: str) -> List[ProductOffer]:
        """
        Executes the full ETL extraction pipeline for the given store.
        
        Args:
            store_id: The identifier for the specific supermarket store.
            
        Returns:
            A list of validated ProductOffer objects.
        """
        raw_data = self.fetch_promotions(store_id)
        if not raw_data:
            return []
        return self.parse_promotions(raw_data, store_id)
