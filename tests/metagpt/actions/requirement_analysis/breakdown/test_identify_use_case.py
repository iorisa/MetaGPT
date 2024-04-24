from pathlib import Path
from typing import List

import pytest
from pydantic import BaseModel

from metagpt.actions.requirement_analysis.breakdown import IdentifyUseCase
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.utils.common import aread, concat_namespace
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import SPO


@pytest.mark.asyncio
async def test_md(context):
    context.kwargs.ns = Namespaces(namespace="RFC225")
    data = await aread(filename=Path(__file__).parent / "../../../../data/graph_db/breakdown.json")
    filename = context.repo.workdir.name + ".json"
    await context.repo.docs.graph_repo.save(filename=filename, content=data)

    graph_db = await DiGraphRepository.load_from(context.repo.docs.graph_repo.workdir / filename)
    action = IdentifyUseCase(graph_db=graph_db, context=context)
    await action._save_use_cases_pdf()
    doc = await context.repo.resources.use_case.get(filename="all.md")
    assert doc
    assert doc.content

    rows = await graph_db.select(
        predicate=concat_namespace(context.kwargs.ns.breakdown_use_case, GraphKeyWords.Has_ + GraphKeyWords.Detail)
    )
    assert rows

    class Data(BaseModel):
        spos: List[SPO]

    v = Data(spos=rows)
    await context.repo.docs.use_case.save(filename="breakdown_use_case_details.json", content=v.model_dump_json())
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
