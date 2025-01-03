import pytest

from metagpt.configs.compress_msg_config import CompressType
from metagpt.configs.llm_config import LLMConfig
from metagpt.provider.base_llm import BaseLLM

TEST_MODELS_GPT = [
    "gpt-4o-2024-05-13",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4o-mini-2024-07-18",
    "gpt-4-0125-preview",
    "gpt-4-turbo-preview",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-4-0613",
    "gpt-4-32k",
    "gpt-4-32k-0613",
    "gpt-3.5-turbo-0125",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-instruct",
    "gpt-3.5-turbo-16k",
    "gpt-3.5-turbo-0613",
    "gpt-3.5-turbo-16k-0613",
    "text-embedding-ada-002",
    "openai/gpt-4",  # start, for openrouter
    "openai/gpt-4-turbo",
    "openai/gpt-4o",
    "openai/gpt-4o-2024-05-13",
    "openai/gpt-4o-mini",
]
TEST_MODELS = [
    "glm-3-turbo",
    "glm-4",
    "gemini-pro",
    "moonshot-v1-8k",
    "open-mistral-7b",
    "open-mixtral-8x7b",
    "mistral-small-latest",
    "claude-3-sonnet-20240229",
    "yi-34b-chat-0205",
    "anthropic/claude-3.5-sonnet",
    "google/gemini-pro-1.5",
    "deepseek/deepseek-coder",
    "deepseek-coder",
    "deepseek-ai/DeepSeek-Coder-V2-Instruct",  # siliconflow
]
TEST_MODELS_MIX = ["anthropic/claude-3.5-sonnet", "gpt-4-32k-0613"]


class MockBaseLLM(BaseLLM):
    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()

    async def _achat_completion(self, messages: list[dict], timeout=3):
        pass

    async def acompletion(self, messages: list[dict], timeout=3):
        pass

    async def _achat_completion_stream(self, messages: list[dict], timeout: int = 3) -> str:
        pass


@pytest.mark.parametrize(
    "test_case",
    [
        {
            "content": "Hello, world! This is a test message.",
            "target_tokens": 3,
            "from_end": False,
            "description": "Short text truncated from start",
        },
        {
            "content": "Hello, world! This is a test message.",
            "target_tokens": 3,
            "from_end": True,
            "description": "Short text truncated from end",
        },
        {
            "content": "Hello, world! " * 100,
            "target_tokens": 10,
            "from_end": False,
            "description": "Long text truncated from start",
        },
        {
            "content": "Hello, world! " * 100,
            "target_tokens": 10,
            "from_end": True,
            "description": "Long text truncated from end",
        },
    ],
)
def test_get_content_under_limit_token(test_case):
    """Test various scenarios for get_content_under_limit_token function"""
    base_llm = MockBaseLLM()
    base_llm.config.model = "gpt-4-32k"

    truncated = base_llm.get_content_under_limit_token(
        test_case["content"], target_token_count=test_case["target_tokens"], from_end=test_case["from_end"]
    )
    token_count = base_llm.count_tokens([{"role": "user", "content": truncated}])

    print(
        f"\n{test_case['description']} - original: '{test_case['content'][:50]}...' -> "
        f"truncated: '{truncated}' (tokens: {token_count})"
    )

    assert isinstance(truncated, str)
    assert len(truncated) <= len(test_case["content"])
    assert token_count == test_case["target_tokens"]


@pytest.mark.parametrize("model", TEST_MODELS)
def test_count_tokens_o_model(model):
    base_llm = MockBaseLLM()
    base_llm.config.model = model
    content = "Hello, world! This is a test message."
    token_count = base_llm.count_tokens([{"role": "user", "content": content}])
    print(f"token count: {token_count}")
    assert token_count == 18


@pytest.mark.parametrize("model", TEST_MODELS_GPT)
def test_count_tokens_GPT(model):
    base_llm = MockBaseLLM()
    base_llm.config.model = model
    content = "Hello, world! This is a test message."
    token_count = base_llm.count_tokens([{"role": "user", "content": content}])
    print(f"token count: {token_count}")
    assert token_count == 10


@pytest.mark.parametrize("compress_type", list(CompressType))
@pytest.mark.parametrize("model", TEST_MODELS_MIX)
def test_compress_messages_no_effect(compress_type, model):
    base_llm = MockBaseLLM()
    base_llm.config.model = model
    messages = [
        {"role": "system", "content": "first system msg"},
        {"role": "system", "content": "second system msg"},
    ]
    for i in range(5):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    compressed = base_llm.compress_messages(messages, compress_type=compress_type)
    # should take no effect for short context
    assert compressed == messages


@pytest.mark.parametrize("compress_type", CompressType.cut_types())
def test_compress_messages_long(compress_type):
    base_llm = MockBaseLLM()
    base_llm.config.model = "LLM_test"
    max_token_limit = 100

    messages = [
        {"role": "system", "content": "first system msg"},
        {"role": "system", "content": "second system msg"},
    ]
    for i in range(10):
        messages.append({"role": "user", "content": f"u{i}" * 10})  # ~2x10x0.5 = 10 tokens
        messages.append({"role": "assistant", "content": f"a{i}" * 10})
    compressed = base_llm.compress_messages(messages, compress_type=compress_type, max_token=max_token_limit)

    print(compressed)
    print(len(compressed))
    assert 3 <= len(compressed) < len(messages)
    assert compressed[0]["role"] == "system" and compressed[1]["role"] == "system"
    assert compressed[2]["role"] != "system"


@pytest.mark.parametrize("compress_type", CompressType.cut_types())
def test_compress_messages_long_no_sys_msg(compress_type):
    base_llm = MockBaseLLM()
    base_llm.config.model = "test_llm"
    max_token_limit = 100

    messages = [{"role": "user", "content": "1" * 10000}]
    compressed = base_llm.compress_messages(messages, compress_type=compress_type, max_token=max_token_limit)

    print(compressed)
    assert compressed
    assert len(compressed[0]["content"]) < len(messages[0]["content"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
