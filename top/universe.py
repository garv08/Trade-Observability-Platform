"""Nifty 50 constituents as of 2026-10-31.

Source: NSE Indices constituent list, republished with weights at
https://whichindex.com/indexes/nifty-50/ (data date 2026-10-31).
Blank index sectors for LT, Adani Ports, Eternal, and Trent are filled
from the company's usual Nifty classification so the desk can filter.
"""

from __future__ import annotations

UNIVERSE = [
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy", "weight": 8.49},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "sector": "Communication Services", "weight": 6.63},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Financials", "weight": 5.76},
    {"symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Financials", "weight": 5.41},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "Information Technology", "weight": 4.88},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Financials", "weight": 4.78},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance", "sector": "Financials", "weight": 3.15},
    {"symbol": "LT", "name": "Larsen & Toubro", "sector": "Industrials", "weight": 2.87},
    {"symbol": "INFY", "name": "Infosys", "sector": "Information Technology", "weight": 2.58},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank", "sector": "Financials", "weight": 2.47},
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever", "sector": "Consumer Staples", "weight": 2.36},
    {"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ", "sector": "Industrials", "weight": 2.30},
    {"symbol": "SUNPHARMA", "name": "Sun Pharma", "sector": "Health Care", "weight": 2.30},
    {"symbol": "TITAN", "name": "Titan Company", "sector": "Consumer Discretionary", "weight": 2.12},
    {"symbol": "HCLTECH", "name": "HCLTech", "sector": "Information Technology", "weight": 2.08},
    {"symbol": "AXISBANK", "name": "Axis Bank", "sector": "Financials", "weight": 2.04},
    {"symbol": "MARUTI", "name": "Maruti Suzuki", "sector": "Consumer Discretionary", "weight": 1.93},
    {"symbol": "ADANIENT", "name": "Adani Enterprises", "sector": "Materials", "weight": 1.88},
    {"symbol": "M&M", "name": "Mahindra & Mahindra", "sector": "Consumer Discretionary", "weight": 1.84},
    {"symbol": "ITC", "name": "ITC", "sector": "Consumer Staples", "weight": 1.79},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement", "sector": "Materials", "weight": 1.75},
    {"symbol": "ETERNAL", "name": "Eternal", "sector": "Consumer Discretionary", "weight": 1.70},
    {"symbol": "NTPC", "name": "NTPC", "sector": "Utilities", "weight": 1.65},
    {"symbol": "JSWSTEEL", "name": "JSW Steel", "sector": "Materials", "weight": 1.64},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto", "sector": "Consumer Discretionary", "weight": 1.53},
    {"symbol": "ONGC", "name": "ONGC", "sector": "Energy", "weight": 1.53},
    {"symbol": "BEL", "name": "Bharat Electronics", "sector": "Industrials", "weight": 1.46},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv", "sector": "Financials", "weight": 1.44},
    {"symbol": "POWERGRID", "name": "Power Grid", "sector": "Utilities", "weight": 1.33},
    {"symbol": "COALINDIA", "name": "Coal India", "sector": "Energy", "weight": 1.29},
    {"symbol": "NESTLEIND", "name": "Nestle India", "sector": "Consumer Staples", "weight": 1.21},
    {"symbol": "ASIANPAINT", "name": "Asian Paints", "sector": "Consumer Discretionary", "weight": 1.20},
    {"symbol": "TATASTEEL", "name": "Tata Steel", "sector": "Materials", "weight": 1.13},
    {"symbol": "GRASIM", "name": "Grasim Industries", "sector": "Materials", "weight": 1.09},
    {"symbol": "EICHERMOT", "name": "Eicher Motors", "sector": "Consumer Discretionary", "weight": 1.07},
    {"symbol": "HINDALCO", "name": "Hindalco Industries", "sector": "Materials", "weight": 1.07},
    {"symbol": "SHRIRAMFIN", "name": "Shriram Finance", "sector": "Financials", "weight": 1.04},
    {"symbol": "INDIGO", "name": "InterGlobe Aviation", "sector": "Industrials", "weight": None},
    {"symbol": "TECHM", "name": "Tech Mahindra", "sector": "Information Technology", "weight": 0.95},
    {"symbol": "SBILIFE", "name": "SBI Life Insurance", "sector": "Financials", "weight": 0.90},
    {"symbol": "TRENT", "name": "Trent", "sector": "Consumer Discretionary", "weight": 0.87},
    {"symbol": "BSE", "name": "BSE", "sector": "Financials", "weight": 0.77},
    {"symbol": "JIOFIN", "name": "Jio Financial Services", "sector": "Financials", "weight": 0.75},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals", "sector": "Health Care", "weight": 0.65},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories", "sector": "Health Care", "weight": 0.61},
    {"symbol": "HDFCLIFE", "name": "HDFC Life", "sector": "Financials", "weight": 0.61},
    {"symbol": "CIPLA", "name": "Cipla", "sector": "Health Care", "weight": 0.60},
    {"symbol": "TATACONSUM", "name": "Tata Consumer Products", "sector": "Consumer Staples", "weight": 0.55},
    {"symbol": "TMPV", "name": "Tata Motors Passenger Vehicles", "sector": "Consumer Discretionary", "weight": 0.53},
    {"symbol": "MAXHEALTH", "name": "Max Healthcare", "sector": "Health Care", "weight": 0.45},
]


def yahoo_symbol(symbol: str) -> str:
    return f"{symbol}.NS"
