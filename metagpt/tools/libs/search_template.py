from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import subprocess

import asyncio

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from metagpt.llm import LLM
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import awrite, log_time, OutputParser
from metagpt.prompts.di.template import read_file

from metagpt.rag.engines import SimpleEngine
from metagpt.rag.schema import FAISSRetrieverConfig, BM25RetrieverConfig, LLMRankerConfig, ColbertRerankConfig
from metagpt.const import METAGPT_ROOT
from metagpt.prompts.di.template import VUE_APP_TEMPLATE

from metagpt.logs import logger


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
    template_path: Path = Field(description="Template path")
    description: str = Field(description="Template description")
    required_fields: List[str] = Field(description="Required field list")


@register_tool(
    tags=["template", "search"],
    include_functions=[
        "search"
    ],
)
class SearchTemplate(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    templates: Dict[str, TemplateInfo] = Field(default_factory=dict)
    llm: Optional[LLM] = Field(default=None)
    template_version: str = Field(default="1.0.0")
    deployment_config: Dict[str, Any] = Field(default_factory=dict)
    output_dir: Path = Field(default=Path(METAGPT_ROOT) / "workspace" / "template")

    rag_top_k: int = Field(default=3, description="RAG top k")

    _engine: Optional[SimpleEngine] = PrivateAttr(default=None)
    _initialized: bool = PrivateAttr(default=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm = kwargs.get('llm') or LLM()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Try to get the current running loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Instead of deferring, create a task in the running loop
                loop.create_task(self._ensure_initialized())
                return
        except RuntimeError:
            # If no loop is running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(self._ensure_initialized())

    async def _init_rag_engine(self):
        """Initialize the RAG engine and load the template description."""
        template_objs = []

        # First, prepare all template documents and objects.
        for template in self.templates.values():
            doc = f"""
            Template Style: {template.style}
            Description: {template.description}
            Required Fields: {', '.join(template.required_fields)}
            
            Template Path:
            {template.template_path}
            """
            template_objs.append(
                TemplateRAGObject(
                    content=doc,
                    metadata={
                        "type": "Business Card Template",
                        "style": template.style
                    }
                )
            )

        # Wrap synchronous operations as asynchronous using asyncio.to_thread.
        self._engine = await asyncio.to_thread(
            SimpleEngine.from_objs,
            objs=template_objs,
            retriever_configs=[
                FAISSRetrieverConfig(),
                BM25RetrieverConfig()
            ],
            ranker_configs=[LLMRankerConfig()],
        )

    async def set_engine(self, engine: SimpleEngine) -> None:
        """Set a pre-computed RAG engine.

        Args:
            engine: A pre-computed SimpleEngine instance

        Notes:
            1. The engine should contain vector representations for all templates
            2. Calling this method will skip the execution of _init_rag_engine
        """
        if not isinstance(engine, SimpleEngine):
            logger.error("Provided engine is not of type SimpleEngine")
            return
            
        self._engine = engine
        logger.info("Successfully set pre-computed RAG engine")

    @log_time
    async def _ensure_initialized(self):
        """Ensure that the template and RAG engine have been initialized."""
        if not self._initialized:
            await self._init_templates()
            await self._init_rag_engine()
            self._initialized = True


    def _get_template_structure(self, template: Path) -> str:
        """Get template directory structure"""
        result = subprocess.run(
            ['tree', template],
            capture_output=True,
            text=True
        )
        return result.stdout

    async def _parse_template_config(self, template_dir: Path) -> Optional[TemplateInfo]:
        """Parse the configuration files in the template directory; if the configuration does not exist, generate it using LLM."""
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
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return self._validate_config(config, config_path)
        except Exception as e:
            logger.error(f"Failed to parse the existing configuration file:{str(e)}")
            return None

    async def _generate_config(self, template_dir: Path, style: str, config_path: Path) -> Optional[TemplateInfo]:
        """Generate new configurations through LLM"""
        dir_structure = self._get_template_structure(template_dir)
        readme_content = read_file(template_dir / "README.md")

        prompt = f"""Please generate a template configuration based on the following template directory information:
        Directory structure:
        {dir_structure}

        README content:
        {readme_content}

        Please generate a configuration in JSON format that includes the following fields:
        1. description: Template description
        2. required_fields: List of required fields

        Please ensure that the generated configuration is in valid JSON format.
        ```json
        {{
            "style": "{style}",
            "description": "the description of template",
            "required_fields": ["name", "job", "email", "phone", "description", "mbti"]
        }}
        ```
        """
        result = await self.llm.aask(prompt)
        result = OutputParser.parse_code(result, "json")
        config = json.loads(result)

        template_info = self._validate_config(config, config_path)
        if template_info:
            await awrite(config_path, json.dumps(config, indent=2, ensure_ascii=False))
            logger.info(f"The template configuration has been generated and saved.: {config_path}")
            return template_info

    def _validate_config(self, config: dict, config_path: Path) -> Optional[TemplateInfo]:
        """Validate the configuration and create a TemplateInfo object."""
        required_config_fields = {'style', 'description', 'required_fields'}
        if not all(field in config for field in required_config_fields):
            logger.warning(f"The template configuration file is missing necessary fields: {config_path}")
            return None
        else:
            return TemplateInfo(
                style=config['style'],
                template_path=config_path.parent,
                description=config['description'],
                required_fields=config['required_fields']
            )

    async def _init_templates(self) -> None:
        """Load all templates asynchronously from the template directory."""
        base_path = METAGPT_ROOT / "template" / "personal_business_card_templates"
        if not base_path.exists():
            logger.warning(f"The template base directory does not exist: {base_path}")
            return

        # Get all template directories
        template_dirs = [d for d in base_path.iterdir() if d.is_dir()]

        # Use asyncio.gather to concurrently process all templates.
        template_infos = await asyncio.gather(
            *[self._parse_template_config(template_dir) for template_dir in template_dirs]
        )

        # Filter out None values and update the template dictionary
        for template_info in template_infos:
            if template_info:
                self.templates[template_info.style] = template_info
                logger.info(f"Template loaded successfully:{template_info.style}")

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
        result = await self._engine.aretrieve(requirement)
        if not result:
            logger.warning('No matching template found')
            return None, ""
        template_name, extra_user_info  = await self.select_from_candidates(result)
        template = self.templates.get(template_name)
        logger.info(f'Selected template: {template.style}')
        return template, extra_user_info

    async def select_from_candidates(self, result: List[Any]) -> Optional[Tuple[str, str]]:
        """Use RAG to select the most matching template."""

        # Take the top k templates with the highest scores from the results list. 
        top_k_score_node = result[-self.rag_top_k:]
        # template_infos = [self.templates.get(node.metadata['obj'].metadata['style']) for node in top_k_score_node]
        selected_template_names = [node.metadata['obj'].metadata['style'] for node in top_k_score_node]
        return selected_template_names[0], ""
    
    # async def extract_user_info(self, )

    async def copy_template(self, template: TemplateInfo) -> Path:
        """Copy the template to the target location."""
        if not template.template_path.exists():
            raise FileNotFoundError(f"Template path {template.template_path} does not exist")

        target_dir = self.output_dir

        shutil.copytree(template.template_path, target_dir, dirs_exist_ok=True)
        logger.info(f"Template copied: {template.style} -> {target_dir}")
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
            if 'rag_top_k' in kwargs:
                rag_top_k = kwargs.get('rag_top_k')
                if isinstance(rag_top_k, int) and rag_top_k > 0:
                    if hasattr(self.template_tool, '_engine'):
                        self.rag_top_k = rag_top_k
                        logger.info(f"Updated RAG top_k to {rag_top_k}")
                else:
                    logger.warning(f"Invalid rag_top_k value: {rag_top_k}")

            return True

        except Exception as e:
            logger.error(f'Error applying user info: {str(e)}')
            return False

    def get_required_fields(self) -> List[str]:
        """Get all required fields for the template"""
        return list(set([field for template in self.templates.values() for field in template.required_fields]))


    async def get_template_info(self, template_info: TemplateInfo = None) -> str:
        """Get the template information for the given template style"""
        if template_info is None:
            return ""
        else:
            return VUE_APP_TEMPLATE.format(
                VUE_APP_TEMPLATE_DESCRIPTION=template_info.description,
                TEMPLATE_PATH=f"{METAGPT_ROOT}/workspace/template",
                TEMPLATE_STRUCTURE=self._get_template_structure(template_info.template_path),
                INDEX_CONTENT=read_file(template_info.template_path / "index.html"),
                MAIN_CONTENT=read_file(template_info.template_path / "src" / "main.js"),
                APP_CONTENT=read_file(template_info.template_path / "src" / "App.vue"),
                INDEX_CSS_CONTENT=read_file(template_info.template_path / "src" / "style.css"),
                CONFIG_CONTENT=read_file(template_info.template_path / "vite.config.js")
            )
            
        

