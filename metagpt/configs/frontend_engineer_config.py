from pydantic import Field

from metagpt.utils.yaml_model import YamlModel


class FrontendEngineerConfig(YamlModel):
    enable_search_template: bool = Field(default=True, description="Whether to enable search template.")
    templates_path: str = Field(
        default="template/personal_business_card_templates", description="The path to the templates."
    )
