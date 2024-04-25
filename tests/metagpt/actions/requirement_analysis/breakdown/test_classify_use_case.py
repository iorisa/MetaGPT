from pathlib import Path

import pytest

from metagpt.actions.requirement_analysis.breakdown import ClassifyUseCase
from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.utils.common import aread
from metagpt.utils.di_graph_repository import DiGraphRepository


@pytest.mark.asyncio
async def test_classify(context):
    context.kwargs.ns = Namespaces(namespace="RFC225")
    data = await aread(filename=Path(__file__).parent / "../../../../data/graph_db/breakdown.json")
    filename = context.repo.workdir.name + ".json"
    await context.repo.docs.graph_repo.save(filename=filename, content=data)

    graph_db = await DiGraphRepository.load_from(context.repo.docs.graph_repo.workdir / filename)
    action = ClassifyUseCase(graph_db=graph_db, context=context)
    await action.run()
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
