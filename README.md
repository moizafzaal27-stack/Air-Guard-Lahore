# AirGuard Lahore — AI Smog Intelligence & Health Guardian

A responsive web application built for the CodeBlue Lahore — Hack 4 Clean Air brief.

## Features
- Live Open-Meteo air-quality readings for Lahore and five other Pakistani cities.
- US AQI, PM2.5, PM10 and weather indicators.
- Experimental next-hour PM2.5 prediction using a Random Forest model trained at runtime on the latest 7 days of hourly Open-Meteo modelled data.
- Chronological hold-out validation MAE, training sample count and model limitations.
- Live-reading-based health and exposure guidance.
- English/Roman Urdu keyword assistant grounded in current Lahore API readings.
- API source links, refresh timestamp and 10-minute cache.

## Project structure
```
AirGuard-Lahore/
├── backend/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

## Requirements
- Python 3.10 or newer
- VS Code
- Internet connection (the app fetches live data)
- A modern browser

## Run on Windows / VS Code

### 1. Open project
Extract the ZIP. In VS Code select **File → Open Folder** and choose `AirGuard-Lahore`.

### 2. Create and activate virtual environment
Open VS Code Terminal (**Terminal → New Terminal**) and run:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this once in the same terminal:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

If `py` is not recognized, try `python -m venv .venv`.

### 3. Install packages
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Start the backend
```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Keep this terminal running. Open `http://127.0.0.1:8000/docs` to test the API.

### 5. Start the frontend
Open a **second** VS Code terminal. From the project root run:

```powershell
cd frontend
python -m http.server 5500
```

Open this URL in Chrome:
`http://127.0.0.1:5500`

Do not double-click `index.html`; use the local server so the browser can call the backend.

## Test with real data
1. Confirm the backend is running.
2. Open `http://127.0.0.1:8000/api/health` — expect `{"status":"ok",...}`.
3. Open `http://127.0.0.1:8000/api/dashboard` — inspect six city records, live timestamps, Lahore hourly series, prediction and data-source links.
4. Open `http://127.0.0.1:5500` — check Lahore plus Karachi, Islamabad, Peshawar, Multan and Faisalabad.
5. Click **Refresh** and confirm the timestamp updates. The backend caches data for 10 minutes, so repeated refreshes inside that window may show cached readings.
6. Ask the assistant: “Is it safe to exercise?” or “Should children play outside?”
7. Inspect `/docs` to test endpoints independently.

## Data and AI transparency
- Live data: Open-Meteo Air Quality API and Open-Meteo Weather Forecast API.
- Air-quality and weather values from Open-Meteo are modelled estimates/forecasts, not necessarily readings from a physical sensor at the user's exact location.
- The Random Forest predicts next-hour PM2.5 from recent hourly PM2.5, PM10, ozone, nitrogen dioxide, wind and humidity values. It trains on the latest 7-day API series, uses a chronological 80/20 hold-out split for the displayed MAE, then refits on the available series for the next-hour estimate.
- This is an experimental short-horizon model. It is not an official forecast, clinical tool, or substitute for government alerts.
- Assistant recommendations are general awareness guidance, not medical diagnosis. School closure decisions must be checked with official authorities.

## Troubleshooting
- **`py` not found:** install Python 3.10+ and enable “Add Python to PATH”, then reopen VS Code.
- **PowerShell activation blocked:** use the `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` command above.
- **`ModuleNotFoundError`:** activate `.venv` and run `pip install -r requirements.txt` inside `backend`.
- **Port 8000 busy:** start with `uvicorn main:app --reload --port 8001`, then change `API` in `frontend/app.js` to `http://127.0.0.1:8001`.
- **Live data error / 502:** check internet access and retry. Open-Meteo can temporarily rate-limit or be unavailable.
- **Chart.js / fonts not loading:** the UI can still run, but internet is needed for CDN assets.
- **No AQI value:** wait for API data; don't replace missing values with made-up readings.

## Before a public deployment
Restrict CORS to the actual frontend domain, add rate limiting, review API terms, and monitor provider availability. Do not expose private keys in frontend JavaScript (this demo uses public APIs without an API key).
