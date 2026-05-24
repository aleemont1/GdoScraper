import logging
import requests
from typing import Dict, Any, Optional
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
)
logger = logging.getLogger("CoopScraper")


class CoopApiClient:
    """
    Client responsible for handling communication with the Coop API.
    Follows the Single Responsibility Principle by only managing network requests
    and data retrieval for Coop endpoints.
    """

    def __init__(self, base_url: str, store_id: str) -> None:
        """
        Initializes the API client with specific store configurations.

        Args:
            base_url: The root URL of the API (e.g., https://svdgt.coopalleanza3-0.it).
            store_id: The identifier for the specific supermarket.
        """
        self._base_url = base_url.rstrip("/")
        self._store_id = store_id
        self._session = requests.Session()

        # Set default headers to mimic a real browser and avoid basic blocks.
        # IMPORTANT: You must update these headers with the exact keys found
        # in your Browser's Developer Tools (Network Tab).
        self._session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.coopalleanza3-0.it",
                "Referer": "https://www.coopalleanza3-0.it/",
                # TODO: Uncomment and populate these based on your DevTools inspection.
                # API Management gateways usually require at least one of these:
                # "Ocp-Apim-Subscription-Key": "YOUR_KEY_HERE",
                # "Authorization": "Bearer YOUR_TOKEN_HERE"
            }
        )

    def fetch_promotions(
        self, page: int = 0, size: int = 50
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves promotional items for the configured store.

        Args:
            page: The page index for pagination (usually starts at 0 or 1).
            size: The number of items to retrieve per request.

        Returns:
            A dictionary containing the parsed JSON data, or None if the request fails.
        """
        # The endpoint path includes the tenant/app ID (P2611IS) and the dynamic store ID
        endpoint_path = f"/apim/P2611IS/{self._store_id}/promos"
        full_url = f"{self._base_url}{endpoint_path}"

        # Populate the query string parameters (the part after the '?')
        # Check DevTools to see if they use 'page'/'size' or 'offset'/'limit'
        query_parameters = {"page": page, "size": size}

        try:
            logger.info(
                f"Requesting data from: {full_url} with params: {query_parameters}"
            )
            response = self._session.get(full_url, params=query_parameters, timeout=10)

            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as http_err:
            logger.error(
                f"HTTP error occurred: {http_err.response.status_code} - {http_err.response.text}"
            )
            logger.info(
                "Hint: A 401 or 403 error usually means missing or invalid authentication headers."
            )
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            logger.error(f"An unexpected network error occurred: {req_err}")
        except ValueError as json_err:
            logger.error(
                f"Failed to parse JSON response: {json_err}. The server might have returned HTML instead of JSON."
            )

        return None


if __name__ == "__main__":
    # Configuration constants
    API_BASE_URL = "https://svdgt.coopalleanza3-0.it"
    STORE_ID = "0315"  # 0315 corresponds to Lungosavio Cesena

    # Initialize the API client instance
    coop_client = CoopApiClient(base_url=API_BASE_URL, store_id=STORE_ID)

    logger.info("Starting promotion extraction process...")

    # Attempt to fetch the first page of promotions
    promotions_data = coop_client.fetch_promotions(page=0, size=50)

    if promotions_data:
        logger.info("Successfully fetched data.")
        # In a real scenario, you would pass 'promotions_data' to a parser/normalizer class.
        # For now, we print the raw JSON to inspect the structure.
        import json

        print(json.dumps(promotions_data, indent=2))
    else:
        logger.error("Failed to retrieve promotions. Execution aborted.")
        sys.exit(1)
