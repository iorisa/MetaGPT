"""Utilities for RAG."""

from llama_index.core.indices.utils import default_parse_choice_select_answer_fn

from metagpt.logs import logger


def parse_choice_select_answer_fn(
    answer: str, num_choices: int, raise_error: bool = False
) -> tuple[list[int], list[float]]:
    """Parse the answer of choice select.

    Override the default_parse_choice_select_answer_fn to handle exceptions.
    Log error and returns empty lists if parsing fails.
    """

    try:
        return default_parse_choice_select_answer_fn(answer, num_choices, raise_error)
    except Exception as e:
        logger.error(
            f"LLM Ranker failed to parse choice select answer, will return empty lists. Answer: {answer[:200]!r}, Error: {str(e)}"
        )
        return [], []
