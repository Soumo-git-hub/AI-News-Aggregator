import os  # Add this line to import the os module
import sqlite3
import requests
import spacy
import pyttsx3  # For TTS
from gtts import gTTS  # Optional: For online TTS
from flask import Flask, render_template, request, jsonify, send_file
from datetime import datetime

# Initialize Flask app and spaCy model
app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

# Initialize TTS engine (offline)
tts_engine = pyttsx3.init()

# Define the NewsAPI key directly in the code
NEWS_API_KEY = "YOUR-API-KEY"  # Place your API key here

# Database setup
def init_db():
    try:
        with sqlite3.connect("news_aggregator.db") as conn:
            cursor = conn.cursor()
            
            # Create user_preferences table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL UNIQUE
                )
            ''')
            
            # Create article_history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS article_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    summary TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            print("Database initialized successfully")
    except sqlite3.Error as e:
        print(f"Error initializing database: {e}")
        raise

# Make sure to call init_db() when the app starts
init_db()

# Database helper functions
def execute_query(query, params=()):
    try:
        with sqlite3.connect("news_aggregator.db") as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return True
    except sqlite3.Error as e:
        print(f"Database error in execute_query: {e}")
        raise

def fetch_data(query, params=()):
    try:
        with sqlite3.connect("news_aggregator.db") as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error in fetch_data: {e}")
        raise

# Fetch articles based on keyword
def fetch_articles(keyword):
    try:
        # Add verify=False if SSL issues persist (not recommended for production)
        url = f"https://newsapi.org/v2/everything?q={keyword}&language=en&apiKey={NEWS_API_KEY}"
        response = requests.get(url, timeout=10)  # Add timeout
        response.raise_for_status()

        articles = response.json().get("articles", [])
        news_feed = []
        for article in articles[:5]:  # Limit to 5 articles
            title = article.get("title", "No Title")
            link = article.get("url", "#")
            summary = summarize_article(article.get("description", "No Description"))
            image_url = article.get("urlToImage", None)  # Get the image URL
            news_feed.append({
                "title": title,
                "url": link,
                "summary": summary,
                "image_url": image_url  # Include the image URL in the response
            })

        return news_feed
    except requests.exceptions.SSLError as e:
        print(f"SSL Error: {e}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching articles: {e}")
        return []

# Summarize articles using spaCy
def summarize_article(text):
    if not text:
        return "No content to summarize."
    doc = nlp(text)
    sentences = [sent.text for sent in doc.sents]
    summary = " ".join(sentences[:2])  # Simplistic summarization, can be improved
    return summary

# Route: Homepage
@app.route("/")
def index():
    return render_template("index.html")

# Route: Add user preferences
@app.route("/add_preference", methods=["POST"])
def add_preference():
    try:
        # Get keyword from form data or JSON
        keyword = request.form.get("keyword")
        if not keyword and request.is_json:
            keyword = request.json.get("keyword")

        if not keyword:
            return jsonify({"error": "Keyword is required."}), 400

        # Check if keyword already exists (case-insensitive)
        existing = fetch_data(
            "SELECT keyword FROM user_preferences WHERE LOWER(keyword) = LOWER(?)",
            (keyword,)
        )
        
        if existing:
            return jsonify({"error": f"'{keyword}' is already in your preferences."}), 400

        # Add new keyword
        execute_query(
            "INSERT INTO user_preferences (keyword) VALUES (?)",
            (keyword,)
        )
        
        return jsonify({"message": f"'{keyword}' added successfully to preferences!"})
    
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return jsonify({"error": "Failed to add preference."}), 500
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({"error": "An unexpected error occurred."}), 500

# Route: Fetch personalized news feed
@app.route("/get_feed", methods=["GET"])
def get_feed():
    try:
        keywords = fetch_data("SELECT keyword FROM user_preferences")
        news_feed = []
        for keyword in keywords:
            articles = fetch_articles(keyword[0])
            news_feed.extend(articles)

        return jsonify(news_feed)
    except Exception as e:
        print(f"Error fetching feed: {e}")
        return jsonify({"error": "Failed to fetch feed."}), 500

# Route: Save article to history
@app.route("/save_article", methods=["POST"])
def save_article():
    data = request.json
    title = data.get("title")
    url = data.get("url")
    summary = data.get("summary")

    if title and url and summary:
        try:
            execute_query(
                "INSERT INTO article_history (title, url, summary) VALUES (?, ?, ?)",
                (title, url, summary)
            )
            return jsonify({"message": "Article saved successfully!"})
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return jsonify({"error": "Failed to save article."}), 500
    return jsonify({"error": "All fields are required."}), 400

# Route: View article history
@app.route("/history", methods=["GET"])
def history():
    try:
        history = fetch_data("SELECT title, url, summary, timestamp FROM article_history")
        return jsonify([{
            "title": row[0],
            "url": row[1],
            "summary": row[2],
            "timestamp": row[3]
        } for row in history])
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return jsonify({"error": "Failed to fetch history."}), 500

# Route: Listen to an article
@app.route("/listen_article", methods=["POST"])
def listen_article():
    data = request.json
    title = data.get("title", "Untitled Article")
    summary = data.get("summary", "No summary available.")

    # Combine title and summary for TTS
    content = f"Title: {title}. Summary: {summary}"

    # Create a temporary directory if it doesn't exist
    temp_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # Save audio to a temporary file with full path
    audio_file = os.path.join(temp_dir, "article_audio.mp3")
    
    try:
        # Use gTTS instead of pyttsx3 for better reliability
        tts = gTTS(text=content, lang='en')
        tts.save(audio_file)
        
        return send_file(
            audio_file,
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name="article_audio.mp3"
        )
    except Exception as e:
        print(f"Error generating audio: {e}")
        return jsonify({"error": "Failed to generate audio"}), 500

if __name__ == "__main__":
    if not os.path.exists("news_aggregator.db"):
        init_db()
    app.run(debug=True)
