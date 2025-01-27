import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

class BlogScraper:
    def __init__(self):
        self.base_url = "https://www.socialmusingsbyaustin.com/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.articles = []
        self.setup_driver()

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # Run in headless mode
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

    def get_current_links(self):
        """Extract current visible post links from the page"""
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        links = soup.find_all('a', href=lambda href: href and '/post/' in href)
        return set(urljoin(self.base_url, link['href']) for link in links)

    def scroll_and_collect_links(self):
        print("Scrolling and collecting article links...")
        all_links = set()
        no_new_links_count = 0
        scroll_attempts = 0
        max_attempts = 50  # Maximum number of scroll attempts
        
        # JavaScript to scroll in different ways
        scroll_scripts = [
            "window.scrollTo(0, document.body.scrollHeight);",
            "window.scrollTo(0, document.body.scrollHeight * 0.8);",  # Scroll to 80% of height
            "window.scrollBy(0, 1000);",  # Scroll by fixed amount
        ]
        
        while scroll_attempts < max_attempts and no_new_links_count < 3:
            # Get current links before scrolling
            current_links = self.get_current_links()
            new_links = current_links - all_links
            
            if new_links:
                print(f"Found {len(new_links)} new articles")
                all_links.update(new_links)
                no_new_links_count = 0
            else:
                no_new_links_count += 1
            
            # Try different scroll methods in rotation
            scroll_script = scroll_scripts[scroll_attempts % len(scroll_scripts)]
            self.driver.execute_script(scroll_script)
            
            # Add some randomization to the wait time
            time.sleep(2 + (scroll_attempts % 2))  # Alternate between 2 and 3 seconds
            
            # Sometimes scroll back up a bit to trigger lazy loading
            if scroll_attempts % 5 == 0:
                self.driver.execute_script("window.scrollBy(0, -500);")
                time.sleep(1)
                self.driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
            
            scroll_attempts += 1
            print(f"Scroll attempt {scroll_attempts}/{max_attempts}, found {len(all_links)} articles so far")
            
            # Every 10 attempts, try to force load more content
            if scroll_attempts % 10 == 0:
                print("Attempting to force load more content...")
                self.driver.execute_script("""
                    // Click any "load more" or similar buttons
                    document.querySelectorAll('button, a').forEach(el => {
                        if (el.textContent.toLowerCase().includes('more') || 
                            el.textContent.toLowerCase().includes('load') ||
                            el.textContent.includes('...')) {
                            el.click();
                        }
                    });
                """)
                time.sleep(3)
        
        if scroll_attempts >= max_attempts:
            print("Reached maximum scroll attempts")
        elif no_new_links_count >= 3:
            print("No new links found after multiple attempts")
            
        print(f"Finished scrolling. Found total of {len(all_links)} unique articles")
        return list(all_links)

    def extract_article_links(self):
        print("Loading main page to extract all article links...")
        self.driver.get(self.base_url)
        
        # Wait for initial content to load
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/post/')]"))
            )
        except Exception as e:
            print(f"Warning: Initial load timeout - {str(e)}")
        
        # Scroll and collect all links
        return self.scroll_and_collect_links()

    def get_soup(self, url):
        response = requests.get(url, headers=self.headers)
        return BeautifulSoup(response.text, 'html.parser')

    def clean_text(self, text):
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def scrape_article(self, url):
        print(f"Scraping: {url}")
        soup = self.get_soup(url)
        
        # Extract article information
        title = soup.find('h1')
        title = title.text.strip() if title else "No title found"
        
        # Get the author and date
        author = "Austin from Austin"  # Default author
        date = None
        meta_div = soup.find('div', string=lambda x: x and "min read" in x)
        if meta_div:
            meta_text = meta_div.get_text()
            date_match = re.search(r'([A-Z][a-z]+ \d+, \d{4})', meta_text)
            if date_match:
                date = date_match.group(1)
        
        # Get the main content by finding all paragraphs after the title
        content_elements = []
        main_content = soup.find_all(['p', 'h2', 'h3', 'li'])
        for element in main_content:
            text = element.get_text().strip()
            if text and not any(skip in text.lower() for skip in ['min read', '©2021', 'subscribe', 'social musings']):
                content_elements.append(text)
        
        content = '\n\n'.join(content_elements)
        content = self.clean_text(content)
        
        # Get categories/tags
        categories = []
        category_elements = soup.find_all('a', {'data-hook': 'post-category'})
        if category_elements:
            categories = [cat.text.strip() for cat in category_elements]
        
        return {
            'url': url,
            'title': title,
            'author': author,
            'date': date,
            'content': content,
            'categories': ', '.join(categories) if categories else ''
        }

    def scrape_all_articles(self):
        article_links = self.extract_article_links()
        print(f"Starting to scrape {len(article_links)} articles")
        
        for url in article_links:
            try:
                article_data = self.scrape_article(url)
                self.articles.append(article_data)
                # Be nice to the server
                time.sleep(1)
            except Exception as e:
                print(f"Error scraping {url}: {str(e)}")

    def save_to_tsv(self, filename='blog_articles.tsv'):
        df = pd.DataFrame(self.articles)
        df.to_csv(filename, sep='\t', index=False)
        print(f"Saved {len(self.articles)} articles to {filename}")

    def cleanup(self):
        self.driver.quit()

def main():
    scraper = BlogScraper()
    try:
        scraper.scrape_all_articles()
        scraper.save_to_tsv()
    finally:
        scraper.cleanup()

if __name__ == "__main__":
    main() 