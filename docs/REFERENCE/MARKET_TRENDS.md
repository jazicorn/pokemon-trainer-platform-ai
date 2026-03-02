# 📈 Pokémon Market Trends & Forecasting

This project simulates a live stock market environment by analyzing platform-wide trade data. It goes
beyond simple counting by using **Momentum Analysis** to forecast future trading behavior.

## 🔍 Market Indicators

The **Market Analyst** agent uses three primary metrics to determine market health:

### 1. The Price Proxy (Demand Ratio)

The core "ticker price" is calculated as $Requested / Offered$.

* **Bullish (> 1.5):** High demand, limited supply. Value is rising.
* **Bearish (< 0.8):** Oversupply, low demand. Value is falling.

### 2. Market Momentum (The Forecast)

We calculate momentum by comparing the **7-day demand ratio** (Short-term) against the **30-day demand
ratio** (Long-term).

$$Momentum = \left( \frac{Ratio_{7d} - Ratio_{30d}}{Ratio_{30d}} \right) \times 100$$

* **Sentiment: Bullish** (Momentum > +15%): Demand is accelerating; a "Strong Buy."
* **Sentiment: Bearish** (Momentum < -15%): Demand is cooling; a "Sell/Trade Away."
* **Sentiment: Stable** (-15% to +15%): Market value is holding steady.

### 3. Asset Liquidity (Success Rate)

The percentage of completed vs. expired trades.

* **High Liquidity (> 70%):** "Blue Chip" assets that move quickly.
* **Low Liquidity (< 30%):** Volatile or niche assets that may stall on the trade board.

## 🤖 Multi-Agent Intelligence

The **Trade Advisor** (Orchestrator) detects market-related keywords like "trend", "bullish",
"bearish", and "sentiment" in your queries and automatically routes them to the **Market Analyst's**
predictive tools.
