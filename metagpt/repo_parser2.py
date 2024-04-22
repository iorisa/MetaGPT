#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build a symbols repository from source code.
This script is designed to create a symbols repository from the provided source code.
"""
from pathlib import Path

from pydantic import BaseModel, Field

from metagpt.tools.parsers import (
    BaseParser,
    BashParser,
    CParser,
    GoParser,
    JavaParser,
    JavaScriptParser,
    PythonParser,
    RustParser,
)


class RepoParser2(BaseModel):
    """
    Tool to build a symbols repository from a project directory.

    Attributes:
        base_directory (Path): The base directory of the project.
    """

    base_directory: Path = Field(default=None)

    async def generate_symbols(self):
        results = []
        parsers = [BashParser(), CParser(), GoParser(), JavaParser(), JavaScriptParser(), PythonParser(), RustParser()]
        for p in parsers:
            r = await self._parse_symbols(parser=p)
            results.extend(r)
        return results

    async def _parse_symbols(self, parser: BaseParser):
        directory = self.base_directory

        matching_files = []
        results = []
        for ext in parser.extensions:
            matching_files += directory.rglob(ext)
        for path in matching_files:
            print(path)
            result = await parser.parse(path)
            print(result.model_dump_json())
            results.append(result)
        return results
