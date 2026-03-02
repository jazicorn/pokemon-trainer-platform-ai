# Welcome to the Pokemon Trainer's Second Brain

This folder exists for one reason: to take you from "I have no idea what any
of this is" to "I understand this system and can contribute to it."

If you have worked with AI systems before and just need to get the project
running, start with [`docs/GETTING_STARTED.md`](../GETTING_STARTED.md)
instead — that is the technical reference doc for people who already know
the concepts.

This folder is for everyone else.

---

## Who This Is For

You belong here if:

- You have never worked in this codebase before
- You have heard terms like "LLM," "agent," or "vector database" but are
  fuzzy on what they actually mean
- You are comfortable with Python but have not worked with AI-powered systems

You do not need to know anything about Pokemon to follow these docs. You also
do not need to know anything about AI. Both are explained from scratch.

---

## What You Will Know When You Are Done

- What the system does and why it was built this way
- What an LLM, an AI agent, RAG, and a vector database are — explained with analogies,
  not academic definitions
- How the four agents in this project divide responsibility and communicate
- How to run the application on your machine and interact with it
- Where every important file lives and what it does
- How to make your first change and verify it works

---

## Reading Order

Work through the files in number order. Each file ends with a pointer to the
next one.

| File | What You Learn | Est. Time |
| --- | --- | --- |
| **You are here** | Orientation | 2 min |
| [01-what-is-this-project.md](01-what-is-this-project.md) | What the system does, why it exists, what you can do with it | 5 min |
| [02-ai-concepts-explained.md](02-ai-concepts-explained.md) | LLMs, agents, RAG, vector databases — from scratch | 15 min |
| [03-system-architecture.md](03-system-architecture.md) | How the four agents work together in this specific project | 10 min |
| [04-setup-and-first-run.md](04-setup-and-first-run.md) | Get it running on your machine and try it yourself | 20 min |
| [05-codebase-tour.md](05-codebase-tour.md) | What every file and folder does | 15 min |
| [06-how-to-contribute.md](06-how-to-contribute.md) | How to make changes, test them, and debug when things break | 10 min |
| [GLOSSARY.md](GLOSSARY.md) | Quick-reference definitions for any term you encounter | As needed |

Total: roughly 75 minutes of reading, plus hands-on setup time in file 04.

---

## A Note on the Pokemon Theme

This project uses Pokemon trading as its domain. That is not just a fun
choice — the problem structure maps cleanly onto real systems that are built
and maintained professionally.

The Trade Advisor is structurally identical to an investment recommendation
engine. The Pokedex Expert is a product catalog specialist. The Trade Market
Analyst is a pricing engine. The Legitimacy Guard is a fraud detection system.

You will see this mapping explicitly in
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) and again in
[03-system-architecture.md](03-system-architecture.md). If you are
presenting this work to someone unfamiliar with Pokemon, the real-world
parallels are the story to tell.

---

**Next: [01-what-is-this-project.md](01-what-is-this-project.md)**
