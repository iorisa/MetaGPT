from uuid import uuid4

from pydantic import Field

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
