import re
import os
import ast
import json
import base64
import asyncio
import copy
import torch
import requests
import traceback
import bittensor as bt
import aiohttp
from . import client
from collections import deque
import re
import html
import unicodedata

list_update_lock = asyncio.Lock()
_text_questions_buffer = deque()


def load_state_from_file(filename="validators/state.json"):
    if os.path.exists(filename):
        with open(filename, "r") as file:
            bt.logging.info("loaded previous state")
            return json.load(file)
    else:
        bt.logging.info("initialized new global state")
        return {
            "text": {
                "themes": None,
                "questions": None,
                "theme_counter": 0,
                "question_counter": 0,
            },
            "images": {
                "themes": None,
                "questions": None,
                "theme_counter": 0,
                "question_counter": 0,
            },
        }


state = load_state_from_file()


def get_state():
    global state
    if state is None:
        load_state_from_file()
    return state


def save_state_to_file(state, filename="state.json"):
    with open(filename, "w") as file:
        bt.logging.success(f"saved global state to {filename}")
        json.dump(state, file)


def preprocess_string(text):
    processed_text = text.replace("\t", "")
    placeholder = "___SINGLE_QUOTE___"
    processed_text = re.sub(r"(?<=\w)'(?=\w)", placeholder, processed_text)
    processed_text = processed_text.replace("'", '"').replace(placeholder, "'")

    # First, remove all comments, ending at the next quote
    no_comments_text = ""
    i = 0
    in_comment = False
    while i < len(processed_text):
        if processed_text[i] == "#":
            in_comment = True
        elif processed_text[i] == '"' and in_comment:
            in_comment = False
            no_comments_text += processed_text[
                i
            ]  # Keep the quote that ends the comment
            i += 1
            continue
        if not in_comment:
            no_comments_text += processed_text[i]
        i += 1

    # Now process the text without comments for quotes
    cleaned_text = []
    inside_quotes = False
    found_first_bracket = False

    i = 0
    while i < len(no_comments_text):
        char = no_comments_text[i]

        if not found_first_bracket:
            if char == "[":
                found_first_bracket = True
            cleaned_text.append(char)
            i += 1
            continue

        if char == '"':
            # Look for preceding comma or bracket, skipping spaces
            preceding_char_index = i - 1
            found_comma_or_bracket = False

            while preceding_char_index >= 0:
                if (
                    no_comments_text[preceding_char_index] in "[,"
                ):  # Check for comma or opening bracket
                    found_comma_or_bracket = True
                    break
                elif (
                    no_comments_text[preceding_char_index] not in " \n"
                ):  # Ignore spaces and new lines
                    break
                preceding_char_index -= 1

            following_char_index = i + 1
            while (
                following_char_index < len(no_comments_text)
                and no_comments_text[following_char_index] in " \n"
            ):
                following_char_index += 1

            if found_comma_or_bracket or (
                following_char_index < len(no_comments_text)
                and no_comments_text[following_char_index] in "],"
            ):
                inside_quotes = not inside_quotes
            else:
                i += 1
                continue  # Skip this quote

            cleaned_text.append(char)
            i += 1
            continue

        if char == " ":
            # Skip spaces if not inside quotes and if the space is not between words
            if not inside_quotes and (
                i == 0
                or no_comments_text[i - 1] in " ,["
                or no_comments_text[i + 1] in " ,]"
            ):
                i += 1
                continue

        cleaned_text.append(char)
        i += 1

    cleaned_str = "".join(cleaned_text)
    cleaned_str = re.sub(r"\[\s+", "[", cleaned_str)
    cleaned_str = re.sub(r"\s+\]", "]", cleaned_str)
    cleaned_str = re.sub(
        r"\s*,\s*", ", ", cleaned_str
    )  # Ensure single space after commas

    start, end = cleaned_str.find("["), cleaned_str.rfind("]")
    if start != -1 and end != -1 and end > start:
        cleaned_str = cleaned_str[start : end + 1]

    return cleaned_str


def convert_to_list(text):
    pattern = r"\d+\.\s"
    items = [item.strip() for item in re.split(pattern, text) if item]
    return items


def extract_python_list(text: str):
    try:
        if re.match(r"\d+\.\s", text):
            return convert_to_list(text)

        bt.logging.debug(f"Preprocessed text = {text}")
        text = preprocess_string(text)
        bt.logging.debug(f"Postprocessed text = {text}")

        # Extracting list enclosed in square brackets
        match = re.search(r'\[((?:[^][]|"(?:\\.|[^"\\])*")*)\]', text, re.DOTALL)
        if match:
            list_str = match.group(1)

            # Using ast.literal_eval to safely evaluate the string as a list
            evaluated = ast.literal_eval("[" + list_str + "]")
            if isinstance(evaluated, list):
                return evaluated

    except Exception as e:
        bt.logging.error(
            f"Unexpected error when extracting list: {e}\n{traceback.format_exc()}"
        )

    return None


async def call_openai(
    messages, temperature, model, seed=1234, response_format=None, top_p=None
):
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        bt.logging.warning("Please set the OPENAI_API_KEY environment variable.")
        return None

    for attempt in range(2):
        bt.logging.trace(
            f"Calling Openai. Temperature = {temperature}, Model = {model}, Seed = {seed},  Messages = {messages}"
        )
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                seed=seed,
                response_format=response_format,
                top_p=top_p,
            )
            response = response.choices[0].message.content
            bt.logging.trace(f"validator response is {response}")
            return response

        except Exception as e:
            bt.logging.error(f"Error when calling OpenAI: {e}")
            await asyncio.sleep(0.5)

    return None


# Github unauthorized rate limit of requests per hour is 60. Authorized is 5000.
def get_version(line_number=22):
    url = f"https://api.github.com/repos/datura-ai/smart-scrape/contents/datura/__init__.py"
    response = requests.get(url)
    if response.status_code == 200:
        content = response.json()["content"]
        decoded_content = base64.b64decode(content).decode("utf-8")
        lines = decoded_content.split("\n")
        if line_number <= len(lines):
            version_line = lines[line_number - 1]
            version_match = re.search(r'__version__ = "(.*?)"', version_line)
            if version_match:
                return version_match.group(1)
            else:
                raise Exception("Version information not found in the specified line")
        else:
            raise Exception("Line number exceeds file length")
    else:
        bt.logging.error("github api call failed")
        return None


def send_discord_alert(message, webhook_url):
    data = {"content": f"@everyone {message}", "username": "Subnet22 Updates"}
    try:
        response = requests.post(webhook_url, json=data)
        if response.status_code == 204:
            print("Discord alert sent successfully!")
        else:
            print(f"Failed to send Discord alert. Status code: {response.status_code}")
    except Exception as e:
        print(f"Failed to send Discord alert: {e}", exc_info=True)


def resync_metagraph(self):
    """Resyncs the metagraph and updates the hotkeys and moving averages based on the new metagraph."""
    bt.logging.info("resync_metagraph()")

    # Copies state of metagraph before syncing.
    previous_metagraph = copy.deepcopy(self.metagraph)

    # Sync the metagraph.
    self.metagraph.sync(subtensor=self.subtensor)

    # Check if the metagraph axon info has changed.
    if previous_metagraph.axons == self.metagraph.axons:
        return

    bt.logging.info(
        "Metagraph updated, re-syncing hotkeys, dendrite pool and moving averages"
    )
    # Zero out all hotkeys that have been replaced.
    for uid, hotkey in enumerate(self.hotkeys):
        if hotkey != self.metagraph.hotkeys[uid]:
            self.moving_averaged_scores[uid] = 0  # hotkey has been replaced

    # Check to see if the metagraph has changed size.
    # If so, we need to add new hotkeys and moving averages.
    if len(self.hotkeys) < len(self.metagraph.hotkeys):
        # Update the size of the moving average scores.
        new_moving_average = torch.zeros((self.metagraph.n)).to(self.device)
        min_len = min(len(self.hotkeys), len(self.moving_averaged_scores))
        new_moving_average[:min_len] = self.moving_averaged_scores[:min_len]
        self.moving_averaged_scores = new_moving_average

    # Update the hotkeys.
    self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)


async def save_logs(logs, netuid):
    logging_endpoint_url = None

    if netuid == 22:
        logging_endpoint_url = "https://api-logs.smartscrape.ai"
    else:
        logging_endpoint_url = "https://api-logs-dev.smartscrape.ai"

    try:
        timeout = aiohttp.ClientTimeout(total=600)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            result = await session.post(
                logging_endpoint_url,
                json={
                    "logs": logs,
                },
            )
            bt.logging.debug(f"Executed save_logs, got result: {await result.text()}")
    except aiohttp.ClientError as e:
        bt.logging.error(f"Error in save_logs: {e}")
    except Exception as e:
        bt.logging.error(f"Unexpected error in save_logs: {e}")


async def save_logs_in_chunks(
    self,
    responses,
    uids,
    rewards,
    summary_rewards,
    twitter_rewards,
    search_rewards,
    performance_rewards,
    original_summary_rewards,
    original_twitter_rewards,
    original_search_rewards,
    original_performance_rewards,
    tweet_scores,
    search_scores,
    summary_link_scores,
    weights,
    neuron,
    netuid,
    organic_penalties,
    is_synthetic=False,  # Pass the `is_synthetic` flag
):
    try:
        logs = [
            {
                "prompt": response.prompt,
                "completion": response.completion,
                # "prompt_analysis": response.prompt_analysis.dict(),
                "data": response.miner_tweets,
                "score": reward,
                "summary_score": summary_reward,
                "twitter_score": twitter_reward,
                "search_score": search_reward,
                "performance_score": performance_reward,
                "original_summary_score": original_summary_reward,
                "original_twitter_score": original_twitter_reward,
                "original_search_score": original_search_reward,
                "original_performance_score": original_performance_reward,
                "tweet_scores": tweet_score,
                "link_scores": search_score,
                "summary_link_scores": summary_link_score,
                "search_results": {
                    "google": response.search_results,
                    "google_news": response.google_news_search_results,
                    "google_image": response.google_image_search_results,
                    "wikipedia": response.wikipedia_search_results,
                    "youtube": response.youtube_search_results,
                    "arxiv": response.arxiv_search_results,
                    "reddit": response.reddit_search_results,
                    "hacker_news": response.hacker_news_search_results,
                    "discord": response.discord_search_results,
                },
                "texts": response.texts,
                "validator_tweets": [
                    val_tweet.dict() for val_tweet in response.validator_tweets
                ],
                "validator_links": response.validator_links,
                "search_completion_links": response.search_completion_links,
                "twitter_completion_links": response.completion_links,
                "weight": weights.get(str(uid)),
                "miner": {
                    "uid": uid,
                    "hotkey": response.axon.hotkey,
                    "coldkey": next(
                        (
                            axon.coldkey
                            for axon in self.metagraph.axons
                            if axon.hotkey == response.axon.hotkey
                        ),
                        None,  # Provide a default value here, such as None or an appropriate placeholder
                    ),
                },
                "validator": {
                    "uid": neuron.uid,
                    "hotkey": neuron.dendrite.keypair.ss58_address,
                    "coldkey": next(
                        (
                            nr.coldkey
                            for nr in self.metagraph.neurons
                            if nr.hotkey == neuron.dendrite.keypair.ss58_address
                        ),
                        None,
                    ),
                },
                "tools": response.tools,
                "date_filter": {
                    "start_date": response.start_date,
                    "end_date": response.end_date,
                    "date_filter_type": response.date_filter_type,
                },
                "time": response.dendrite.process_time,
                "organic_penalty": organic_penalty,
                "type": "synthetic" if is_synthetic else "organic",  # Add type
                "max_execution_time": response.max_execution_time,  # Add max_execution_time
            }
            for response, uid, reward, summary_reward, twitter_reward, search_reward, performance_reward, original_summary_reward, original_twitter_reward, original_search_reward, original_performance_reward, tweet_score, search_score, summary_link_score, organic_penalty in zip(
                responses,
                uids.tolist(),
                rewards.tolist(),
                summary_rewards.tolist(),
                twitter_rewards.tolist(),
                search_rewards.tolist(),
                performance_rewards.tolist(),
                original_summary_rewards,
                original_twitter_rewards,
                original_search_rewards,
                original_performance_rewards,
                tweet_scores,
                search_scores,
                summary_link_scores,
                organic_penalties,
            )
        ]

        chunk_size = 20

        log_chunks = [logs[i : i + chunk_size] for i in range(0, len(logs), chunk_size)]

        for chunk in log_chunks:
            await save_logs(
                logs=chunk,
                netuid=netuid,
            )
    except Exception as e:
        bt.logging.error(f"Error in save_logs_in_chunks: {e}")
        raise e


def calculate_bonus_score(
    original_score, link_count, max_bonus=0.2, link_sensitivity=2
):
    """
    Calculate the new score with a bonus based on the number of links.

    :param original_score: The original score ranging from 0.1 to 1.
    :param link_count: The number of links in the tweet.
    :param max_bonus: The maximum bonus to add to the score. Default is 0.2.
    :param link_sensitivity: Controls how quickly the bonus grows with the number of links. Higher values mean slower growth.
    :return: The new score with the bonus included.
    """
    # Calculate the bonus
    bonus = max_bonus * (1 - 1 / (1 + link_count / link_sensitivity))

    # Ensure the total score does not exceed 1
    new_score = min(1, original_score + bonus)

    return new_score


def clean_text(text):
    # Unescape HTML entities
    text = html.unescape(text)

    # Remove URLs
    text = re.sub(r"(https?://)?\S+\.\S+\/?(\S+)?", "", text)

    # Remove mentions at the beginning of the text
    text = re.sub(r"^(@\w+\s*)+", "", text)

    # Remove emojis and other symbols
    text = re.sub(r"[^\w\s,]", "", text)

    # Normalize whitespace and newlines
    text = re.sub(r"\s+", " ", text).strip()

    # Remove non-printable characters and other special Unicode characters
    text = "".join(
        char
        for char in text
        if char.isprintable() and not unicodedata.category(char).startswith("C")
    )

    return text
