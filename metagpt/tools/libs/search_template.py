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


class TemplateStyle(Enum):
    """模板风格枚举"""
    COMMON = "common"  # 普通风格
    NATURE = "nature"  # 自然风格
    SALE = "sale"  # 销售风格


class TemplateInfo(BaseModel):
    """模板信息数据类"""
    style: TemplateStyle
    template_path: Path
    preview_image: str
    description: str
    required_fields: List[str]


def read_file_by_path(file_path: Path) -> str:
    """读取文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""


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
    """模板搜索工具，用于根据用户需求匹配合适的名片模板
    
    ## Example
    需求：帮我制作一张个人名片，我是一名产品经理
    使用方法：
    >>> template_tool = SearchTemplate()
    >>> result = await template_tool.search("帮我制作一张个人名片，我是一名产品经理")
    >>> if result:
    >>>     template, user_info = result
    >>>     print(f"Selected template: {template.style}")
    >>>     print(f"User info: {user_info}")
    """

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
        self._init_templates()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._init_rag_engine()

    def _init_rag_engine(self):
        """初始化 RAG 引擎并加载模板描述"""
        # template_docs = []
        template_objs = []
        
        # 首先准备所有模板文档和对象
        for template in self.templates.values():
            doc = f"""
            Template Style: {template.style.value}
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
                        "style": template.style.value
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

    def _get_template_content(self, template: TemplateInfo) -> str:
        """获取模板内容"""
        try:
            content = ""
            for file_path in template.template_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in ['.html', '.js', '.css']:
                    content += f"\n### {file_path.name}\n"
                    content += read_file_by_path(file_path)
            return content
        except Exception:
            return ""

    def _init_templates(self) -> None:
        """初始化内置模板"""
        base_path = METAGPT_ROOT / "template"

        self.templates[TemplateStyle.COMMON] = TemplateInfo(
            style=TemplateStyle.COMMON,
            template_path=base_path / "common",
            preview_image="assets/previews/common.png",
            description="简洁大方的通用名片模板",
            required_fields=["name", "job", "email", "phone", "description", "mbti"]
        )

        self.templates[TemplateStyle.NATURE] = TemplateInfo(
            style=TemplateStyle.NATURE,
            template_path=base_path / "nature",
            preview_image="assets/previews/nature.png",
            description="自然清新风格的名片模板",
            required_fields=["name", "job", "email", "phone", "description", "mbti"]
        )

        self.templates[TemplateStyle.SALE] = TemplateInfo(
            style=TemplateStyle.SALE,
            template_path=base_path / "sale",
            preview_image="assets/previews/sale.png",
            description="专业的销售风格名片模板",
            required_fields=["name", "job", "email", "phone", "description", "mbti"]
        )

    def monitor_performance(func: Callable) -> Callable:
        """性能监控装饰器"""
        
        @wraps(func)
        async def wrapper(self, *args, **kwargs) -> Any:
            start_time = time.time()
            result = await func(self, *args, **kwargs)
            execution_time = time.time() - start_time

            logger.info(f"Action: {func.__name__}, Execution time: {execution_time:.2f}s, Success: {result is not None}")

            return result

        return wrapper

    @monitor_performance
    async def search(self, requirement: str) -> Optional[TemplateInfo]:
        """搜索匹配的模板并提取用户信息"""
        try:
            template = await self._select_template(requirement)
            if not template:
                logger.warning("No matching template found")
                return None

            # user_info = await self._extract_user_info(requirement, template.required_fields)

            logger.info(f"Selected template: {template.style.value}")
            # logger.info(f"User info: {user_info}")

            return template
        except Exception as e:
            logger.error(f"Template search failed: {str(e)}")
            logger.error(f"Requirement: {requirement}")
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

            logger.info(f"Direct select: Template {style.value}")
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
            logger.info(f"Template copied: {template.style.value} -> {target_dir}")
            return target_dir
        except Exception as e:
            logger.error(f"Failed to copy template: {str(e)}")
            raise IOError(f"Failed to copy template: {str(e)}")

    @monitor_performance
    async def update_user_info(self, target_path: Path, user_info: Dict[str, Any]) -> bool:
        """将用户信息应用到模板中"""
        try:
            # Get all template files that need to be modified
            template_files = list(target_path.rglob("*.html")) + list(target_path.rglob("*.js")) + list(
                target_path.rglob("*.css"))

            for file_path in template_files:
                # Read file content
                content = await read_file_by_path(file_path)

                # Replace placeholders with user information
                new_content = content
                for key, value in user_info.items():
                    if value:  # Only replace if value is not None
                        placeholder = f"{{{{user.{key}}}}}"
                        new_content = new_content.replace(placeholder, str(value))

                # Write modified content back
                await awrite(file_path, new_content)

            logger.info(f"User info applied: {str(target_path)}")
            logger.info(f"Modified files: {len(template_files)}")

            return True

        except Exception as e:
            logger.error(f"Error applying user info: {str(e)}")
            return False

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

    @monitor_performance
    async def reload_templates(self) -> None:
        """重新加载所有模板，支持热更新"""
        try:
            # 清空现有模板
            self.templates.clear()
            # 重新始化模板
            self._init_templates()

            logger.info(f"Templates reloaded: {len(self.templates)}")
        except Exception as e:
            logger.error(f"Error reloading templates: {str(e)}")


if __name__ == "__main__":
    import asyncio


    async def main():
        async with SearchTemplate() as search_tool:
            requirement = "帮我制作一张个人名片，我是一名产品经理"
            result = await search_tool.search(requirement)

            if result:
                template, user_info = result
                print(f"Selected template: {template.style}")
                print(f"User info: {user_info}")
            else:
                print("No matching template found")


    asyncio.run(main())
