import os
import logging
from dotenv import load_dotenv
from tavily import AsyncTavilyClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

## TOOLS

## 1. Tavily Internet Search

tavily_search_tool_json = {
    "type": "function",
    "name": "tavily_search",
    "description": "Performs an internet search using the Tavily API.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to search for on Tavily",
            },
        },
        "required": ["query"],
    },
}

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    raise ValueError(
        "Missing the Azure OpenAI API key. Please set it in the .env file."
    )

atavily_client = AsyncTavilyClient(api_key=TAVILY_API_KEY)


async def tavily_search(query: str):
    """Search internet with Tavily API for a given search query"""
    try:
        logger.info(f"🕵 Performing internet search for query: '{query}'")
        response = await atavily_client.search(
            query=query,
            search_depth="basic",
            include_answer=False,
            topic="news",
            days=3,
            max_results=5,
        )

        # Extracting the result for formatting
        answer = response.get("answer", "")
        results = response.get("results", [])
        if not results:
            logger.info(f"No results found for '{query}'.")
            return None

        full_content = "\n\n".join([result["content"] for result in results])

        # Formatting the results in a more readable way
        formatted_results = "\n".join(
            [
                f"{i+1}. [{result['title']}]({result['url']})\n{result['content'][:200]}..."
                for i, result in enumerate(results)
            ]
        )

        message_content = f"Short answer for '{query}': {answer}\n\nSearch Results:\n\n{formatted_results}"
        logger.info(message_content)

        return answer, full_content
    except Exception as e:
        logger.error(f"❌ Error performing internet search: {str(e)}")
