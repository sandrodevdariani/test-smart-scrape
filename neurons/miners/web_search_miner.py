import bittensor as bt
from datura.protocol import WebSearchSynapse, WebSearchResult
from pydantic import ValidationError


class WebSearchMiner:
    def __init__(self, miner: any):
        self.miner = miner

    def _generate_mock_search_result(self, **kwargs):
        """
        Generate a mock web search result using a structured class or dictionary.

        Parameters:
            **kwargs: Fields to override in the default mock result.

        Returns:
            dict: Formatted mock search result as a dictionary.
        """
        try:
            mock_result = WebSearchResult(
                title="Mock Search Result Title",
                snippet="This is a mock snippet for the search result.",
                link="https://example.com/mock-result",
                date="1 hour ago",
                source="Mock Source",
                **kwargs,  # Override any fields with provided values
            )
            return mock_result.dict()
        except ValidationError as e:
            bt.logging.error(f"Validation error while creating mock search result: {e}")
            raise

    async def search(self, synapse: WebSearchSynapse):
        """
        Perform a mock web search and assign the results to the synapse.

        Parameters:
            synapse (WebSearchSynapse): The input synapse containing query parameters.

        Returns:
            WebSearchSynapse: The synapse with mock search results.
        """
        # Extract the query from the synapse
        query = synapse.query

        # Log the mock search execution
        bt.logging.info(f"Executing mock web search with query: {query}")

        # Generate a mock search result
        mock_result = self._generate_mock_search_result()

        # Assign the mock result to the results field of the synapse
        synapse.results = [mock_result]

        bt.logging.info(f"Here is the final synapse: {synapse}")
        return synapse
