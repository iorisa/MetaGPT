#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module Description: This script defines the LearnReadMe class, which is an action to learn from the contents of
    a README.md file.
Author: mashenquan
Date: 2024-3-20
"""
from pathlib import Path
from typing import Optional

from pydantic import Field

from metagpt.actions import Action
from metagpt.const import GRAPH_REPO_FILE_REPO
from metagpt.schema import Message
from metagpt.utils.common import aread
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphKeyword, GraphRepository


class LearnReadMe(Action):
    """
    An action to learn from the contents of a README.md file.

    Attributes:
        graph_db (Optional[GraphRepository]): A graph database repository.
        install_to_path (Optional[str]): The path where the repository to install to.
    """

    graph_db: Optional[GraphRepository] = None
    install_to_path: Optional[str] = Field(default="/TO/PATH")
    _readme: Optional[str] = None
    _filename: Optional[str] = None

    async def run(self, with_messages=None, **kwargs):
        """
        Implementation of `Action`'s `run` method.

        Args:
            with_messages (Optional[Type]): An optional argument specifying messages to react to.
        """
        graph_repo_pathname = self.context.git_repo.workdir / GRAPH_REPO_FILE_REPO / self.context.git_repo.workdir.name
        self.graph_db = await DiGraphRepository.load_from(str(graph_repo_pathname.with_suffix(".json")))
        summary = await self.summarize()
        await self.graph_db.insert(subject=self._filename, predicate=GraphKeyword.HAS_SUMMARY, object_=summary)
        install = await self.install()
        await self.graph_db.insert(subject=self._filename, predicate=GraphKeyword.HAS_INSTALL, object_=install)
        conf = await self.config()
        await self.graph_db.insert(subject=self._filename, predicate=GraphKeyword.HAS_CONFIG, object_=conf)
        usage = await self.usage()
        await self.graph_db.insert(subject=self._filename, predicate=GraphKeyword.HAS_USAGE, object_=usage)

        await self.graph_db.save()

        return Message(content="", cause_by=self)

    async def summarize(self) -> str:
        readme = await self._get()
        summary = await self.llm.aask(
            readme,
            system_msgs=[
                "You are a tool can summarize git repository README.md file.",
                "Return the summary about what is the repository.",
            ],
        )
        return summary

    async def install(self) -> str:
        readme = await self._get()
        install = await self.llm.aask(
            readme,
            system_msgs=[
                "You are a tool can install git repository according to README.md file.",
                "Return a bash code block of markdown including:\n"
                f"1. git clone the repository to the directory `{self.install_to_path}`;\n"
                f"2. cd `{self.install_to_path}`;\n"
                f"3. install the repository.",
            ],
        )
        return install

    async def config(self) -> str:
        readme = await self._get()
        configuration = await self.llm.aask(
            readme,
            system_msgs=[
                "You are a tool can configure git repository according to README.md file.",
                "Return a bash code block of markdown object to configure the repository if necessary, otherwise return"
                " a empty bash code block of markdown object",
            ],
        )
        return configuration

    async def usage(self) -> str:
        readme = await self._get()
        usage = await self.llm.aask(
            readme,
            system_msgs=[
                "You are a tool can summarize all usages of git repository according to README.md file.",
                "Return a list of code block of markdown objects to demonstrates the usage of the repository.",
            ],
        )
        return usage

    async def _get(self) -> str:
        if self._readme is not None:
            return self._readme
        filename = Path(self.i_context).resolve() / "README.md"
        self._readme = await aread(filename=filename, encoding="utf-8")
        self._filename = str(filename)
        return self._readme
