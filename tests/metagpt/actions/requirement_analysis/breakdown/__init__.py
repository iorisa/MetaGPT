from pathlib import Path

from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.utils.common import aread
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository


async def prepare_graph_db(context) -> GraphRepository:
    context.kwargs.ns = Namespaces(namespace="RFC225")
    data = await aread(filename=Path(__file__).parent / "../../../../data/graph_db/breakdown.json")
    filename = context.repo.workdir.name + ".json"
    await context.repo.docs.graph_repo.save(filename=filename, content=data)
    graph_db = await DiGraphRepository.load_from(context.repo.docs.graph_repo.workdir / filename)
    return graph_db
