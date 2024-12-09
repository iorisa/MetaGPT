from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from PIL import Image
from playwright.async_api import Browser as Browser_
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, ConfigDict, Field

from metagpt.config2 import Config
from metagpt.const import DEFAULT_WORKSPACE_ROOT
from metagpt.provider.base_llm import BaseLLM
from metagpt.provider.openai_api import OpenAILLM
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import decode_image
from metagpt.utils.proxy_env import get_proxy_from_env
from metagpt.utils.report import BrowserReporter

DOWNLOAD_PICTURE_JAVASCRIPT = """
async () => {{
    var img = document.querySelector('{img_element_selector}');
    if (img && img.src) {{
        const response = await fetch(img.src);
        if (response.ok) {{
            const blob = await response.blob();
            return await new Promise(resolve => {{
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result);
                reader.readAsDataURL(blob);
            }});
        }}
    }}
    return null;
}}
"""
llm_config = Config.default().llm


@register_tool(include_functions=["get", "process"])
class ImageGetter(BaseModel):
    """
    A tool to get images.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    playwright: Optional[Playwright] = Field(default=None, exclude=True)
    browser_instance: Optional[Browser_] = Field(default=None, exclude=True)
    browser_ctx: Optional[BrowserContext] = Field(default=None, exclude=True)
    page: Optional[Page] = Field(default=None, exclude=True)
    headless: bool = Field(default=True)
    proxy: Optional[dict] = Field(default_factory=get_proxy_from_env)
    reporter: BrowserReporter = Field(default_factory=BrowserReporter)
    url: str = "https://unsplash.com/s/photos/{search_term}/"
    img_element_selector: str = ".zNNw1 > div > img:nth-of-type(2)"
    # Add llm field to store instance
    llm: BaseLLM = Field(default_factory=lambda: OpenAILLM(llm_config))

    # Remove gen_image field and replace with property
    @property
    def gen_image(self) -> Callable:
        return self.llm.gen_image

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.page:
            await self.page.close()
        if self.browser_ctx:
            await self.browser_ctx.close()
        if self.browser_instance:
            await self.browser_instance.close()
        if self.playwright:
            await self.playwright.stop()

    async def _save_image(self, image: Image, image_save_path: str) -> str:
        """Helper method to save image and process path"""
        # Save the image to the given path. Due to agent instability, we need to handle two cases:
        # 1. If the path is relative, consider the project folder structure and save under the project folder.
        # 2. If the path is absolute, save directly to the given path.
        # TODO: Consider better approach to handle the image save path.
        image_file_name = os.path.basename(image_save_path)
        if not Path(image_save_path).is_absolute():
            # Check if there is a project folder under the default workspace.
            # FIXME: use a hard rule for now, assume the first folder alphabetically is the project folder.
            project_folder = os.listdir(DEFAULT_WORKSPACE_ROOT)[0]
            save_dir = os.path.dirname(os.path.join(DEFAULT_WORKSPACE_ROOT, project_folder, image_save_path))
            split_str = project_folder + "/"
        else:
            save_dir = os.path.dirname(image_save_path)
            split_str = "public"
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
        image.save(os.path.join(save_dir, image_file_name))

        if split_str in image_save_path:
            image_save_path = image_save_path.split("public")[-1]
        return image_save_path

    async def _retry_goto(self, page: Page, url: str, max_retries: int = 3, timeout: int = 20000):
        """Helper method for retrying page navigation"""
        for attempt in range(max_retries):
            try:
                await page.goto(url, timeout=timeout)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Failed to navigate to {url} after {max_retries} attempts") from e

    async def start(self) -> None:
        """Starts Playwright and launches a browser"""
        if self.playwright is None:
            self.playwright = playwright = await async_playwright().start()
            browser = self.browser_instance = await playwright.chromium.launch(headless=self.headless, proxy=self.proxy)
            browser_ctx = self.browser_ctx = await browser.new_context()
            self.page = await browser_ctx.new_page()

    async def create_image(self, image_description: str, image_save_path: str) -> Image:
        """Create an image with dall-e-3"""
        images = await self.gen_image(model="dall-e-3", prompt=image_description)
        return images[0]

    async def search_image(self, search_term: str, image_save_path: str) -> str:
        """
        Get an image related to the search term.

        Args:
            search_term (str): The term to search for the image. The search term must be in English. Using any other language may lead to a mismatch.
            image_save_path (str): The file path where the image will be saved.
        """
        if not self.playwright:
            await self.start()

        browser_ctx = None
        page = None

        browser_ctx = await self.browser_instance.new_context()
        page = await browser_ctx.new_page()

        url = self.url.format(search_term=search_term.replace(" ", "%20"))
        await self._retry_goto(page, url)
        await page.wait_for_selector(self.img_element_selector)

        image_base64 = await page.evaluate(
            DOWNLOAD_PICTURE_JAVASCRIPT.format(img_element_selector=self.img_element_selector)
        )

        if image_base64:
            image = decode_image(image_base64)
        else:
            images = await self.gen_image(model="dall-e-3", prompt=search_term)
            image = images[0]
        if page:
            await page.close()  # Close the page to avoid memory leaks
        if browser_ctx:
            await browser_ctx.close()  # Close the context to avoid memory leaks
        return image

    async def get(self, search_term: str, image_save_path: str, mode="search") -> str:
        """Get an image related to the search term."""
        if mode == "search":
            try:
                image = await self.search_image(search_term, image_save_path)
            except Exception:
                image = await self.create_image(search_term, image_save_path)
        elif mode == "create":
            image = await self.create_image(search_term, image_save_path)
        else:
            raise ValueError(f"Invalid mode: {mode}")
        return await self._save_image(image, image_save_path)

    async def rembg_image(self, image_path: str, image_save_path: str) -> str:
        try:
            from rembg import remove
        except ImportError:
            raise ImportError("Please install rembg with `pip install rembg`.")

        image = remove(Image.open(image_path))
        image_save_path = await self._save_image(image, image_save_path)
        return image_save_path

    async def process(self, image_path: str, image_save_path: str, mode: str = "rembg") -> str:
        """Process an image in various mode."""
        if mode == "rembg":
            return await self.rembg_image(image_path, image_save_path)
        else:
            raise ValueError(f"Invalid mode: {mode}")
