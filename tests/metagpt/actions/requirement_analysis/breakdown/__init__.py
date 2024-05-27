from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.const import METAGPT_ROOT
from metagpt.utils.common import aread
from metagpt.utils.di_graph_repository import DiGraphRepository
from metagpt.utils.graph_repository import GraphRepository


async def prepare_graph_db(context) -> GraphRepository:
    context.kwargs.ns = Namespaces(namespace="RFC225")
    data = await aread(filename=METAGPT_ROOT / "tests/data/graph_db/breakdown.json")
    filename = context.repo.workdir.name + ".json"
    await context.repo.docs.graph_repo.save(filename=filename, content=data)
    graph_db = await DiGraphRepository.load_from(context.repo.docs.graph_repo.workdir / filename)
    return graph_db
