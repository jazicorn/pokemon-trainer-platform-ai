import { defineCollection, z } from "astro:content";
import { docsLoader } from "@astrojs/starlight/loaders";
import { docsSchema } from "@astrojs/starlight/schema";

// The eight Pokemon-type tokens (ROADMAP.md Phase 10) a page can carry as a badge, set by
// scripts/docs_prepare.py during content generation rather than authored by hand per-page.
export const POKEMON_TYPES = [
  "dragon",
  "psychic",
  "electric",
  "dark",
  "fighting",
  "steel",
  "grass",
  "fire",
] as const;

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        pokemonType: z.enum(POKEMON_TYPES).optional(),
      }),
    }),
  }),
};
