from __future__ import annotations

import os
from typing import Callable, Optional

from playwright.async_api import Browser as Browser_
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, ConfigDict, Field

from metagpt.config2 import Config
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


@register_tool(include_functions=["get_image", "create_image"])
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

    async def start(self) -> None:
        """Starts Playwright and launches a browser"""
        if self.playwright is None:
            self.playwright = playwright = await async_playwright().start()
            browser = self.browser_instance = await playwright.chromium.launch(headless=self.headless, proxy=self.proxy)
            browser_ctx = self.browser_ctx = await browser.new_context()
            self.page = await browser_ctx.new_page()

    async def create_image(self, image_description: str, image_save_path: str) -> str:
        """
        Create an image with dall-e-3 based on the description.

        Args:
            image_description (str): The description of the image.
            image_save_path (str): The file path where the image will be saved.
        """
        images = await self.gen_image(model="dall-e-3", prompt=image_description)
        image = images[0]
        # Get the directory path from the full file path
        save_dir = os.path.dirname(image_save_path)
        # Create directory if it doesn't exist
        if save_dir and not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        image.save(image_save_path)
        # Ensure both image_save_path and DEFAULT_WORKSPACE_ROOT are strings
        if "public" in image_save_path:
            image_save_path = image_save_path.split("public")[-1]

        return image_save_path

    async def get_image(self, search_term, image_save_path):
        """Get an image related to the search term."""
        browser_ctx = None
        page = None

        try:
            if self.playwright is None:
                await self.start()

            # Create new context and page for this request
            browser_ctx = await self.browser_instance.new_context()
            page = await browser_ctx.new_page()

            encoded_term = search_term.replace(" ", "%20")
            url = self.url.format(search_term=encoded_term)

            try:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await page.goto(url, timeout=20000)
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise e
                        continue

                await page.wait_for_selector(self.img_element_selector)

                image_base64 = await page.evaluate(
                    DOWNLOAD_PICTURE_JAVASCRIPT.format(img_element_selector=self.img_element_selector)
                )

                if image_base64:
                    image = decode_image(image_base64)
                else:
                    images = await self.gen_image(model="dall-e-3", prompt=search_term)
                    image = images[0]

            except Exception:
                images = await self.gen_image(model="dall-e-3", prompt=search_term)
                image = images[0]

            save_dir = os.path.dirname(image_save_path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            image.save(image_save_path)

            if "public" in image_save_path:
                image_save_path = image_save_path.split("public")[-1]

            return image_save_path

        except Exception as e:
            raise Exception(f"Failed to get/save image: {str(e)}")

        finally:
            # Clean up resources
            if page:
                await page.close()
            if browser_ctx:
                await browser_ctx.close()
