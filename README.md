# HitCapsule — Pick a date. Press play.

Choose a date, fetch the **Billboard Hot 100**, and automatically build a **Spotify playlist** in your account.

## Features
- Billboard Hot 100 scraping (song **title + artist**, resilient selectors)
- Spotify search & add (Spotipy) — secure credentials via **.env**
- Smart matching: primary-artist extraction, title normalization, **A/B single** splitting, staged queries
- Missing tracks report: `missing_YYYY-MM-DD.csv`
- **Private** playlist by default

## Requirements
- Python 3.10+
- Spotify account and a **Spotify for Developers** app

## Setup
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

**Spotify Redirect URI** (Developer Dashboard → Edit Settings):
```
http://127.0.0.1:8080/callback
```

Copy `.env.example` to `.env` and fill in:
```ini
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8080/callback
SPOTIFY_MARKET=US
```

## Run
**Windows, macOS, or Linux**
```bash
cd src
python -m hitcapsule --date 1997-03-06
```

## Usage
- `--date, -d`: Target date `YYYY-MM-DD` (if omitted, the CLI will prompt)

**Examples**
```bash
python -m hitcapsule
python -m hitcapsule -d 2015-03-06
```

## Outputs
- On Spotify: a playlist named `<date> Billboard Hot 100`
- In the project root: `missing_<date>.csv` (unmatched items)

## Project Structure
```
hitcapsule/
├─ .env.example
├─ .gitignore
├─ LICENSE
├─ pyproject.toml
├─ README.md
├─ requirements.txt
└─ src/
   └─ hitcapsule/
      ├─ __init__.py
      ├─ __main__.py
      ├─ billboard.py
      ├─ cli.py
      └─ spotify_client.py
```

## Troubleshooting
- **Invalid redirect URI**: The Dashboard and `.env` values must match **exactly**.
- **Low match count**: Clear `.cache/` and try `SPOTIFY_MARKET=TR` or `US`.
- **No module named hitcapsule**: Mark `src` as *Sources Root* or `cd src` before running.

## License
MIT — see `LICENSE`.
