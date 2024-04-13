#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import List

import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser

from metagpt.tools.parsers import BaseParser, ParseResult


class CParser(BaseParser):
    async def parse(
        self,
        filename: str | Path = Path("tmpfile"),
        content: str = "",
        old_result: ParseResult = None,
    ) -> ParseResult:
        filename = Path(filename).resolve()
        content = await self._read_file(filename=filename, content=content)

        if not self.parser:
            parser_language = Language(tscpp.language(), "cpp")
            self.parser = Parser()
            self.parser.set_language(parser_language)

        new_tree = self._parse(content=content, old_result=old_result)
        result = ParseResult(tree=new_tree, filename=str(filename))
        result.update()
        return result

    @property
    def extensions(self) -> List[str]:
        return ["*.c", "*.cpp", "*.cu", "*.h", "*.cc"]
