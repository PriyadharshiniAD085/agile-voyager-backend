import os
import json
import requests
import time
import bcrypt
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Literal, List, Optional
from dotenv import load_dotenv
import certifi
from datetime import datetime
import uvicorn
import smtplib
import ssl
import httpx
from email.message import EmailMessage
from db import conn, cursor
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, timedelta
from typing import Dict, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

CURRENCY_MAP = {
    "london": ("GBP", "£"), "england": ("GBP", "£"), "uk": ("GBP", "£"),
    "manchester": ("GBP", "£"), "birmingham": ("GBP", "£"),
    "paris": ("EUR", "€"), "france": ("EUR", "€"), "germany": ("EUR", "€"),
    "berlin": ("EUR", "€"), "italy": ("EUR", "€"), "rome": ("EUR", "€"),
    "spain": ("EUR", "€"), "barcelona": ("EUR", "€"), "madrid": ("EUR", "€"),
    "amsterdam": ("EUR", "€"), "portugal": ("EUR", "€"), "lisbon": ("EUR", "€"),
    "greece": ("EUR", "€"), "athens": ("EUR", "€"),
    "switzerland": ("CHF", "Fr"),
    "dubai": ("AED", "AED"), "uae": ("AED", "AED"), "abu dhabi": ("AED", "AED"),
    "japan": ("JPY", "¥"), "tokyo": ("JPY", "¥"), "osaka": ("JPY", "¥"),
    "thailand": ("THB", "฿"), "bangkok": ("THB", "฿"),
    "singapore": ("SGD", "S$"),
    "malaysia": ("MYR", "RM"), "kuala lumpur": ("MYR", "RM"),
    "bali": ("IDR", "Rp"), "indonesia": ("IDR", "Rp"),
    "vietnam": ("VND", "₫"), "hanoi": ("VND", "₫"),
    "china": ("CNY", "¥"), "beijing": ("CNY", "¥"), "shanghai": ("CNY", "¥"),
    "korea": ("KRW", "₩"), "seoul": ("KRW", "₩"),
    "nepal": ("NPR", "₨"), "kathmandu": ("NPR", "₨"),
    "sri lanka": ("LKR", "Rs"), "colombo": ("LKR", "Rs"),
    "maldives": ("MVR", "Rf"),
    "usa": ("USD", "$"), "new york": ("USD", "$"), "america": ("USD", "$"),
    "los angeles": ("USD", "$"), "chicago": ("USD", "$"),
    "canada": ("CAD", "C$"), "toronto": ("CAD", "C$"),
    "australia": ("AUD", "A$"), "sydney": ("AUD", "A$"),
    "new zealand": ("NZD", "NZ$"), "auckland": ("NZD", "NZ$"),
    "india": ("INR", "₹"), "mumbai": ("INR", "₹"), "delhi": ("INR", "₹"),
    "bangalore": ("INR", "₹"), "chennai": ("INR", "₹"),
}

def detect_currency(destination: str):
    """Returns (currency_code, currency_symbol) based on destination string."""
    if not destination:
        return ("INR", "₹")
    lower = destination.lower()
    for key, (code, symbol) in CURRENCY_MAP.items():
        if key in lower:
            return (code, symbol)
    return ("INR", "₹") 

# Load environment variables
load_dotenv('.env.local')

app = FastAPI(title="Travel Planner API")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001", "https://agile-voyager.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- EMAIL CONFIGURATION ---
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"

print(f"✅ Email Host: {EMAIL_HOST}")
print(f"✅ Email Port: {EMAIL_PORT}")
print(f"✅ Email User: {'SET' if EMAIL_USER else 'MISSING'}")
print(f"✅ Email Password: {'SET' if EMAIL_PASSWORD else 'MISSING'}")

# --- MODELS ---


class UserSignUp(BaseModel):
    name: str
    email: str
    dob: str
    password: str

class UserSignIn(BaseModel):
    email: str
    password: str

class TravelFormData(BaseModel):
    destination: str
    departureCity: str
    departureDate: str
    returnDate: str
    flightBudget: str
    accommodationBudget: str
    tripBudget: str
    tripType: Literal["relaxation", "business", "adventure", "romantic", "family", "solo"]
    numberOfPeople: Literal["1", "2", "3", "4", "5", "6+"]
    rentCar: bool
    needsFlight: bool
    dob: str
    userId: str

class Attraction(BaseModel):
    name: str
    lat: float
    lng: float
    day: int
    description: str = ""

class WeatherRequest(BaseModel):
    city: str

class WeatherResponse(BaseModel):
    city: str
    temperature: float
    description: str
    humidity: int
    wind_speed: float

class Feedback(BaseModel):
    message: str
    user_name: str | None = None

class Expense(BaseModel):
    trip_id: int
    category: str
    amount: float
    description: str
    date: str

class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    date: Optional[str] = None

class EmailItineraryWithUserId(BaseModel):
    email: EmailStr | None = None
    userId: str | None = None
    destination: str
    itinerary: str
    packingList: str | None = None
    departureDate: str
    returnDate: str
    budget: str
    travelers: str

class TripComplete(BaseModel):
    completed: bool

class TripUpdate(BaseModel):
    destination: Optional[str] = None
    total_budget: Optional[float] = None
    days: Optional[int] = None
    trip_type: Optional[str] = None
    members: Optional[int] = None
    completed: Optional[bool] = None
    year: Optional[int] = None

class GoogleToken(BaseModel):
    id_token: str | None = None
    credential: str | None = None

class IterateRequest(BaseModel):
    formData: TravelFormData
    previousNames: List[str] | None = None

# NEW MODEL FOR SEND-ITINERARY
class EmailItinerary(BaseModel):
    email: EmailStr
    destination: str
    itinerary: str
    packingList: str
    departureDate: str
    returnDate: str
    budget: str
    travelers: str

# --- API KEYS ---
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

print(f"✅ OpenWeather Key: {'SET' if OPENWEATHER_API_KEY else 'MISSING'}")
print(f"✅ Amadeus Client ID: {'SET' if AMADEUS_CLIENT_ID else 'MISSING'}")
print(f"✅ Amadeus Client Secret: {'SET' if AMADEUS_CLIENT_SECRET else 'MISSING'}")
print(f"✅ RapidAPI Key: {'SET' if RAPIDAPI_KEY else 'MISSING'}")

OSM_GEOCODING_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "TravelPlannerApp/1.0 (contact@example.com)"

# --- PASSWORD UTILITIES ---
def hash_password_bcrypt(password: str) -> str:
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception as e:
        print("❌ Password verification error:", e)
        return False

def check_db_connection():
    """Check if database is connected"""
    if conn is None or cursor is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    return True

# --- UTILITIES ---
def geocode_location(location_name: str):
    params = {"q": location_name, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}
    verify_ca = certifi.where()

    FALLBACK_COORDS = {
        "paris": {"lat": 48.8566, "lon": 2.3522, "display_name": "Paris, France"},
        "bali": {"lat": -8.3405, "lon": 115.0920, "display_name": "Bali, Indonesia"},
        "jammu and kashmir": {"lat": 33.7782, "lon": 76.5762, "display_name": "Jammu and Kashmir, India"}
    }

    attempts = 3
    delay = 1
    for attempt in range(1, attempts + 1):
        try:
            try:
                response = requests.get(OSM_GEOCODING_URL, params=params, headers=headers, timeout=10, verify=verify_ca)
            except requests.exceptions.SSLError:
                print("⚠️ SSL verification failed when contacting geocoding service — retrying without verification (insecure).")
                response = requests.get(OSM_GEOCODING_URL, params=params, headers=headers, timeout=10, verify=False)

            if response.status_code == 200:
                data = response.json()
                if not data:
                    return None
                return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"]), "display_name": data[0]["display_name"]}
            elif response.status_code in (429, 502, 503, 504) and attempt < attempts:
                print(f"⚠️ Geocoding request rate-limited/server error (status={response.status_code}), retry {attempt}/{attempts} after {delay}s")
                time.sleep(delay)
                delay *= 2
                continue
            else:
                print(f"⚠️ Geocoding failed with status {response.status_code}: {response.text[:200]}")
                break
        except requests.exceptions.RequestException as re:
            print(f"⚠️ Geocoding request exception: {re} (attempt {attempt}/{attempts})")
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
                continue
            break

    key = (location_name or "").strip().lower()
    if key in FALLBACK_COORDS:
        print(f"ℹ️ Using fallback coordinates for {key}")
        return FALLBACK_COORDS[key]

    return None

def get_country_centroid(name: str):
    """Try to resolve a country name to a lat/lon using the Rest Countries API as a fallback."""
    if not name:
        return None
    try:
        url = f"https://restcountries.com/v3.1/name/{requests.utils.requote_uri(name)}?fields=latlng,name"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data or not isinstance(data, list):
            return None
        entry = data[0]
        latlng = entry.get("latlng")
        if latlng and isinstance(latlng, list) and len(latlng) >= 2:
            return {"lat": float(latlng[0]), "lon": float(latlng[1]), "display_name": entry.get("name", {}).get("common", name)}
    except Exception as e:
        print("⚠️ RestCountries lookup failed:", e)
    return None

def get_tourist_attractions(lat: float, lon: float, radius_km: int = 50):
    radius_m = radius_km * 1000
    query = f"""
    [out:json][timeout:25];
    (
      node["tourism"="attraction"](around:{radius_m},{lat},{lon});
      node["tourism"="museum"](around:{radius_m},{lat},{lon});
      node["tourism"="viewpoint"](around:{radius_m},{lat},{lon});
      node["historic"](around:{radius_m},{lat},{lon});
      node["natural"="peak"](around:{radius_m},{lat},{lon});

      way["tourism"="attraction"](around:{radius_m},{lat},{lon});
      way["tourism"="museum"](around:{radius_m},{lat},{lon});
      way["historic"](around:{radius_m},{lat},{lon});

      relation["tourism"="attraction"](around:{radius_m},{lat},{lon});
      relation["tourism"="museum"](around:{radius_m},{lat},{lon});
      relation["historic"](around:{radius_m},{lat},{lon});
    );
    out body center;
    """
    try:
        verify_ca = certifi.where()
        try:
            res = requests.post(OVERPASS_API_URL, data=query, headers={"User-Agent": USER_AGENT}, timeout=30, verify=verify_ca)
        except requests.exceptions.SSLError:
            print("⚠️ SSL verification failed when contacting Overpass API — retrying without verification (insecure).")
            res = requests.post(OVERPASS_API_URL, data=query, headers={"User-Agent": USER_AGENT}, timeout=30, verify=False)
        elements = res.json().get("elements", [])
        seen, attractions = set(), []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name or name in seen:
                continue
            lat_val = el.get("lat")
            lon_val = el.get("lon")
            if lat_val is None or lon_val is None:
                center = el.get("center") or {}
                lat_val = center.get("lat")
                lon_val = center.get("lon")
            if lat_val is None or lon_val is None:
                continue
            try:
                lat_f = float(lat_val)
                lon_f = float(lon_val)
            except Exception:
                continue
            seen.add(name)
            desc_parts = [tags.get(k, "").replace("_", " ").title() for k in ["tourism", "historic", "natural"] if k in tags]
            attractions.append({
                "name": name,
                "lat": lat_f,
                "lon": lon_f,
                "description": " • ".join(desc_parts) or "Tourist attraction"
            })
        return attractions
    except Exception as e:
        print("Error fetching attractions:", e)
        return []

# --- NEW ENDPOINT: SEND-ITINERARY ---
# Replace your /send-itinerary endpoint with this updated version:
FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY", "")

@app.post("/popular-places")
async def get_popular_places(request: dict):
    destination = request.get("destination", "")
    trip_type = request.get("trip_type", "")
    
    if not destination:
        return {"places": "No destination provided", "activities": "No activities available"}
    
    try:
        # First, geocode the destination to get coordinates
        geocode_url = f"https://nominatim.openstreetmap.org/search?format=json&q={destination}&limit=1"
        
        async with httpx.AsyncClient() as client:
            geocode_response = await client.get(
                geocode_url,
                headers={"User-Agent": "TravelPlanner/1.0"}
            )
            geocode_data = geocode_response.json()
            
            if not geocode_data:
                return await get_fallback_data(destination, trip_type)
            
            lat = float(geocode_data[0]["lat"])
            lon = float(geocode_data[0]["lon"])
            
            # Fetch popular places using Foursquare API (alternative to Google Places)
            places_data = await fetch_foursquare_places(lat, lon, destination)
            
            # Fetch activities based on trip type
            activities_data = await fetch_activities_by_type(lat, lon, trip_type, destination)
            
            return {
                "places": places_data,
                "activities": activities_data
            }
            
    except Exception as e:
        print(f"Error fetching popular places: {e}")
        return await get_fallback_data(destination, trip_type)


async def fetch_foursquare_places(lat: float, lon: float, destination: str):
    """Fetch popular places using Foursquare Places API"""
    
    if not FOURSQUARE_API_KEY:
        return f"Popular attractions in {destination}\n• Enable Foursquare API for real-time data"
    
    try:
        # Foursquare Places API - Free tier available
        url = "https://api.foursquare.com/v3/places/search"
        
        params = {
            "ll": f"{lat},{lon}",
            "radius": 10000,  # 10km radius
            "categories": "16000,10000,12000",  # Landmarks, Arts, Entertainment
            "limit": 10
        }
        
        headers = {
            "Accept": "application/json",
            "Authorization": FOURSQUARE_API_KEY
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            data = response.json()
            
            if "results" in data and len(data["results"]) > 0:
                places_list = []
                for place in data["results"][:8]:
                    name = place.get("name", "Unknown")
                    categories = place.get("categories", [])
                    category = categories[0].get("name", "") if categories else ""
                    places_list.append(f"• {name} - {category}")
                
                return f"Popular places in {destination}:\n" + "\n".join(places_list)
            
    except Exception as e:
        print(f"Foursquare API error: {e}")
    
    return f"Popular attractions in {destination}\n• Check local tourism sites for details"


async def fetch_activities_by_type(lat: float, lon: float, trip_type: str, destination: str):
    """Fetch activities based on trip type using real data"""
    
    # Map trip types to Foursquare category IDs
    category_map = {
        "adventure": "18000,19000",  # Recreation, Travel
        "relaxation": "10027,10032",  # Spa, Beach
        "business": "13065,13032",  # Convention Center, Coworking
        "romantic": "13065,10040",  # Restaurant, Winery
        "family": "10019,10047",  # Theme Park, Zoo
        "solo": "10023,10018"  # Museum, Art Gallery
    }
    
    categories = category_map.get(trip_type.lower(), "16000")
    
    try:
        url = "https://api.foursquare.com/v3/places/search"
        
        params = {
            "ll": f"{lat},{lon}",
            "radius": 15000,
            "categories": categories,
            "limit": 8
        }
        
        headers = {
            "Accept": "application/json",
            "Authorization": FOURSQUARE_API_KEY
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            data = response.json()
            
            if "results" in data and len(data["results"]) > 0:
                activities_list = []
                for activity in data["results"][:6]:
                    name = activity.get("name", "Unknown")
                    categories = activity.get("categories", [])
                    category = categories[0].get("name", "") if categories else ""
                    activities_list.append(f"• {name} - {category}")
                
                return f"Things to do in {destination} ({trip_type}):\n" + "\n".join(activities_list)
    
    except Exception as e:
        print(f"Activities fetch error: {e}")
    
    # Fallback if API fails
    return await get_fallback_activities(trip_type, destination)


async def get_fallback_data(destination: str, trip_type: str):
    """Fallback when APIs are unavailable"""
    
    # Try to get data from Wikipedia or other sources
    try:
        # Search Wikipedia for the destination
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{destination.replace(' ', '_')}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(wiki_url)
            
            if response.status_code == 200:
                wiki_data = response.json()
                extract = wiki_data.get("extract", "")
                
                # Extract key information
                places = f"About {destination}:\n{extract[:300]}...\n\n• Visit local tourism office for detailed attractions"
                activities = await get_fallback_activities(trip_type, destination)
                
                return {"places": places, "activities": activities}
    
    except Exception as e:
        print(f"Fallback error: {e}")
    
    return {
        "places": f"Explore {destination}\n• Check TripAdvisor or Google Maps for popular attractions",
        "activities": await get_fallback_activities(trip_type, destination)
    }


async def get_fallback_activities(trip_type: str, destination: str):
    """Fallback activities based on trip type"""
    
    activities_map = {
        "adventure": f"Adventure activities in {destination}:\n• Outdoor sports and hiking\n• Local adventure tours\n• Water activities\n• Cycling routes\n• Photography expeditions",
        "relaxation": f"Relaxation in {destination}:\n• Spa and wellness centers\n• Beach or lakeside spots\n• Yoga and meditation\n• Scenic walks\n• Local cafes",
        "business": f"Business amenities in {destination}:\n• Business hotels\n• Conference facilities\n• Networking venues\n• Fine dining\n• Transport services",
        "romantic": f"Romantic experiences in {destination}:\n• Couples dining\n• Sunset viewpoints\n• Cultural shows\n• Romantic walks\n• Wine tasting",
        "family": f"Family activities in {destination}:\n• Family-friendly attractions\n• Parks and playgrounds\n• Interactive museums\n• Kid-friendly restaurants\n• Entertainment venues",
        "solo": f"Solo travel in {destination}:\n• Walking tours\n• Local meetups\n• Cultural experiences\n• Street food tours\n• Museums and galleries"
    }
    
    return activities_map.get(trip_type.lower(), f"Things to do in {destination}:\n• City exploration\n• Local cuisine\n• Cultural sites\n• Shopping\n• Photography")

@app.post("/send-itinerary")
async def send_itinerary(data: EmailItineraryWithUserId):
    """
    Send itinerary email to user AND save trip to database
    """
    try:
        currency_code, currency_symbol = detect_currency(data.destination)
        recipient_email = data.email
        user_id = None  # We'll determine the actual DB user_id
        
        # If email is placeholder or missing, fetch from database
        if not recipient_email or recipient_email == "user@example.com":
            if not data.userId:
                print("❌ No email or userId provided")
                return {
                    "success": False,
                    "message": "No valid email address or user ID provided"
                }
            
            # Fetch user email from database
            try:
                if conn and cursor:
                    cursor.execute("SELECT id, email FROM users WHERE id = ?", (data.userId,))
                    user = cursor.fetchone()
                    if user:
                        recipient_email = user["email"]
                        user_id = user["id"]
                        print(f"✅ Fetched from DB - Email: {recipient_email}, UserID: {user_id}")
                    else:
                        print(f"❌ User not found with ID: {data.userId}")
                        return {
                            "success": False,
                            "message": "User not found in database"
                        }
                else:
                    print("❌ Database not available")
                    return {
                        "success": False,
                        "message": "Database connection not available"
                    }
            except Exception as db_error:
                print(f"❌ Database error: {db_error}")
                return {
                    "success": False,
                    "message": f"Failed to fetch user email: {str(db_error)}"
                }
        else:
            # Email was provided, get user_id from email
            try:
                if conn and cursor:
                    cursor.execute("SELECT id FROM users WHERE email = ?", (recipient_email,))
                    user = cursor.fetchone()
                    if user:
                        user_id = user["id"]
                        print(f"✅ Found user_id {user_id} for email {recipient_email}")
                    else:
                        print(f"❌ No user found with email: {recipient_email}")
                        return {
                            "success": False,
                            "message": f"No user found with email: {recipient_email}"
                        }
            except Exception as e:
                print(f"❌ Error fetching user_id: {e}")
                return {
                    "success": False,
                    "message": "Failed to fetch user from database"
                }
        
        # Validate we have both email and user_id
        if not recipient_email or not user_id:
            print(f"❌ Missing data - Email: {recipient_email}, UserID: {user_id}")
            return {
                "success": False,
                "message": "Could not determine user email or ID"
            }
        
        print(f"📧 Sending itinerary to: {recipient_email} (user_id: {user_id})")
        
        if not EMAIL_USER or not EMAIL_PASSWORD:
            print("⚠️ Email credentials not configured")
            return {
                "success": False,
                "message": "Email service not configured. Please set EMAIL_USER and EMAIL_PASSWORD in .env.local"
            }
        
        # Create email message
        msg = EmailMessage()
        msg['Subject'] = f"Your {data.destination} Travel Itinerary"
        msg['From'] = f"Agile Voyager <{EMAIL_USER}>"
        msg['To'] = recipient_email
        
        # Create HTML email body
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">
              <h1 style="color: #2563eb; border-bottom: 3px solid #2563eb; padding-bottom: 10px;">
                ✈️ Your {data.destination} Travel Plan
              </h1>
              
              <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h2 style="color: #7c3aed;">📅 Trip Details</h2>
                <p><strong>Destination:</strong> {data.destination}</p>
                <p><strong>Dates:</strong> {data.departureDate} to {data.returnDate}</p>
                <p><strong>Budget:</strong> {currency_symbol}{data.budget}</p>
                <p><strong>Travelers:</strong> {data.travelers}</p>
              </div>

              <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h2 style="color: #7c3aed;">🗺️ Your Itinerary</h2>
                <pre style="white-space: pre-wrap; font-family: Arial; font-size: 14px;">{data.itinerary}</pre>
              </div>

              <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h2 style="color: #7c3aed;">🎒 Packing List</h2>
                <pre style="white-space: pre-wrap; font-family: Arial; font-size: 14px;">{data.packingList}</pre>
              </div>

              <div style="margin-top: 30px; padding: 15px; background: #eff6ff; border-left: 4px solid #2563eb; border-radius: 4px;">
                <p style="margin: 0; font-size: 14px;">
                  <strong>Have a wonderful trip! 🌟</strong><br>
                  This itinerary was generated by AI Trip Planner
                </p>
              </div>
            </div>
          </body>
        </html>
        """
        
        # Set content
        msg.set_content(f"Your {data.destination} Travel Itinerary\n\n{data.itinerary}\n\nPacking List:\n{data.packingList}")
        msg.add_alternative(html_body, subtype='html')
        
        # Send email
        context = ssl.create_default_context()
        
        try:
            if EMAIL_PORT == 465:
                with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=context, timeout=15) as server:
                    server.login(EMAIL_USER, EMAIL_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=15) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(EMAIL_USER, EMAIL_PASSWORD)
                    server.send_message(msg)
            
            print(f"✅ Itinerary email sent successfully to {recipient_email}")
            
            # ===== SAVE TRIP TO DATABASE =====
            if conn and cursor and user_id:
                try:
                    # Calculate days from dates
                    days = None
                    try:
                        dep = datetime.strptime(data.departureDate, "%Y-%m-%d")
                        ret = datetime.strptime(data.returnDate, "%Y-%m-%d")
                        days = max(1, (ret - dep).days)
                    except:
                        days = None
                    
                    # Extract year from departure date
                    year = None
                    try:
                        dep = datetime.strptime(data.departureDate, "%Y-%m-%d")
                        year = dep.year
                    except:
                        year = datetime.now().year
                    
                    # Parse travelers to get member count
                    members = None
                    try:
                        members = int(data.travelers.split()[0]) if data.travelers else None
                    except:
                        members = 1
                    
                    # Parse budget (remove ₹ and commas)
                    total_budget = None
                    try:
                        budget_str = str(data.budget).replace('₹', '').replace(',', '').strip()
                        total_budget = float(budget_str)
                    except:
                        total_budget = None
                    
                    # Combine itinerary and packing list as plan_text
                    plan_text = f"ITINERARY:\n{data.itinerary}\n\nPACKING LIST:\n{data.packingList}"
                    # Create structured itinerary JSON for expense tracker
                    itinerary_json = json.dumps({
                        "itinerary_text": data.itinerary,
                        "packing_list": data.packingList
                    })
                    
                    print(f"💾 Saving trip to database:")
                    print(f"   - user_id: {user_id} (type: {type(user_id)})")
                    print(f"   - destination: {data.destination}")
                    print(f"   - budget: {total_budget}")
                    print(f"   - days: {days}")
                    print(f"   - year: {year}")
                    
                    # Insert trip into database with VERIFIED user_id
                    # Create itinerary_json for expense tracker
                    itinerary_json = json.dumps({
                        "itinerary": data.itinerary,
                        "packing_list": data.packingList
                    })

                    cursor.execute(
                        """INSERT INTO confirmed_trips 
                            (user_id, destination, plan_text, total_budget, days, members, year, itinerary_json, completed) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                        (user_id, data.destination, plan_text, total_budget, days, members, year, itinerary_json)
                    )
                    conn.commit()
                    new_trip_id = cursor.lastrowid
                    print(f"✅ Trip saved to database with ID: {new_trip_id}")
                    
                    # VERIFY the save by querying it back
                    cursor.execute("SELECT id, user_id, destination FROM confirmed_trips WHERE id = ?", (new_trip_id,))
                    saved_trip = cursor.fetchone()
                    if saved_trip:
                        print(f"✅ VERIFICATION - Trip {saved_trip['id']} has user_id: {saved_trip['user_id']}")
                    else:
                        print(f"⚠️ Could not verify saved trip")
                    
                except Exception as db_error:
                    print(f"⚠️ Failed to save trip to database: {db_error}")
                    import traceback
                    traceback.print_exc()
                    # Don't fail the whole request if DB save fails
                    if conn:
                        conn.rollback()
            # ===== END SAVE CODE =====
            
            return {
                "success": True,
                "message": f"Itinerary sent successfully to {recipient_email}",
                "email": recipient_email,
                "user_id": user_id
            }
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication failed: {e}")
            return {
                "success": False,
                "message": "Email authentication failed. Please check your email credentials and use an App Password for Gmail."
            }
        except smtplib.SMTPException as e:
            print(f"❌ SMTP error: {e}")
            return {
                "success": False,
                "message": f"Failed to send email: {str(e)}"
            }
        except Exception as e:
            print(f"❌ Unexpected error sending email: {e}")
            return {
                "success": False,
                "message": str(e)
            }
            
    except Exception as e:
        print(f"❌ Error in send_itinerary endpoint: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": str(e)
        }

    
@app.patch("/trips/{trip_id}/complete")
async def toggle_trip_completion(trip_id: int, completion: TripComplete):
    """Mark a trip as completed or pending"""
    check_db_connection()
    try:
        print(f"🔄 Toggling completion for trip_id: {trip_id} to {completion.completed}")
        
        # Check if trip exists
        cursor.execute("SELECT id, completed FROM confirmed_trips WHERE id = ?", (trip_id,))
        trip = cursor.fetchone()
        
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        # Update completion status
        cursor.execute(
            "UPDATE confirmed_trips SET completed = ? WHERE id = ?",
            (1 if completion.completed else 0, trip_id)
        )
        conn.commit()
        
        print(f"✅ Trip {trip_id} marked as {'completed' if completion.completed else 'pending'}")
        
        # Get updated trip
        cursor.execute(
            """SELECT id, destination, total_budget, days, trip_type, members, 
               completed, year, created_at 
               FROM confirmed_trips 
               WHERE id = ?""",
            (trip_id,)
        )
        updated_trip = cursor.fetchone()
        
        trip_dict = dict(updated_trip)
        trip_dict['completed'] = bool(trip_dict.get('completed', 0))
        
        return {
            "success": True,
            "message": f"Trip marked as {'completed' if completion.completed else 'pending'}",
            "trip": trip_dict
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Error toggling trip completion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- EMAIL ENDPOINT (existing) ---
@app.post("/send-email")
async def send_email(data: dict):
    """
    Send trip confirmation email with proper error handling
    """
    try:
        user_email = data.get("user_email") or data.get("to") or data.get("email")
        trip_details = data.get("trip_details", {})
        itinerary = data.get("itinerary", [])
        
        if not user_email:
            return {"success": False, "message": "Missing recipient email"}
        
        if not EMAIL_USER or not EMAIL_PASSWORD:
            return {
                "success": False,
                "message": "Email service not configured. Please set EMAIL_USER and EMAIL_PASSWORD in .env.local file"
            }
        
        subject = f"Your Trip to {trip_details.get('destination', 'Destination')} - Itinerary Confirmed"
        
        # Text version
        text_content = f"""
Hello {trip_details.get('user_name', 'Traveler')}!

Your trip to {trip_details.get('destination', 'your destination')} has been confirmed!

Trip Details:
-------------
Destination: {trip_details.get('destination', 'N/A')}
Dates: {trip_details.get('start_date', 'N/A')} to {trip_details.get('end_date', 'N/A')}
Duration: {trip_details.get('duration', 'N/A')}
Travelers: {trip_details.get('travelers', 'N/A')}
Budget: {trip_details.get('budget', 'N/A')}
Trip Type: {trip_details.get('trip_type', 'N/A')}

Your Itinerary:
--------------
"""
        
        for day_item in itinerary:
            text_content += f"\nDay {day_item.get('day', 'N/A')}: {day_item.get('title', '')}\n"
            for activity in day_item.get('activities', []):
                text_content += f"  • {activity.get('title', '')}\n"
                if activity.get('description'):
                    text_content += f"    {activity.get('description', '')}\n"
        
        text_content += "\n\nHave a wonderful trip!\n\nBest regards,\nAI Trip Planner Team"
        
        # HTML version
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9;">
                <h2 style="color: #2563eb;">🎉 Your Trip is Confirmed!</h2>
                <p>Hello <strong>{trip_details.get('user_name', 'Traveler')}</strong>!</p>
                <p>Your trip to <strong>{trip_details.get('destination', 'your destination')}</strong> has been confirmed!</p>
                
                <div style="background-color: white; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #2563eb; margin-top: 0;">📋 Trip Details</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td style="padding: 8px 0;"><strong>Destination:</strong></td><td>{trip_details.get('destination', 'N/A')}</td></tr>
                        <tr><td style="padding: 8px 0;"><strong>Dates:</strong></td><td>{trip_details.get('start_date', 'N/A')} to {trip_details.get('end_date', 'N/A')}</td></tr>
                        <tr><td style="padding: 8px 0;"><strong>Duration:</strong></td><td>{trip_details.get('duration', 'N/A')}</td></tr>
                        <tr><td style="padding: 8px 0;"><strong>Travelers:</strong></td><td>{trip_details.get('travelers', 'N/A')}</td></tr>
                        <tr><td style="padding: 8px 0;"><strong>Budget:</strong></td><td>{trip_details.get('budget', 'N/A')}</td></tr>
                        <tr><td style="padding: 8px 0;"><strong>Trip Type:</strong></td><td>{trip_details.get('trip_type', 'N/A')}</td></tr>
                    </table>
                </div>
                
                <div style="background-color: white; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #2563eb; margin-top: 0;">🗓️ Your Itinerary</h3>
        """
        
        for day_item in itinerary:
            html_content += f"""
                    <div style="margin-bottom: 20px;">
                        <h4 style="color: #6366f1; margin-bottom: 10px;">Day {day_item.get('day', 'N/A')}: {day_item.get('title', '')}</h4>
            """
            for activity in day_item.get('activities', []):
                html_content += f"""
                        <div style="margin-left: 20px; margin-bottom: 10px;">
                            <strong>📍 {activity.get('title', '')}</strong><br>
                            <span style="color: #666; font-size: 14px;">{activity.get('description', '')}</span><br>
                            <span style="color: #999; font-size: 12px;">Location: {activity.get('location', 'N/A')}</span>
                        </div>
                """
            html_content += "</div>"
        
        html_content += """
                </div>
                
                <p style="margin-top: 30px;">Have a wonderful trip! 🌍✈️</p>
                <p style="color: #666; font-size: 14px;">Best regards,<br>AI Trip Planner Team</p>
            </div>
        </body>
        </html>
        """
        
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_USER
        msg["To"] = user_email
        msg.set_content(text_content)
        msg.add_alternative(html_content, subtype="html")
        
        context = ssl.create_default_context()
        
        try:
            if EMAIL_PORT == 465:
                with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=context, timeout=10) as server:
                    server.login(EMAIL_USER, EMAIL_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(EMAIL_USER, EMAIL_PASSWORD)
                    server.send_message(msg)
            
            print(f"✅ Email sent successfully to {user_email}")
            return {
                "success": True,
                "message": f"Email sent successfully to {user_email}"
            }
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication failed: {e}")
            return {
                "success": False,
                "message": "Email authentication failed. Please check your email credentials and use an App Password for Gmail."
            }
        except smtplib.SMTPException as e:
            print(f"❌ SMTP error: {e}")
            return {
                "success": False,
                "message": f"Failed to send email: {str(e)}"
            }
        except Exception as e:
            print(f"❌ Unexpected error sending email: {e}")
            return {
                "success": False,
                "message": f"connect ECONNREFUSED {EMAIL_HOST}:{EMAIL_PORT}" if "Connection refused" in str(e) else str(e)
            }
            
    except Exception as e:
        print(f"❌ Error in send_email endpoint: {e}")
        return {
            "success": False,
            "message": str(e)
        }

@app.get("/expenses/{trip_id}")
async def get_trip_expenses(trip_id: int):
    """Get all expenses and budget for a specific trip"""
    check_db_connection()
    try:
        print(f"🔍 Fetching expenses for trip_id: {trip_id}")
        
        # Get trip details including budget
        cursor.execute(
            "SELECT id, destination, total_budget FROM confirmed_trips WHERE id = ?",
            (trip_id,)
        )
        trip = cursor.fetchone()
        
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        print(f"✅ Found trip: {trip['destination']}, budget: {trip['total_budget']}")
        
        # Get all expenses for this trip
        cursor.execute(
            "SELECT id, category, amount, description, date, created_at FROM expenses WHERE trip_id = ? ORDER BY date DESC",
            (trip_id,)
        )
        expenses = [dict(e) for e in cursor.fetchall()]
        
        print(f"📊 Found {len(expenses)} expenses")
        
        # Calculate total spent
        total_spent = sum(e['amount'] for e in expenses)
        
        return {
            "trip_id": trip["id"],
            "destination": trip["destination"],
            "total_budget": float(trip["total_budget"]) if trip["total_budget"] else 0,
            "total_spent": total_spent,
            "remaining_budget": (float(trip["total_budget"]) if trip["total_budget"] else 0) - total_spent,
            "expenses": expenses
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting expenses: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/expenses/user/{user_id}")
async def get_user_expenses(user_id: str):
    """Get all expenses for all trips of a user"""
    check_db_connection()
    try:
        print(f"🔍 Fetching all expenses for user_id: {user_id}")
        
        # Get all trips for this user
        cursor.execute(
            "SELECT id, destination, total_budget FROM confirmed_trips WHERE user_id = ?",
            (user_id,)
        )
        trips = [dict(t) for t in cursor.fetchall()]
        
        print(f"📊 Found {len(trips)} trips for user {user_id}")
        
        if not trips:
            return {
                "user_id": user_id,
                "trips": [],
                "total_budget": 0,
                "total_spent": 0
            }
        
        # Get expenses for all trips
        trip_ids = [t['id'] for t in trips]
        placeholders = ','.join('?' * len(trip_ids))
        cursor.execute(
            f"SELECT trip_id, category, amount, description, date FROM expenses WHERE trip_id IN ({placeholders})",
            trip_ids
        )
        all_expenses = [dict(e) for e in cursor.fetchall()]
        
        print(f"💰 Found {len(all_expenses)} total expenses")
        
        # Organize expenses by trip
        for trip in trips:
            trip['expenses'] = [e for e in all_expenses if e['trip_id'] == trip['id']]
            trip['total_spent'] = sum(e['amount'] for e in trip['expenses'])
            trip['remaining_budget'] = (float(trip['total_budget']) if trip['total_budget'] else 0) - trip['total_spent']
        
        total_budget = sum(float(t['total_budget']) if t['total_budget'] else 0 for t in trips)
        total_spent = sum(t['total_spent'] for t in trips)
        
        return {
            "user_id": user_id,
            "trips": trips,
            "total_budget": total_budget,
            "total_spent": total_spent,
            "remaining_budget": total_budget - total_spent
        }
    except Exception as e:
        print(f"❌ Error getting user expenses: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/expenses")
async def add_expense(expense: Expense):
    """Add a new expense to a trip"""
    check_db_connection()
    try:
        # Verify trip exists
        cursor.execute("SELECT id FROM confirmed_trips WHERE id = ?", (expense.trip_id,))
        trip = cursor.fetchone()
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        # Insert expense
        cursor.execute(
            "INSERT INTO expenses (trip_id, category, amount, description, date) VALUES (?, ?, ?, ?, ?)",
            (expense.trip_id, expense.category, expense.amount, expense.description, expense.date)
        )
        conn.commit()
        new_id = cursor.lastrowid
        
        # Get the created expense
        cursor.execute(
            "SELECT id, trip_id, category, amount, description, date, created_at FROM expenses WHERE id = ?",
            (new_id,)
        )
        new_expense = cursor.fetchone()
        
        return {
            "success": True,
            "message": "Expense added successfully",
            "expense": dict(new_expense)
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/expenses/{expense_id}")
async def update_expense(expense_id: int, expense_update: ExpenseUpdate):
    """Update an existing expense"""
    check_db_connection()
    try:
        # Check if expense exists
        cursor.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Expense not found")
        
        # Build update query dynamically
        updates = []
        params = []
        if expense_update.category is not None:
            updates.append("category = ?")
            params.append(expense_update.category)
        if expense_update.amount is not None:
            updates.append("amount = ?")
            params.append(expense_update.amount)
        if expense_update.description is not None:
            updates.append("description = ?")
            params.append(expense_update.description)
        if expense_update.date is not None:
            updates.append("date = ?")
            params.append(expense_update.date)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        params.append(expense_id)
        query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()
        
        # Get updated expense
        cursor.execute(
            "SELECT id, trip_id, category, amount, description, date, created_at FROM expenses WHERE id = ?",
            (expense_id,)
        )
        updated_expense = cursor.fetchone()
        
        return {
            "success": True,
            "message": "Expense updated successfully",
            "expense": dict(updated_expense)
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: int):
    check_db_connection()
    try:
        print(f"🗑️ Deleting expense ID: {expense_id}")

        # Check if expense exists first
        cursor.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,))
        existing = cursor.fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Expense not found")

        # Delete the expense
        cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()  # 🔥 CRITICAL - ensures deletion is permanent
        
        print(f"✅ Expense {expense_id} deleted successfully")

        return {
            "success": True,
            "message": "Expense deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting expense: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trips/user/{user_id}")
async def get_user_trips(user_id: str):
    """Get all confirmed trips for a user"""
    check_db_connection()
    try:
        cursor.execute(
            "SELECT id, destination, total_budget, days, trip_type, members, created_at FROM confirmed_trips WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        trips = [dict(t) for t in cursor.fetchall()]
        
        return {
            "user_id": user_id,
            "trips": trips,
            "count": len(trips)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- CONFIRM TRIP ENDPOINT ---
@app.post("/confirm-trip")
async def confirm_trip(data: dict):
    """Store a confirmed trip for a user."""
    try:
        user_id = data.get("userId") or data.get("user_id")
        destination = data.get("destination")
        plan_text = data.get("planText") or data.get("text")
        total_budget = data.get("total_budget") or data.get("tripBudget")
        days = int(data.get("days")) if data.get("days") else None
        trip_type = data.get("trip_type") or data.get("tripType")
        members = int(data.get("members")) if data.get("members") else None
        itinerary = data.get("itinerary")

        if not user_id:
            return {"success": False, "message": "Missing userId"}
        if not destination:
            return {"success": False, "message": "Missing destination"}
        if not plan_text:
            return {"success": False, "message": "Missing planText"}

        if not conn or not cursor:
            print("⚠️ Database not available, skipping trip save")
            return {
                "success": False,
                "message": "Database not available. Trip not saved, but you can still receive the email."
            }

        itinerary_json = None
        if itinerary is not None:
            try:
                itinerary_json = json.dumps(itinerary)
            except Exception as e:
                print(f"⚠️ Failed to serialize itinerary: {e}")
                itinerary_json = None

        try:
            cursor.execute(
                "INSERT INTO confirmed_trips (user_id, destination, plan_text, total_budget, days, trip_type, members, itinerary_json) VALUES (?,?,?,?,?,?,?,?)",
                (user_id, destination, plan_text, total_budget, days, trip_type, members, itinerary_json)
            )
            conn.commit()
            new_id = cursor.lastrowid
            
            print(f"✅ Trip saved to database with ID: {new_id}")
            
            cursor.execute("SELECT id, user_id, destination, plan_text, total_budget, days, trip_type, members, itinerary_json, created_at FROM confirmed_trips WHERE id = ?", (new_id,))
            row = cursor.fetchone()
            
            if row:
                result = dict(row)
                return {"success": True, "confirmed_trip": result, "message": "Trip saved successfully"}
            else:
                return {"success": True, "message": "Trip saved but could not retrieve details"}
                
        except Exception as db_error:
            print(f"❌ Database error: {db_error}")
            if conn:
                conn.rollback()
            return {
                "success": False,
                "message": f"Database error: {str(db_error)}"
            }
            
    except Exception as e:
        print(f"❌ Error in confirm_trip: {e}")
        return {
            "success": False,
            "message": str(e)
        }
# Replace BOTH of your /confirmed-trip endpoints with this single one:

@app.get("/debug/all-data")
async def debug_all_data():
    """Debug endpoint to see all data in database"""
    check_db_connection()
    try:
        # Check users
        cursor.execute("SELECT id, email, name FROM users")
        users = [dict(u) for u in cursor.fetchall()]
        
        # Check trips
        cursor.execute("SELECT * FROM confirmed_trips")
        trips = [dict(t) for t in cursor.fetchall()]
        
        # Check expenses
        cursor.execute("SELECT * FROM expenses")
        expenses = [dict(e) for e in cursor.fetchall()]
        
        return {
            "users": users,
            "trips": trips,
            "expenses": expenses,
            "trip_count": len(trips),
            "expense_count": len(expenses)
        }
    except Exception as e:
        return {"error": str(e)}

# 2. FIXED /confirmed-trip ENDPOINT
@app.get("/confirmed-trip")
async def get_latest_confirmed_trip_by_email(email: str):
    """Fetch the latest confirmed trip by email"""
    check_db_connection()

    try:
        print(f"🔍 Fetching confirmed trip for email: {email}")

        # Get user_id from email
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if not user:
            print("❌ No user found with that email")
            raise HTTPException(status_code=404, detail="No user found for this email")

        user_id = user["id"]
        print(f"🔑 Found user_id: {user_id}")

        # Debug: Check what's in the database
        cursor.execute("SELECT COUNT(*) as count FROM confirmed_trips WHERE user_id = ?", (user_id,))
        count_result = cursor.fetchone()
        count = count_result["count"] if count_result else 0
        print(f"📊 Found {count} trips for user_id {user_id}")

        if count == 0:
            print("❌ No trips found in database for this user")
            raise HTTPException(status_code=404, detail="No confirmed trip found")

        # Fetch the LATEST trip
        cursor.execute(
            """
            SELECT id, user_id, destination, plan_text, total_budget, days,
                   trip_type, members, itinerary_json, completed, year, created_at
            FROM confirmed_trips
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,)
        )

        trip = cursor.fetchone()

        if not trip:
            print("❌ Query returned no results")
            raise HTTPException(status_code=404, detail="No confirmed trip found")

        print(f"✅ Found trip ID: {trip['id']} - {trip['destination']}")
        
        trip_dict = dict(trip)

        # Parse JSON if exists
        if trip_dict.get("itinerary_json"):
            try:
                trip_dict["itinerary"] = json.loads(trip_dict["itinerary_json"])
            except Exception as e:
                print(f"⚠️ Failed to parse itinerary_json: {e}")
                trip_dict["itinerary"] = None

        # Convert budget to float
        if trip_dict.get("total_budget") is not None:
            trip_dict["total_budget"] = float(trip_dict["total_budget"])

        # Ensure completed is boolean
        trip_dict["completed"] = bool(trip_dict.get("completed", 0))

        return trip_dict

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Backend error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/weather-forecast")
async def get_weather_forecast(weather_request: WeatherRequest, days: int = 7):
    """Get multi-day weather forecast"""
    if not OPENWEATHER_API_KEY:
        raise HTTPException(status_code=503, detail="Weather service not configured")
    
    # Use the 5-day forecast endpoint (free tier)
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={weather_request.city}&appid={OPENWEATHER_API_KEY}&units=metric&cnt={days * 8}"  # 8 readings per day
    
    response = requests.get(url)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch weather forecast")
    
    data = response.json()
    
    # Group by date and get daily averages
    daily_forecasts = {}
    for item in data['list']:
        date = item['dt_txt'].split(' ')[0]  # Extract date
        if date not in daily_forecasts:
            daily_forecasts[date] = {
                'temp': [],
                'description': item['weather'][0]['description'],
                'humidity': item['main']['humidity'],
                'wind_speed': item['wind']['speed']
            }
        daily_forecasts[date]['temp'].append(item['main']['temp'])
    
    # Calculate daily averages
    forecast_list = []
    for date, info in daily_forecasts.items():
        forecast_list.append({
            'date': date,
            'temperature': sum(info['temp']) / len(info['temp']),
            'description': info['description'],
            'humidity': info['humidity'],
            'wind_speed': info['wind_speed']
        })
    
    return {
        'city': weather_request.city,
        'forecasts': forecast_list[:days]
    }

# --- WEATHER ---
@app.post("/weather", response_model=WeatherResponse)
async def get_weather(weather_request: WeatherRequest):
    if not OPENWEATHER_API_KEY:
        raise HTTPException(status_code=503, detail="Weather service not configured")
    url = f"https://api.openweathermap.org/data/2.5/weather?q={weather_request.city}&appid={OPENWEATHER_API_KEY}&units=metric"
    r = requests.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail="Failed to fetch weather")
    d = r.json()
    return WeatherResponse(
        city=d["name"], temperature=d["main"]["temp"],
        description=d["weather"][0]["description"],
        humidity=d["main"]["humidity"], wind_speed=d["wind"]["speed"]
    )

# --- TRAVEL PLAN ---
@app.post("/travel-plan", response_model=List[Attraction])
async def create_travel_plan(form_data: TravelFormData):
    try:
        loc = geocode_location(form_data.destination)
        if not loc:
            loc = get_country_centroid(form_data.destination)
            if loc:
                print(f"ℹ️ Resolved '{form_data.destination}' via RestCountries to {loc['lat']},{loc['lon']}")
        if not loc:
            print(f"⚠️ Location not found for '{form_data.destination}'; returning empty attractions list for graceful fallback")
            return []
        attractions = get_tourist_attractions(loc["lat"], loc["lon"])
        dep = datetime.strptime(form_data.departureDate, "%Y-%m-%d")
        ret = datetime.strptime(form_data.returnDate, "%Y-%m-%d")
        days = max(1, (ret - dep).days)
        itinerary = []
        max_places = min(len(attractions), days * 3)
        for i in range(max_places):
            p = attractions[i]
            itinerary.append(Attraction(
                name=p["name"], lat=p["lat"], lng=p["lon"],
                day=(i % days) + 1, description=p["description"]
            ))
        if conn and cursor:
            for p in itinerary:
                try:
                    cursor.execute(
                        "INSERT INTO itineraries (user_id, name, lat, lng, day, description) VALUES (?,?,?,?,?,?)",
                        (form_data.userId, p.name, p.lat, p.lng, p.day, p.description)
                    )
                    conn.commit()
                except Exception:
                    if conn:
                        conn.rollback()
        return itinerary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- FEEDBACK ---
@app.get("/feedbacks")
async def get_feedbacks():
    check_db_connection()
    try:
        cursor.execute("SELECT message, user_name FROM feedbacks ORDER BY id DESC")
        feedbacks = [{"message": r["message"], "user_name": r["user_name"]} for r in cursor.fetchall()]
        return feedbacks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedbacks")
async def post_feedback(fb: Feedback):
    check_db_connection()
    try:
        cursor.execute("INSERT INTO feedbacks (message, user_name) VALUES (?, ?)", (fb.message, fb.user_name))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trips/user/{user_id}/all")
async def get_all_user_trips(user_id: str):
    """Get ALL confirmed trips for a user (for roadmap display)"""
    check_db_connection()
    try:
        print(f"🔍 Fetching all trips for user_id: {user_id}")
        
        cursor.execute(
            """SELECT id, destination, total_budget, days, trip_type, members, 
               completed, year, created_at 
               FROM confirmed_trips 
               WHERE user_id = ? 
               ORDER BY COALESCE(year, strftime('%Y', created_at)) ASC, created_at ASC""",
            (user_id,)
        )
        trips = cursor.fetchall()
        
        print(f"📊 Found {len(trips)} trips for user {user_id}")
        
        trips_list = []
        for trip in trips:
            trip_dict = dict(trip)
            # If year is not set, extract from created_at
            if not trip_dict.get('year'):
                try:
                    created_date = datetime.strptime(trip_dict['created_at'], '%Y-%m-%d %H:%M:%S')
                    trip_dict['year'] = created_date.year
                except:
                    trip_dict['year'] = datetime.now().year
            
            # Ensure completed is boolean
            trip_dict['completed'] = bool(trip_dict.get('completed', 0))
            trips_list.append(trip_dict)
        
        return {
            "user_id": user_id,
            "trips": trips_list,
            "count": len(trips_list),
            "completed_count": sum(1 for t in trips_list if t['completed']),
            "pending_count": sum(1 for t in trips_list if not t['completed'])
        }
    except Exception as e:
        print(f"❌ Error getting user trips: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/trips/{trip_id}/complete")
async def toggle_trip_completion(trip_id: int, completion: TripComplete):
    """Mark a trip as completed or pending"""
    check_db_connection()
    try:
        # Check if trip exists
        cursor.execute("SELECT id, completed FROM confirmed_trips WHERE id = ?", (trip_id,))
        trip = cursor.fetchone()
        
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        # Update completion status
        cursor.execute(
            "UPDATE confirmed_trips SET completed = ? WHERE id = ?",
            (1 if completion.completed else 0, trip_id)
        )
        conn.commit()
        
        # Get updated trip
        cursor.execute(
            """SELECT id, destination, total_budget, days, trip_type, members, 
               completed, year, created_at 
               FROM confirmed_trips 
               WHERE id = ?""",
            (trip_id,)
        )
        updated_trip = cursor.fetchone()
        
        trip_dict = dict(updated_trip)
        trip_dict['completed'] = bool(trip_dict.get('completed', 0))
        
        return {
            "success": True,
            "message": f"Trip marked as {'completed' if completion.completed else 'pending'}",
            "trip": trip_dict
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/trips/{trip_id}")
async def update_trip(trip_id: int, trip_update: TripUpdate):
    """Update trip details"""
    check_db_connection()
    try:
        # Check if trip exists
        cursor.execute("SELECT id FROM confirmed_trips WHERE id = ?", (trip_id,))
        trip = cursor.fetchone()
        
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        # Build update query dynamically
        updates = []
        params = []
        
        if trip_update.destination is not None:
            updates.append("destination = ?")
            params.append(trip_update.destination)
        if trip_update.total_budget is not None:
            updates.append("total_budget = ?")
            params.append(trip_update.total_budget)
        if trip_update.days is not None:
            updates.append("days = ?")
            params.append(trip_update.days)
        if trip_update.trip_type is not None:
            updates.append("trip_type = ?")
            params.append(trip_update.trip_type)
        if trip_update.members is not None:
            updates.append("members = ?")
            params.append(trip_update.members)
        if trip_update.completed is not None:
            updates.append("completed = ?")
            params.append(1 if trip_update.completed else 0)
        if trip_update.year is not None:
            updates.append("year = ?")
            params.append(trip_update.year)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        params.append(trip_id)
        query = f"UPDATE confirmed_trips SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()
        
        # Get updated trip
        cursor.execute(
            """SELECT id, destination, total_budget, days, trip_type, members, 
               completed, year, created_at 
               FROM confirmed_trips 
               WHERE id = ?""",
            (trip_id,)
        )
        updated_trip = cursor.fetchone()
        
        trip_dict = dict(updated_trip)
        trip_dict['completed'] = bool(trip_dict.get('completed', 0))
        
        return {
            "success": True,
            "message": "Trip updated successfully",
            "trip": trip_dict
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}/achievements")
async def get_user_achievements(user_id: str):
    """Get user achievements based on completed trips"""
    check_db_connection()
    try:
        # Get all completed trips
        cursor.execute(
            """SELECT id, destination, days, trip_type, year 
               FROM confirmed_trips 
               WHERE user_id = ? AND completed = 1
               ORDER BY year ASC""",
            (user_id,)
        )
        completed_trips = [dict(t) for t in cursor.fetchall()]
        
        # Calculate achievement statistics
        total_trips = len(completed_trips)
        solo_trips = sum(1 for t in completed_trips if t['trip_type'] == 'Solo')
        group_trips = sum(1 for t in completed_trips if t['trip_type'] == 'Group')
        total_days = sum(t['days'] for t in completed_trips if t['days'])
        unique_years = len(set(t['year'] for t in completed_trips if t['year']))
        
        achievements = []
        
        # Tier-based achievements
        if total_trips >= 10:
            achievements.append({
                "icon": "🌟",
                "title": "Legendary Explorer",
                "subtitle": f"{total_trips} trips completed",
                "color": "from-purple-400 to-pink-500",
                "unlocked": True
            })
        elif total_trips >= 5:
            achievements.append({
                "icon": "🌍",
                "title": "World Traveler",
                "subtitle": f"{total_trips} trips completed",
                "color": "from-blue-400 to-indigo-500",
                "unlocked": True
            })
        elif total_trips >= 3:
            achievements.append({
                "icon": "🗺️",
                "title": "Cultural Explorer",
                "subtitle": f"{total_trips} trips completed",
                "color": "from-green-400 to-emerald-500",
                "unlocked": True
            })
        elif total_trips >= 1:
            achievements.append({
                "icon": "✈️",
                "title": "First Journey",
                "subtitle": "1 trip completed",
                "color": "from-teal-400 to-cyan-500",
                "unlocked": True
            })
        
        # Solo achievements
        if solo_trips >= 3:
            achievements.append({
                "icon": "🎒",
                "title": "Solo Adventurer",
                "subtitle": f"{solo_trips} solo trips",
                "color": "from-orange-400 to-red-500",
                "unlocked": True
            })
        elif solo_trips >= 1:
            achievements.append({
                "icon": "💼",
                "title": "Independent Traveler",
                "subtitle": "First solo trip",
                "color": "from-yellow-400 to-orange-400",
                "unlocked": True
            })
        
        # Group achievements
        if group_trips >= 3:
            achievements.append({
                "icon": "👥",
                "title": "Group Leader",
                "subtitle": f"{group_trips} group trips",
                "color": "from-teal-400 to-cyan-500",
                "unlocked": True
            })
        elif group_trips >= 1:
            achievements.append({
                "icon": "🧭",
                "title": "Team Explorer",
                "subtitle": "First group trip",
                "color": "from-emerald-400 to-teal-400",
                "unlocked": True
            })
        
        # Time-based achievements
        if total_days >= 30:
            achievements.append({
                "icon": "⏰",
                "title": "Time Traveler",
                "subtitle": f"{total_days} days traveled",
                "color": "from-indigo-400 to-purple-500",
                "unlocked": True
            })
        
        if unique_years >= 3:
            achievements.append({
                "icon": "📅",
                "title": "Annual Explorer",
                "subtitle": f"{unique_years} years active",
                "color": "from-pink-400 to-rose-500",
                "unlocked": True
            })
        
        return {
            "user_id": user_id,
            "achievements": achievements,
            "statistics": {
                "total_trips": total_trips,
                "solo_trips": solo_trips,
                "group_trips": group_trips,
                "total_days": total_days,
                "unique_years": unique_years
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# UPDATE EXISTING confirm-trip ENDPOINT
# ============================================
# Replace your existing confirm-trip with this updated version:

@app.post("/confirm-trip")
async def confirm_trip(data: dict):
    """Store a confirmed trip for a user with year extraction"""
    try:
        user_id = data.get("userId") or data.get("user_id")
        destination = data.get("destination")
        plan_text = data.get("planText") or data.get("text")
        total_budget = data.get("total_budget") or data.get("tripBudget")
        days = int(data.get("days")) if data.get("days") else None
        trip_type = data.get("trip_type") or data.get("tripType")
        members = int(data.get("members")) if data.get("members") else None
        itinerary = data.get("itinerary")
        
        # Extract year from departure date if available
        year = None
        departure_date = data.get("departureDate")
        if departure_date:
            try:
                date_obj = datetime.strptime(departure_date, "%Y-%m-%d")
                year = date_obj.year
            except:
                year = datetime.now().year
        else:
            year = datetime.now().year

        if not user_id:
            return {"success": False, "message": "Missing userId"}
        if not destination:
            return {"success": False, "message": "Missing destination"}
        if not plan_text:
            return {"success": False, "message": "Missing planText"}

        if not conn or not cursor:
            print("⚠️ Database not available, skipping trip save")
            return {
                "success": False,
                "message": "Database not available. Trip not saved, but you can still receive the email."
            }

        itinerary_json = None
        if itinerary is not None:
            try:
                itinerary_json = json.dumps(itinerary)
            except Exception as e:
                print(f"⚠️ Failed to serialize itinerary: {e}")
                itinerary_json = None

        try:
            cursor.execute(
                """INSERT INTO confirmed_trips 
                   (user_id, destination, plan_text, total_budget, days, trip_type, members, itinerary_json, year, completed) 
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (user_id, destination, plan_text, total_budget, days, trip_type, members, itinerary_json, year, 0)
            )
            conn.commit()
            new_id = cursor.lastrowid
            
            print(f"✅ Trip saved to database with ID: {new_id}")
            
            cursor.execute(
                """SELECT id, user_id, destination, plan_text, total_budget, days, 
                   trip_type, members, itinerary_json, year, completed, created_at 
                   FROM confirmed_trips WHERE id = ?""", 
                (new_id,)
            )
            row = cursor.fetchone()
            
            if row:
                result = dict(row)
                result['completed'] = bool(result.get('completed', 0))
                return {"success": True, "confirmed_trip": result, "message": "Trip saved successfully"}
            else:
                return {"success": True, "message": "Trip saved but could not retrieve details"}
                
        except Exception as db_error:
            print(f"❌ Database error: {db_error}")
            if conn:
                conn.rollback()
            return {
                "success": False,
                "message": f"Database error: {str(db_error)}"
            }
            
    except Exception as e:
        print(f"❌ Error in confirm_trip: {e}")
        return {
            "success": False,
            "message": str(e)
        }
    
# --- AUTH ENDPOINTS ---
@app.post("/register-user")
async def register_user(user: UserSignUp):
    """Register a new user with email and password"""
    check_db_connection()
    try:
        print(f"📝 Registration attempt for: {user.email}")
        cursor.execute("SELECT email FROM users WHERE email = ?", (user.email,))
        existing = cursor.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        hashed_password = hash_password_bcrypt(user.password)
        cursor.execute(
            "INSERT INTO users (name, email, dob, password_hash) VALUES (?, ?, ?, ?)",
            (user.name, user.email, user.dob, hashed_password)
        )
        conn.commit()
        new_id = cursor.lastrowid
        cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (new_id,))
        new_user = cursor.fetchone()
        return {
            "status": "success",
            "message": "User registered successfully",
            "user": {"id": new_user["id"], "name": new_user["name"], "email": new_user["email"]}
        }
    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/signin")
async def signin(user: UserSignIn):
    """Sign in with email and password"""
    check_db_connection()
    try:
        print(f"🔐 Sign-in attempt for: {user.email}")
        cursor.execute("SELECT id, name, email, dob, password_hash FROM users WHERE email = ?", (user.email,))
        db_user = cursor.fetchone()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        if not verify_password(user.password, db_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")
        return {
            "status": "success",
            "message": "Sign in successful",
            "user": {"id": db_user["id"], "name": db_user["name"], "email": db_user["email"], "dob": db_user.get("dob") if isinstance(db_user, dict) else db_user["dob"] if "dob" in db_user.keys() else db_user[3] },
            "token": f"token_{db_user['id']}_{int(time.time())}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users")
async def get_users():
    """Get all users"""
    check_db_connection()
    try:
        cursor.execute("SELECT id, name, email, dob, created_at FROM users;")
        users = [dict(u) for u in cursor.fetchall()]
        return {"users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}")
async def get_user_profile(user_id: int):
    """Get user profile by ID"""
    check_db_connection()
    try:
        cursor.execute("SELECT id, name, email, dob FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "username": user["name"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- HEALTH CHECK ---
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "OpenWeather": bool(OPENWEATHER_API_KEY),
            "Amadeus": bool(AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET),
            "RapidAPI": bool(RAPIDAPI_KEY),
            "Email": bool(EMAIL_USER and EMAIL_PASSWORD),
            "OpenStreetMap": True,
            "SQLite": bool(conn and cursor),
        },
    }

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Agile Voyager API is running",
        "version": "1.0",
        "endpoints": {
            "auth": "/api/auth/signin, /register-user",
            "travel": "/travel-plan, /confirm-trip, /send-email, /send-itinerary",
            "weather": "/weather",
            "users": "/users"
        }
    }

@app.on_event("shutdown")
def shutdown_db():
    try:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        print("✅ Database connection closed")
    except Exception:
        pass

if __name__ == "__main__":
    print("🚀 Starting Travel Planner Backend...")
    print("📍 Server will run on: http://localhost:8001")
    uvicorn.run("main:app", host="localhost", port=8001, reload=True)

PORT = int(os.environ.get("PORT", 8001))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)