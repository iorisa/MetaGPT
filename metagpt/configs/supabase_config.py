import re
from uuid import uuid4

from pydantic import Field, model_validator

from metagpt.logs import logger
from metagpt.utils.yaml_model import YamlModel


class SupabaseConfig(YamlModel):
    enable: bool = Field(default=False, description="Whether to use Supabase as the backend service.")
    project_url: str = Field(default=None, description="The endpoint URL for connecting to specific Supabase project.")
    project_key: str = Field(default=None, description="The anon/public key used for client API authentication.")
    project_ref: str = Field(default=None, description="The unique reference ID of your Supabase project.")
    access_token: str = Field(default=None, description="The service role API key for Supabase management API.")
    management_base_url: str = Field(
        default="https://api.supabase.com/v1", description="The base URL for Supabase management API endpoints."
    )
    session_id: str = Field(
        default_factory=lambda: uuid4().hex[:5],
        description="A unique session identifier generated for each chat. Used for creating isolated database tables.",
    )

    @model_validator(mode="after")
    def initialize(self):
        if not self.enable:
            return self

        self.project_ref = self._extract_project_ref()

        return self

    def _extract_project_ref(self) -> str:
        # extract project_ref from project_url, e.g. https://mcpkxegjwqjovrmegysk.supabase.co -> mcpkxegjwqjovrmegysk
        match = re.search(r"//([^\.]+)\.", self.project_url)

        if match:
            return match.group(1)

        logger.warning(f"Failed to extract project_ref from project_url: {self.project_url}")
        return ""
