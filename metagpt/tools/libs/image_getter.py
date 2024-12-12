from __future__ import annotations

import asyncio
import os
from io import BytesIO
from pathlib import Path
from typing import Callable

import pixabay_python as pxb
import requests
from PIL import Image
from PIL.ImageFile import ImageFile
from pydantic import BaseModel, ConfigDict, Field

from metagpt.config2 import Config
from metagpt.const import DEFAULT_WORKSPACE_ROOT
from metagpt.logs import logger
from metagpt.provider.base_llm import BaseLLM
from metagpt.provider.openai_api import OpenAILLM
from metagpt.tools.tool_registry import register_tool

llm_config = Config.default().llm


@register_tool(include_functions=["get", "process"])
class ImageGetter(BaseModel):
    """
    A tool to get images.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: pxb.PixabayClient = Field(
        default_factory=lambda: pxb.PixabayClient(apiKey="47578704-13cb6079bb33fc6ef70bd1c63"), exclude=True
    )
    # Add llm field to store instance
    llm: BaseLLM = Field(default_factory=lambda: OpenAILLM(llm_config))

    # Remove gen_image field and replace with property
    @property
    def gen_image(self) -> Callable:
        return self.llm.gen_image

    def _process_save_path(self, image_save_path: str) -> tuple[str, str]:
        project_folder = os.listdir(DEFAULT_WORKSPACE_ROOT)[0]
        if not Path(image_save_path).is_absolute():
            # Check if there is a project folder under the default workspace.
            # FIXME: use a hard rule for now, assume the first folder alphabetically is the project folder.
            save_dir = os.path.dirname(os.path.join(DEFAULT_WORKSPACE_ROOT, project_folder, image_save_path))
        else:
            save_dir = os.path.dirname(image_save_path)
            image_save_path = (
                Path(image_save_path).relative_to(os.path.join(DEFAULT_WORKSPACE_ROOT, project_folder)).__str__()
            )

        return save_dir, image_save_path

    async def _save_image(self, image: Image, image_save_path: str) -> str:
        """Helper method to save image and process path"""
        # Save the image to the given path. Due to agent instability, we need to handle two cases:
        # 1. If the path is relative, consider the project folder structure and save under the project folder.
        # 2. If the path is absolute, save directly to the given path.
        # TODO: Consider better approach to handle the image save path.
        image_file_name = os.path.basename(image_save_path)
        save_dir, image_save_path = self._process_save_path(image_save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
        image.save(os.path.join(save_dir, image_file_name))
        return image_save_path.replace("public", "")

    async def create_image(self, image_description: str) -> Image:
        """Create an image with dall-e-3"""
        images = await self.gen_image(model="dall-e-3", prompt=image_description)
        return images[0]

    def download_image(self, url: str, connect_timeout: int = 20, read_timeout: int = 20) -> ImageFile | None:
        resp = requests.get(url=url, verify=True, timeout=(connect_timeout, read_timeout))
        if resp.status_code == 200:
            # load the image
            image = Image.open(BytesIO(resp.content))
            return image
        else:
            return None

    async def search_image(self, search_term: str) -> ImageFile | None:
        searchResult = self.client.searchImage(q=search_term, perPage=1)
        hitsList = list(searchResult.hits)
        image = self.download_image(hitsList[0].largeImageURL)
        return image

    async def _get_async(self, search_term: str, image_save_path: str, mode: str):
        """Handle the actual image processing asynchronously"""
        try:
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
        except Exception as e:
            # Handle/log error appropriately
            logger.info(f"Error processing image: {e}")

    async def rembg_image(self, image_path: str) -> str:
        try:
            from rembg import remove
        except ImportError:
            raise ImportError("Please install rembg with `pip install rembg`.")

        image = remove(Image.open(image_path))

        return image

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
        asyncio.create_task(self._get_async(search_term, image_save_path, mode))
        _, image_save_path = self._process_save_path(image_save_path)
        return image_save_path.replace("public", "")

    async def process(self, image_path: str, image_save_path: str, mode: str = "rembg") -> str:
        """Process an existing image with various filters.

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
