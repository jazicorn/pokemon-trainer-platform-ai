# Adding Arize Phoenix to a PydanticAI Project

## Introduction

This guide walks you through setting up **Arize Phoenix**, an open-source AI observability platform, to monitor and debug your PydanticAI agents. By the end, you'll have traces flowing from your agents into Phoenix for visualization and debugging.

---

## Background: What's Actually Happening?

Before diving in, here's the 30-second version of what we're setting up:

1. **PydanticAI** emits **traces** (detailed records of agent execution)
2. Traces are sent using **OpenTelemetry** (an industry-standard observability protocol)
3. **Phoenix** receives and visualizes these traces

### Key Concepts

| Component | What It Does |
|-----------|--------------|
| **TracerProvider** | Central configuration object that manages trace creation |
| **SpanProcessor** | Processes spans before export (can transform, filter, or batch) |
| **SpanExporter** | Sends spans to a backend (Phoenix) via OTLP protocol |
| **Span** | A unit of work—an LLM call, a tool invocation, an agent run |
| **Trace** | A tree of related spans representing a complete operation |

### Semantic Conventions: OTel GenAI vs OpenInference

There are two ways to format AI/LLM trace data:

| Convention | Used By | Phoenix Support |
|------------|---------|-----------------|
| **OTel GenAI** | Industry standard, PydanticAI native | Good — traces display correctly |
| **OpenInference** | Arize ecosystem (Phoenix, Arize AX) | Best — richer visualizations, conversation threading, session attribution |

Both work with Phoenix. **We recommend OpenInference** for the best Phoenix experience. Use standard OTel if you need portability to other backends (Jaeger, Datadog, Honeycomb, etc.).

---

## Running Phoenix

You need Phoenix running to receive traces.

**Recommended** (using uvx):

We don't need Phoenix installed into our agent's virtual environment; we just need it running as a standalone service. The `uvx` command launches it in a temporary virtual environment:

```bash
uvx arize-phoenix serve
```

**Alternative** (using pip):

If you want to install Phoenix into a specific virtual environment:

```bash
uv pip install arize-phoenix
uv run arize-phoenix serve
```

**Alternative** (using Docker):

```bash
docker run -d -p 6006:6006 arizephoenix/phoenix:latest
```

### Accessing Phoenix

Phoenix will be available at **http://127.0.0.1:6006**. Open this in your browser to see the UI.

---

## Setup

### Install Dependencies

```bash
uv pip install opentelemetry-sdk opentelemetry-exporter-otlp openinference-instrumentation-pydantic-ai
```

> **Note:** If you only need standard OTel (no OpenInference enrichment), you can skip `openinference-instrumentation-pydantic-ai`.

### The `init_telemetry` Function

Add this function to your project. It handles all the OpenTelemetry configuration for Phoenix:

```python
from pydantic_ai import Agent


def init_telemetry(
    project_name: str | None = None,
    endpoint: str = "http://127.0.0.1:6006",
    enrich_spans: bool = True,
) -> None:
    """Initialize OpenTelemetry tracing for Phoenix.

    Args:
        project_name: Project name shown in Phoenix UI.
        endpoint: Phoenix server base URL.
        enrich_spans: If True, add OpenInference span enrichment for richer
            Phoenix visualizations. If False, use standard OTel format.
    """
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    # Create and register a TracerProvider (Phoenix uses this attribute for project routing)
    resource = (
        Resource.create({"openinference.project.name": project_name})
        if project_name
        else None
    )
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    # Optionally enrich spans with OpenInference attributes (must be added before exporter)
    if enrich_spans:
        from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor

        tracer_provider.add_span_processor(OpenInferenceSpanProcessor())

    # Export spans to Phoenix
    tracer_provider.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )

    # Enable PydanticAI instrumentation
    Agent.instrument_all()
```

### Complete Example

```python
import asyncio
from pydantic_ai import Agent


def init_telemetry(
    project_name: str | None = None,
    endpoint: str = "http://127.0.0.1:6006",
    enrich_spans: bool = True,
) -> None:
    """Initialize OpenTelemetry tracing for Phoenix."""
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    resource = (
        Resource.create({"openinference.project.name": project_name})
        if project_name
        else None
    )
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    if enrich_spans:
        from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor

        tracer_provider.add_span_processor(OpenInferenceSpanProcessor())

    tracer_provider.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )

    Agent.instrument_all()


# Initialize telemetry BEFORE creating agents
init_telemetry(project_name="weather-app")

agent = Agent(
    "anthropic:claude-sonnet-4-5",
    instructions="You are a helpful weather assistant.",
)


@agent.tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is sunny and 22°C"


async def main():
    result = await agent.run("What's the weather in Melbourne?")
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
```

Run this, then open http://127.0.0.1:6006 to see your trace.

---

## Choosing Between OpenInference and Standard OTel

The `enrich_spans` parameter controls which semantic convention is used:

### `enrich_spans=True` (Recommended)

Uses OpenInference semantic conventions for richer Phoenix visualizations:

- Conversation threading
- Session attribution
- User tracking
- Enhanced span metadata

```python
init_telemetry(project_name="my-app", enrich_spans=True)
```

### `enrich_spans=False`

Uses standard OTel GenAI format. Choose this if you need portability to other observability backends (Jaeger, Datadog, Honeycomb, etc.):

```python
init_telemetry(project_name="my-app", enrich_spans=False)
```

### Summary

| Setting | Semantic Convention | Phoenix Features | Portability |
|---------|---------------------|------------------|-------------|
| `enrich_spans=True` | OpenInference | Best (threading, sessions) | Arize ecosystem |
| `enrich_spans=False` | OTel GenAI | Good | Any OTel backend |

---

## Why Not Use `phoenix.otel.register()`?

Phoenix provides a convenience function `register()` that simplifies setup for many libraries. However, **it doesn't work well with PydanticAI** because:

1. **Processor order matters.** The `OpenInferenceSpanProcessor` must enrich spans *before* the exporter sends them. `register()` adds its exporter internally, so we can't insert our processor before it.

2. **`auto_instrument=True` doesn't help.** Unlike libraries that OpenInference auto-patches (OpenAI, LangChain), PydanticAI's OpenInference package is a span processor, not an auto-instrumentor. PydanticAI has its own instrumentation via `Agent.instrument_all()`.

The manual setup shown above gives us full control over processor order.

---

## Advanced Configuration

### Using BatchSpanProcessor (Production)

For production, use `BatchSpanProcessor` instead of `SimpleSpanProcessor` for better performance:

```python
from opentelemetry.sdk.trace.export import BatchSpanProcessor

tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
)
```

Spans are buffered and sent in batches, which is more efficient but introduces a slight delay before traces appear in Phoenix.

### Graceful Shutdown

When using `BatchSpanProcessor`, ensure buffered spans are flushed before your application exits:

```python
from opentelemetry import trace

# At application shutdown
tracer_provider = trace.get_tracer_provider()
if hasattr(tracer_provider, "shutdown"):
    tracer_provider.shutdown()
```

### Adding Session and User Context

OpenInference provides a context manager to attach metadata to traces:

```python
from openinference.instrumentation import using_attributes


async def handle_user_message(user_id: str, session_id: str, message: str):
    with using_attributes(
        session_id=session_id,
        user_id=user_id,
        metadata={"environment": "development"},
    ):
        result = await agent.run(message)
        return result.output
```

This metadata appears in Phoenix and makes it easy to filter traces by user, session, or custom attributes.

---

## Troubleshooting

### Traces not appearing in Phoenix

1. **Is Phoenix running?** Check that http://127.0.0.1:6006 loads in your browser.

2. **Initialization order?** Call `init_telemetry()` *before* creating any agents or making LLM calls.

3. **Missing `Agent.instrument_all()`?** This enables PydanticAI's instrumentation.

### Empty or minimal trace data

By default, PydanticAI includes message content in traces. If you're seeing empty content:

```python
from pydantic_ai.models.instrumented import InstrumentationSettings

Agent.instrument_all(InstrumentationSettings(include_content=True))
```

### Traces appearing but not linked together

This usually means the TracerProvider wasn't set before agents were created. Ensure `init_telemetry()` is called at application startup, before any agent code runs.

---

## References

- [Arize Phoenix Documentation](https://arize.com/docs/phoenix/)
- [PydanticAI Instrumentation API](https://ai.pydantic.dev/api/models/instrumented/)
- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/languages/python/)
- [OpenInference Semantic Conventions](https://arize-ai.github.io/openinference/)
- [OpenInference PydanticAI Instrumentation](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-pydantic-ai)
