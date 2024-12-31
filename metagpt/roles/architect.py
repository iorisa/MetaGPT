#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/5/11 14:43
@Author  : alexanderwu
@File    : architect.py
"""
# from agentops import track_agent
from pydantic import Field, model_validator

from metagpt.actions.design_api import WriteDesign
from metagpt.actions.write_prd import WritePRD
from metagpt.prompts.di.architect import ARCHITECT_INSTRUCTION, SYSTEM_DESIGN_EXAMPLE
from metagpt.prompts.di.supabase import get_backend_prompt_for_architect
from metagpt.prompts.di.template import GENERAL_WEB_APP_TEMPLATE_PROMPT
from metagpt.roles.di.role_zero import RoleZero
from metagpt.tools.libs.terminal import Terminal


# @track_agent("Architect")
class Architect(RoleZero):
    """
    Represents an Architect role in a software development process.

    Attributes:
        name (str): Name of the architect.
        profile (str): Role profile, default is 'Architect'.
        goal (str): Primary goal or responsibility of the architect.
        constraints (str): Constraints or guidelines for the architect.
    """

    name: str = "Bob"
    profile: str = "Architect"
    goal: str = "Design a concise, usable, complete software system. Output the system design."
    constraints: str = "Make sure the architecture is simple enough and use appropriate open source libraries. Use same language as user requirement"
    terminal: Terminal = Field(default_factory=Terminal)
    instruction: str = ARCHITECT_INSTRUCTION
    tools: list[str] = [
        "Editor:write,read,similarity_search",
        "RoleZero",
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # NOTE: The following init setting will only be effective when self.use_fixed_sop is changed to True
        self.enable_memory = False
        # Initialize actions specific to the Architect role
        self.set_actions([WriteDesign])

        # Set events or actions the Architect should watch or be aware of
        self._watch({WritePRD})

    @model_validator(mode="after")
    def set_instruction(self):
        self.instruction = ARCHITECT_INSTRUCTION.format(
            backend_info=get_backend_prompt_for_architect(),
            system_design_example=SYSTEM_DESIGN_EXAMPLE,
            template_info=GENERAL_WEB_APP_TEMPLATE_PROMPT,
        )
        return self
