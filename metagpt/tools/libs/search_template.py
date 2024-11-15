from __future__ import annotations

import json
import shutil
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from functools import wraps
import time

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


class TemplateStyle(str, Enum):
    """模板风格枚举
    
    继承 str 使其更容易序列化和处理
    """
    COMMON = "common"  # 普通风格
    NATURE = "nature"  # 自然风格
    SALE = "sale"    # 销售风格

    @classmethod
    def register(cls, style_name: str) -> 'TemplateStyle':
        """注册新的模板风格
        
        Args:
            style_name: 新风格的名称
            
        Returns:
            新创建的 TemplateStyle 枚举成员
        """
        if style_name.upper() not in cls.__members__:
            cls._member_map_[style_name.upper()] = style_name.lower()
        return cls(style_name.lower())


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

    templates: Dict[TemplateStyle, TemplateInfo] = Field(default_factory=dict)
    llm: Optional[LLM] = Field(default=None)
    template_version: str = Field(default="1.0.0")
    deployment_config: Dict[str, Any] = Field(default_factory=dict)
    output_dir: Path = Field(default=Path(METAGPT_ROOT) / "workspace" / "template")

    _engine: Optional[SimpleEngine] = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm = kwargs.get('llm') or LLM()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _init_rag_engine(self):
        """初始化 RAG 引擎并加载模板描述"""
        # template_docs = []
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
            # template_docs.append(doc)
            template_objs.append(
                TemplateRAGObject(
                    content=doc,
                    metadata={
                        "type": "template",
                        "style": template.style
                    }
                )
            )

        # 使用准备好的对象初始化引擎
        self._engine = SimpleEngine.from_objs(
            objs=template_objs,  # 传入初始对象列表
            retriever_configs=[
                FAISSRetrieverConfig(dimensions=1536),  # 明确指定维度
                BM25RetrieverConfig()
            ]
        )

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
        """从模板目录自动加载所有模板"""
        base_path = METAGPT_ROOT / "template"
        if not base_path.exists():
            logger.warning(f"模板基础目录不存在: {base_path}")
            return

        # 直接使用异步方式遍历和处理模板
        for template_dir in base_path.iterdir():
            if not template_dir.is_dir():
                continue
            
            template_info = await self._parse_template_config(template_dir)
            if template_info:
                self.templates[template_info.style] = template_info
                logger.info(f"成功加载模板: {template_info.style} from {template_dir}")

    

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

    def get_template(self, style: TemplateStyle) -> Optional[TemplateInfo]:
        """获取指定风格的模板"""
        return self.templates.get(style, None)

    def get_all_templates(self) -> Dict[TemplateStyle, TemplateInfo]:
        """获取所有模板"""
        return self.templates.copy()

    def register_template(self, template: TemplateInfo) -> None:
        """注册新模板"""
        self.templates[template.style] = template

    async def _select_template(self, requirement: str) -> Optional[TemplateInfo]:
        """Use RAG to select the best-matched template."""
        try:
            # 使用 RAG 检索最相关的模板
            result = await self._engine.aquery(requirement)
            if not result:
                return None

            # logger.info("meta data", result.metadata)

            # 首先尝试从 source_nodes 中获取风格信息
            if hasattr(result, 'source_nodes') and result.source_nodes:
                for node in result.source_nodes:
                    if hasattr(node, 'metadata') and 'style' in node.metadata:
                        style_name = node.metadata['style']
                        try:
                            style = TemplateStyle(style_name)
                            return self.templates.get(style)
                        except ValueError:
                            continue

            # 如果从 source_nodes 中没找到，尝试从 response 文本中提取风格信息
            if hasattr(result, 'response'):
                response_text = str(result.response).lower()
                # 根据响应文本判断最适合的模板风格
                if '销售' in response_text or 'sale' in response_text:
                    return self.templates.get(TemplateStyle.SALE)
                elif '自然' in response_text or 'nature' in response_text:
                    return self.templates.get(TemplateStyle.NATURE)

            # 默认返回通用模板
            logger.info("Using default COMMON template style")
            return self.templates.get(TemplateStyle.COMMON)

        except Exception as e:
            logger.error(f"Error selecting template: {str(e)}")
            logger.error(f"Result response: {result.response if hasattr(result, 'response') else None}")
            return None

    @monitor_performance
    async def direct_select(self, style: TemplateStyle, user_info: Dict[str, Any]) -> Optional[
        Tuple[TemplateInfo, Dict[str, Any]]]:
        """Handling the case where the user directly selects a template

        Args:
            style: The template style chosen by the user
            user_info: Information provided by the user

        Returns:
            If successful, returns a tuple (template information, supplemented user information)
            If failed, returns None
        """
        try:
            template = self.get_template(style)
            if not template:
                return None

            # 补充缺失的用户信息
            complete_info = await self._complete_user_info(user_info, template.required_fields)

            logger.info(f"Direct select: Template {style}")
            logger.info(f"User info: {complete_info}")

            return template, complete_info
        except Exception as e:
            logger.error(f"Error direct selecting template: {str(e)}")
            return None

    async def copy_template(self, template: TemplateInfo) -> Path:
        """复制模板到目标位置"""
        if not template.template_path.exists():
            raise FileNotFoundError(f"Template path {template.template_path} does not exist")

        target_dir = self.output_dir
        # target_dir.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copytree(template.template_path, target_dir, dirs_exist_ok=True)
            logger.info(f"Template copied: {template.style} -> {target_dir}")
            return target_dir
        except Exception as e:
            logger.error(f"Failed to copy template: {str(e)}")
            raise IOError(f"Failed to copy template: {str(e)}")

    async def _complete_user_info(self, user_info: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
        """补充缺失的用户信息
        
        如果有缺失字段，使用LLM生成合理的默认值
        """
        complete_info = user_info.copy()
        missing_fields = [field for field in required_fields if field not in user_info or not user_info[field]]

        if missing_fields:
            prompt = f"""基于已有信息，为以下字段生成合理的默认值:
            已有信息: {json.dumps(user_info, ensure_ascii=False)}
            需要补充的字段: {', '.join(missing_fields)}
            
            请以JSON格式返回补充的字段值。
            """
            result = await self.llm.aask(prompt)
            try:
                supplementary_info = json.loads(result)
                complete_info.update(supplementary_info)
            except json.JSONDecodeError:
                pass

        return complete_info
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
