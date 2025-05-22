from typing import Literal, Optional
from pydantic import BaseModel, Field
import threading
from pathlib import Path
import os
import urllib.parse
from time import sleep
import random
import http.client
import json
import re
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class SeleniumDriverManager:
    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:            
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            options = Options()
            # options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1920x1080')
            # Keep browser open after script ends
            options.add_experimental_option("detach", True)
            cls._driver = webdriver.Chrome(options=options)
        return cls._driver

class BrowseWebLink(ServiceOrientedArchitecture):

    @classmethod
    def description(cls):
        return """
        This service browses and scrapes the information from the provided web link.
        Supports parsing specific domains like YouTube, GitHub, Qiita, AWS, and Google Search.
        """

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            headless: bool = Field(False, description="Run browser in headless mode.")
            remove_tags: list[str] = Field(['script', 'style', 'data:image'], description="List of HTML tags to remove.")

        class Args(BaseModel):
            link: str = Field(..., description="The URL to browse.")
            filename: Optional[str] = Field(None, description="Optional filename to save content.")

        class Return(BaseModel):
            result: str = Field(..., description="Result message or error details.")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {
                    "param": {"headless": True},
                    "args": {"link": "https://www.example.com"},
                }
            ]

        version: Version = Version()
        param: Param = Param()
        args: Args
        ret: Optional[Return] = Return(result="")
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):

        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: BrowseWebLink.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                link = self.model.args.link
                filename = self.model.args.filename
                result_text = "can not open the link!"

                try:
                    result_text = self.browse_website(link)
                    
                    if filename:
                        folder = Path(self.model.version.class_name)
                        folder.mkdir(exist_ok=True)
                        filename = folder / f'link_{self.date()}.txt'
                        with open(filename, 'w', encoding='utf-8', errors='ignore') as f:
                            f.write(result_text)
                        self.model.ret.result = f"Saved information to {filename}"
                    else:
                        self.model.ret.result = result_text
                except Exception as e:
                    self.model.ret.result = f"Error: {str(e)}"
                return self.model

        def to_stop(self):
            self.model.ret.result = "Execution stopped by flag."
            return self.model

        def browse_website(self, link: str) -> str:
            parsed_url = urllib.parse.urlparse(link)
            domain = parsed_url.hostname or ""
            if 'youtube.com' in domain or 'youtu.be' in domain:
                return self._parse_youtube_video(link)
            elif 'google.com' in domain and 'search' in link:
                return self._google_search(link)
            else:
                html = self._fetch_page_content(link)
                return self.scrape_text(link, html)


        def _fetch_page_content(self, link: str) -> str:
            if not self.model.param.headless:
                return self._fetch_with_selenium(link)
            else:
                return self._fetch_with_requests(link)

        def _fetch_with_requests(self, link: str) -> str:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.49 Safari/537.36"
            }
            response = requests.get(link, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text

        def _fetch_with_selenium(self, link: str) -> str:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.common.by import By
            
            # options = Options()
            # # options.add_argument('--headless')
            # options.add_argument('--disable-gpu')
            # options.add_argument('--no-sandbox')
            # options.add_argument('--window-size=1920x1080')
            # # Keep browser open after script ends
            # options.add_experimental_option("detach", True)

            # driver = webdriver.Chrome(options=options)
            driver = SeleniumDriverManager.get_driver()
            if link:
                driver.get(link)

            # Wait if needed (can be improved with WebDriverWait)
            sleep(2)

            html = driver.page_source
            # driver.quit()
            return html

        def scrape_text(self, link: str, html: str) -> str:
            if 'qiita.com' in link:
                return self._parse_qiita(html)
            elif 'github.com' in link and self._is_file(link):
                return self._parse_github_file(html)
            elif 'aws.amazon.com' in link:
                return self._parse_aws(html)
            else:
                cleaned_html = self.remove_tags_using_bs(html, tags=self.model.param.remove_tags)
                return md(cleaned_html)

        def _parse_youtube_video(self, url: str) -> str:
            def extract_video_id(url):
                pattern = re.compile(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", re.IGNORECASE)
                match = pattern.search(url)
                return match.group(1) if match else None

            video_id = extract_video_id(url)
            if not video_id:
                return "Video ID not found"

            video_info_url = f"URL_ADDRESS.youtube.com/oembed?url=URL_ADDRESSoutube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            response = requests.get(video_info_url)
            response.raise_for_status()
            video_info = response.json()
            return video_info.get("title", "Video title not found")

        def _parse_qiita(self, html: str) -> str:
            soup = BeautifulSoup(html, 'html.parser')
            article = soup.find('div', id='personal-public-article-body')
            return article.text.replace('Copied!', '') if article else "Article body not found"

        def _parse_aws(self, html: str) -> str:
            if '<h1 class="error-code">404</h1>' in html:
                return "404 error on AWS page"
            soup = BeautifulSoup(html, "html.parser")
            text = soup.find(id="main-col-body")
            return text.text if text else "Content not found"

        def _parse_github_file(self, html: str) -> str:
            soup = BeautifulSoup(html, 'html.parser')
            textarea = soup.find(id="read-only-cursor-text-area")
            return textarea.text if textarea else "GitHub file not found"

        def _is_file(self, url: str) -> bool:
            return bool(re.search(r'\.[a-z]{2,}$', url.split('/')[-1], re.IGNORECASE))

        def remove_tags_using_bs(self, html_doc, tags=['script', 'style', 'data:image']):
            soup = BeautifulSoup(html_doc, 'html.parser')
            # Remove specified tags
            for tag in tags:
                if tag == 'data:image':
                    # Remove base64 encoded images
                    for img in soup.find_all('img'):
                        src = img.get('src', '')
                        if src.startswith('data:image'):
                            img.decompose()
                else:
                    for match in soup.find_all(tag):
                        match.decompose()
                    
            return str(soup)
            
        def _google_search(self, url: str) -> str:
            try:
                q = self._extract_google_query(url)
                if 'SERPER_API_KEY' in os.environ:
                    return self._serper_search(os.environ['SERPER_API_KEY'], q=q)
                else:
                    return self._manual_google_search(q)
            except Exception as e:
                return f"Google search failed: {str(e)}"

        def _extract_google_query(self, url: str) -> str:
            parsed = urllib.parse.urlparse(url)
            return urllib.parse.parse_qs(parsed.query).get("q", [""])[0]

        def _serper_search(self, key: str, q: str) -> str:
            conn = http.client.HTTPSConnection("google.serper.dev")
            payload = json.dumps({"q": q})
            headers = {"X-API-KEY": key, "Content-Type": "application/json"}
            conn.request("POST", "/search", payload, headers)
            res = conn.getresponse()
            return res.read().decode("utf-8")

        def _manual_google_search(self, query: str, lang="en", timeout=5) -> str:
            escaped_term = urllib.parse.quote_plus(query)
            url = f"https://www.google.com/search?q={escaped_term}&hl={lang}"
            headers = {
                "User-Agent": random.choice([
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0',
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'
                ])
            }
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text

if __name__ == "__main__":
    m = BrowseWebLink.Model(
        **{ "param": {"headless": False},
            "args": {"link": "https://en.wikipedia.org/wiki/Apple"}}
    )
    res = BrowseWebLink.Action(m, None)()
    print(res)