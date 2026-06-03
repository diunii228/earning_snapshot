# Agent Competitor

Base code cho AI Agents sử dụng LangGraph với multi-LLM support.

## Cấu trúc

```
agent-competitor/
├── graph/
│   ├── base_agent/          # Base workflow với nodes & edges
│   │   ├── base.py          # BaseAgent, BaseState
│   │   └── prompts.py       # Prompt templates
│   └── <your_agent>/        # Thêm agents mới tại đây
├── models/
│   └── llm_factory.py       # Multi-LLM factory (OpenAI, Anthropic, Google, Azure)
├── schemas/                  # Pydantic schemas cho structured output
├── utils/
│   └── setting.py           # Configuration & Settings
└── pyproject.toml
```

## Cài đặt

```bash
pip install -e .
```

## Cấu hình

Tạo file `.env`:

```env
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=xxx
DEFAULT_LLM_PROVIDER=openai
```

## Sử dụng

### Basic

```python
from graph import BaseAgent

agent = BaseAgent()
result = agent.invoke("Hello!")
```

### Switch LLM Provider

```python
from graph import BaseAgent
from utils import LLMProvider

# Anthropic
agent = BaseAgent(provider=LLMProvider.ANTHROPIC)

# OpenAI với custom settings
agent = BaseAgent(provider=LLMProvider.OPENAI, temperature=0.5)
```

### Structured Output

```python
from schemas import ResearchOutput

response = llm.with_structured_output(ResearchOutput).invoke(messages)
```

## Tạo Agent mới

```python
# graph/my_agent/base.py
from dataclasses import dataclass, field
from typing import Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from models import get_llm

@dataclass
class MyState:
    messages: Annotated[list, add_messages] = field(default_factory=list)
    # thêm fields của bạn

class MyAgent:
    def __init__(self, llm=None, provider=None, **kwargs):
        self.llm = llm or get_llm(provider=provider, **kwargs)
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def _build_graph(self):
        builder = StateGraph(MyState)
        
        # Định nghĩa nodes
        builder.add_node("step1", self._step1)
        builder.add_node("step2", self._step2)
        
        # Định nghĩa edges
        builder.add_edge(START, "step1")
        builder.add_edge("step1", "step2")
        builder.add_edge("step2", END)
        
        return builder.compile()

    def _step1(self, state):
        # logic node 1
        return {"messages": [...]}

    def _step2(self, state):
        # logic node 2
        return {"messages": [...]}

    def invoke(self, input_data):
        return self.graph.invoke(input_data)
```

## LLM Providers

| Provider | Env Variable | Model Default |
|----------|--------------|---------------|
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| Anthropic | `ANTHROPIC_API_KEY` | claude-3-5-sonnet-20241022 |
| Google | `GOOGLE_API_KEY` | gemini-1.5-pro |
| Azure | `AZURE_OPENAI_*` | gpt-4 |
