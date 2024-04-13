#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field
from tree_sitter import Parser

from metagpt.tools.parsers import ParseResult
from metagpt.utils.common import aread


class BaseParser(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    parser: Parser = Field(default=None, exclude=True)

    @abstractmethod
    async def parse(
        self,
        filename: str | Path = Path("tmpfile"),
        content: str = "",
        old_result: ParseResult = None,
    ) -> ParseResult:
        pass

    @abstractmethod
    # @property
    def extensions(self) -> List[str]:
        pass

    @staticmethod
    async def _read_file(filename: str | Path = Path("tmpfile"), content: str = "") -> str:
        if not content:
            filename = Path(filename).resolve()
            if not filename.exists():
                raise ValueError(f"Invalid filename: {filename}")

            content = await aread(filename=filename)
        return content

    def _parse(self, content: str, old_result):
        if old_result and old_result.tree:
            new_tree = self.parser.parse(content.encode("utf-8"), old_result.tree)
        else:
            new_tree = self.parser.parse(content.encode("utf-8"))
        return new_tree
