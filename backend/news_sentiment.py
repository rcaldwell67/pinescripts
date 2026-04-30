import requests
import pandas as pd
from textblob import TextBlob

NEWSAPI_KEY = ''  # Add your NewsAPI key if available

# Example: Fetch news headlines from NewsAPI (or use Yahoo RSS as fallback)
def fetch_news_headlines(symbol, api_key=NEWSAPI_KEY):
    if api_key:
        url = f'https://newsapi.org/v2/everything?q={symbol}&apiKey={api_key}'
        resp = requests.get(url)
        articles = resp.json().get('articles', [])
        headlines = [a['title'] for a in articles]
    else:
        # Fallback: Yahoo Finance RSS
        url = f'https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US'
        resp = requests.get(url)
        headlines = []
        if resp.ok:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            for item in root.findall('.//item/title'):
                headlines.append(item.text)
    return headlines

def analyze_sentiment(headlines):
    sentiments = []
    for headline in headlines:
        blob = TextBlob(headline)
        sentiments.append(blob.sentiment.polarity)
    if sentiments:
        avg_sentiment = sum(sentiments) / len(sentiments)
    else:
        avg_sentiment = 0
    return avg_sentiment

if __name__ == '__main__':
    symbol = 'AAPL'
    headlines = fetch_news_headlines(symbol)
    print('Headlines:', headlines)
    print('Average sentiment:', analyze_sentiment(headlines))
