from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from functools import lru_cache
from typing import Any
import math
import requests
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from pydantic import BaseModel

app = FastAPI(title="AirGuard Lahore API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local hackathon demo. Restrict this to your deployed frontend in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CITIES = {
    "Lahore": {"latitude": 31.5204, "longitude": 74.3587},
    "Karachi": {"latitude": 24.8607, "longitude": 67.0011},
    "Islamabad": {"latitude": 33.6844, "longitude": 73.0479},
    "Peshawar": {"latitude": 34.0151, "longitude": 71.5249},
    "Multan": {"latitude": 30.1575, "longitude": 71.5249},
    "Faisalabad": {"latitude": 31.4504, "longitude": 73.1350},
}
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 20
CACHE_SECONDS = 600
_cache: dict[str, tuple[float, dict]] = {}

def get_json(url: str, params: dict) -> dict:
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Live data provider unavailable: {exc}")

def cached_city_data(city: str) -> dict:
    import time
    now = time.time()
    if city in _cache and now - _cache[city][0] < CACHE_SECONDS:
        return _cache[city][1]

    coords = CITIES[city]
    air = get_json(AIR_URL, {
        **coords,
        "hourly": "pm2_5,pm10,ozone,nitrogen_dioxide,us_aqi",
        "past_days": 7,
        "forecast_days": 2,
        "timezone": "Asia/Karachi",
    })
    weather = get_json(WEATHER_URL, {
        **coords,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "past_days": 7,
        "forecast_days": 2,
        "timezone": "Asia/Karachi",
    })

    a = air.get("hourly", {})
    w = weather.get("hourly", {})
    times = a.get("time", [])
    weather_index = {t: i for i, t in enumerate(w.get("time", []))}
    rows = []
    for i, stamp in enumerate(times):
        wi = weather_index.get(stamp)
        if wi is None:
            continue
        def val(obj, key, idx):
            values = obj.get(key, [])
            return values[idx] if idx < len(values) else None
        row = {
            "time": stamp,
            "pm2_5": val(a, "pm2_5", i),
            "pm10": val(a, "pm10", i),
            "ozone": val(a, "ozone", i),
            "nitrogen_dioxide": val(a, "nitrogen_dioxide", i),
            "us_aqi": val(a, "us_aqi", i),
            "temperature": val(w, "temperature_2m", wi),
            "humidity": val(w, "relative_humidity_2m", wi),
            "wind_speed": val(w, "wind_speed_10m", wi),
        }
        rows.append(row)

    usable = [r for r in rows if r["pm2_5"] is not None]
    if not usable:
        raise HTTPException(status_code=502, detail=f"No current air-quality observations returned for {city}.")
    # The API response includes forecast hours after the present. Never mistake
    # the final forecast point for the current reading.
    now_local = datetime.now(ZoneInfo("Asia/Karachi"))
    cutoff = now_local.strftime("%Y-%m-%dT%H:00")
    observed = [r for r in usable if r["time"] <= cutoff]
    if not observed:
        observed = usable[:1]
    current = observed[-1]
    result = {
        "city": city,
        "current": current,
        "hourly": observed[-168:],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Open-Meteo Air Quality API + Open-Meteo Weather Forecast API",
        "source_note": "Open-Meteo modelled estimates/forecasts; not a substitute for a regulatory ground monitor.",
    }
    _cache[city] = (now, result)
    return result

def aqi_label(value: float | None) -> tuple[str, str]:
    if value is None:
        return ("Unavailable", "unknown")
    if value <= 50: return ("Good", "good")
    if value <= 100: return ("Moderate", "moderate")
    if value <= 150: return ("Unhealthy for sensitive groups", "sensitive")
    if value <= 200: return ("Unhealthy", "unhealthy")
    if value <= 300: return ("Very unhealthy", "very-unhealthy")
    return ("Hazardous", "hazardous")

def train_and_predict(rows: list[dict]) -> dict:
    # Transparent supervised ML: learn next-hour PM2.5 from the previous two hours
    # and current co-pollutants/weather, using the API's past 7-day hourly series.
    feature_rows, targets = [], []
    valid = [r for r in rows if all(isinstance(r.get(k), (int, float)) for k in
              ["pm2_5", "pm10", "ozone", "nitrogen_dioxide", "wind_speed", "humidity"])]
    for i in range(2, len(valid) - 1):
        prev2, prev1, cur, nxt = valid[i-2], valid[i-1], valid[i], valid[i+1]
        feature_rows.append([
            prev2["pm2_5"], prev1["pm2_5"], cur["pm2_5"], cur["pm10"],
            cur["ozone"], cur["nitrogen_dioxide"], cur["wind_speed"], cur["humidity"],
        ])
        targets.append(nxt["pm2_5"])
    if len(feature_rows) < 30:
        return {"available": False, "reason": "Not enough complete hourly data to train the model yet."}

    X, y = np.asarray(feature_rows), np.asarray(targets)
    split = max(20, int(len(X) * 0.8))
    if split >= len(X):
        split = len(X) - 1
    model = RandomForestRegressor(n_estimators=120, max_depth=7, min_samples_leaf=2,
                                  random_state=42, n_jobs=-1)
    model.fit(X[:split], y[:split])
    test_pred = model.predict(X[split:])
    mae = float(mean_absolute_error(y[split:], test_pred))
    final_model = RandomForestRegressor(n_estimators=120, max_depth=7, min_samples_leaf=2,
                                        random_state=42, n_jobs=-1)
    final_model.fit(X, y)
    last = valid[-1]
    before = valid[-2]
    current_features = [[
        valid[-3]["pm2_5"], before["pm2_5"], last["pm2_5"], last["pm10"],
        last["ozone"], last["nitrogen_dioxide"], last["wind_speed"], last["humidity"],
    ]]
    prediction = max(0.0, float(final_model.predict(current_features)[0]))
    return {
        "available": True,
        "next_hour_pm2_5": round(prediction, 1),
        "current_pm2_5": round(float(last["pm2_5"]), 1),
        "change": round(prediction - float(last["pm2_5"]), 1),
        "validation_mae": round(mae, 2),
        "training_samples": int(len(X)),
        "method": "Random Forest Regressor",
        "explanation": "Trained on the latest 7 days of hourly Open-Meteo modelled PM2.5, co-pollutant and weather data. The displayed MAE is measured on a chronological hold-out split.",
        "caution": "Short-horizon experimental estimate, not an official forecast or health diagnosis.",
    }

def make_advice(current: dict) -> list[dict]:
    aqi = current.get("us_aqi")
    pm = current.get("pm2_5")
    wind = current.get("wind_speed")
    tips = []
    if aqi is not None and aqi > 150:
        tips.append({"level":"high","title":"Limit outdoor exposure","detail":"Avoid strenuous outdoor activity. Keep children, older adults and people with heart or lung conditions indoors where possible."})
    elif aqi is not None and aqi > 100:
        tips.append({"level":"medium","title":"Reduce prolonged outdoor activity","detail":"Sensitive groups should reduce prolonged or heavy outdoor exertion and monitor symptoms."})
    else:
        tips.append({"level":"good","title":"Check conditions before heading out","detail":"Air quality can change during the day. Recheck the live reading before extended outdoor activity."})
    if pm is not None and pm > 35:
        tips.append({"level":"medium","title":"Reduce particle exposure","detail":"Keep windows closed when outdoor air is polluted; use a properly sized HEPA air purifier if available."})
    if wind is not None and wind < 8:
        tips.append({"level":"medium","title":"Low wind may limit dispersion","detail":"Low wind can allow pollution to linger. This is a weather indicator, not proof of a specific pollution source."})
    tips.append({"level":"info","title":"For travel","detail":"Prefer shorter trips and less congested roads where practical. This app does not currently measure street-by-street exposure."})
    return tips

@app.get("/api/health")
def health():
    return {"status":"ok", "service":"AirGuard Lahore API"}

@app.get("/api/cities")
def city_list():
    return {"cities": list(CITIES.keys())}

@app.get("/api/dashboard")
def dashboard():
    results = []
    for city in CITIES:
        data = cached_city_data(city)
        current = data["current"]
        label, category = aqi_label(current.get("us_aqi"))
        results.append({
            "city": city, "aqi": current.get("us_aqi"),
            "aqi_label": label, "category": category,
            "pm2_5": current.get("pm2_5"), "pm10": current.get("pm10"),
            "temperature": current.get("temperature"), "humidity": current.get("humidity"),
            "wind_speed": current.get("wind_speed"), "time": current.get("time"),
            "updated_at": data["updated_at"],
        })
    lahore = cached_city_data("Lahore")
    prediction = train_and_predict(lahore["hourly"])
    return {
        "cities": results,
        "lahore": lahore,
        "prediction": prediction,
        "advice": make_advice(lahore["current"]),
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "cache_seconds": CACHE_SECONDS,
        "sources": [
            {"name":"Open-Meteo Air Quality API","url":"https://open-meteo.com/en/docs/air-quality-api"},
            {"name":"Open-Meteo Weather Forecast API","url":"https://open-meteo.com/en/docs"},
        ],
    }

class ChatRequest(BaseModel):
    message: str

@app.post("/api/assistant")
def assistant(payload: ChatRequest):
    message = payload.message.strip().lower()
    lahore = cached_city_data("Lahore")
    current = lahore["current"]
    aqi = current.get("us_aqi")
    pm = current.get("pm2_5")
    aqi_text, _ = aqi_label(aqi)
    urdu = any(word in message for word in ["urdu", "اردو", "smog kya", "kya kar"])
    if any(k in message for k in ["school", "child", "student", "school"]):
        answer = f"Lahore ka latest estimated US AQI {aqi if aqi is not None else 'available nahi'} ({aqi_text}) hai. Bachon ki outdoor sports ko high pollution mein avoid karein aur school ke official notices follow karein. AirGuard school band hone ka official faisla nahi karta."
    elif any(k in message for k in ["mask", "ماسک"]):
        answer = "Pollution zyada ho to well-fitted N95/KN95 respirator particles ke exposure ko kam kar sakta hai. Mask ki fitting zaroori hai. Yeh medical advice ka replacement nahi."
    elif any(k in message for k in ["window", "ventilat", "khirki"]):
        answer = "Jab outdoor AQI/PM2.5 high ho to windows band rakhein. Ventilation tab karein jab outdoor air comparatively behtar ho. Agar indoor source (cooking/smoke) ho to safe exhaust use karein."
    elif any(k in message for k in ["aqi", "pollution", "air", "smog", "pm2", "لاہور"]):
        answer = f"Lahore ka latest Open-Meteo estimated US AQI {aqi if aqi is not None else 'available nahi'} ({aqi_text}) aur PM2.5 {round(pm,1) if pm is not None else 'available nahi'} µg/m³ hai. "
        answer += "Agar AQI 150 se upar ho to outdoor exertion limit karein, khas taur par sensitive groups ke liye."
    else:
        answer = f"Main live Lahore air-quality data ke mutabiq madad kar sakta hoon. Current estimated AQI: {aqi if aqi is not None else 'N/A'} ({aqi_text}), PM2.5: {round(pm,1) if pm is not None else 'N/A'} µg/m³. Aap mask, school, outdoor activity, ya ventilation ke bare mein pooch sakte hain."
    if urdu:
        answer += " (Roman Urdu: Lahore ki hawa ki quality waqt ke sath badalti hai; nikalne se pehle dobara live reading check karein.)"
    return {"answer": answer, "based_on": {"us_aqi": aqi, "pm2_5": pm, "time": current.get("time")},
            "disclaimer":"General awareness only; not medical advice or an official school/government alert."}
