from atproto import Client as BlueskyClient
from mastodon import Mastodon
import anthropic
import os
import re
import sys

def load_text(filepath):
    try:
        with open(filepath, 'r') as f:
            text = f.read()
        return text
    except FileNotFoundError:
        print(f"Text file not found: {filepath}")
        return ''
    except Exception as e:
        print(f"Error reading text file: {e}")
        return ''

def generate_tweet(text):
    """
    Use Claude API to generate a tweet about a paper
    """
    # Ensure Anthropic API key is set
    client = anthropic.Anthropic(
        api_key=os.getenv('ANTHROPIC_API_KEY')
    )
    
    # Validate API key
    if not client.api_key:
        raise ValueError("Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable.")
       
    # Prompt for tweet generation
    prompt = f"""Based on the text below, create a concise tweet that:
    - Selects the most relevant paper
    - Uses an engaging, witty tone
    - Uses relevant emojis, when appropriate
    - Uses relevant hashtags
    - Has less than 250 characters
    - Never mentions other accounts / handles
    - Only write the tweet, no introduction

    {text}

    Your tweet should capture the essence of the selected paper in an exciting, accessible way."""

    # Call Anthropic's Claude API
    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7
        )
        
        # Extract and return the tweet
        return response.content[0].text
    
    except Exception as e:
        print(f"Error generating editorial with Claude: {e}")
        return None

def prepare_tweet(tweet, url = '' ):
    final_tweet = re.sub(r'@\w+', '', tweet)
    final_tweet +=  ' ' + url
    if len(final_tweet) > 300:
        final_tweet = re.sub(r'#\w+', '', final_tweet)
        if len(final_tweet) > 300:
            final_tweet = 'Check out the latest genomics news! 🧬 ' + url    
    return final_tweet

def create_facets(text, url = ''):
    facets = []
    # Handle URL
    if url in text:
        start = len(text[:text.find(url)].encode('utf-8'))
        end = start + len(url.encode('utf-8'))
        facets.append({
            'index': {
                'byteStart': start,
                'byteEnd': end
            },
            'features': [{
                '$type': 'app.bsky.richtext.facet#link',
                'uri': url
            }]
        })
    # Handle hashtags
    words = text.split()
    current_position = 0
    for word in words:
        if word.startswith('#'):
            start = len(text[:text.find(word, current_position)].encode('utf-8'))
            end = start + len(word.encode('utf-8'))
            facets.append({
                'index': {
                    'byteStart': start,
                    'byteEnd': end
                },
                'features': [{
                    '$type': 'app.bsky.richtext.facet#tag',
                    'tag': word[1:]
                }]
            })
        current_position = text.find(word, current_position) + len(word)
    
    return facets

def post_bluesky(tweet, url = ''):
    BSKY_USER = os.getenv('BSKY_USER')
    BSKY_PASSWORD = os.getenv('BSKY_PASSWORD')
    client = BlueskyClient()
    client.login(BSKY_USER, BSKY_PASSWORD)
    facets = create_facets(tweet, url = url)
    client.send_post(text=tweet,facets=facets)

def post_mastodon(tweet):
    MASTODON_TOKEN=os.getenv('MASTODON_TOKEN')
    MASTODON_INSTANCE=os.getenv('MASTODON_INSTANCE')
    client = Mastodon(access_token=MASTODON_TOKEN,api_base_url=MASTODON_INSTANCE)
    client.status_post(tweet)

def main():
    myURL = 'https://emmecola.github.io/genomics-daily'
    text_file = sys.argv[1]
    text = load_text(text_file)
    tweet = generate_tweet(text)
    final_tweet = prepare_tweet(tweet,url=myURL)
    print(final_tweet)
    post_bluesky(final_tweet,url=myURL)
    post_mastodon(final_tweet)

if __name__ == "__main__":
    main()


