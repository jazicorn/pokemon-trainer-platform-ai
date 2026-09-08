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

    # 1. Setup Resource (Labels the data in Phoenix)
    resource = Resource.create({"openinference.project.name": project_name}) if project_name else None

    # 2. Setup Tracer
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    # 3. Add AI-specific enrichment (if requested)
    if enrich_spans:
        from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor

        tracer_provider.add_span_processor(OpenInferenceSpanProcessor())

    # 4. Connect to Phoenix Server
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))

    # 5. Tell PydanticAI to start watching all agents
    Agent.instrument_all()
