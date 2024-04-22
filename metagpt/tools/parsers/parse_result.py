#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import uuid
from enum import Enum
from pathlib import Path
from pprint import pformat
from typing import Any, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field
from tree_sitter import Node, Tree


class CodeBlockType(Enum):
    SYNTAX_ERROR = "SYNTAX_ERROR"
    STRING = "string"
    IMPORT = "import"
    DOTTED_NAME = "dotted_name"
    IDENTIFIER = "identifier"
    SCOPED_IDENTIFIER = "scoped_identifier"
    IMPORT_CONTENT = "import_content"
    MODIFIERS = "modifiers"
    WORD = "word"
    LEFT_PARENTHESIS = "("
    RIGHT_PARENTHESIS = ")"
    COMPOUND_STATEMENT = "compound_statement"
    PRIMITIVE_TYPE = "primitive_type"
    FUNCTION_DECLARATOR = "function_declarator"
    PARAMETER_LIST = "parameter_list"
    SYSTEM_LIB_STRING = "system_lib_string"
    PARAMETER_DECLARATION = "parameter_declaration"
    ASTERISK = "*"
    POINTER_DECLARATOR = "pointer_declarator"
    CLASS_BODY = "class_body"
    PREPROC_ARG = "preproc_arg"


class NodeChain(BaseModel):
    parent: Optional[Any] = Field(default=None, exclude=True)
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, exclude=True)
    imports: Optional[List["ImportStatement"]] = None
    classes: Optional[List["ClassDeclaration"]] = None
    expression_statements: Optional[List["ExpressionStatement"]] = None
    functions: Optional[List[Union["FunctionDefinition", "PreprocDef"]]] = None


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

    @classmethod
    def load(cls, node: Node, parent: Any = None):
        module = cls(parent=parent, code=CodeBlock.load(node=node))
        add_node(parent=module, children=node.children)
        return module


class ExpressionStatement(NodeChain):
    code: CodeBlock

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> ExpressionStatement:
        obj = cls(parent=parent, code=CodeBlock.load(node))
        add_node(parent=obj, children=node.children)
        return obj


class ImportStatement(NodeChain):
    code: CodeBlock
    dotted_name: List[str] = Field(default_factory=list)

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> ImportStatement:
        statement = cls(parent=parent, code=CodeBlock.load(node=node))
        for i in node.children:
            if i.type == CodeBlockType.SCOPED_IDENTIFIER.value:
                statement.dotted_name = cls._parse_scoped_identifier(i)
            elif i.type == CodeBlockType.IMPORT_CONTENT.value:
                statement.dotted_name = cls._parse_dotted_name(i)
            elif i.type == CodeBlockType.IDENTIFIER.value:
                statement.dotted_name.append(i.text.decode("utf-8"))
        return statement

    @classmethod
    def _parse_dotted_name(cls, node: Node) -> List[str]:
        names = []
        for i in node.children:
            if i.type == CodeBlockType.IDENTIFIER.value:
                names.append(i.text.decode("utf-8"))
        return names

    @classmethod
    def _parse_scoped_identifier(cls, node: Node) -> List[str]:
        names = []
        for i in node.children:
            if i.type == CodeBlockType.SCOPED_IDENTIFIER.value:
                names = cls._parse_scoped_identifier(i)
            elif i.type == CodeBlockType.IDENTIFIER.value:
                names.append(i.text.decode("utf-8"))
        return names


class ClassDeclaration(NodeChain):
    code: CodeBlock
    modifiers: Optional[List[str]] = None
    name: Optional[str] = None

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> ClassDeclaration:
        statement = cls(parent=parent, code=CodeBlock.load(node=node))
        for i in node.children:
            if i.type == CodeBlockType.MODIFIERS.value:
                statement._parse_modifiers(i)
            elif i.type == CodeBlockType.IDENTIFIER.value:
                statement.name = i.text.decode("utf-8")
            elif i.type == CodeBlockType.CLASS_BODY.value:
                statement._parse_body(i)
        return statement

    def _parse_modifiers(self, node: Node):
        pass

    def _parse_body(self, node: Node):
        pass


class ParameterDeclaration(NodeChain):
    type_: Optional[str] = None
    name: Optional[str] = None
    pointer_declarator: Optional[str] = None

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> ParameterDeclaration:
        statement = cls(parent=parent, code=CodeBlock.load(node=node))
        statement._parse(node)
        return statement

    def _parse(self, node: Node):
        for i in node.children:
            if i.type == CodeBlockType.PRIMITIVE_TYPE.value:
                self.type_ = i.text.decode("utf-8")
            elif i.type == CodeBlockType.POINTER_DECLARATOR.value:
                self._parse_pointer_declarator(i)
            elif i.type == CodeBlockType.IDENTIFIER.value:
                self.name = i.text.decode("utf-8")

    def _parse_pointer_declarator(self, node: Node):
        for i in node.children:
            if i.type == CodeBlockType.ASTERISK.value:
                if self.pointer_declarator is None:
                    self.pointer_declarator = CodeBlockType.ASTERISK.value
                else:
                    self.pointer_declarator += CodeBlockType.ASTERISK.value
            elif i.type == CodeBlockType.IDENTIFIER.value:
                self.name = i.text.decode("utf-8")


class FunctionDefinition(NodeChain):
    code: CodeBlock
    name: Optional[str] = None
    parameters: Optional[List[ParameterDeclaration]] = None
    body: Optional[str] = None
    return_type: Optional[str] = None

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> FunctionDefinition:
        statement = cls(parent=parent, code=CodeBlock.load(node=node))
        statement._parse_declaration(node)
        return statement

    def _parse_declaration(self, node: Node):
        for i in node.children:
            if i.type == CodeBlockType.WORD.value:
                self.name = i.text.decode("utf-8")
            elif i.type == CodeBlockType.LEFT_PARENTHESIS.value:
                pass
            elif i.type == CodeBlockType.RIGHT_PARENTHESIS.value:
                pass
            elif i.type == CodeBlockType.COMPOUND_STATEMENT.value:
                self.body = i.text.decode("utf-8")
            elif i.type == CodeBlockType.PRIMITIVE_TYPE.value:
                self.return_type = i.text.decode("utf-8")
            elif i.type == CodeBlockType.FUNCTION_DECLARATOR.value:
                self._parse_function_declarator(i)

    def _parse_function_declarator(self, node: Node):
        for i in node.children:
            if i.type == CodeBlockType.IDENTIFIER.value:
                self.name = i.text.decode("utf-8")
            elif i.type == CodeBlockType.PARAMETER_LIST.value:
                self._parse_parameter_list(i)

    def _parse_parameter_list(self, node: Node):
        for i in node.children:
            if i.type == CodeBlockType.PARAMETER_DECLARATION.value:
                v = ParameterDeclaration.load(node=i, parent=self)
                if self.parameters is None:
                    self.parameters = [v]
                else:
                    self.parameters.append(v)


class PreprocDef(NodeChain):
    code: CodeBlock
    name: Optional[str] = None
    body: Optional[str] = None

    @classmethod
    def load(cls, node: Node, parent: Any = None) -> PreprocDef:
        statement = cls(parent=parent, code=CodeBlock.load(node=node))
        statement._parse(node)
        return statement

    def _parse(self, node: Node):
        for i in node.children:
            if i.type == CodeBlockType.IDENTIFIER.value:
                self.name = i.text.decode("utf-8")
            elif i.type == CodeBlockType.PREPROC_ARG.value:
                self.body = i.text.decode("utf-8")


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


def add_node(parent: Any, children: List[Node]):
    for i in children:
        module_ = sys.modules[__name__]
        add_func = getattr(module_, f"_add_{i.type}", dummy_func)
        add_func(parent=parent, node=i)


def dummy_func(parent: Any, node: Node):
    print(f"Unsupported node:{node.type}, text:{node.text.decode('utf-8')}, {pformat(node)}")


def _add_import_declaration(parent: Any, node: Node):
    statement = ImportStatement.load(node=node, parent=parent)
    if parent.imports is None:
        parent.imports = [statement]
    else:
        parent.imports.append(statement)


def _add_class_declaration(parent: Any, node: Node):
    statement = ClassDeclaration.load(node=node, parent=parent)
    if parent.classes is None:
        parent.classes = [statement]
    else:
        parent.classes.append(statement)


def _add_comment(parent: Any, node: Node):
    pass


def _add_preproc_include(parent: Any, node: Node):
    for i in node.children:
        if i.type == CodeBlockType.SYSTEM_LIB_STRING.value:
            lib_string = i.text.decode("utf-8")
            if parent.imports is None:
                parent.imports = [lib_string]
            else:
                parent.imports.append(lib_string)


def _add_type_definition(parent: Any, node: Node):
    pass


def _add_preproc_def(parent: Any, node: Node):
    statement = PreprocDef.load(node=node, parent=parent)
    if parent.functions is None:
        parent.functions = [statement]
    else:
        parent.functions.append(statement)


def _add_preproc_ifdef(parent: Any, node: Node):
    pass


def _add_function_definition(parent: Any, node: Node):
    statement = FunctionDefinition.load(node=node, parent=parent)
    if parent.functions is None:
        parent.functions = [statement]
    else:
        parent.functions.append(statement)
