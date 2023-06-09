from bs4 import BeautifulSoup
import requests

import openai
import os
import time
from tqdm import tqdm
from typing import Optional

import datetime
date_time_string = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

model = "gpt-3.5-turbo" # try to cut down costs by using GPT3.5
skip_generate_text = False
skip_narration = False
max_retries = 5
max_article_length = 4*3000 if model=="gpt-3.5-turbo" else 4*7000 # token is roughly 4 characters, so use 3000 for GPT3 for testing and 7000 for GPT4.

openai.api_key = os.getenv("OPENAI_API_KEY")
language = "Italian"
# language = "Spanish"
# language = "Portuguese"
# language = "Slovak"
# language = "German"
number_of_articles = 5
text_file = f"/Users/lukasplatinsky/workspace/hn-slow-italian/episode-transcripts/hn-ep-{language}-transcript-{date_time_string}.txt"
file_audio = f"hn-ep-{language}-audio" + date_time_string

playht_api_key = os.getenv("PLAYHT_API_KEY")
playht_user_id = os.getenv("PLAYHT_USER_ID")
playht_voice = 'it-IT-ElsaNeural'
# playht_voice = "es-ES_LauraV3Voice"
# playht_voice = "pt-PT-FernandaNeural"
# playht_voice = "sk-SK-LukasNeural"
# playht_voice = "VickiNeural"

denylist_urls = [
    # Everything should be handled in the prompt now, fingers crossed.
]


def get_link_content(url: str, retry_attempt: int = 0) -> str:
    try:
        res = requests.get(url)
        html_page = res.content
        soup = BeautifulSoup(html_page, 'html.parser')
        text = soup.find_all(text=True)

        output = ''
        denylist = [
            '[document]',
            'noscript',
            'header',
            'html',
            'meta',
            'head',
            'input',
            'script',
            'style',
        ]

        for t in text:
            if t.parent.name not in denylist:
                output += '{} '.format(t)

        # TODO: Currently long articles are chopped off to fit the GPT limits. May want to address this at some point.
        return output[:max_article_length].strip()
    except Exception as e:
        if retry_attempt < max_retries:
            print("Error downloading article, retrying...")
            time.sleep(2 ^ retry_attempt)
            return get_link_content(url, retry_attempt + 1)
        else:
            raise Exception("Article download failed", e)


def make_gpt4_call(prompt: str, retry_attempt: int = 0) -> str:
    print(prompt)
    print("---------------------------------")

    try:
        completion = openai.ChatCompletion.create(
            model= model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        print(completion.choices[0].message.content)
        print("---------------------------------")
        return completion.choices[0].message.content

    except Exception as e:
        if e.error.type == "server_error" and retry_attempt < max_retries:
            print("Server error, retrying...")
            time.sleep(2 ^ retry_attempt)
            return make_gpt4_call(prompt, retry_attempt + 1)

        else:
            raise Exception("GPT call failed", e)

def get_hn_links():
    hn_url = 'https://news.ycombinator.com/'
    res = requests.get(hn_url)
    html_page = res.content
    soup = BeautifulSoup(html_page, 'html.parser')
    links = soup.find_all('a')
    articles = []
    for link in links:
        # Skip YC links and PDFs
        if link.get('href')[:4] == 'http' and link.get('href')[:29] != 'https://news.ycombinator.com' and link.get('href')[:28] != 'https://www.ycombinator.com/' and "[pdf]" not in link.text:
                skip = False
                for url in denylist_urls:
                    if url in link.get('href'):
                        skip = True
                if not skip:
                    articles.append((link.get('href'), link.text))
    return articles

def create_introduction(episode) -> str:
    prompt = f"Imagine you are creating an episode for a podcast called \"Hacker News in Slow {language}\" that summarizes the top {number_of_articles} articles on Hacker News that should be accessible for people learning {language}. Use simple, short sentences, and the most common words in {language}.\n\n"
    prompt += f"This is the content of the episode:\n{episode}\n\n"
    prompt += "\nCreate a short introduction paragraph for the episode to get people excited about today's content. Use an easy-to-follow and conversational style as you would in a podcast.\n\n"

    return make_gpt4_call(prompt)

def create_ending(episode) -> str:
    prompt = f"Imagine you are creating an episode for a podcast called \"Hacker News in Slow {language}\" that summarizes the top {number_of_articles} articles on Hacker News that should be accessible for people learning {language}. Use simple, short sentences, and the most common words in {language}. "
    prompt += f"Here is the text of the episode:\n{episode}\n\n"
    prompt += "Create a short ending for the episode. Use an easy-to-follow and conversational style as you would in a podcast.\n\n"

    return make_gpt4_call(prompt)

def summarize_article(link, index: int) -> Optional[str]:
    url, title = link
    try:
        content = get_link_content(url)
        prompt = f"Create a summary of a content on the website (usually this contains an article, but could also be a github repo or a forum). Make the summary accessible for people learning {language}. Use simple grammar, short sentences, and only the most commonly used words in {language}.\n\n"
        prompt += f"This is the text scraped from the website:\n<text>{content}</text>\n\n"
        prompt += f"If no substantial content wasn't returned due to an error during the scraping, return just \"ERROR\".\n\n"
        prompt += f"Otherwise, generate an engaging and in-depth summary of the most interesting information (3-5 paragraphs long) in {language}. Use an easy-to-follow and conversational style. Start by mentioning the website's title \"{title}\"."
        response = make_gpt4_call(prompt)

        if response.lower().startswith("error"):
            return None

        return response

    except:
        return None

def generate_episode_text() -> str:
    print("Getting links...")
    links = get_hn_links()
    print("Summarising articles...")
    summaries = []
    index = 0
    generated = []
    skipped = []
    while len(summaries) < number_of_articles and index < len(links):
        summary = summarize_article(links[index], index)
        if summary is not None:
            summaries.append(summary)
            generated.append(links[index])

        else:
            skipped.append(links[index])

        index += 1

    content = "\n\n".join(summaries)

    print("Generating beginning and ending...")
    transcript = create_introduction(content) + "\n\n" + content + "\n\n" + create_ending(content)
    print("Generated links:", generated)
    print("Skipped links:", skipped)
    return transcript

def playht_narrate(text):
    url = "https://play.ht/api/v1/convert"

    payload = {
        "content": [s for s in text.split("\n") if len(s) > 0],
        "voice": playht_voice,
        "globalSpeed": "85",
        "title": file_audio,
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "AUTHORIZATION": playht_api_key,
        "X-USER-ID": playht_user_id
    }

    response = requests.post(url, json=payload, headers=headers)
    print(response.text)

    # TODO: Poll until finished, then download.
    url = "https://play.ht/api/v1/articleStatus?transcriptionId=-NOjGbpFU1Exf3DxhLHU"
    headers = {
        "accept": "application/json",
        "AUTHORIZATION": playht_api_key,
        "X-USER-ID": playht_user_id
    }
    response = requests.get(url, headers=headers)
    print(response.text)

if __name__ == '__main__':
    if not skip_generate_text:
        print("Generating episode text...")
        text = generate_episode_text()
        with open(text_file, "w") as f:
            f.write(text)

    if not skip_narration:
        with open(text_file, "r") as f:
            text = f.read()

            print("Generating episode audio...")
            playht_narrate(text)

    print("Done!")


