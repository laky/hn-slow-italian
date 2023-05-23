from bs4 import BeautifulSoup
import requests

import openai
import os
from tqdm import tqdm

from narakeet_api import AudioAPI

openai.api_key = os.getenv("OPENAI_API_KEY")
language = "Italian"
number_of_articles = 5
audio_format = "m4a"
result_file = f"/Users/lukasplatinsky/workspace/hn-slow-italian/output.{audio_format}"

narakeet_api_key = os.getenv("NARAKEET_API_KEY")
voice = 'Ludovica'
speed = 0.85


def get_link_content(url: str) -> str:
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
        # there may be more elements you don't want, such as "style", etc.
    ]

    for t in text:
        if t.parent.name not in blacklist:
            output += '{} '.format(t)

    return output


def make_gpt4_call(prompt: str) -> str:
    completion = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return completion.choices[0].message.content

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

def create_introduction(links) -> str:
    prompt = f"Imagine you are creating an episode for a podcast called \"Hacker News in Slow Italian\" that summarizes the top {number_of_articles} articles on Hacker News that should be accessible for people learning {language}. Use simple, short sentences, and the most common words in {language}. These are the article titles:\n"
    for link, text in links:
        prompt += f"- {text}\n"
    prompt += "\nCreate a short introduction for the episode. Use an easy-to-follow and conversational style as you would in a podcast.\n\n"

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
        content = f"Unfortunately, the article with the title {title} could not be downloaded. Perhaps it got too popular and the server is down. Who knows..."

    prompt = f"Imagine you are creating an article summary for an episode for a podcast called \"Hacker News in Slow Italian\" that summarizes the top {number_of_articles} articles on Hacker News that should be accessible for people learning {language}. Use simple, short sentences, and the most common words in {language}. This is the text from article {index} out of {number_of_articles}:\n"
    prompt += f"{content}\n\n"
    prompt += "The text you generate will be used in the middle of the episode to talk about this article. The introduction to the episode was already written, so jump straight in and write just the summary of the article. Use an easy-to-follow and conversational style as you would in a podcast.\n\n"

    return make_gpt4_call(prompt)

def generate_episode_text() -> str:
    print("Getting links...")
    links = get_hn_links()
    print("Generating introduction...")
    transcript = create_introduction(links) + "\n\n"
    print("Summarising articles...")
    summaries = [summarize_article(link, index) for index, link in tqdm(enumerate(links))]
    transcript += "\n\n".join(summaries) + "\n\n"
    print("Generating ending...")
    transcript += create_ending(transcript)

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
    print("Generating episode text...")
    text = generate_episode_text()
    print(text)

    print("Generating episode audio...")
    narrate_text(text)


