#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/1/20
@Author  : mashenquan
@File    : text_to_class.py
@Desc    : Tools for the implementation of RFC145. https://deepwisdom.feishu.cn/docx/VhRCdcfQQoIlaJxWvyLcMDP9nbg
"""

from typing import List

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_random_exponential

from metagpt.logs import logger
from metagpt.utils.common import (
    general_after_log,
    json_to_markdown_prompt,
    parse_json_code_block,
)


class ClassCodeBlock(BaseModel):
    name: str
    description: str
    goal: str
    properties: List[str]
    reason: str


@retry(
    wait=wait_random_exponential(min=1, max=20),
    stop=stop_after_attempt(6),
    after=general_after_log(logger),
)
async def text_to_class(detail: str, llm) -> List[ClassCodeBlock]:
    prompt = json_to_markdown_prompt(detail)
    rsp = await llm.aask(
        msg=prompt,
        system_msgs=[
            "You are a tool that translates class descriptions into UML 2.0 classes.",
            'Return a JSON object in Markdown format with a "name" key for the class name, a "description" key to describe the class functionality, a "goal" key to outline the goal the class aims to achieve, a "properties" key to list the properties of the class, and a "reason" key to provide explanations.',
        ],
    )
    logger.info(rsp)
    json_blocks = parse_json_code_block(rsp)

    return [ClassCodeBlock.model_validate_json(block) for block in json_blocks]
