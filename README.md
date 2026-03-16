# Fly-O-Myte ✈️

The smart travel expense optimizer for Australian families. Tracks the specific trips you are considering, builds its own price history, and tells you one thing: **Book Now, Wait, or Monitor** — with a real explanation of why.

Fly-O-Myte calculates the **True Family Cost** including bags, seat selection, and infant fees, ensuring you never get surprised by "budget" airline add-ons.

---

## 🚀 Quick Start (Web UI)

The recommended way to use Fly-O-Myte is via the modern Web UI.

1. **Install Dependencies**
   ```bash
   make install
   ```

2. **Configure Your Family**
   The first time you run the app, visit the **Family Profile** tab to set up your passengers, origin airport, and school holiday state.

3. **Set API Keys**
   Create a `.env` file and add your SerpAPI key (required for live prices):
   ```bash
   echo "SERPAPI_API_KEY=your_key_here" >> .env
   ```

4. **Launch the App**
   ```bash
   make app
   ```
   Visit **[http://localhost:5173](http://localhost:5173)** to start scouting and tracking journeys.

---

## ✨ Key Features

### 📊 Command Center (Dashboard)
Visual cards for all your tracked trips. High-signal "Buy/Wait/Monitor" badges use vibrant gradients to show urgency. The **Family Savings Gauge** shows exactly how good the current price is compared to historical data.

### 🔍 Smart Scout
Interactive heatmap showing prices across entire months. Features a **Holiday Shield** overlay that highlights school holiday periods (QLD/NSW/VIC/etc.) so you can avoid the peak-pricing traps.

### 🤖 AI Planner
Just tell Fly-O-Myte what you're thinking: *"Bangalore in December to Jan for 25 days"* or *"Japan for cherry blossoms"*. The natural language engine extracts your intent and generates scouting windows instantly.

### ⏱️ Monitoring & Cron
View and manage your automated daily price checks directly from the UI. See system health and trigger manual "Poll All" refreshes with one click.

---

## 💻 CLI Reference

For power users, the `fom` CLI remains fully supported:

```bash
fom setup                                    First-run wizard
fom scout BNE SYD --months jul-2026          Interactive month scouting
fom watch BNE SYD 2026-07-20 2026-07-27     Start tracking a journey
fom status                                   Morning check of all trips
fom flex <id>                                Find ±3 day alternatives
fom plan "Sri Lanka in July"                 Natural language planning
```

---

## 🧮 True Family Cost Calculation

Fly-O-Myte never shows just the base fare. Every price shown is the **True Family Cost**:

```
  Base fare per adult  ×  adults
+ Child fares (estimated based on age)
+ Checked bags  ×  total passengers
+ Seat selection  ×  total passengers
+ Infant lap fees ×  sectors
──────────────────────────────────────
= TRUE FAMILY COST (AUD)
```

The fee rates come from an embedded database of 15+ major airlines including Qantas, Virgin, Jetstar, Singapore Airlines, and Emirates.

---

## 🛠️ Data & Privacy

All data lives locally on your machine in `~/.fly-o-myte/`:
- `config.yaml`: Your family profile.
- `fly-o-myte.db`: SQLite database of trip history.
- `analytics/`: DuckDB store for route statistics.

No personal payment data is ever stored.

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.
