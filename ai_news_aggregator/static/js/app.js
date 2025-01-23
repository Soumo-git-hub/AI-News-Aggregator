document.addEventListener('DOMContentLoaded', function () {
    const addPreferenceBtn = document.getElementById('addPreference');
    const fetchFeedBtn = document.getElementById('fetchFeed');
    const viewHistoryBtn = document.getElementById('viewHistory');
    const newsFeed = document.getElementById('newsFeed');
    const articleHistory = document.getElementById('articleHistory');

    addPreferenceBtn.addEventListener('click', addPreference);
    fetchFeedBtn.addEventListener('click', fetchNewsFeed);
    viewHistoryBtn.addEventListener('click', viewArticleHistory);

    async function addPreference(event) {
        event.preventDefault();  // Prevent default button behavior
        const keyword = document.getElementById('keyword').value.trim();
        if (!keyword) {
            alert('Please enter a valid keyword.');
            return;
        }

        try {
            const response = await fetch('/add_preference', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ keyword }),
            });

            const data = await response.json();
            if (response.ok) {
                alert(data.message);
                document.getElementById('keyword').value = '';
            } else {
                throw new Error(data.error || 'Failed to add preference.');
            }
        } catch (error) {
            alert(error.message || 'An error occurred while adding the preference.');
        }
    }

    async function fetchNewsFeed() {
        try {
            const response = await fetch('/get_feed');
            const newsFeedData = await response.json();
            displayNewsFeed(newsFeedData);
        } catch (error) {
            alert('An error occurred while fetching the news feed. Please try again.');
        }
    }

    function displayNewsFeed(feed) {
        newsFeed.innerHTML = '';
        if (feed.length === 0) {
            newsFeed.innerHTML = '<p>No articles found for your preferences.</p>';
            return;
        }

        feed.forEach(article => {
            const articleElement = document.createElement('div');
            articleElement.className = 'news-item';

            // Try to fetch the thumbnail either from article.thumbnail or extract it from article.content
            const thumbnail = article.thumbnail || extractImageFromContent(article.content);
            
            articleElement.innerHTML = `
                <div class="article-thumbnail">
                    <img src="${thumbnail || '/static/images/default-thumbnail.jpg'}" alt="Thumbnail" class="thumbnail-img">
                </div>
                <h3>${article.title}</h3>
                <p>${article.summary}</p>
                <a href="${article.url}" target="_blank">Read more</a>
                <button class="saveArticle" data-article='${JSON.stringify(article)}'>Save</button>
            `;
            newsFeed.appendChild(articleElement);
        });

        document.querySelectorAll('.saveArticle').forEach(button => {
            button.addEventListener('click', saveArticle);
        });
    }

    // Helper function to extract image URL from the article content
    function extractImageFromContent(content) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(content, 'text/html');
        const img = doc.querySelector('img');
        return img ? img.src : null;
    }

    async function saveArticle(event) {
        const article = JSON.parse(event.target.getAttribute('data-article'));
        try {
            const response = await fetch('/save_article', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(article),
            });

            const data = await response.json();
            if (response.ok) {
                alert(data.message);
            } else {
                throw new Error(data.error || 'Failed to save article.');
            }
        } catch (error) {
            alert(error.message || 'An error occurred while saving the article.');
        }
    }

    async function viewArticleHistory() {
        try {
            const response = await fetch('/history');
            const history = await response.json();
            displayArticleHistory(history);
        } catch (error) {
            alert('An error occurred while fetching the article history. Please try again.');
        }
    }

    function displayArticleHistory(history) {
        articleHistory.innerHTML = '';
        if (history.length === 0) {
            articleHistory.innerHTML = '<p>No saved articles found.</p>';
            return;
        }

        history.forEach(article => {
            const articleElement = document.createElement('div');
            articleElement.className = 'history-item';

            // Try to fetch the thumbnail either from article.thumbnail or extract it from article.content
            const thumbnail = article.thumbnail || extractImageFromContent(article.content);

            articleElement.innerHTML = `
                <div class="article-thumbnail">
                    <img src="${thumbnail || '/static/images/default-thumbnail.jpg'}" alt="Thumbnail" class="thumbnail-img">
                </div>
                <h3>${article.title}</h3>
                <p>${article.summary}</p>
                <a href="${article.url}" target="_blank">Read more</a>
                <span class="timestamp">Saved on: ${new Date(article.timestamp).toLocaleString()}</span>
            `;
            articleHistory.appendChild(articleElement);
        });
    }
});
