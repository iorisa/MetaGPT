#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from enum import Enum
from pathlib import Path
from pprint import pformat
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from tree_sitter import Node, Tree


class CodeBlockType(Enum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    STRING = "string"
    IMPORT = "import"
    DOTTED_NAME = "dotted_name"
    IDENTIFIER = "identifier"


def dummy_func(node: Node):
    print(f"Unsupported node:{node.type}, text:{node.text.decode('utf-8')}, {pformat(node)}")


class NodeChain(BaseModel):
    parent: Optional[Any] = Field(default=None, exclude=True)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, exclude=True)


class CodeBlock(NodeChain):
    start_lineno: int  # 1-based
    start_colno: int  # 1-based
    end_lineno: int  # 1-based
    end_colno: int  # 1-based
    text: str = Field(exclude=True)
    type_: str

    @classmethod
    def load(cls, node: Node, type_: str = "", parent: Any = None) -> CodeBlock:
        return cls(
            parent=parent,
            start_lineno=node.start_point[0] + 1,  # 0-based to 1-based
            start_colno=node.start_point[1] + 1,  # 0-based to 1-based
            end_lineno=node.end_point[0] + 1,  # 0-based to 1-based
            end_colno=node.end_point[1] + 1,  # 0-based to 1-based
            text=node.text.decode("utf-8"),
            type_=type_ or node.type,
        )


class Module(NodeChain):
    code: CodeBlock
    expression_statements: List = Field(default_factory=list)
    imports: List = Field(default_factory=list)

    @classmethod
    def load(cls, node: Node, parent: Any = None):
        module = cls(parent=parent, code=CodeBlock.load(node=node))
        for i in node.children:
            add_func = getattr(module, f"_add_{i.type}", dummy_func)
            add_func(i)
        return module

    def _add_expression_statement(self, node: Node):
        statement = ExpressionStatement.load(node, parent=self)
        self.expression_statements.append(statement)

    def _add_import_statement(self, node: Node):
        statement = ImportStatement.load(node, parent=self)
        self.imports.append(statement)


class ExpressionStatement(NodeChain):
    code: CodeBlock
    expression_statements: List = Field(default_factory=list)

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> ExpressionStatement:
        obj = cls(parent=parent, code=CodeBlock.load(node))
        for i in node.children:
            add_func = getattr(obj, f"_add_{i.type}", dummy_func)
            add_func(i)
        return obj

    def _add_string(self, node: Node):
        statement = StringStatement.load(node=node, parent=self)
        self.expression_statements.append(statement)


class StringStatement(NodeChain):
    start: CodeBlock = None
    content: CodeBlock = None
    end: CodeBlock = None

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> StringStatement:
        statement = cls(
            parent=parent,
            type_=CodeBlockType.STRING.value,
            text=node.text.decode("utf-8"),
        )
        for i in node.children:
            if i.type == "string_start":
                statement.start = CodeBlock.load(node=i)
            elif i.type == "string_content":
                statement.content = CodeBlock.load(node=i)
            elif i.type == "string_end":
                statement.end = CodeBlock.load(node=i)
            else:
                raise ValueError(f"Unsupported node:{i.type}, text={i.text.decode('utf-8')}")

        return statement


class ImportStatement(NodeChain):
    code: CodeBlock
    dotted_name: Optional[List[str]] = None
    identifier: Optional[str] = None

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> ImportStatement:
        statement = cls(parent=parent, code=CodeBlock.load(node=node))
        import_content_node = None
        for i in node.children:
            if i.type == CodeBlockType.IMPORT.value:
                continue
            import_content_node = i
            break
        for i in import_content_node.children:
            if i.type == CodeBlockType.DOTTED_NAME.value:
                statement.dotted_name = cls._parse_dotted_name(i)
            elif i.type == CodeBlockType.IDENTIFIER.value:
                statement.identifier = i.text.decode("utf=8")
        return statement

    @classmethod
    def _parse_dotted_name(cls, node: Node) -> List[str]:
        names = []
        for i in node.children:
            if i.type == CodeBlockType.IDENTIFIER.value:
                names.append(i.text.decode("utf-8"))
        return names


class ParseResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tree: Tree = Field(default=None, exclude=True)
    filename: Path
    errors: List[CodeBlock] = Field(default_factory=list)
    module: Optional[Module] = Field(default=None)

    def update(self):
        self._on_update()
        self._on_update_errors()

    def _on_update(self):
        self.module = Module.load(node=self.tree.root_node)

    def _on_update_errors(self):
        if not self.tree:
            self.errors = []
            return
        self.errors = []
        for i in self.tree.root_node.children:
            if not i.has_error:
                continue
            errs = self._get_syntax_error(i)
            self.errors.extend(errs)

    def _get_syntax_error(self, n: Node) -> List[CodeBlock]:
        if n.has_error and n.type == "ERROR":
            return [
                CodeBlock(
                    filename=str(self.filename),
                    start_lineno=n.start_point[0] + 1,  # 0-based to 1-based
                    start_colno=n.start_point[1] + 1,  # 0-based to 1-based
                    end_lineno=n.end_point[0] + 1,  # 0-based to 1-based
                    end_colno=n.end_point[1] + 1,  # 0-based to 1-based
                    text=n.text.decode("utf-8"),
                    type_=CodeBlockType.SYNTAX_ERROR.value,
                )
            ]

        errs = []
        for i in n.children:
            if not i.has_error:
                continue
            v = self._get_syntax_error(i)
            if v:
                errs.extend(v)
        return errs
