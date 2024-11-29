from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from metagpt.const import METAGPT_ROOT, REACT_TEMPLATE_PATH
from metagpt.llm import LLM
from metagpt.logs import logger
from metagpt.prompts.di.template import (
    GENERAL_WEB_APP_TEMPLATE,
    GENERATE_TEMPLATE_CONFIG_PROMPT,
    read_file,
)
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.async_helper import run_coroutine_sync
from metagpt.utils.common import OutputParser, awrite, log_time


class TemplateRAGObject(BaseModel):
    """Template object class implementing the RAGObject interface"""

    content: str = Field(description="Template content")
    metadata: dict = Field(description="Metadata")

    def rag_key(self) -> str:
        """Return key content used for RAG retrieval"""
        return self.content

    def rag_meta(self) -> dict:
        """Return metadata"""
        return self.metadata


class TemplateInfo(BaseModel):
    """Template information data category"""

    # style: TemplateStyle
    style: str = Field(description="Template style")
    scene: str = Field(description="Template Scene")
    template_path: Path = Field(description="Template path")
    description: str = Field(description="Template description")
    required_fields: List[str] = Field(description="Required field list")
    required_files: List[str] = Field(description="Required file list")
    lang: str = Field(description="Template language")
    framework: str = Field(description="Template framework")


@register_tool(
    tags=["template", "search"],
    include_functions=["search"],
)
class SearchTemplate(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    templates: Dict[str, TemplateInfo] = Field(default_factory=dict)
    template_path: Path = Field(default=Path(METAGPT_ROOT) / "template")
    template_scenes: List[str] = Field(
        default=[
            "personal_business_card_template",
            "content_building_tool_template",
            "personal_demonstration_template",
            "default_web_project",
            "default_python_project",
        ]
    )
    llm: Optional[LLM] = Field(default=None, exclude=True)
    template_version: str = Field(default="1.0.0")
    deployment_config: Dict[str, Any] = Field(default_factory=dict)
    output_dir: Path = Field(default=Path(METAGPT_ROOT) / "workspace" / "template")

    rag_top_k: int = Field(default=5, description="RAG top k")

    _engine: Any = PrivateAttr(default=None)
    _initialized: bool = PrivateAttr(default=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm = kwargs.get("llm") or LLM()
        run_coroutine_sync(self._ensure_initialized())

    @property
    def engine(self) -> "SimpleEngine":
        if self._engine is None:
            from metagpt.rag.engines import SimpleEngine
            from metagpt.rag.schema import FAISSRetrieverConfig, LLMRankerConfig

            logger.info("RAG engine not initialized, initializing...")
            """Initialize the RAG engine and load the template description."""
            if not self.templates:
                logger.warning("No templates found, please check the template path")
                return False

            template_objs = []

            # First, prepare all template documents and objects.
            for template in self.templates.values():
                doc = f"""
                Template Scene: {template.scene}
                Template Description: {template.description}
                Template Language: {template.lang}
                Template Framework: {template.framework}
                Template Style: {template.style}
                """
                template_objs.append(
                    TemplateRAGObject(
                        content=doc,
                        metadata={
                            "style": template.style,
                        },
                    )
                )  # Style is unique

            self.engine = SimpleEngine.from_objs(
                objs=template_objs,
                retriever_configs=[FAISSRetrieverConfig()],
                ranker_configs=[LLMRankerConfig(top_n=self.rag_top_k)],
            )
            return True
        return self._engine

    @engine.setter
    def engine(self, value):
        self._engine = value

    async def set_engine(self, value) -> None:
        """Set a pre-computed RAG engine.

        Args:
            engine: A pre-computed SimpleEngine instance

        Notes:
            1. The engine should contain vector representations for all templates
            2. Calling this method will skip the execution of _init_rag_engine
        """

        self._engine = value
        logger.info("Successfully set pre-computed RAG engine")

    async def set_templates(self, templates: Dict[str, TemplateInfo]) -> None:
        """Set the templates dictionary."""
        self.templates = templates
        logger.info(f"Templates set: {len(self.templates)}")

    @log_time
    async def _ensure_initialized(self):
        """Ensure that the template and RAG engine have been initialized."""
        if not self._initialized:
            init_tempalte_flag, init_rag_flag = False, False
            if not self.templates:
                init_tempalte_flag = await self._init_templates()
            if self.engine is None and init_tempalte_flag:
                init_rag_flag = True
            self._initialized = init_tempalte_flag and init_rag_flag

    def _get_template_structure(self, template: Path) -> str:
        """Get template directory structure"""
        result = subprocess.run(["tree", template], capture_output=True, shell=True, text=True)
        return result.stdout

    async def _parse_template_config(self, template_dir: Path) -> Optional[TemplateInfo]:
        """Parse the configuration files in the template directory; if the configuration
        does not exist, generate it using LLM."""
        config_path = template_dir / "template_config.json"
        style = template_dir.name

        # Try to read the existing configuration.
        if config_path.exists():
            template_info = await self._read_existing_config(config_path)
            if template_info:
                return template_info

        # Generate new configuration
        return await self._generate_config(template_dir, style, config_path)

    async def _read_existing_config(self, config_path: Path) -> Optional[TemplateInfo]:
        """Read and verify the existing configuration file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return self._validate_config(config, config_path)
        except Exception as e:
            logger.error(f"Failed to parse the existing configuration file:{str(e)}")
            return None

    async def _generate_config(self, template_dir: Path, style: str, config_path: Path) -> Optional[TemplateInfo]:
        """Generate new configurations through LLM"""
        dir_structure = self._get_template_structure(template_dir)
        readme_content = ""
        for file in template_dir.iterdir():
            if file.name.lower() == "readme.md":
                readme_content = read_file(file).content
                break

        # If no readme found, log warning but continue
        if not readme_content:
            logger.warning(f"No README file found in {template_dir}")
        logger.info(style.strip())
        prompt = GENERATE_TEMPLATE_CONFIG_PROMPT.format(dir_structure=dir_structure, readme_content=readme_content)
        retry_times = 3
        success = False
        for _ in range(retry_times):
            try:
                result = await self.llm.aask(prompt)
                config = OutputParser.parse_code(result, "json")
                config = json.loads(config)
                if config:
                    success = True
                    break
            except Exception as e:
                logger.error(f"Failed to generate template configuration: {str(e)}; retry times: {retry_times - _}")

        if not success:
            raise Exception("Failed to generate template configuration")

        config[
            "description"
        ] = f"{config['description']} The following information is project's README file content: {readme_content}"
        config["style"] = style.strip()
        # Update the Template Scene
        config["scene"] = config_path.parent.parent.name

        template_info = self._validate_config(config, config_path)
        if template_info:
            await awrite(config_path, json.dumps(config, indent=2, ensure_ascii=False))
            logger.info(f"The template configuration has been generated and saved.: {config_path}")
            return template_info

    def _validate_config(self, config: dict, config_path: Path) -> Optional[TemplateInfo]:
        """Validate the configuration and create a TemplateInfo object."""
        required_config_fields = {"style", "description", "required_fields", "required_files", "lang", "framework"}
        if not all(field in config for field in required_config_fields):
            logger.warning(f"The template configuration file is missing necessary fields: {config_path}")
            return None
        else:
            return TemplateInfo(
                style=config["style"],
                scene=config["scene"],
                template_path=config_path.parent,
                description=config["description"],
                required_fields=config["required_fields"],
                required_files=config["required_files"],
                lang=config["lang"],
                framework=config["framework"],
            )

    async def _init_templates(self) -> bool:
        """Load all templates asynchronously from the template directory."""
        if not self.template_path.exists():
            logger.warning(f"The template base directory does not exist: {self.template_path}")
            return False

        # Get all template directories
        template_type_dirs = [d for d in self.template_path.iterdir() if d.is_dir() and d.name in self.template_scenes]
        template_dirs = [d for dirs in template_type_dirs for d in dirs.iterdir() if d.is_dir()]

        # Use asyncio.gather to concurrently process all templates.
        template_infos = await asyncio.gather(
            *[self._parse_template_config(template_dir) for template_dir in template_dirs]
        )

        # Filter out None values and update the template dictionary
        for idx, template_info in enumerate(template_infos):
            if template_info:
                self.templates[template_info.style] = template_info
                logger.info(f"Template loaded successfully:{template_info.style}")
        return True

    @log_time
    async def search(self, requirement: str) -> Optional[Tuple[TemplateInfo, str]]:
        """Search for matching template and extract user information.

        Args:
            requirement: User's requirement text for template search.

        Returns:
            TemplateInfo if a matching template is found, None otherwise.

        Raises:
            Exception: If template search process fails.
        """

        logger.info("Start searching for templates")
        requirement = f"Please search for the most suitable template based on the following requirements: {requirement}\n\nNote: DON'T select completely irrelevant templates;"
        result = await self.engine.aretrieve(requirement)
        if not result:
            logger.warning("No matching template found")
            return None, ""
        template_name, extra_user_info = await self.select_from_candidates(result)
        if template_name is None:
            return None, ""
        template = self.templates.get(template_name)
        # logger.info(f"Selected template: {template.style}")
        return template, extra_user_info

    async def select_from_candidates(self, result: List[Any]) -> Optional[Tuple[str, str]]:
        """Use RAG to select the most matching template."""

        # Take the top k templates with the highest scores from the results list.
        top_k_score_node = result[-self.rag_top_k :]
        selected_template_styles = [node.metadata["obj"].metadata["style"] for node in top_k_score_node]
        logger.info(f"Selected templates: {selected_template_styles}")
        return selected_template_styles[0], ""

    # async def extract_user_info(self, )

    async def copy_template(
        self, template_path: str = REACT_TEMPLATE_PATH, template_style: str = "react_template"
    ) -> Path:
        """Copy the template to the target location."""
        if not template_path.exists():
            raise FileNotFoundError(f"Template path {template_path} does not exist")

        target_dir = self.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(template_path, target_dir, dirs_exist_ok=True)
        logger.info(f"Template copied: {template_style}")
        return target_dir

    async def __aenter__(self):
        """Initialize templates and RAG engine when entering context"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass

    @log_time
    async def reload_templates(self) -> None:
        """Reload all templates, support hot update"""
        try:
            # Clear existing template
            self.templates.clear()
            # Reinitialize template
            await self._init_templates()

            logger.info(f"Templates reloaded: {len(self.templates)}")
        except Exception as e:
            logger.error(f"Error reloading templates: {str(e)}")

    async def update_search_template_tool(self, **kwargs) -> bool:
        """Updates SearchTemplate with some user defined information

        Args:
            **kwargs: User defined information

        Returns:
            bool: True if update succeeds, False otherwise.

        Raises:
            IOError: If file reading or writing operations fail.
            Exception: For any other unexpected errors.
        """
        try:
            # update rag top_k, check 'rag_top_k' where in kwargs
            if "rag_top_k" in kwargs:
                rag_top_k = kwargs.get("rag_top_k")
                if isinstance(rag_top_k, int) and rag_top_k > 0:
                    if hasattr(self.template_tool, "_engine"):
                        self.rag_top_k = rag_top_k
                        logger.info(f"Updated RAG top_k to {rag_top_k}")
                else:
                    logger.warning(f"Invalid rag_top_k value: {rag_top_k}")

            return True

        except Exception as e:
            logger.error(f"Error applying user info: {str(e)}")
            return False

    def get_required_fields(self) -> List[str]:
        """Get all required fields for the template"""
        return list(set([field for template in self.templates.values() for field in template.required_fields]))

    async def get_template_info(self, template_info: TemplateInfo = None) -> str:
        """Get the template information for the given template style"""
        if template_info is None:
            return ""
        else:
            template_structure = self._get_template_structure(template_info.template_path)
            required_file_instruction = (
                f"The following files are required to be known: {', '.join(template_info.required_files)}"
            )
            required_field_instruction = (
                f"The following fields are could be modified: {', '.join(template_info.required_fields)}"
            )
            file_content = ""
            for required_file in template_info.required_files:
                file_content = f"{file_content}\n{required_file}:\n{read_file(template_info.template_path / required_file).content}\n\n"
            return GENERAL_WEB_APP_TEMPLATE.format(
                TEMPLATE_NAME=template_info.scene,
                TEMPLATE_DESCRIPTION=template_info.description,
                TEMPLATE_STRUCTURE=template_structure,
                TEMPLATE_PATH=template_info.template_path,
                REQUIRED_FILES_INSTRUCTION=required_file_instruction,
                REQUIRED_FIELDS_INSTRUCTION=required_field_instruction,
                FILE_CONTENT=file_content,
                TEMPLATE_LANG=template_info.lang,
                TEMPLATE_FRAMEWORK=template_info.framework,
            )
