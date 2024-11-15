from __future__ import annotations

import json
import re
import shutil
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
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
    """实现 RAGObject 接口的模板对象类"""
    content: str = Field(description="模板内容")
    metadata: dict = Field(description="元数据")

    def rag_key(self) -> str:
        """返回用于 RAG 检索的关键内容"""
        return self.content

    def rag_meta(self) -> dict:
        """返回元数据"""
        return self.metadata


class TemplateInfo(BaseModel):
    """模板信息数据类"""
    # style: TemplateStyle
    style: str = Field(description="模板风格") 
    template_path: Path = Field(description="模板路径")
    preview_image: str = Field(description="预览图片路径")
    description: str = Field(description="模板描述")
    required_fields: List[str] = Field(description="必需的字段列表")


def read_file_by_path(file_path: Path) -> str:
    """读取文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""

def monitor_performance(func: Callable) -> Callable:
        """性能监控装饰器"""

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
    tags=["template", "search", "update_user_info"],
    include_functions=[
        "search",
        "get_template",
        "get_all_templates",
        "register_template",
        "direct_select",
        "update_user_info"
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
        # 添加一个标志位来追踪初始化状态
        self._initialized = False

    @monitor_performance
    async def _init_rag_engine(self):
        """初始化 RAG 引擎并加载模板描述"""
        template_objs = []

        # 首先准备所有模板文档和对象
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

        # 使用 asyncio.to_thread 将同步操作包装为异步
        self._engine = await asyncio.to_thread(
            SimpleEngine.from_objs,
            objs=template_objs,
            retriever_configs=[
                FAISSRetrieverConfig(dimensions=1536),
                BM25RetrieverConfig()
            ]
        )
        

    async def _ensure_initialized(self):
        """确保模板和RAG引擎已经初始化"""
        if not self._initialized:
            await self._init_templates()
            await self._init_rag_engine()  # 修改为await调用
            self._initialized = True

    def _get_template_structure(self, template: Path) -> str:
        """获取模板目录结构"""
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
        """解析模板目录下的配置文件,如果配置不存在则通过 LLM 生成"""
        config_path = template_dir / "template_config.json"
        style = template_dir.name
        
        # 尝试读取现有配置
        if config_path.exists():
            template_info = await self._read_existing_config(config_path)
            if template_info:
                return template_info
        
        # 生成新配置
        return await self._generate_config(template_dir, style, config_path)

    async def _read_existing_config(self, config_path: Path) -> Optional[TemplateInfo]:
        """读取并验证现有的配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return self._validate_config(config, config_path)
        except Exception as e:
            logger.error(f"解析现有配置文件失败: {str(e)}")
            return None

    async def _generate_config(self, template_dir: Path, style: str, config_path: Path) -> Optional[TemplateInfo]:
        """通过 LLM 生成新的配置"""
        try:
            dir_structure = self._get_template_structure(template_dir)
            readme_content = read_file_by_path(template_dir / "README.md")
            
            prompt = f"""请根据以下模板目录信息生成一个模板配置:

目录结构:
{dir_structure}

README 内容:
{readme_content}

请生成一个 JSON 格式的配置，包含以下字段:
1. preview_image: 预览图片路径
2. description: 模板描述
3. required_fields: 必需的字段列表

请确保生成的是合法的 JSON 格式。
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
                logger.info(f"已生成并保存模板配置: {config_path}")
                return template_info
            
        except Exception as e:
            logger.error(f"通过 LLM 生成配置失败: {str(e)}")
            return None

    def _validate_config(self, config: dict, config_path: Path) -> Optional[TemplateInfo]:
        """验证配置并创建 TemplateInfo 对象"""
        required_config_fields = {'style', 'preview_image', 'description', 'required_fields'}
        if not all(field in config for field in required_config_fields):
            logger.warning(f"模板配置文件缺少必要字段: {config_path}")
            return None
        
        try:
                
            return TemplateInfo(
                style=config['style'],
                template_path=config_path.parent,
                preview_image=config['preview_image'],
                description=config['description'],
                required_fields=config['required_fields']
            )
        except Exception as e:
            logger.error(f"验证配置失败: {str(e)}")
            return None
    
    @monitor_performance
    async def _init_templates(self) -> None:
        """从模板目录异步加载所有模板"""
        base_path = METAGPT_ROOT / "template"
        if not base_path.exists():
            logger.warning(f"模板基础目录不存在: {base_path}")
            return

        # 获取所有模板目录
        template_dirs = [d for d in base_path.iterdir() if d.is_dir()]
        
        # 使用 asyncio.gather 并发处理所有模板
        template_infos = await asyncio.gather(
            *[self._parse_template_config(template_dir) for template_dir in template_dirs]
        )
        
        # 过滤掉 None 值并更新模板字典
        for template_info in template_infos:
            if template_info:
                self.templates[template_info.style] = template_info
                logger.info(f"成功加载模板: {template_info.style}")

    

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
        try:
            # 确保已初始化
            await self._ensure_initialized()

            template = await self._select_template(requirement)
            if not template:
                logger.warning('No matching template found')
                return None

            logger.info(f'Selected template: {template.style}')
            return template

        except Exception as e:
            logger.error(f'Template search failed: {str(e)}')
            logger.error(f'Requirement: {requirement}')
            return None

    def get_template(self, style: str) -> Optional[TemplateInfo]:
        """获取指定风格的模板"""
        return self.templates.get(style, None)

    def get_all_templates(self) -> Dict[str, TemplateInfo]:
        """获取所有模板"""
        return self.templates.copy()

    def register_template(self, template: TemplateInfo) -> None:
        """注册新模板"""
        self.templates[template.style] = template

    async def _select_template(self, requirement: str) -> Optional[TemplateInfo]:
        """Use RAG to select the most matching template."""
        try:
            logger.info("Start searching for templates")
            result = await self._engine.aretrieve(requirement)
            if not result:
                return None

            # Take the template style with the highest score from the results list.
            max_score_node = max(result, key=lambda x: x.score)
            style_name = max_score_node.metadata['obj'].metadata['style']
            
            return self.templates.get(style_name)

        except Exception as e:
            logger.error(f"Error selecting template:{str(e)}")
            return None

    async def copy_template(self, template: TemplateInfo) -> Path:
        """Copy the template to the target location."""
        if not template.template_path.exists():
            raise FileNotFoundError(f"Template path {template.template_path} does not exist")

        target_dir = self.output_dir

        try:
            shutil.copytree(template.template_path, target_dir, dirs_exist_ok=True)
            logger.info(f"Template copied: {template.style} -> {target_dir}")
            return target_dir
        except Exception as e:
            logger.error(f"Failed to copy template: {str(e)}")
            raise IOError(f"Failed to copy template: {str(e)}")

    async def __aenter__(self):
        await self._init_templates()
        self._init_rag_engine()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass

    
    @monitor_performance
    async def reload_templates(self) -> None:
        """重新加载所有模板，支持热更新"""
        try:
            # 清空现有模板
            self.templates.clear()
            # 重新始化模板
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
        """获取所有模板所需字段"""
        return list(set([field for template in self.templates.values() for field in template.required_fields]))

if __name__ == "__main__":
    import asyncio


    async def main():
        async with SearchTemplate() as search_tool:
            requirement = "帮我制作一张个人名片，我是一名产品经理"
            result = await search_tool.search(requirement)

            if result:
                template = result
                print(f"Selected template: {template.style}")
                # print(f"User info: {user_info}")
            else:
                print("No matching template found")


    asyncio.run(main())
