from __future__ import annotations

import os
from abc import abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import aiohttp
from PIL import Image
from PIL.ImageFile import ImageFile
from playwright.async_api import Browser as Browser_
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class BaseImageProvider(BaseModel):
    """Abstract base class for image getter tools."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    # Common fields
    llm: BaseLLM = Field(default_factory=lambda: OpenAILLM(Config.default().llm))
    working_dir: Path = Field(default=DEFAULT_WORKSPACE_ROOT, exclude=True)
    project_folder: Path = Field(default=None, exclude=True)

    @property
    def gen_image(self) -> Callable:
        return self.llm.gen_image

    def _process_save_path(self, image_save_path: str) -> tuple[str, str]:
        """Process and validate the save path."""
        if self.project_folder is None:
            # Try to auto-detect project folder by finding the first non-hidden directory
            # in working_dir. This has limitations:
            # - Only uses first matching directory found
            # - No validation that directory is actually a project
            # - Will fail if no valid directories exist
            # - Assumes project directories never start with "."
            for path in os.listdir(self.working_dir):
                if os.path.isdir(os.path.join(self.working_dir, path)) and not path.startswith("."):
                    self.project_folder = os.path.join(self.working_dir, path)
                    break
        if not Path(image_save_path).is_absolute():
            save_dir = os.path.dirname(os.path.join(self.project_folder, image_save_path))
        else:
            save_dir = os.path.dirname(image_save_path)
            image_save_path = Path(image_save_path).relative_to(self.project_folder).__str__()
        return save_dir, image_save_path

    async def _save_image(self, image: Image, image_save_path: str) -> str:
        """Save image and return processed path."""
        image_file_name = os.path.basename(image_save_path)
        save_dir, image_save_path = self._process_save_path(image_save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
        image.save(os.path.join(save_dir, image_file_name))
        return image_save_path.replace("public", "")

    async def create_image(self, image_description: str) -> Image:
        """Create an image with dall-e-3."""
        images = await self.gen_image(model="dall-e-3", prompt=image_description)
        return images[0]

    @abstractmethod
    async def search_image(self, search_term: str) -> ImageFile | None:
        """Search for an image. Must be implemented by subclasses."""
        raise NotImplementedError

    async def _get_async(self, search_term: str, image_save_path: str, mode: str):
        """Handle image retrieval and saving."""
        if mode == "search":
            try:
                image = await self.search_image(search_term)
            except Exception:
                image = await self.create_image(search_term)
        elif mode == "create":
            image = await self.create_image(search_term)
        else:
            raise ValueError(f"Invalid mode: {mode}")

        await self._save_image(image, image_save_path)

    async def get(self, search_term: str, image_save_path: str, mode="search") -> str:
        """Get an image either by searching online or generating with AI.

        Args:
            search_term (str): Search query or image description. Must be in English.
            image_save_path (str): Path where the image will be saved. Must be a absolute path to the public folder.
            mode (str): How to obtain the image:
                - "search": Search online (falls back to AI generation if search fails)
                - "create": Generate using DALL-E 3

        Returns:
            str: Relative path to the saved image (public/ prefix removed)

        Raises:
            ValueError: If an invalid mode is specified
            RuntimeError: If image retrieval fails
        """
        await self._get_async(search_term, image_save_path, mode)
        _, image_save_path = self._process_save_path(image_save_path)
        return image_save_path.replace("public", "")

    async def rembg_image(self, image_path: str) -> Image:
        """Remove image background."""
        try:
            from rembg import remove
        except ImportError:
            raise ImportError("Please install rembg with `pip install rembg`.")
        return remove(Image.open(image_path))

    async def process(self, image_path: str, image_save_path: str, mode: str = "rembg") -> str:
        """Process an existing image with filters.

        Args:
            image_path (str): Path to the source image
            image_save_path (str): Path where processed image will be saved. Must be a absolute path to the public folder.
            mode (str): Processing mode to apply:
                - "rembg": Remove image background

        Returns:
            str: Relative path to the processed image (public/ prefix removed)

        Raises:
            ValueError: If an invalid mode is specified
            ImportError: If required processing libraries are not installed
        """
        if mode == "rembg":
            image = await self.rembg_image(image_path)
        else:
            raise ValueError(f"Invalid mode: {mode}")
        image_save_path = await self._save_image(image, image_save_path)
        return image_save_path

    async def download_image(self, url: str, connect_timeout: int = 20, read_timeout: int = 20) -> ImageFile | None:
        """Download image from URL."""
        async with aiohttp.ClientSession() as client:
            timeout = aiohttp.ClientTimeout(connect=connect_timeout, sock_read=read_timeout)
            async with client.get(url=url, verify_ssl=True, timeout=timeout) as resp:
                if resp.status == 200:
                    return Image.open(BytesIO(await resp.read()))


class PixabayAPI(BaseImageProvider):
    """Image getter using Pixabay."""

    # client: pxb.PixabayClient = Field(
    #     default_factory=lambda: pxb.PixabayClient(apiKey=Config.default().pixabay_api_key), exclude=True
    # )
    client: Any = Field(default=None, exclude=True, description="Pixabay API client")

    @model_validator(mode="after")
    def _ensure_client(self) -> "PixabayAPI":
        """Ensure that the Pixabay API client is initialized."""
        if self.client is None:
            try:
                import pixabay_python as pxb

                self.client = pxb.PixabayClient(apiKey=Config.default().pixabay_api_key)
            except ImportError:
                raise ImportError("Please install pixabay_python with `pip install pixabay_python`.")
        return self

    async def search_image(self, search_term: str) -> ImageFile | None:
        """Search for image using Pixabay API."""
        searchResult = self.client.searchImage(q=search_term, perPage=1)
        hitsList = list(searchResult.hits)
        return await self.download_image(hitsList[0].largeImageURL)


class UnsplashWeb(BaseImageProvider):
    """Image getter using Unsplash."""

    playwright: Optional[Playwright] = Field(default=None, exclude=True)
    browser_instance: Optional[Browser_] = Field(default=None, exclude=True)
    browser_ctx: Optional[BrowserContext] = Field(default=None, exclude=True)
    page: Optional[Page] = Field(default=None, exclude=True)
    headless: bool = Field(default=True)
    proxy: Optional[dict] = Field(default_factory=get_proxy_from_env)
    reporter: BrowserReporter = Field(default_factory=BrowserReporter)
    url: str = "https://unsplash.com/s/photos/{search_term}/"
    img_element_selector: str = ".zNNw1 > div > img:nth-of-type(2)"

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

    async def start(self) -> None:
        """Starts Playwright and launches a browser"""
        if self.playwright is None:
            self.playwright = playwright = await async_playwright().start()
            browser = self.browser_instance = await playwright.chromium.launch(headless=self.headless, proxy=self.proxy)
            browser_ctx = self.browser_ctx = await browser.new_context()
            self.page = await browser_ctx.new_page()

    async def _retry_goto(self, page: Page, url: str, max_retries: int = 3, timeout: int = 20000):
        """Helper method for retrying page navigation"""
        for attempt in range(max_retries):
            try:
                await page.goto(url, timeout=timeout)
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Failed to navigate to {url} after {max_retries} attempts") from e

    async def search_image(self, search_term: str) -> ImageFile | None:
        """Search for image using Unsplash website."""
        if not self.playwright:
            await self.start()

        async with await self.browser_instance.new_context() as browser_ctx:
            async with await browser_ctx.new_page() as page:
                url = self.url.format(search_term=search_term.replace(" ", "%20"))
                await self._retry_goto(page, url)
                await page.wait_for_selector(self.img_element_selector)

                image_base64 = await page.evaluate(
                    DOWNLOAD_PICTURE_JAVASCRIPT.format(img_element_selector=self.img_element_selector)
                )

                if image_base64:
                    image = decode_image(image_base64)
                    return image
                return None


class UnsplashApi(BaseImageProvider):
    """Image getter using Unsplash API."""

    api_key: str
    api_base: str = "https://api.unsplash.com"
    headers: Dict[str, str] = Field(default_factory=dict)

    async def search_image(self, search_term: str) -> ImageFile | None:
        """Search for image using Unsplash API."""
        params = {"query": search_term, "per_page": 1, "orientation": "landscape"}
        headers = {"Authorization": f"Client-ID {self.api_key}"}
        headers.update(self.headers)
        async with aiohttp.ClientSession() as client:
            async with client.get(f"{self.api_base}/search/photos", headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if results := data.get("results"):
                        # Get regular sized image URL
                        image_url = results[0]["urls"]["regular"]
                        return await self.download_image(image_url)


@register_tool(include_functions=["get", "process"])
class ImageGetter(BaseModel):
    """
    A tool to get/create/process images.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    image_provider: BaseImageProvider = Field(
        default=None,
        exclude=True,
        description="The image getter to use. Choose from Pixabay, Unsplash, or Unsplash API. Defaults to Unsplash API.",
    )

    @model_validator(mode="after")
    def set_provider(self) -> "ImageGetter":
        if self.image_provider is None:
            image_search_config = Config.default().image_search
            api_type = image_search_config.api_type
            params = image_search_config.model_dump(exclude=("api_type",), exclude_none=True, exclude_defaults=True)
            if api_type == "unsplash":
                self.image_provider = UnsplashApi(**params)
            elif api_type == "pixabay":
                self.image_provider = PixabayAPI(**params)
            else:
                raise ValueError("No image provider configured. Please set either unsplash_api_key or pixabay_api_key.")
        return self

    @classmethod
    def is_available(cls) -> bool:
        config = Config.default()
        return (
            config.image_search.api_type == "unsplash"
            and config.image_search.api_key
            or config.image_search == "pixabay"
        )

    async def get(self, search_term: str, image_save_path: str, mode="search") -> str:
        """Get an image either by searching online or generating with AI.

        Args:
            search_term (str): Search query or image description. Must be in English.
            image_save_path (str): Path where the image will be saved. Must be a absolute path to the public folder.
            mode (str): How to obtain the image:
                - "search": Search online (falls back to AI generation if search fails)
                - "create": Generate using DALL-E 3

        Returns:
            str: Relative path to the saved image (public/ prefix removed)

        Raises:
            ValueError: If an invalid mode is specified
            RuntimeError: If image retrieval fails
        """
        return await self.image_provider.get(search_term, image_save_path, mode)

    async def process(self, image_path: str, image_save_path: str, mode: str = "rembg") -> str:
        """Process an existing image with filters.

        Args:
            image_path (str): Path to the source image
            image_save_path (str): Path where processed image will be saved. Must be a absolute path to the public folder.
            mode (str): Processing mode to apply:
                - "rembg": Remove image background

        Returns:
            str: Relative path to the processed image (public/ prefix removed)
        """
        return await self.image_provider.process(image_path, image_save_path, mode)
