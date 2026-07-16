"""
Config for Rural synthetic data.

Kept separate from generation logic so sectors/places/names can be extended
without touching the generator itself.

12 sectors: That are genuinely common rural/semi-urban micro-enterprise categories in Gujarat."""

SECTORS = [
    "dairy",
    "poultry",
    "food_processing",
    "handicrafts",
    "rural_retail",
    "flour_mill",
    "oil_mill",
    "textile_weaving",
    "brick_kiln",
    "agri_input_retail",
    "auto_repair",
    "tea_stall_eatery",
]

SECTOR_BASE_INCOME = {
    "dairy": 28000,
    "poultry": 35000,
    "food_processing": 32000,
    "handicrafts": 18000,
    "rural_retail": 25000,
    "flour_mill": 30000,
    "oil_mill": 34000,
    "textile_weaving": 22000,
    "brick_kiln": 55000,          # seasonal but high-value, kiln operators run bigger cash volumes
    "agri_input_retail": 40000,   # seed/fertilizer/pesticide shops, spikes at sowing season
    "auto_repair": 26000,
    "tea_stall_eatery": 16000,
}

# monthly seasonality multiplier, index 0 = Jan
SECTOR_SEASONALITY = {
    "dairy":              [1.05, 1.05, 1.0, 0.9, 0.8, 0.75, 0.8, 0.85, 0.9, 1.0, 1.1, 1.1],
    "poultry":            [1.0, 1.0, 0.95, 0.9, 0.85, 0.85, 0.9, 0.95, 1.0, 1.1, 1.15, 1.05],
    "food_processing":    [0.95, 0.95, 1.0, 1.0, 1.05, 1.0, 0.95, 0.95, 1.0, 1.1, 1.15, 1.1],
    "handicrafts":        [0.8, 0.8, 0.85, 0.85, 0.9, 0.9, 0.9, 0.95, 1.1, 1.35, 1.4, 1.1],
    "rural_retail":       [0.9, 0.9, 0.95, 0.95, 1.0, 1.0, 0.95, 0.95, 1.05, 1.25, 1.3, 1.05],
    # brick kilns: near-dormant in monsoon (Jun-Sep), can't fire/dry bricks in rain
    "brick_kiln":         [1.2, 1.25, 1.15, 1.0, 0.85, 0.3, 0.2, 0.2, 0.35, 0.9, 1.2, 1.25],
    # flour/oil mills: fairly steady staple-goods demand, mild post-harvest bump
    "flour_mill":         [1.05, 1.0, 1.0, 1.05, 1.0, 0.95, 0.95, 0.95, 1.0, 1.05, 1.1, 1.05],
    "oil_mill":           [1.05, 1.0, 1.0, 1.05, 1.0, 0.9, 0.9, 0.9, 0.95, 1.1, 1.15, 1.1],
    # textile weaving: festival-driven like handicrafts but less extreme
    "textile_weaving":    [0.9, 0.9, 0.9, 0.9, 0.95, 0.95, 0.95, 1.0, 1.1, 1.25, 1.2, 1.0],
    # agri input retail: two sharp spikes -- kharif sowing (Jun-Jul) and rabi sowing (Oct-Nov)
    "agri_input_retail":  [0.7, 0.6, 0.6, 0.65, 0.8, 1.35, 1.4, 1.0, 0.8, 1.3, 1.35, 0.9],
    "auto_repair":        [1.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.9, 0.9, 0.95, 1.05, 1.1, 1.05],
    # tea stalls/eateries: steady, small festival + winter bump
    "tea_stall_eatery":   [1.0, 1.0, 0.95, 0.95, 0.95, 0.9, 0.9, 0.9, 1.0, 1.1, 1.15, 1.1],
}

# ---------------------------------------------------------------------------
# Gujarat districts & places
# ---------------------------------------------------------------------------
# climate_zone controls baseline rainfall level/variance:
#   "high"   -> south Gujarat (heavy monsoon)
#   "medium" -> central Gujarat
#   "low"    -> north Gujarat / Saurashtra fringe
#   "arid"   -> Kutch / Banaskantha belt (low, erratic rainfall)
PLACES = [
    # district, place, climate_zone
    ("Vadodara", "Vadodara", "medium"),
    ("Vadodara", "Padra", "medium"),
    ("Vadodara", "Dabhoi", "medium"),
    ("Vadodara", "Savli", "medium"),
    ("Anand", "Anand", "medium"),
    ("Anand", "Borsad", "medium"),
    ("Anand", "Petlad", "medium"),
    ("Kheda", "Nadiad", "medium"),
    ("Kheda", "Kapadvanj", "medium"),
    ("Panchmahal", "Godhra", "medium"),
    ("Panchmahal", "Halol", "medium"),
    ("Chhota Udepur", "Chhota Udepur", "medium"),
    ("Narmada", "Rajpipla", "medium"),
    ("Bharuch", "Bharuch", "high"),
    ("Bharuch", "Ankleshwar", "high"),
    ("Bharuch", "Jambusar", "high"),
    ("Surat", "Surat", "high"),
    ("Surat", "Bardoli", "high"),
    ("Navsari", "Navsari", "high"),
    ("Navsari", "Gandevi", "high"),
    ("Valsad", "Valsad", "high"),
    ("Valsad", "Vapi", "high"),
    ("Tapi", "Vyara", "high"),
    ("Dang", "Ahwa", "high"),
    ("Ahmedabad", "Ahmedabad", "medium"),
    ("Ahmedabad", "Dholka", "medium"),
    ("Ahmedabad", "Sanand", "medium"),
    ("Gandhinagar", "Gandhinagar", "medium"),
    ("Mehsana", "Mehsana", "low"),
    ("Mehsana", "Visnagar", "low"),
    ("Mehsana", "Unjha", "low"),
    ("Patan", "Patan", "low"),
    ("Banaskantha", "Palanpur", "arid"),
    ("Banaskantha", "Deesa", "arid"),
    ("Sabarkantha", "Himatnagar", "low"),
    ("Surendranagar", "Surendranagar", "low"),
    ("Surendranagar", "Wadhwan", "low"),
    ("Rajkot", "Rajkot", "low"),
    ("Rajkot", "Gondal", "low"),
    ("Rajkot", "Jetpur", "low"),
    ("Jamnagar", "Jamnagar", "low"),
    ("Junagadh", "Junagadh", "low"),
    ("Junagadh", "Veraval", "low"),
    ("Porbandar", "Porbandar", "low"),
    ("Bhavnagar", "Bhavnagar", "low"),
    ("Bhavnagar", "Mahuva", "low"),
    ("Amreli", "Amreli", "low"),
    ("Botad", "Botad", "low"),
    ("Morbi", "Morbi", "arid"),
    ("Kutch", "Bhuj", "arid"),
    ("Kutch", "Gandhidham", "arid"),
    ("Kutch", "Anjar", "arid"),
]

# Which districts each sector is realistically concentrated in (weighted).
# Mirrors real Gujarat geography: dairy/agri co-ops cluster in the Anand/Kheda
# "milk belt", handicrafts in Kutch, brick kilns near Vadodara/Bharuch clay
# river-belt areas, textile weaving around Surat, etc. Sectors not listed use
# a uniform distribution across all districts.
SECTOR_DISTRICT_WEIGHTS = {
    "dairy": {"Anand": 4, "Kheda": 4, "Vadodara": 2, "Banaskantha": 3, "Mehsana": 2},
    "handicrafts": {"Kutch": 5, "Patan": 2, "Surendranagar": 2, "Banaskantha": 2},
    "brick_kiln": {"Vadodara": 4, "Bharuch": 4, "Anand": 2, "Kheda": 2, "Surat": 2},
    "textile_weaving": {"Surat": 5, "Ahmedabad": 3, "Bharuch": 2, "Navsari": 2},
    "agri_input_retail": {"Anand": 2, "Kheda": 2, "Mehsana": 2, "Rajkot": 2, "Banaskantha": 2, "Junagadh": 2},
    "poultry": {"Panchmahal": 3, "Anand": 2, "Vadodara": 2, "Ahmedabad": 2},
}

# Enterprise name generation pools

PERSON_FIRST_NAMES = [
    "Ramesh", "Suresh", "Kiran", "Bharat", "Naresh", "Mahesh", "Jayesh", "Nitin",
    "Ashok", "Kantibhai", "Chandubhai", "Dahyabhai", "Vinod", "Pravin", "Dilip",
    "Rajesh", "Bhavesh", "Kalpesh", "Hitesh", "Girish", "Manoj", "Ratilal",
    "Ishwarbhai", "Jagdish", "Bhupendra", "Vijaybhai", "Kaushik", "Amit",
]

SURNAMES_GENERAL = ["Patel", "Shah", "Desai", "Rana", "Solanki", "Chauhan", "Thakor", "Parmar"]
SURNAMES_TRIBAL = ["Rathwa", "Baria", "Vasava", "Macwan", "Damor", "Bhuriya"]  # common in Panchmahal/Narmada/Chhota Udepur/Tapi/Dang belt

DEITY_PREFIXES = ["Shree", "Shri", "Jai", "Maa", "Om", "Ambe", "Khodiyar", "Ranchhod", "Umiya", "Santoshi"]

BUSINESS_SUFFIX = {
    "dairy": ["Dairy", "Doodh Kendra", "Milk Producers Co-op"],
    "poultry": ["Poultry Farm", "Poultry Farms", "Hatchery"],
    "food_processing": ["Food Products", "Agro Foods", "Snacks Udyog"],
    "handicrafts": ["Handicrafts", "Hastkala Kendra", "Kala Kendra"],
    "rural_retail": ["General Store", "Kirana Store", "Provision Store"],
    "flour_mill": ["Flour Mill", "Aata Chakki", "Flour Mills"],
    "oil_mill": ["Oil Mill", "Ghani Udyog", "Tel Mill"],
    "textile_weaving": ["Weaving Works", "Textiles", "Handloom Works"],
    "brick_kiln": ["Brick Works", "Bhattha Udyog", "Bricks & Tiles"],
    "agri_input_retail": ["Krishi Kendra", "Agro Center", "Beej Bhandar"],
    "auto_repair": ["Auto Works", "Garage", "Motor Works"],
    "tea_stall_eatery": ["Tea Stall", "Hotel", "Bhojnalay", "Nasta Center"],  # "Hotel" = common Indian usage for small eatery
}


def sector_district_choice(rng, sector):
    """Pick a (district, place, climate_zone) tuple, weighted toward sectors'
    realistic regional clusters when defined, else uniform."""
    weights_map = SECTOR_DISTRICT_WEIGHTS.get(sector)
    if weights_map is None:
        idx = rng.integers(0, len(PLACES))
        return PLACES[idx]

    weights = []
    for (district, place, zone) in PLACES:
        w = weights_map.get(district, 1)
        weights.append(w)
    weights = [w / sum(weights) for w in weights]
    idx = rng.choice(len(PLACES), p=weights)
    return PLACES[idx]


def generate_enterprise_name(rng, sector):
    """Randomly combine one of three realistic naming patterns."""
    pattern = rng.choice(["proprietor", "deity", "cooperative"], p=[0.5, 0.35, 0.15])
    suffix = rng.choice(BUSINESS_SUFFIX[sector])

    if pattern == "proprietor":
        first = rng.choice(PERSON_FIRST_NAMES)
        surname_pool = SURNAMES_TRIBAL if rng.random() < 0.25 else SURNAMES_GENERAL
        surname = rng.choice(surname_pool)
        return f"{first} {surname} {suffix}"
    elif pattern == "deity":
        prefix = rng.choice(DEITY_PREFIXES)
        return f"{prefix} {suffix}"
    else:  # cooperative / place-based, common for dairy/agri
        return f"{suffix} Sahakari Mandali"
