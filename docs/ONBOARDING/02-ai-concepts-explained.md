# AI Concepts Explained

This is the most important file in the onboarding folder. Read it before
anything else about the system's architecture.

After reading this file you will understand every AI concept you will encounter
in this codebase — not just what the terms mean, but why they exist and how
they connect to each other. No prior AI knowledge required.

---

## 1. What Is an LLM (Large Language Model)?

### What it is NOT

An LLM is not a database. It does not look up answers. It does not have a
table of facts it searches through. If you ask it "what are Charizard's base
stats?" it does not retrieve a row from a table.

### What it IS

An LLM is a system trained on an enormous amount of text — web pages, books,
code, documentation — that learned the statistical patterns in that text. It
learned what ideas tend to follow other ideas, what words tend to appear
together, what a reasonable answer to a question looks like.

When you ask it something, it generates a response word-by-word (technically
token-by-token), each token being its best prediction of what should come next
given everything before it.

Think of it as very sophisticated autocomplete. Not "next word" autocomplete —
"next coherent paragraph of thoughtful response" autocomplete.

### The critical limitation

An LLM can only use information it absorbed during training. It does not know:

- What is in your Pokemon collection
- What trades happened on the platform last week
- Anything that happened after its training cutoff date

And because it is generating predictions rather than looking things up, it can
produce answers that sound completely correct but are factually wrong. This is
called **hallucination**. A model might confidently give you Dragonite's stats
with slightly wrong numbers, or invent a rule about ball legality that does not
exist in the game.

### LLMs in this project

The LLM (Claude by default, but also GPT-4 and Gemini are supported) is the
reasoning engine inside each agent. When an agent produces a response, the LLM
is the part that decides what to say. But critically, it does not do it alone
— it has access to tools that give it real data to reason over.

---

## 2. What Is an AI Agent?

### The core idea

An agent is an LLM that has been given the ability to take actions, not just
produce text. Specifically, it can call **tools** — regular Python functions —
and use their results before producing its final answer.

### A concrete example

Imagine asking a plain LLM: "What is the weather in Tokyo right now?"

A plain LLM has two options: make something up, or say it does not know.
Either way, the answer is not actually the current weather.

An agent LLM with a `get_weather(city)` tool works differently:

```text
You: "What is the weather in Tokyo right now?"

Agent decides: I need real data for this. I will call get_weather("Tokyo").
Tool returns: {"temp": 18, "condition": "Partly cloudy", "humidity": 62}
Agent now responds: "It is currently 18°C and partly cloudy in Tokyo with 62% humidity."
```

The LLM decided to call the tool, decided what arguments to pass, received the
result, and incorporated it into a grounded, accurate response.

### The agent loop

```text
User input
    ↓
LLM reads input and decides: do I need more information?
    ↓ (if yes)
LLM calls a tool with specific arguments
    ↓
Tool runs (a real Python function) and returns a result
    ↓
LLM reads the result and decides: do I need more information?
    ↓ (repeat if needed, stop when ready)
LLM produces final response using the real data it collected
    ↓
Response shown to user
```

The developer defines which tools exist and what they do. The LLM decides when
to call them, which one to call, and what to do with the results.

### Agents in this project

Every agent has a set of tools. The Pokedex Expert has three:
`search_pokemon`, `get_type_effectiveness`, and `get_my_collection`. When you
ask "what fire types do I have?", the agent calls `get_my_collection()` to get
your actual collection from the JSON file. The LLM reasons over real data
rather than guessing what you might own.

In the code, tools are regular Python `async` functions decorated with
`@agent.tool` (more on this in [05-codebase-tour.md](05-codebase-tour.md)).

---

## 3. What Is a Multi-Agent System?

### One agent is not enough

A single agent with 20 tools covering every possible task quickly becomes
unreliable. The LLM gets "decision fatigue" — with too many options, it
becomes less precise about which tool to use and when. Its responses get less
consistent.

There is also a quality problem: a generalist agent is mediocre at everything.
A specialist agent that only handles one domain can have a finely tuned system
prompt, exactly the right tools, and consistently high accuracy.

### Enter specialists

Think of a hospital. When you check in, a generalist doctor sees you first.
They assess the situation and route you: "you need a cardiologist for the
heart issue, and a radiologist to interpret the scan." Each specialist is
deeply expert in their domain. The generalist synthesizes their findings and
gives you the overall picture.

Multi-agent systems work the same way. One agent is the coordinator
(orchestrator). Other agents are specialists. The orchestrator delegates to
specialists and synthesizes their outputs.

### Why this is better than one big agent

- **Fewer hallucinations**: each agent has a narrow scope, so the LLM is less
  likely to wander into territory it does not know well
- **Easier to test**: you can test each agent independently with focused test
  cases
- **Easier to debug**: when something goes wrong, you can see exactly which
  agent produced the bad output
- **Easier to improve**: upgrading the Pokedex Expert does not require
  touching the Market Analyst

### The pattern used here

This project uses **hierarchical delegation**: one orchestrator (the Trade
Advisor) that routes to worker agents (Pokedex Expert, Market Analyst,
Legitimacy Guard). The orchestrator never touches data directly — all data
access happens through its workers.

### Multi-agent in this project

When you type `trade alakazam for gengar`, the Trade Advisor does not look up
Alakazam's stats itself. It calls the Pokedex Expert with a tool called
`get_pokemon_info("alakazam")`. The Pokedex Expert then looks up the stats
from ChromaDB and returns the result. The Trade Advisor receives that result
and incorporates it — same as the weather example, just between agents instead
of between an agent and a simple function.

---

## 4. What Is RAG (Retrieval Augmented Generation)?

### The problem

LLMs are trained on text from the internet. They have general knowledge of
Pokemon from walkthroughs, wikis, and strategy guides. But:

- They may have the wrong exact stats (wikis get edited, different game
  generations have different values)
- They do not know your specific collection
- They do not know what the trading platform's transaction history looks like
- Their training data has a cutoff date

RAG is the standard solution to this.

### What RAG does

Before asking the LLM to answer, **retrieve relevant documents from a
knowledge base and include them in the context the LLM sees**.

The LLM is not guessing anymore — it is reading real, specific, up-to-date
data and reasoning over it.

### The two phases

**Phase 1 — Ingestion (happens once at setup):**

1. Get your data (in this project: fetch 40+ Pokemon from the PokeAPI)
2. Store it in a searchable knowledge base (ChromaDB)

**Phase 2 — Retrieval (happens at query time):**

1. User asks a question: "What are Dragonite's weaknesses?"
2. Search the knowledge base for documents about Dragonite
3. Include those documents in the prompt context
4. LLM answers the question using real, specific data

### Why it dramatically reduces hallucination

The LLM is not being asked "tell me about Dragonite from memory." It is being
asked "given these specific documents about Dragonite, answer this question."
It is reasoning over evidence, not guessing.

The project measured this directly: RAG-enabled answers were **15.8% more
accurate** than answers without RAG on Pokemon knowledge questions. On complex
multi-step questions (e.g., "What is Pikachu's evolution ancestor?"), the
accuracy improvement was 100% — the model got all of those right with RAG and
none without.

See [docs/REFERENCE/EVAL_RESULTS.md](../REFERENCE/EVAL_RESULTS.md) for the full evaluation
results.

### RAG in this project

The Pokedex Expert agent uses RAG. When it calls
`search_pokemon("dragonite")`, that function queries ChromaDB and returns the
most relevant stored documents about Dragonite. The agent then reasons over
those documents to answer your question.

---

## 5. What Is a Vector Database?

### The search problem

RAG requires a knowledge base you can search. But how do you search text
effectively?

Keyword search has a fundamental flaw: it matches exact words. If you ask
"what are Dragonite's resistances?" and the stored document says "Dragonite
resists Electric and Steel type moves," a keyword search on "resistances" will
miss it.

Vector databases solve this.

### How vector search works

An **embedding model** is a system that converts text into a list of numbers
— called a **vector** or **embedding**. Two pieces of text that mean similar
things produce similar number lists. Text with unrelated meaning produces very
different number lists.

For example, these two sentences would produce similar vectors:

- "Dragonite resists Electric attacks"
- "Dragonite takes reduced damage from Electric type moves"

They share almost no words, but they mean the same thing.

To search, you:

1. Convert your query into a vector using the same embedding model
2. Ask the database: "which stored document vectors are closest to this query
  vector?"
3. Return the documents whose vectors are nearest

This is called **semantic search** — search by meaning, not by words.

### The library analogy

Imagine a library organized not by title keyword but by subject matter. You
say "I want books about sea creatures" and the library returns books about
ocean wildlife, marine biology, and underwater ecosystems — even if none of
them have the word "sea" in the title. That is the difference between keyword
search and semantic search.

### Vector databases in this project

ChromaDB is the vector database. When Pokemon data is ingested at setup time,
each Pokemon's stats and description are converted to a vector and stored.
When the Pokedex Expert calls
`search_pokemon("electric type pokemon with high speed")`, ChromaDB converts
that query to a vector and returns the Pokemon documents whose vectors are
most similar.

**One important note about this project's setup:** By default, the project
uses a hash-based embedding function rather than a real semantic embedding
model. This is a deliberate trade-off — it avoids requiring an external
embedding service for basic use. Hash-based embeddings are deterministic and
fast but do not capture semantic meaning, so searches are more like advanced
keyword matching. For true semantic search, set `USE_OLLAMA_EMBEDDINGS=true`
in your environment and have Ollama running. This is documented in
[`docs/GETTING_STARTED.md`](../GETTING_STARTED.md).

---

## 6. How All of This Connects

Here is everything from sections 1–5 mapped onto a single request through
this project:

```text
You type: "trade pikachu for charizard"
                    │
                    ▼
          ┌──────────────────┐
          │  Trade Advisor   │  ← Agent (LLM + tools)
          │  (Orchestrator)  │  ← Decides what data it needs
          └────────┬─────────┘
                   │
         ┌─────────┼──────────────┐
         ▼         ▼              ▼
  get_pokemon   get_market    get_user
  _info(...)    _data(...)    _context()
         │         │              │
         ▼         ▼              ▼
  ┌────────────┐  ┌─────────────┐  ┌──────────┐
  │  Pokedex   │  │   Market    │  │  SQLite  │
  │  Expert    │  │   Analyst   │  │  memory  │
  │  (Agent)   │  │   (Agent)   │  └──────────┘
  └─────┬──────┘  └──────┬──────┘
        │                │
        ▼                ▼
  search_pokemon()    get_market_
  on ChromaDB ← RAG   forecast()
        │              on trade
        ▼              history JSON
  Returns Pikachu's
  actual stats and          │
  type data                 ▼
        │          Returns demand
        │          ratio, momentum,
        │          sentiment
        │                │
        └────────────────┘
                    │
                    ▼
          Trade Advisor synthesizes:
          - Pikachu stats vs Charizard stats
          - Market demand comparison
          - Your personal goals (from memory)
          - Legitimacy check result
                    │
                    ▼
          "Charizard has stronger market demand
          and better competitive coverage for
          your goal of building a fire-type
          team. This trade favors you. Recommend
          accepting."
```

Every step involves real data. No guessing.

---

## Summary

| Concept | What It Is | Why It Matters Here |
| --- | --- | --- |
| LLM | Text pattern-completion engine | The reasoning core inside each agent |
| AI Agent | LLM + Python tools it can call | Grounds answers in real data |
| Multi-agent system | Multiple specialized agents coordinated by one orchestrator | Reduces hallucination, easier to test and debug |
| RAG | Retrieve real documents before asking the LLM | Pokemon stats are accurate, not hallucinated |
| Vector database | Semantic search over stored documents | Finds relevant documents even when words do not match |

---

**Next: [03-system-architecture.md](03-system-architecture.md)**
