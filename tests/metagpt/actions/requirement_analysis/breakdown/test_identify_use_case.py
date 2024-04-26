from typing import List

import pytest
from pydantic import BaseModel

from metagpt.actions.requirement_analysis.breakdown import IdentifyUseCase
from metagpt.actions.requirement_analysis.graph_key_words import GraphKeyWords
from metagpt.utils.common import concat_namespace
from metagpt.utils.graph_repository import SPO
from tests.metagpt.actions.requirement_analysis.breakdown import prepare_graph_db


@pytest.mark.asyncio
async def test_md(context):
    graph_db = await prepare_graph_db(context)
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
