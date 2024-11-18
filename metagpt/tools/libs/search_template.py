from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from functools import wraps
import time
import asyncio

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from metagpt.llm import LLM
from metagpt.tools.tool_registry import register_tool
from metagpt.utils.common import awrite, aread

from metagpt.rag.engines import SimpleEngine
from metagpt.rag.schema import FAISSRetrieverConfig, BM25RetrieverConfig
from metagpt.const import METAGPT_ROOT

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
    preview_image: str = Field(description="Preview image path")
    description: str = Field(description="Template description")
    required_fields: List[str] = Field(description="Required field list")


def monitor_performance(func: Callable) -> Callable:
    """Performance Monitoring Decorator"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs) -> Any:
        start_time = time.time()
        result = await func(self, *args, **kwargs)
        execution_time = time.time() - start_time

        logger.info(
            f"Action: {func.__name__}, Execution time: {execution_time:.2f}s, Success: {result is not None}")

        return result

    return wrapper


@register_tool(
    tags=["template", "search"],
    include_functions=[
        "search",
        "direct_select",
    ],
)
class SearchTemplate(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    templates: Dict[str, TemplateInfo] = Field(default_factory=dict)
    llm: Optional[LLM] = Field(default=None)
    template_version: str = Field(default="1.0.0")
    deployment_config: Dict[str, Any] = Field(default_factory=dict)
    output_dir: Path = Field(default=Path(METAGPT_ROOT) / "workspace" / "template")

    _engine: Optional[SimpleEngine] = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm = kwargs.get('llm') or LLM()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Add a flag to track the initialization status.
        self._initialized = False

    @monitor_performance
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
                        "type": "template",
                        "style": template.style
                    }
                )
            )

        # Wrap synchronous operations as asynchronous using asyncio.to_thread.
        self._engine = await asyncio.to_thread(
            SimpleEngine.from_objs,
            objs=template_objs,
            retriever_configs=[
                FAISSRetrieverConfig(dimensions=1536),
                BM25RetrieverConfig()
            ]
        )

    async def _ensure_initialized(self):
        """Ensure that the template and RAG engine have been initialized."""
        if not self._initialized:
            await self._init_templates()
            await self._init_rag_engine()
            self._initialized = True

    def _get_template_structure(self, template: Path) -> str:
        """Get template directory structure"""
        try:
            import subprocess
            result = subprocess.run(
                ['tree', template],
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception:
            return ""

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
            logger.error(f"解析现有配置文件失败: {str(e)}")
            return None

    async def _generate_config(self, template_dir: Path, style: str, config_path: Path) -> Optional[TemplateInfo]:
        """Generate new configurations through LLM"""
        dir_structure = self._get_template_structure(template_dir)
        readme_content = await aread(template_dir / "README.md")

        prompt = f"""Please generate a template configuration based on the following template directory information:
        Directory structure:
        {dir_structure}

        README content:
        {readme_content}

        Please generate a configuration in JSON format that includes the following fields:
        1. preview_image: Path to the preview image
        2. description: Template description
        3. required_fields: List of required fields

        Please ensure that the generated configuration is in valid JSON format.
        ```json
        {{
            "style": "{style}",
            "preview_image": "the path of preview image, relative to template root",
            "description": "the description of template",
            "required_fields": ["name", "job", "email", "phone", "description", "mbti"]
        }}
        ```
        """
        result = await self.llm.aask(prompt)
        result = result.replace("```json", "").replace("```", "").strip("\n")
        config = json.loads(result)

        template_info = self._validate_config(config, config_path)
        if template_info:
            await awrite(config_path, json.dumps(config, indent=2, ensure_ascii=False))
            logger.info(f"The template configuration has been generated and saved.: {config_path}")
            return template_info

    def _validate_config(self, config: dict, config_path: Path) -> Optional[TemplateInfo]:
        """Validate the configuration and create a TemplateInfo object."""
        required_config_fields = {'style', 'preview_image', 'description', 'required_fields'}
        if not all(field in config for field in required_config_fields):
            logger.warning(f"The template configuration file is missing necessary fields: {config_path}")
            return None
        else:
            return TemplateInfo(
                style=config['style'],
                template_path=config_path.parent,
                preview_image=config['preview_image'],
                description=config['description'],
                required_fields=config['required_fields']
            )

    @monitor_performance
    async def _init_templates(self) -> None:
        """Load all templates asynchronously from the template directory."""
        base_path = METAGPT_ROOT / "template"
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

    @monitor_performance
    async def search(self, requirement: str) -> Optional[TemplateInfo]:
        """Search for matching template and extract user information.

        Args:
            requirement: User's requirement text for template search.

        Returns:
            TemplateInfo if a matching template is found, None otherwise.

        Raises:
            Exception: If template search process fails.
        """
        # Ensure it is initialized.
        await self._ensure_initialized()

        template = await self._select_template(requirement)
        if not template:
            logger.warning('No matching template found')
            return None

        logger.info(f'Selected template: {template.style}')
        return template

    async def _select_template(self, requirement: str) -> Optional[TemplateInfo]:
        """Use RAG to select the most matching template."""
        logger.info("Start searching for templates")
        result = await self._engine.aretrieve(requirement)
        if not result:
            return None

        # Take the template style with the highest score from the results list.
        max_score_node = max(result, key=lambda x: x.score)
        style_name = max_score_node.metadata['obj'].metadata['style']

        return self.templates.get(style_name)

    async def copy_template(self, template: TemplateInfo) -> Path:
        """Copy the template to the target location."""
        if not template.template_path.exists():
            raise FileNotFoundError(f"Template path {template.template_path} does not exist")

        target_dir = self.output_dir

        shutil.copytree(template.template_path, target_dir, dirs_exist_ok=True)
        logger.info(f"Template copied: {template.style} -> {target_dir}")
        return target_dir

    async def __aenter__(self):
        await self._init_templates()
        self._init_rag_engine()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass

    @monitor_performance
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
        return f"""### Template Intro
            1. This is a template for {template_info.description}
            2. The template is at {METAGPT_ROOT}/workspace/template
            3. Modify index.html, create new jsx files under src if needed, and rewrite src/App.jsx to meet the user's requirements.
            4. Style your elements with Tailwind CSS classes directly in the jsx files.

            ### Template Structure
            {self._get_template_structure(template_info.template_path)}
            
            ### File Content
            #### index.html (Modify the title)
            {await aread(template_info.template_path / "index.html")}

            #### src/main.jsx (You should NOT modify it)
            {await aread(template_info.template_path / "src" / "main.jsx")}

            #### src/App.jsx (to be modified)
            {await aread(template_info.template_path / "src" / "App.jsx")}

            #### src/index.css (You should NOT modify it)
            {await aread(template_info.template_path / "src" / "index.css")}

            #### vite.config.js (only modify it if extra config is absolutely necessary)
            {await aread(template_info.template_path / "vite.config.js")}

        """

