"""Set of default prompts."""

from llama_index.core.prompts.base import PromptTemplate
from llama_index.core.prompts.prompt_type import PromptType

DEFAULT_CHOICE_SELECT_PROMPT_TMPL = """
You are a highly efficient assistant, tasked with evaluating a list of documents to a given question.

I will provide you with a question with a list of documents. Your task is to respond with the numbers of the documents you should consult to answer the question, in order of relevance, as well as the relevance score. 


## Question
{query_str}

## Documents
{context_str}

## Format Example
Doc: 9, Relevance: 7
Doc: 3, Relevance: 5

## Instructions
- Understand the question.
- Evaluate the relevance between the question and the documents.
- The relevance score is a number from 1-10 based on how relevant you think the document is to the question.
- Do not include any documents that are not relevant to the question.
- If none of the documents provided contain information that directly answers the question, simply respond with "no relevant documents".

## Required Output Format
- ONLY output in the exact format: Doc: [number], Relevance: [score]
- DO NOT include any other text or explanations
- Multiple relevant documents should be on separate lines

## Action
Follow instructions, output ONLY the doc numbers and relevance scores in the required format.
"""

DEFAULT_CHOICE_SELECT_PROMPT = PromptTemplate(DEFAULT_CHOICE_SELECT_PROMPT_TMPL, prompt_type=PromptType.CHOICE_SELECT)
