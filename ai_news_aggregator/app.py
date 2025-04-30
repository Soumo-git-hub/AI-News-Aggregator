import os
import sqlite3
import requests
import spacy
import pyttsx3
from gtts import gTTS
from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime, timedelta
from functools import lru_cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
from queue import Queue
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app and spaCy model
app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Get API key from environment variable
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "PUT_HERE")

# Database connection pool
class DatabasePool:
    def __init__(self, max_connections=5):
        self.max_connections = max_connections
        self.connections = Queue(maxsize=max_connections)
        self.lock = threading.Lock()
        
        # Use existing database from db directory
        db_path = os.path.join(os.path.dirname(__file__), "db", "news_aggregator.db")
        
        # Verify database exists
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database file not found at {db_path}")
        
        for _ in range(max_connections):
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self.connections.put(conn)
    
    def get_connection(self):
        return self.connections.get()
    
    def return_connection(self, conn):
        self.connections.put(conn)

db_pool = DatabasePool()

@lru_cache(maxsize=100)
def execute_query(query, params=()):
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        db_pool.return_connection(conn)
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error in execute_query: {e}")
        raise

@lru_cache(maxsize=100)
def fetch_data(query, params=()):
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchall()
        db_pool.return_connection(conn)
        return result
    except sqlite3.Error as e:
        logger.error(f"Database error in fetch_data: {e}")
        raise

# Cache API responses for 5 minutes
@lru_cache(maxsize=100)
def fetch_articles(keyword):
    try:
        url = f"https://newsapi.org/v2/everything?q={keyword}&language=en&apiKey={NEWS_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        articles = response.json().get("articles", [])
        news_feed = []
        for article in articles[:5]:
            title = article.get("title", "No Title")
            link = article.get("url", "#")
            summary = summarize_article(article.get("description", "No Description"))
            image_url = article.get("urlToImage", None)
            news_feed.append({
                "title": title,
                "url": link,
                "summary": summary,
                "image_url": image_url
            })

        return news_feed
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching articles: {e}")
        return []

def summarize_article(text):
    if not text:
        return "No content to summarize."
    
    # Use a more efficient summarization approach
    doc = nlp(text)
    sentences = [sent.text for sent in doc.sents]
    
    # Calculate sentence importance based on length and content
    important_sentences = []
    for sent in sentences[:3]:  # Consider first 3 sentences
        if len(sent.split()) > 5:  # Only include sentences with more than 5 words
            important_sentences.append(sent)
    
    return " ".join(important_sentences[:2])

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/add_preference", methods=["POST"])
@limiter.limit("10 per minute")
def add_preference():
    try:
        keyword = request.form.get("keyword") or (request.json.get("keyword") if request.is_json else None)
        
        if not keyword:
            return jsonify({"error": "Keyword is required."}), 400

        existing = fetch_data(
            "SELECT keyword FROM user_preferences WHERE LOWER(keyword) = LOWER(?)",
            (keyword,)
        )
        
        if existing:
            return jsonify({"error": f"'{keyword}' is already in your preferences."}), 400

        execute_query(
            "INSERT INTO user_preferences (keyword) VALUES (?)",
            (keyword,)
        )
        
        return jsonify({"message": f"'{keyword}' added successfully to preferences!"})
    
    except Exception as e:
        logger.error(f"Error in add_preference: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500

@app.route("/get_feed", methods=["GET"])
@limiter.limit("30 per minute")
def get_feed():
    try:
        keywords = fetch_data("SELECT keyword FROM user_preferences")
        news_feed = []
        
        # Use threading to fetch articles concurrently
        threads = []
        results = []
        
        def fetch_articles_thread(keyword):
            articles = fetch_articles(keyword[0])
            results.extend(articles)
        
        for keyword in keywords:
            thread = threading.Thread(target=fetch_articles_thread, args=(keyword,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Error fetching feed: {e}")
        return jsonify({"error": "Failed to fetch feed."}), 500

@app.route("/save_article", methods=["POST"])
@limiter.limit("20 per minute")
def save_article():
    try:
        data = request.json
        title = data.get("title")
        url = data.get("url")
        summary = data.get("summary")
        keyword = data.get("keyword", "")  # Make keyword optional with default empty string

        if not all([title, url, summary]):
            return jsonify({"error": "Title, URL, and summary are required."}), 400

        execute_query(
            "INSERT INTO article_history (title, url, summary, keyword) VALUES (?, ?, ?, ?)",
            (title, url, summary, keyword)
        )
        return jsonify({"message": "Article saved successfully!"})
    except Exception as e:
        logger.error(f"Error saving article: {e}")
        return jsonify({"error": "Failed to save article."}), 500

@app.route("/history", methods=["GET"])
@limiter.limit("30 per minute")
def history():
    try:
        history = fetch_data(
            "SELECT title, url, summary, timestamp, keyword FROM article_history ORDER BY timestamp DESC LIMIT 100"
        )
        return jsonify([{
            "title": row[0],
            "url": row[1],
            "summary": row[2],
            "timestamp": row[3],
            "keyword": row[4]
        } for row in history])
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return jsonify({"error": "Failed to fetch history."}), 500

@app.route("/listen_article", methods=["POST"])
@limiter.limit("10 per minute")
def listen_article():
    try:
        data = request.json
        title = data.get("title", "Untitled Article")
        summary = data.get("summary", "No summary available.")

        content = f"Title: {title}. Summary: {summary}"
        temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        audio_file = os.path.join(temp_dir, "article_audio.mp3")
        
        tts = gTTS(text=content, lang='en')
        tts.save(audio_file)
        
        return send_file(
            audio_file,
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name="article_audio.mp3"
        )
    except Exception as e:
        logger.error(f"Error generating audio: {e}")
        return jsonify({"error": "Failed to generate audio"}), 500

if __name__ == "__main__":
    app.run(debug=True, threaded=True)