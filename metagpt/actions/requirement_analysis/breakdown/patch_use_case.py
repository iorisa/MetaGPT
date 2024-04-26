#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : patch_use_case.py
@Desc    : The implementation of the Chapter 2.2.3 of RFC225.
"""

from metagpt.actions.requirement_analysis import GraphDBAction
from metagpt.schema import Message


class PatchUseCase(GraphDBAction):
    async def run(self, with_messages: Message = None):
        await self.load_graph_db()
