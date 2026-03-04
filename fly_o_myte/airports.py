"""
Airport name resolver for international destinations.

Maps city names, country names, and common travel nicknames to IATA airport codes.
Covers ~60 top international destinations for Australian families.

AU domestic airports are NOT included here — they are handled by
price_sources.serpapi._AU_AIRPORTS.

Usage:
    from fly_o_myte.airports import resolve_destination

    resolve_destination('sri lanka')  # [('CMB', 'Colombo Bandaranaike (Sri Lanka)')]
    resolve_destination('japan')      # [('FUK', ...), ('HND', ...), ('KIX', ...), ('NRT', ...)]
"""

from __future__ import annotations

# Each entry: (IATA_code, display_name, search_terms)
# search_terms is a list of lowercase strings for partial matching.
_AIRPORTS: list[tuple[str, str, list[str]]] = [
    # Singapore
    ("SIN", "Singapore Changi (Singapore)", ["singapore", "sin", "changi"]),
    # Japan
    ("NRT", "Tokyo Narita (Japan)", ["japan", "tokyo", "narita", "nrt"]),
    ("HND", "Tokyo Haneda (Japan)", ["japan", "tokyo", "haneda", "hnd"]),
    ("KIX", "Osaka Kansai (Japan)", ["japan", "osaka", "kansai", "kix"]),
    ("FUK", "Fukuoka (Japan)", ["japan", "fukuoka", "fuk"]),
    ("NGO", "Nagoya Chubu (Japan)", ["japan", "nagoya", "chubu", "ngo"]),
    # Thailand
    (
        "BKK",
        "Bangkok Suvarnabhumi (Thailand)",
        ["thailand", "bangkok", "bkk", "suvarnabhumi"],
    ),
    ("HKT", "Phuket (Thailand)", ["thailand", "phuket", "hkt"]),
    ("CNX", "Chiang Mai (Thailand)", ["thailand", "chiang mai", "chiangmai", "cnx"]),
    ("USM", "Koh Samui (Thailand)", ["thailand", "koh samui", "samui", "usm"]),
    # Sri Lanka
    (
        "CMB",
        "Colombo Bandaranaike (Sri Lanka)",
        ["sri lanka", "colombo", "cmb", "bandaranaike"],
    ),
    # Bali / Indonesia
    (
        "DPS",
        "Bali Ngurah Rai (Indonesia)",
        ["bali", "denpasar", "dps", "ngurah rai", "indonesia"],
    ),
    (
        "CGK",
        "Jakarta Soekarno-Hatta (Indonesia)",
        ["jakarta", "indonesia", "cgk", "soekarno"],
    ),
    ("SUB", "Surabaya (Indonesia)", ["surabaya", "indonesia", "sub"]),
    # UK / Europe
    (
        "LHR",
        "London Heathrow (UK)",
        ["london", "uk", "united kingdom", "england", "britain", "heathrow", "lhr"],
    ),
    (
        "LGW",
        "London Gatwick (UK)",
        ["london", "uk", "united kingdom", "england", "britain", "gatwick", "lgw"],
    ),
    (
        "MAN",
        "Manchester (UK)",
        ["manchester", "man", "uk", "united kingdom", "england"],
    ),
    ("EDI", "Edinburgh (UK)", ["edinburgh", "scotland", "uk", "united kingdom", "edi"]),
    # France
    (
        "CDG",
        "Paris Charles de Gaulle (France)",
        ["paris", "france", "cdg", "charles de gaulle"],
    ),
    ("ORY", "Paris Orly (France)", ["paris", "france", "ory", "orly"]),
    # Italy
    ("FCO", "Rome Fiumicino (Italy)", ["rome", "italy", "fco", "fiumicino"]),
    ("MXP", "Milan Malpensa (Italy)", ["milan", "italy", "mxp", "malpensa"]),
    ("VCE", "Venice Marco Polo (Italy)", ["venice", "italy", "vce"]),
    # Spain
    ("BCN", "Barcelona El Prat (Spain)", ["barcelona", "spain", "bcn"]),
    ("MAD", "Madrid Barajas (Spain)", ["madrid", "spain", "mad"]),
    # Germany
    ("FRA", "Frankfurt (Germany)", ["frankfurt", "germany", "fra"]),
    ("MUC", "Munich (Germany)", ["munich", "germany", "muc"]),
    # Netherlands
    (
        "AMS",
        "Amsterdam Schiphol (Netherlands)",
        ["amsterdam", "netherlands", "holland", "ams"],
    ),
    # Greece
    ("ATH", "Athens Eleftherios Venizelos (Greece)", ["athens", "greece", "ath"]),
    ("HER", "Heraklion Crete (Greece)", ["crete", "heraklion", "greece", "her"]),
    # Hong Kong
    ("HKG", "Hong Kong International", ["hong kong", "hkg"]),
    # UAE
    (
        "DXB",
        "Dubai International (UAE)",
        ["dubai", "uae", "united arab emirates", "dxb"],
    ),
    ("AUH", "Abu Dhabi (UAE)", ["abu dhabi", "auh", "uae", "united arab emirates"]),
    # Qatar
    ("DOH", "Doha Hamad (Qatar)", ["doha", "qatar", "doh"]),
    # India
    (
        "DEL",
        "Delhi Indira Gandhi (India)",
        ["delhi", "india", "new delhi", "del", "indira gandhi"],
    ),
    ("BOM", "Mumbai Chhatrapati Shivaji (India)", ["mumbai", "bombay", "india", "bom"]),
    ("MAA", "Chennai (India)", ["chennai", "madras", "india", "maa"]),
    ("BLR", "Bangalore Kempegowda (India)", ["bangalore", "bengaluru", "india", "blr"]),
    ("GOI", "Goa Dabolim (India)", ["goa", "india", "goi", "dabolim"]),
    # New Zealand
    ("AKL", "Auckland (New Zealand)", ["auckland", "new zealand", "nz", "akl"]),
    ("WLG", "Wellington (New Zealand)", ["wellington", "new zealand", "nz", "wlg"]),
    ("CHC", "Christchurch (New Zealand)", ["christchurch", "new zealand", "nz", "chc"]),
    ("ZQN", "Queenstown (New Zealand)", ["queenstown", "new zealand", "nz", "zqn"]),
    # USA
    (
        "LAX",
        "Los Angeles (USA)",
        ["los angeles", "lax", "usa", "united states", "america"],
    ),
    (
        "JFK",
        "New York JFK (USA)",
        ["new york", "jfk", "usa", "united states", "america", "nyc"],
    ),
    (
        "SFO",
        "San Francisco (USA)",
        ["san francisco", "sfo", "usa", "united states", "america"],
    ),
    (
        "HNL",
        "Honolulu Hawaii (USA)",
        ["honolulu", "hawaii", "hnl", "usa", "united states"],
    ),
    ("LAS", "Las Vegas (USA)", ["las vegas", "las", "usa", "united states", "america"]),
    # South Korea
    (
        "ICN",
        "Seoul Incheon (South Korea)",
        ["seoul", "south korea", "korea", "icn", "incheon"],
    ),
    (
        "GMP",
        "Seoul Gimpo (South Korea)",
        ["seoul", "south korea", "korea", "gimpo", "gmp"],
    ),
    ("PUS", "Busan (South Korea)", ["busan", "south korea", "korea", "pus"]),
    # Malaysia
    ("KUL", "Kuala Lumpur (Malaysia)", ["kuala lumpur", "kl", "malaysia", "kul"]),
    ("PEN", "Penang (Malaysia)", ["penang", "malaysia", "pen"]),
    # Philippines
    ("MNL", "Manila (Philippines)", ["manila", "philippines", "mnl"]),
    ("CEB", "Cebu (Philippines)", ["cebu", "philippines", "ceb"]),
    # Vietnam
    (
        "SGN",
        "Ho Chi Minh City (Vietnam)",
        ["ho chi minh", "saigon", "hcmc", "vietnam", "sgn"],
    ),
    ("HAN", "Hanoi (Vietnam)", ["hanoi", "vietnam", "han"]),
    ("DAD", "Da Nang (Vietnam)", ["da nang", "danang", "vietnam", "dad"]),
    ("PQC", "Phu Quoc (Vietnam)", ["phu quoc", "vietnam", "pqc"]),
    # China
    ("PEK", "Beijing Capital (China)", ["beijing", "china", "pek"]),
    ("PVG", "Shanghai Pudong (China)", ["shanghai", "china", "pvg"]),
    ("CAN", "Guangzhou (China)", ["guangzhou", "canton", "china", "can"]),
    # Maldives
    ("MLE", "Male Velana (Maldives)", ["maldives", "male", "mle", "velana"]),
    # Fiji
    ("NAN", "Nadi (Fiji)", ["fiji", "nadi", "nan"]),
    # Mauritius
    ("MRU", "Mauritius Sir Seewoosagur Ramgoolam", ["mauritius", "mru"]),
    # South Africa
    (
        "JNB",
        "Johannesburg O.R. Tambo (South Africa)",
        ["johannesburg", "south africa", "jnb"],
    ),
    ("CPT", "Cape Town (South Africa)", ["cape town", "south africa", "cpt"]),
    # Canada
    ("YVR", "Vancouver (Canada)", ["vancouver", "canada", "yvr"]),
    ("YYZ", "Toronto Pearson (Canada)", ["toronto", "canada", "yyz"]),
    # Mexico
    ("CUN", "Cancun (Mexico)", ["cancun", "mexico", "cun"]),
    # Turkey
    ("IST", "Istanbul (Turkey)", ["istanbul", "turkey", "ist"]),
    # Egypt
    ("HRG", "Hurghada (Egypt)", ["hurghada", "egypt", "hrg"]),
    ("SSH", "Sharm el-Sheikh (Egypt)", ["sharm el-sheikh", "sharm", "egypt", "ssh"]),
]


def resolve_destination(query: str) -> list[tuple[str, str]]:
    """Return list of (IATA_code, display_name) matching the query string.

    Matching is case-insensitive and partial — a query of 'japan' will return
    all airports whose search terms contain 'japan'. Results are sorted
    alphabetically by IATA code.

    AU domestic airports are excluded; use price_sources.serpapi._AU_AIRPORTS
    for domestic routes.
    """
    q = query.lower().strip()
    if not q:
        return []

    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for iata, display_name, terms in _AIRPORTS:
        if iata in seen:
            continue
        if (
            any(q in term for term in terms)
            or q in iata.lower()
            or q in display_name.lower()
        ):
            results.append((iata, display_name))
            seen.add(iata)

    return sorted(results, key=lambda x: x[0])
