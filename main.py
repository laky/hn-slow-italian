from bs4 import BeautifulSoup
import requests

import openai
import os
import time
from tqdm import tqdm

from narakeet_api import AudioAPI

import datetime

test = False
skip_generate_text = True
skip_narration = False
max_retries = 5
max_article_length = 4*3000 if test else 4*7000 # token is roughly 4 characters, so use 3000 for GPT3 for testing and 7000 for GPT4.

openai.api_key = os.getenv("OPENAI_API_KEY")
language = "Italian"
number_of_articles = 5
audio_format = "m4a"
text_file = "/Users/lukasplatinsky/workspace/hn-slow-italian/output.txt"
result_file = f"/Users/lukasplatinsky/workspace/hn-slow-italian/output.{audio_format}"

narakeet_api_key = os.getenv("NARAKEET_API_KEY")
voice = 'Ludovica'
speed = 0.85

playht_api_key = os.getenv("PLAYHT_API_KEY")
playht_user_id = os.getenv("PLAYHT_USER_ID")
playht_voice = 'it-IT-ElsaNeural'


def get_link_content(url: str, retry_attempt: int = 0) -> str:
    try:
        res = requests.get(url)
        html_page = res.content
        soup = BeautifulSoup(html_page, 'html.parser')
        text = soup.find_all(text=True)

        output = ''
        blacklist = [
            '[document]',
            'noscript',
            'header',
            'html',
            'meta',
            'head',
            'input',
            'script',
            'style',
            # there may be more elements you don't want, such as "style", etc.
        ]

        for t in text:
            if t.parent.name not in blacklist:
                output += '{} '.format(t)

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
            model= "gpt-3.5-turbo" if test else "gpt-4",
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
        if link.get('href')[:4] == 'http' and link.get('href')[:29] != 'https://news.ycombinator.com' and link.get('href')[:28] != 'https://www.ycombinator.com/':
                articles.append((link.get('href'), link.text))
    return articles[:number_of_articles]

def create_introduction(episode) -> str:
    prompt = f"Imagine you are creating an episode for a podcast called \"Hacker News in Slow Italian\" that summarizes the top {number_of_articles} articles on Hacker News that should be accessible for people learning {language}. Use simple, short sentences, and the most common words in {language}.\n\n"
    prompt += f"This is the content of the episode:\n{episode}\n\n"
    prompt += "\nCreate a short introduction paragraph for the episode to get people excited about today's content. Use an easy-to-follow and conversational style as you would in a podcast.\n\n"

    return make_gpt4_call(prompt)

def create_ending(episode) -> str:
    prompt = f"Imagine you are creating an episode for a podcast called \"Hacker News in Slow Italian\" that summarizes the top {number_of_articles} articles on Hacker News that should be accessible for people learning {language}. Use simple, short sentences, and the most common words in {language}. "
    prompt += f"Here is the text of the episode:\n{episode}\n\n"
    prompt += "Create a short ending for the episode. Use an easy-to-follow and conversational style as you would in a podcast.\n\n"

    return make_gpt4_call(prompt)

def summarize_article(link, index: int) -> str:
    url, title = link
    try:
        content = get_link_content(url)
    except:
        content = f"Unfortunately, there's no text for the article with the title {title} as it could not be downloaded. Perhaps it got too popular and the server is down. Who knows..."

    prompt = f"Create a summary of an article. Make the summary accessible for people learning {language}. Use simple, short sentences, and the most common words in {language}.\n\n"
    prompt += f"This is the text from the article:\n<text>{content}</text>\n\n"
    prompt += f"Generate an engaging and in-depth summary (3-5 paragraphs long) in {language}. Use an easy-to-follow and conversational style. Start by mentioning the article's title \"{title}\"."

    return make_gpt4_call(prompt)

def generate_episode_text() -> str:
    print("Getting links...")
    links = get_hn_links()
    print("Summarising articles...")
    summaries = [summarize_article(link, index) for index, link in tqdm(enumerate(links))]
    content = "\n\n(pause: 3)\n".join(summaries)

    print("Generating beginning and ending...")
    transcript = create_introduction(content) + "\n\n" + content + "\n\n" + create_ending(content)
    return transcript

def show_progress(progress_data):
    # change this to do something smarter with percent, message and thumbnail
    print(progress_data)

def narrate_text(text: str) -> str:
    api = AudioAPI(narakeet_api_key)

    # start a build task using the text sample and voice
    # and wait for it to finish
    task = api.request_audio_task(audio_format, text, voice, speed)
    task_result = api.poll_until_finished(task['statusUrl'], show_progress)

    # grab the result file
    if task_result['succeeded']:
        api.download_to_file(task_result['result'], result_file)
        print(f'downloaded to {result_file}')
    else:
        raise Exception(task_result['message'])

def playht_narrate(text):
    url = "https://play.ht/api/v1/convert"

    payload = {
        "content": [text],
        "voice": playht_voice,
        "globalSpeed": "85",
        "title": "hn-ep-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "AUTHORIZATION": playht_api_key,
        "X-USER-ID": playht_user_id
    }

    response = requests.post(url, json=payload, headers=headers)
    print(response.text)

def get_an_episode() -> str:
    text = generate_episode_text()
    narration_url = narrate_text(text)

    return text, narration_url

def test_download_article():
    url = 'https://www.engineersneedart.com/blog/samestop/samestop.html'
    print(get_link_content(url))

def test_get_links():
    for link, text in get_hn_links():
        print(text, link)


if __name__ == '__main__':
    if not skip_generate_text:
        print("Generating episode text...")
        text = generate_episode_text()
        with open(text_file, "w") as f:
            f.write(text)

    if not test and not skip_narration:
        with open(text_file, "r") as f:
            text = f.read()
            print("Generating episode audio...")
            # narrate_text(text)
            playht_narrate(text)

    print("Done!")


