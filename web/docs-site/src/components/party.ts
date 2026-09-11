// The five agents (src/agents/*.py at the repo root) mapped to their type token.
// Shared by PartyChrome.astro (header strip) and the home page's agent cards.
export interface PartyMember {
  initials: string;
  type: "dragon" | "psychic" | "electric" | "dark" | "fighting";
  name: string;
  role: string;
}

export const PARTY: PartyMember[] = [
  { initials: "Ad", type: "dragon", name: "Trade Advisor", role: "orchestrator" },
  { initials: "Px", type: "psychic", name: "Pokedex Expert", role: "RAG knowledge" },
  { initials: "Mk", type: "electric", name: "Market Analyst", role: "forecasting" },
  { initials: "Lg", type: "dark", name: "Legitimacy Guard", role: "fraud / PII" },
  { initials: "Bt", type: "fighting", name: "Battle Strategy Advisor", role: "viability evals" },
];
