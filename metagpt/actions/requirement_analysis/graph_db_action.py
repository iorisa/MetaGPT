#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2024/4/23
@Author  : mashenquan
@File    : graph_action.py
@Desc    : The base class of action using graph db.
"""
from pathlib import Path
from typing import Optional

from metagpt.actions import Action
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository


class GraphDBAction(Action):
    graph_db: Optional[GraphRepository] = None

    async def load_graph_db(self):
        filename = Path(self.context.repo.workdir.name).with_suffix(".json")
        self.graph_db = await DiGraphRepository.load_from(self.context.repo.docs.graph_repo.workdir / filename)
