from metagpt.actions.requirement_analysis.namespaces import Namespaces
from metagpt.const import METAGPT_ROOT
from metagpt.utils.common import aread


async def prepare_graph_db(context):
    context.kwargs.ns = Namespaces(namespace="RFC145")
    graph_db_filename = METAGPT_ROOT / "tests/data/graph_db/requirement_analyze.json"
    graph_db = await aread(filename=graph_db_filename, encoding="utf-8")
    await context.repo.docs.graph_repo.save(filename=context.repo.workdir.name + ".json", content=graph_db)
