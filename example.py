import asyncio
import aiohttp
import json


async def search_smart_scrape():
    url = "https://api.smartscrape.ai/search"
    # url = "http://localhost:8005/search"  # Local

    body = {
        "prompt": "What are the recent sport news?",
        "tools": [
            "Google Search",
        ],  # ["Twitter Search", "Google Search", "Google News Search", "Google Image Search", "Bing Search", "ArXiv Search", "Wikipedia Search", "Youtube Search", "Hacker News Search", "Reddit Search"]
        "model": "NOVA",  # "NOVA", "ORBIT", "HORIZON"
        "response_order": "LINKS_FIRST",  # "LINKS_FIRST", "SUMMARY_FIRST"
        "date_filter": "PAST_WEEK",  # "PAST_DAY", "PAST_WEEK", "PAST_2_WEEKS", "PAST_MONTH", "PAST_YEAR"
    }

    headers = {"Access-Key": "test"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as response:
            async for chunk in response.content.iter_any():
                decoded_data = chunk.decode("utf-8")

                if decoded_data.startswith("data: "):
                    json_data = decoded_data[6:]  # Remove 'data: ' prefix
                    try:
                        parsed_data = json.loads(json_data)

                        content_type = parsed_data.get("type")
                        content = parsed_data.get("content")

                        if content_type == "completion":
                            print("-" * 50)
                            print("Completion:\n")
                            print(content.strip())
                        else:
                            # Process the other type of chunks
                            print(parsed_data)
                    except json.JSONDecodeError:
                        print("Failed to decode JSON:", json_data)


# Run the async function
asyncio.run(search_smart_scrape())