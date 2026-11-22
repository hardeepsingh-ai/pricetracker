# PriceTracker

AI-powered convenience store price comparison tool with consumer behaviour analytics, loyalty programmes, and NPS feedback.

## Features

### Core
- **Multi-store management** with role-based access (owner, admin, scanner, viewer)
- **Real-time price comparison** via Trolley.co.uk scraping with brand & size matching
- **Employee team management** with invite codes and activity logging

### Consumer Behaviour Analytics
- **Customer Segmentation** — automatic classification (price-conscious, brand-loyal, impulse buyer)
- **Loss Leader Analysis** — identify products priced below competitors to drive footfall
- **Anchoring Bias Engine** — printable "Why Pay More?" posters using price anchoring psychology
- **Impulse Buy Suggestions** — cross-sell recommendations based on transaction patterns
- **Dynamic Pricing Signals** — time-based pricing recommendations
- **Basket Affinity Analysis** — association rule mining for product bundles
- **Seasonal Demand Forecasting** — predict next month's demand shifts
- **Local Price Index** — benchmark store affordability vs. supermarkets

### Customer Engagement
- **Loyalty Programme** — stamp-card system with points and redemption
- **NPS Feedback System** — QR code customer feedback with Net Promoter Score
- **Public Price Comparison** — customer-facing page to check prices

## Tech Stack

- **Backend:** Python, FastAPI, Uvicorn
- **Frontend:** Jinja2 templates, vanilla CSS/JS
- **Data:** JSON file database
- **Scraping:** httpx, BeautifulSoup4
- **Deployment:** Render.com

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Author

**Hardeep Singh** — [GitHub](https://github.com/hardeepsingh-ai)

## License

MIT License — see [LICENSE](LICENSE) for details.
