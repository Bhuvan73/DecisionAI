# DecisionAI: real-time AI shopping & price comparison

Search a product by name or paste a product URL. DecisionAI retrieves **real Google Shopping offers through SerpApi**, groups
offers for the *same* product variant, compares sellers, saves every retrieved price with its timestamp, and answers questions
about the products with an AI assistant that only uses the retrieved data.

> **What was and wasn't verified (please read).** The build environment had **no internet access and no SerpApi key**, so the
> author could **not** call SerpApi or any real shop. Everything else was run for real (96 automated tests, a real server, a real
> headless browser), but with **fixtures shaped like SerpApi responses**. The one thing that proves live data works is
> `python scripts/verify_serpapi.py` with **your** key. Run it first (it uses 4 searches). Nothing here claims real prices work until it passes.
> The design reference https://pricetrackerai.com/ could not be opened either, so the layout follows your written description.

## Windows quick start
1. Install **Python 3.10+** from python.org (tick *Add python.exe to PATH*). Node.js is **not** needed.
2. Extract the ZIP. Double-click **`run.bat`** once: it creates a virtual environment, installs `requests` + `beautifulsoup4`, and creates `.env`.
3. Open **`.env`** in Notepad and set your key (get one at https://serpapi.com): `SERPAPI_KEY=your_real_key`. Save.
4. Double-click **`run.bat`** again. The site opens at **http://localhost:8000**. (The database is created automatically on first start in `.local_data\decisionai.db`.)
5. Check live data: open a terminal in the folder, `.venv\Scripts\activate`, `python scripts\verify_serpapi.py`.
6. Tests: `run.bat test`.

Without a key the site still starts and shows a clear "Setup needed" message. It never substitutes made-up products.

## Using it
- **Search by name:** "iPhone 16 128GB", "Sony WH-1000XM5"… Enter or the Search button.
- **Search by URL:** paste a product link. The server fetches that public page (robots.txt respected, no CAPTCHA/login bypass, private/internal addresses blocked), reads JSON-LD / Open Graph metadata with BeautifulSoup, then searches Google Shopping for that product. If the page can't be read (Amazon and Flipkart often block automated access) you get an honest message and a suggested search from the link text; nothing is invented.
- **Compare** page: tick products you searched; **Price Tracker** page: saved price history + alerts; **AI Assistant** page and the inline assistant under the results.

## API (JSON)
`POST /api/search` body `{"query": "..."}` or `{"url": "..."}` (+ optional `budget`, `brand`, `category`) · `GET /api/products/{id}` · `GET /api/products/{id}/offers` · `GET /api/products/{id}/history` · `GET /api/health` · also `POST /api/chat`, `POST /api/compare`, `GET/POST /api/alerts`.
Errors use real status codes with a message: 400 bad input, 422 unreadable URL, 503 no key configured, 401 key rejected, 429 quota/rate limit, 504 timeout, 502 other upstream failure.
Each product has title, brand, model, variant, image, and offers with seller, price, currency, original price (only if returned), product URL, rating, review count, source and retrieval timestamp.

## Data, matching, history
- **SerpApi request:** `GET https://serpapi.com/search.json` with `engine=google_shopping, google_domain=google.co.in, gl=in, hl=en, q, api_key`. The key is read from `SERPAPI_KEY` (the older `SERPAPI_API_KEY` also works), stays on the server, and is redacted from errors/logs. 10 s timeout, response validation, quota/auth/timeout errors mapped to clear messages.
- **Saving your free allowance:** results are cached (`CACHE_TTL_MINUTES`, default 180). Case/spacing/budget wording don't create new API calls. A cached result is labelled *Cached* with its original retrieval time and is never recorded as a new observation.
- **Variants:** offers merge only when brand, model, storage, RAM, colour and new/refurbished/used all match. "iPhone 16 128GB" never mixes with 256 GB or "Pro". Uncertain matches are labelled *Possible match* (e.g. listing doesn't state storage) or *Different variant*.
- **Links:** Google Shopping results often link to a Google page, not the store. Those cards say "Link opens Google Shopping"; a direct retailer link is shown only when one was returned; otherwise a labelled search link.
- **SQLite tables:** `products(id,title,brand,model,variant,image_url,created_at,…)`, `offers(id,product_id,seller,price,currency,product_url,source,last_checked,…)`, `price_snapshots(id,offer_id,price,currency,observed_at)`, plus `alerts`, `searches`. Snapshots are written only for freshly retrieved prices (an unchanged price seen within 6 h isn't duplicated). The chart plots saved snapshots only, with a list of exactly when each was collected; with none it says "Price history starts when tracking begins." An older database from a previous version is kept aside (tables renamed `*_legacy`), not deleted.

## AI
- With `LLM_API_KEY` (any OpenAI-compatible API): intent parsing, explanations and a RAG assistant. Retrieved offers, stats, specs, ratings and recorded history become numbered sources; the model must cite `[S#]`; answers that cite nothing, cite an unknown source, or quote an amount not in the sources/your question are **discarded**.
- Without a key: a **rule-based** assistant answers from the same data (cheapest seller, worth buying, best value, cheaper vs pricier variant, pros/cons, within budget) and says "No AI model is configured"; it never presents itself as an AI model. Missing data (no rating, no history, one seller) is stated explicitly.

## Features implemented
Search by name · URL search (JSON-LD/Open Graph) · SerpApi provider with caching and error mapping · variant-aware offer grouping and match labels · price statistics · seller cards with last-checked time · price history from real snapshots · alerts (checked only while the app runs) · Compare/Tracker/Assistant pages · rule-based and LLM assistants (RAG) · light/dark theme · responsive layout · health endpoint.

## Not done / limitations
- Live SerpApi behaviour is **unverified** until you run `scripts/verify_serpapi.py`. Real response edge cases (missing `extracted_price`, odd sellers) are handled defensively but may need tuning.
- Backend is Python's standard-library server, not FastAPI, and the frontend is plain JS, not a separate React app (the build environment couldn't install packages, so a stack I couldn't run wasn't shipped). The API layer (`src/api.py`) is framework-free for a later move.
- URL mode can't read pages that block bots (common for Amazon/Flipkart); it won't try to get around that.
- Deployment: set `HOST=0.0.0.0` and the platform's `PORT`; the same server serves the site, so Vercel (frontend) + Render (backend) split isn't configured; SQLite needs a persistent disk on Render; Supabase/Postgres isn't implemented.
- Price history/alerts only grow while you keep searching; nothing is monitored when the app is closed. No email/push alerts.
- No store logos are bundled (letter badges); optional logo files go in `web/static/logos/`.

## Tests
`run.bat test` (pytest). Covers variants/grouping, matching, budget validation, SerpApi request parameters and error mapping (401/403/429/5xx/timeouts/bad JSON/quota), key redaction in errors and logs, cache behaviour, URL extraction (JSON-LD/OG, SSRF blocking, robots.txt, bot blocks, CAPTCHA pages), DB snapshots/offers/history/alerts, price stats, rule-based and LLM advisor grounding, and real HTTP requests to the running server. `scripts/e2e_check.py` (optional, needs Playwright) drives the real page in Chromium.
