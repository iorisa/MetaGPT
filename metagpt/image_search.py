from typing import Optional

from pydantic import BaseModel


class ImageSearchConfig(BaseModel):
    api_type: str = ""
    api_key: str = ""
    api_base: Optional[str] = None
