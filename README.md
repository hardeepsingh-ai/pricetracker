# PriceTracker — AI-Powered Convenience Store Price Intelligence Platform

<p align="center">
  <strong>Real-time price comparison, consumer behaviour analytics, and customer engagement tools built for independent UK convenience stores.</strong>
</p>

<p align="center">
  <a href="https://pricetracker-emao.onrender.com">Live Demo</a> · 
  <a href="#features">Features</a> · 
  <a href="#architecture">Architecture</a> · 
  <a href="#getting-started">Getting Started</a>
</p>

---

## The Problem

Independent convenience store owners in the UK have **no affordable way to compare their prices** against major supermarkets. They rely on guesswork, manual competitor visits, or expensive trade subscriptions. This puts them at a disadvantage when customers increasingly expect competitive pricing.

## The Solution

**PriceTracker** is a full-stack web application that gives store owners instant, automated price comparisons across UK supermarkets — plus a suite of AI-powered analytics tools that were previously available only to large retail chains.

A store owner scans a product, and PriceTracker immediately shows the cheapest price across **Tesco, Sainsbury's, Asda, Morrisons, Waitrose, Aldi, Lidl, Iceland, Co-op**, and more — scraped in real time from [Trolley.co.uk](https://www.trolley.co.uk), the UK's largest grocery price comparison database.

### Key Innovation

This is not just a price checker. PriceTracker applies **consumer behaviour science** (price anchoring, loss leader analysis, impulse buying psychology, customer segmentation) to help store owners make data-driven pricing decisions — capabilities that supermarket chains spend millions on, delivered as a free, open-source tool.

---

## Features

### 1. Real-Time Price Comparison Engine

- **Multi-store scraping** — compares prices across 10+ UK supermarkets in real time
- **Intelligent product matching** — custom NLP-based scoring algorithm handles brand names, sizes, multipack formats (e.g., "6x25g" ↔ "6 pack"), flavour variants, and fuzzy matching
- **Two-pass search strategy** — searches with brand first, then falls back to brandless search while preserving brand scoring to avoid wrong-brand matches
- **Size/quantity validation** — ensures 500ml matches 500ml, not 2L or a multipack
- **Customer-facing display** — a live price comparison screen for in-store TVs/tablets showing customers the savings they get

### 2. Consumer Behaviour Analytics

| Feature | Description |
|---------|-------------|
| **Customer Segmentation** | Automatically classifies customers as price-conscious, brand-loyal, impulse buyer, or regular based on transaction patterns |
| **Loss Leader Analysis** | Identifies products priced below competitors that drive footfall — the same strategy used by Tesco and Aldi |
| **Price Anchoring Engine** | Generates printable "Why Pay More?" posters using anchoring bias psychology, showing supermarket prices next to store prices |
| **Impulse Buy Suggestions** | Cross-sell recommendations based on basket affinity analysis (e.g., "Customers who buy bread also buy butter") |
| **Dynamic Pricing Signals** | Time-based pricing recommendations considering day-of-week and seasonal demand patterns |
| **Basket Affinity Analysis** | Association rule mining to discover product bundles and optimise store layout |
| **Seasonal Demand Forecasting** | Predicts next month's demand shifts using historical transaction data |
| **Local Price Index** | Benchmarks overall store affordability against supermarket averages |

### 3. AI-Powered Insights

- **Sentiment Analysis** — NLP processing of customer feedback to identify improvement areas
- **Price Elasticity Modelling** — estimates how price changes affect demand for each product
- **Churn Prediction** — identifies at-risk customers before they switch stores
- **Personalised Promotions** — generates targeted offers based on individual purchase history
- **Store Layout Heatmap** — optimises product placement based on category performance data
- **Trust Dashboard** — real-time store health metrics combining pricing, satisfaction, and loyalty data

### 4. Customer Engagement

- **Loyalty Programme** — digital stamp-card system with points accumulation and redemption
- **NPS Feedback System** — QR code-based customer feedback with Net Promoter Score tracking
- **Public Price Comparison Page** — shareable URL where customers can verify store competitiveness

### 5. Multi-Store & Team Management

- **Multi-store support** — manage multiple shop locations from a single account
- **Role-based access control** — owner, admin, scanner, and viewer roles
- **Employee management** — invite codes, activity logging, and permission controls
- **Stock management** — track inventory status and supplier pricing
- **CSV export** — download all pricing data for external analysis

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Client Layer                         │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐  ┌────────┐ │
│  │Dashboard │  │ Display  │  │  Analytics │  │ Mobile │ │
│  │  (Owner) │  │(In-store)│  │  Reports   │  │  Web   │ │
│  └────┬─────┘  └────┬─────┘  └─────┬──────┘  └───┬────┘ │
│       └──────────────┴──────────────┴─────────────┘      │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTPS
┌───────────────────────────┴─────────────────────────────┐
│                   FastAPI Backend                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  Price Engine │  │  Analytics   │  │  Auth & Teams  │ │
│  │  (Scraper)   │  │  (Behaviour) │  │  (RBAC)        │ │
│  └──────┬───────┘  └──────────────┘  └────────────────┘ │
│         │                                                │
│  ┌──────┴───────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Trolley.co.uk│  │  PostgreSQL  │  │  JSON Fallback │ │
│  │ (Live Data)  │  │  (Render DB) │  │  (Local Dev)   │ │
│  └──────────────┘  └──────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Technical Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.11, FastAPI | Async web framework with high performance |
| **Frontend** | Jinja2, Vanilla CSS/JS | Server-rendered templates, no framework overhead |
| **Database** | PostgreSQL (production), JSON (development) | Dual-mode data layer with automatic detection |
| **Scraping** | httpx, BeautifulSoup4 | Async HTTP client with HTML parsing |
| **Deployment** | Render.com | Auto-deploy from GitHub with managed PostgreSQL |
| **Scheduling** | APScheduler | Background price monitoring jobs |
| **Authentication** | bcrypt, python-jose | Secure password hashing and JWT sessions |

### Product Matching Algorithm

The scraper uses a custom scoring algorithm (`scraper.py`) that solves several non-trivial matching problems:

1. **Token-based matching** — normalises text (hyphens, ampersands, whitespace) and computes word overlap ratio
2. **Brand detection** — boosts exact brand matches, penalises wrong-brand results even on brandless searches
3. **Size validation** — parses multipack formats (`4x380ml`, `6 pack`, `200g`) with unit-aware comparison
4. **Variant/flavour detection** — distinguishes "Coca-Cola Zero" from "Coca-Cola Original", "Pringles Sour Cream & Onion" from "Pringles Original"
5. **Strong vs. incidental classification** — "diet" and "zero" always penalise mismatches; "chocolate" in "Dairy Milk Chocolate Bar" does not
6. **Multipack disambiguation** — correctly matches "6 pack" to "6x25g" format while penalising unwanted multipacks

**Test coverage:** 89/113 common UK grocery products match correctly (79% accuracy), with remaining failures due to Trolley.co.uk search gaps rather than algorithm errors.

---

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL (optional — falls back to JSON file storage)

### Local Development

```bash
# Clone the repository
git clone https://github.com/hardeepsingh-ai/pricetracker.git
cd pricetracker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Run the development server
uvicorn main:app --reload --port 8000
```

Visit `http://localhost:8000` to create an account and start adding products.

### Production Deployment (Render)

1. Fork this repository
2. Create a new **Web Service** on [Render.com](https://render.com)
3. Connect your GitHub repository
4. Set the build command: `pip install -r requirements.txt`
5. Set the start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add a PostgreSQL database and set `DATABASE_URL` environment variable
7. Deploy — the app auto-deploys on every push to `main`

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | No | PostgreSQL connection string (falls back to JSON file) |
| `PORT` | No | Server port (default: 8000, set by Render) |

---

## Project Structure

```
pricetracker/
├── main.py              # FastAPI application — routes, middleware, auth
├── scraper.py           # Price comparison engine — Trolley.co.uk scraping
├── database.py          # Dual-mode data layer (PostgreSQL / JSON)
├── scheduler.py         # Background job scheduling
├── requirements.txt     # Python dependencies
├── Procfile             # Render deployment configuration
├── runtime.txt          # Python version specification
├── LICENSE              # MIT License
├── templates/           # Jinja2 HTML templates
│   ├── base.html        # Base layout template
│   ├── dashboard.html   # Owner dashboard with price overview
│   ├── display.html     # Customer-facing live price display
│   ├── analytics.html   # Consumer behaviour analytics dashboard
│   ├── ai_insights.html # AI-powered recommendations engine
│   ├── insights.html    # Business intelligence reports
│   ├── loyalty.html     # Loyalty programme management
│   ├── feedback.html    # NPS feedback dashboard
│   ├── feedback_form.html # Public customer feedback form
│   ├── anchoring_poster.html # Price anchoring poster generator
│   ├── poster.html      # Promotional poster template
│   ├── public_compare.html # Public price comparison page
│   ├── setup.html       # Product setup wizard
│   ├── stock.html       # Inventory management
│   ├── stores.html      # Multi-store management
│   ├── team.html        # Employee management
│   ├── report.html      # Downloadable reports
│   ├── login.html       # Authentication
│   └── register.html    # Account creation
├── static/              # Static assets (PWA icons)
│   ├── icon-192.png
│   └── icon-512.png
└── data/                # Local development data
    ├── db.json          # Runtime database (gitignored)
    └── db.seed.json     # Seed data for development
```

---

## Live Demo

**Production URL:** [https://pricetracker-emao.onrender.com](https://pricetracker-emao.onrender.com)

> Note: The app runs on Render's free tier, which sleeps after 15 minutes of inactivity. The first request may take 5–10 seconds to wake the service.

---

## Roadmap

- [ ] Barcode scanning via device camera (mobile PWA)
- [ ] Push notifications for price drops
- [ ] Multi-language support (initially English and Punjabi)
- [ ] Supplier price negotiation tools
- [ ] Integration with EPOS/till systems
- [ ] WhatsApp price alerts for customers

---

## Impact

PriceTracker was built to solve a real problem identified while working with an independent convenience store owner in Aberdeen, Scotland. The tool democratises access to retail intelligence that was previously available only to large chains with dedicated pricing teams.

**Real-world deployment:**
- Tested with over 113 UK grocery products across 9 categories
- Covers 10+ UK supermarkets for price comparison
- Includes consumer behaviour analytics based on established retail psychology research
- Mobile-responsive design works on phones, tablets, and in-store display screens

---

## Author

**Hardeep Singh**  
MSc Marketing (Distinction), University of Aberdeen  
[GitHub](https://github.com/hardeepsingh-ai) · [LinkedIn](https://www.linkedin.com/in/hardeepsingh-ai/)

---

## License

This project is open source under the [MIT License](LICENSE).

---

## Contributing

Contributions are welcome. Please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
