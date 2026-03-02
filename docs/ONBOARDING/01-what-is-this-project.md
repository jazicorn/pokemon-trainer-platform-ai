# What Is This Project?

No jargon in this file. This is just: what does the system do, why does it
exist, and what can you actually do with it.

---

## The Problem It Solves

Imagine you are a Pokemon trainer and someone offers you a trade: their Gengar
for your Alakazam.

To decide if that is a good trade, you need to know several things at once:

1. **Stats and capabilities**: Is Gengar actually a strong Pokemon? What are its
   weaknesses? How does it compare to Alakazam?
2. **Market demand**: Do other trainers want Gengar right now, or is it easy to
   come by? Is the demand for Alakazam rising or falling?
3. **Legitimacy**: Is this Gengar actually a legitimate Pokemon, or has it been
   hacked into the game with illegal attributes?
4. **Your personal goals**: Are you trying to build a specific team type? Is
   Alakazam one you want to keep?

No single source answers all of these. The stats live in game data. The demand
data lives in the trading platform's transaction history. The legitimacy rules
are buried in game mechanics documentation. Your personal goals are in your
head.

This system answers all four questions simultaneously and synthesizes them into
a recommendation.

---

## What You Can Actually Do With It

The application is a command-line interface (CLI). You type commands and get
responses. Here is what it looks like:

```text
============================================================
       Pokemon Trainer's Second Brain
============================================================

TRADE
  trade    {your-pokemon} for {their-pokemon}  Evaluate a trade
  suggest                                       Get AI recommendations
  offer    {pokemon} to {user} for {theirs}    Send an offer
  offers   / offers sent                        View inbox or sent
  accept   / decline  {offer-id}               Respond to an offer

RESEARCH
  pokedex  {query}   Lookup stats, types & abilities
  market   {query}   Platform demand & trends

PROFILE
  status   View your trainer status & collection
  prefs    View your trading goals & preferences
  history  Recent advisor insights
```

### Evaluating a trade

```text
> trade alakazam for gengar
```

The system will look up both Pokemon, check current market demand for each,
verify that the offered Pokemon appears legitimate, factor in your personal
trading goals, and return a recommendation with reasoning. It will tell you
whether the trade favors you, is roughly fair, or favors the other party —
and explain why.

### Getting market intelligence

```text
> market What Pokemon are trending right now?
```

Returns the Pokemon with the most trade activity on the platform over the
past 30 days, along with whether demand is rising (Bullish) or falling
(Bearish).

```text
> market How is Dragonite doing?
```

Returns Dragonite's demand ratio (how many people want it vs. how many are
offering it), momentum score, and a market sentiment classification.

### Looking up Pokemon data

```text
> pokedex What are Charizard's weaknesses?
> pokedex Compare Mewtwo and Lugia stats
> pokedex What fire types do I have?
```

The last one queries your actual collection. The system knows what you own.

### Managing trade offers

```text
> offers
```

Shows your pending incoming trade offers. For each one, the system has
already done a legitimacy check and shows you AI analysis alongside the raw
offer details.

```text
> accept 3
```

Accepts offer number 3. The system will confirm with you before actually
executing the acceptance.

### Getting proactive suggestions

```text
> suggest
```

Based on your trading goals and what other trainers are offering, the system
generates a list of outgoing trade offers you could send. It presents them
to you and only sends them if you confirm.

---

## Why This Is More Than a Chatbot

A plain chatbot (like asking ChatGPT "should I trade Alakazam for Gengar?")
has two fundamental problems:

**It only knows what it learned during training.** It does not know your
specific collection, it does not know what trades happened on the platform
last week, and it does not know that you are currently trying to complete a
specific team. It will give you a generic answer.

**It can make things up.** AI language models sometimes generate
plausible-sounding but wrong answers — especially for specific factual
questions like exact Pokemon stats or which PokeBalls a legendary can
legally come from. This is called "hallucination" and it is a known
limitation.

This system solves both problems:

- It gives each agent access to real data sources (game data from an API,
  actual platform transaction history, hardcoded legitimacy rules)
- It uses multiple specialized agents instead of one general one, which
  dramatically reduces the chance of any single agent going off-rails

More on how that works in [02-ai-concepts-explained.md](02-ai-concepts-explained.md).

---

## The Real-World Version of This System

The Pokemon theme is the domain. The architecture is generic and transferable.

| This Project | Real-World Equivalent |
| --- | --- |
| Pokemon Trade Advisor | Investment recommendation engine |
| Pokedex Expert | Product catalog / specs database |
| Trade Market Analyst | Market research / pricing engine |
| Legitimacy Guard | Fraud detection system |
| User preferences + history | Customer profile / CRM data |
| "Should I trade X for Y?" | "Should I buy or sell this asset?" |
| Platform trade history | Transaction data / order book |

The same architecture pattern is used in production at companies like
Robinhood (personalized investment guidance), eBay/StockX (marketplace
pricing based on supply and demand), Netflix (multi-factor recommendation
engines), and Salesforce (CRM systems that learn from interaction history).

---

## What This Project Is NOT

- It does not connect to any real Pokemon game. No saves are read, no game
  data is modified.
- The "platform trade history" is mock data generated at setup time, not
  real transactions.
- The user collection is a JSON file, not connected to any game or service.
- This is a self-contained demonstration system built to showcase
  multi-agent AI architecture.

---

**Next: [02-ai-concepts-explained.md](02-ai-concepts-explained.md)**
