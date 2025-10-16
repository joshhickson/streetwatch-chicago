"""
Enhanced location extraction for Chicago-specific cross-streets and neighborhoods.
This module provides pattern matching and local knowledge to supplement NER models.
"""

import re
from typing import List, Tuple, Set, Optional

# Chicago neighborhoods and community areas
CHICAGO_NEIGHBORHOODS = {
    'hermosa', 'logan square', 'wicker park', 'bucktown', 'humboldt park',
    'pilsen', 'little village', 'bridgeport', 'chinatown', 'hyde park',
    'south shore', 'woodlawn', 'englewood', 'austin', 'garfield park',
    'lawndale', 'west town', 'near north', 'near south', 'uptown',
    'edgewater', 'rogers park', 'lincoln park', 'lakeview', 'andersonville',
    'albany park', 'avondale', 'belmont cragin', 'brighton park',
    'archer heights', 'ashburn', 'auburn gresham', 'avalon park',
    'beverly', 'burnside', 'calumet heights', 'chatham', 'clearing',
    'douglas', 'dunning', 'east garfield park', 'west garfield park',
    'east side', 'forest glen', 'fuller park', 'gage park', 'grand boulevard',
    'greater grand crossing', 'hegewisch', 'irving park', 'jefferson park',
    'kenwood', 'lake view', 'lincoln square', 'lower west side',
    'mckinley park', 'montclare', 'morgan park', 'mount greenwood',
    'near west side', 'new city', 'north center', 'north lawndale',
    'north park', 'norwood park', 'oakland', 'ohare', "o'hare",
    'portage park', 'pullman', 'riverdale', 'roseland', 'south chicago',
    'south deering', 'south lawndale', 'south shore', 'washington heights',
    'washington park', 'west elsdon', 'west englewood', 'west lawn',
    'west pullman', 'west ridge', 'west town', 'evanston'
}

# Major Chicago streets and avenues (commonly mentioned in sightings)
CHICAGO_STREETS = {
    'western', 'ashland', 'halsted', 'cicero', 'pulaski', 'kedzie',
    'california', 'damen', 'kimball', 'central', 'harlem', 'narragansett',
    'austin', 'laramie', 'cottage grove', 'stony island', 'cottagegrove', 'stonyisland',
    'clark', 'broadway', 'sheridan', 'lake shore', 'lakeshore', 'michigan',
    'state', 'wabash', 'lasalle', 'wells', 'franklin', 'canal',
    'milwaukee', 'archer', 'clybourn', 'elston', 'lincoln',
    'belmont', 'fullerton', 'armitage', 'north', 'division',
    'chicago', 'grand', 'ohio', 'ontario', 'erie', 'huron',
    'superior', 'washington', 'madison', 'monroe', 'adams',
    'jackson', 'van buren', 'vanburen', 'congress', 'harrison', 'polk',
    'roosevelt', 'cermak', '18th', '26th', '31st', '35th',
    '47th', '55th', '63rd', '71st', '79th', '87th', '95th',
    '103rd', '111th', '119th', '127th', '130th', '138th',
    'pershing', 'garfield', 'marquette', 'irving park', 'irvingpark', 'montrose',
    'lawrence', 'foster', 'bryn mawr', 'brynmawr', 'devon', 'touhy',
    'howard', 'pratt', 'lunt', 'morse', 'greenleaf',
    'racine', 'wood', 'paulina', 'hermitage', 'seeley',
    'hoyne', 'leavitt', 'oakley', 'claremont', 'campbell',
    'artesian', 'rockwell', 'maplewood', 'troy', 'sacramento',
    'albany', 'whipple', 'drake', 'st louis', 'stlouis', 'spaulding',
    'crawford', 'homan', 'trumbull', 'ridgeway', 'lawndale',
    'ogden', 'kostner', 'kildare', 'kilbourn', 'kolmar',
    'kenton', 'kilpatrick', 'keeler', 'kenneth', 'karlov',
    'river', 'desplaines', 'jefferson', 'clinton', 'peoria',
    'sangamon', 'morgan', 'carpenter', 'green', 'union',
    # Multi-word arterials (normalized, no suffixes)
    'martin luther king jr', 'martin luther king', 'mlk',
    'ida b wells', 'ida b. wells',
    'old orchard', 'skokie', 'skokie boulevard'
}

# Common Chicago landmarks
CHICAGO_LANDMARKS = {
    'red line', 'blue line', 'green line', 'orange line', 'pink line',
    'brown line', 'purple line', 'yellow line', 'metra',
    'union station', 'ogilvie', 'millennium station',
    'ohare', "o'hare", 'midway', 'navy pier', 'soldier field',
    'wrigley field', 'united center', 'grant park', 'millennium park',
    'loop', 'river north', 'magnificent mile', 'gold coast'
}


class ChicagoLocationExtractor:
    """Enhanced location extractor with Chicago-specific patterns and knowledge."""
    
    # Regex patterns for cross-street detection (handles both named and numbered streets)
    # Pattern component: Matches "Fullerton", "95th St", "Lake Shore Drive", "Martin Luther King Jr Drive", 
    # "Ida B. Wells Drive", etc. Allows for multi-word street names (up to 6 words for Chicago streets)
    STREET_TOKEN = r'(?:\d+(?:st|nd|rd|th)?(?:\s+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive))?|[A-Za-z]+(?:\.)?(?:\s+[A-Za-z]+(?:\.)?){0,5})'
    
    CROSS_STREET_PATTERNS = [
        # "corner of Fullerton and Western" OR "corner of 95th and Halsted"
        rf'(?:corner|intersection)\s+(?:of\s+)?({STREET_TOKEN})\s+(?:and|&)\s+({STREET_TOKEN})\b',
        
        # "(at/near) Fullerton and Western" OR "(at/near) 26th and Pulaski"
        rf'(?:at|near|on)\s+({STREET_TOKEN})\s+(?:and|&)\s+({STREET_TOKEN})\b',
        
        # "Fullerton and Western" OR "95th and Halsted" - simple form
        rf'\b({STREET_TOKEN})\s+and\s+({STREET_TOKEN})\b',
        
        # "Fullerton & Western" OR "95th & Halsted" - with ampersand
        rf'\b({STREET_TOKEN})\s+&\s+({STREET_TOKEN})\b',
    ]
    
    # Street with type patterns (e.g., "Milwaukee Ave", "Western Avenue")
    STREET_TYPE_PATTERN = r'\b([A-Za-z]+(?:\s+[A-Za-z]+)?)\s+(Ave(?:nue)?|St(?:reet)?|Rd|Road|Blvd|Boulevard|Dr|Drive|Pkwy|Parkway)\b'
    
    # Numbered street patterns (e.g., "95th Street", "18th and Halsted")
    NUMBERED_STREET_PATTERN = r'\b(\d{1,3}(?:st|nd|rd|th))\s+(Street|St|and|&)?\s*([A-Za-z]+)?\b'
    
    # Neighborhood mention patterns
    NEIGHBORHOOD_PATTERN = r'\b(in|near|around|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
    
    def __init__(self):
        self.compiled_cross_street = [re.compile(p, re.IGNORECASE) for p in self.CROSS_STREET_PATTERNS]
        self.compiled_street_type = re.compile(self.STREET_TYPE_PATTERN, re.IGNORECASE)
        self.compiled_numbered = re.compile(self.NUMBERED_STREET_PATTERN, re.IGNORECASE)
        self.compiled_neighborhood = re.compile(self.NEIGHBORHOOD_PATTERN, re.IGNORECASE)
    
    def _normalize_street_name(self, street: str) -> str:
        """Normalize street name by removing common suffixes for matching."""
        street_lower = street.lower().strip()
        
        # Remove common street type suffixes
        suffixes = [
            ' avenue', ' ave', ' street', ' st', ' road', ' rd',
            ' boulevard', ' blvd', ' drive', ' dr', ' parkway', ' pkwy'
        ]
        
        for suffix in suffixes:
            if street_lower.endswith(suffix):
                return street_lower[:-len(suffix)].strip()
        
        return street_lower
    
    def extract_cross_streets(self, text: str) -> List[Tuple[str, str]]:
        """Extract cross-street intersections from text."""
        cross_streets = []
        
        # Words that shouldn't be part of a street name
        excluded_words = {'ice', 'checkpoint', 'border', 'patrol', 'saw', 'spotted', 
                         'reported', 'sighting', 'activity', 'presence', 'raid'}
        
        # Street type suffixes that shouldn't appear alone as street names
        suffix_only_words = {'avenue', 'ave', 'street', 'st', 'road', 'rd', 'boulevard', 
                            'blvd', 'drive', 'dr', 'parkway', 'pkwy'}
        
        for pattern in self.compiled_cross_street:
            matches = pattern.findall(text)
            for match in matches:
                if len(match) == 2:
                    street1, street2 = match
                    street1_lower = street1.lower().strip()
                    street2_lower = street2.lower().strip()
                    
                    # Skip if either part is an excluded word
                    if street1_lower in excluded_words or street2_lower in excluded_words:
                        continue
                    
                    # Skip if either street is ONLY a suffix word (e.g., just "Avenue" or just "Street")
                    if street1_lower in suffix_only_words or street2_lower in suffix_only_words:
                        continue
                    
                    # Normalize street names (remove Ave, St, etc.) before checking
                    street1_normalized = self._normalize_street_name(street1)
                    street2_normalized = self._normalize_street_name(street2)
                    
                    # Check if streets are in known Chicago streets database
                    street1_match = (street1_normalized in CHICAGO_STREETS or 
                                   street1_normalized.replace(' ', '') in CHICAGO_STREETS)
                    street2_match = (street2_normalized in CHICAGO_STREETS or 
                                   street2_normalized.replace(' ', '') in CHICAGO_STREETS)
                    
                    # Check if both have street type suffixes (strong signal it's a valid intersection)
                    has_suffix_pattern = r'(?:avenue|ave|street|st|road|rd|boulevard|blvd|drive|dr|pkwy|parkway)$'
                    street1_has_suffix = bool(re.search(has_suffix_pattern, street1_lower, re.IGNORECASE))
                    street2_has_suffix = bool(re.search(has_suffix_pattern, street2_lower, re.IGNORECASE))
                    both_have_suffixes = street1_has_suffix and street2_has_suffix
                    
                    # Accept if: at least one is known Chicago street OR both have street type suffixes
                    if street1_match or street2_match or both_have_suffixes:
                        cross_streets.append((street1.strip(), street2.strip()))
        
        return cross_streets
    
    def extract_streets_with_type(self, text: str) -> List[str]:
        """Extract streets with explicit type (e.g., 'Milwaukee Ave')."""
        streets = []
        matches = self.compiled_street_type.findall(text)
        
        for match in matches:
            if len(match) == 2:
                street_name, street_type = match
                # Verify it's a known Chicago street
                if street_name.lower() in CHICAGO_STREETS:
                    streets.append(f"{street_name} {street_type}".strip())
        
        return streets
    
    def extract_numbered_streets(self, text: str) -> List[str]:
        """Extract numbered streets (e.g., '95th Street')."""
        streets = []
        matches = self.compiled_numbered.findall(text)
        
        for match in matches:
            if match[0]:  # Has numbered part
                numbered = match[0]
                if match[2]:  # Has cross street
                    cross = match[2]
                    if cross.lower() in CHICAGO_STREETS:
                        streets.append(f"{numbered} and {cross}")
                else:
                    streets.append(f"{numbered} Street")
        
        return streets
    
    def extract_neighborhoods(self, text: str) -> List[str]:
        """Extract Chicago neighborhood names."""
        neighborhoods = []
        
        # Direct pattern matching
        matches = self.compiled_neighborhood.findall(text)
        for match in matches:
            if len(match) == 2:
                neighborhood = match[1].strip()
                if neighborhood.lower() in CHICAGO_NEIGHBORHOODS:
                    neighborhoods.append(neighborhood)
        
        # Also check for standalone neighborhood names
        words_in_text = text.lower().split()
        for neighborhood in CHICAGO_NEIGHBORHOODS:
            if neighborhood in text.lower():
                # Check it's not part of a longer word
                if neighborhood in ' '.join(words_in_text):
                    neighborhoods.append(neighborhood.title())
        
        return list(set(neighborhoods))  # Remove duplicates
    
    def extract_landmarks(self, text: str) -> List[str]:
        """Extract Chicago landmarks and transit references."""
        landmarks = []
        text_lower = text.lower()
        
        for landmark in CHICAGO_LANDMARKS:
            if landmark in text_lower:
                landmarks.append(landmark.title())
        
        return landmarks
    
    def extract_all_locations(self, text: str) -> dict:
        """Extract all types of locations from text."""
        return {
            'cross_streets': self.extract_cross_streets(text),
            'streets_with_type': self.extract_streets_with_type(text),
            'numbered_streets': self.extract_numbered_streets(text),
            'neighborhoods': self.extract_neighborhoods(text),
            'landmarks': self.extract_landmarks(text)
        }
    
    def prioritize_locations(self, extracted: dict) -> List[str]:
        """
        Prioritize extracted locations by specificity.
        Most specific (cross-streets) to least specific (landmarks).
        """
        prioritized = []
        
        # 1. Cross-streets (most specific)
        for street1, street2 in extracted.get('cross_streets', []):
            prioritized.append(f"{street1} and {street2}")
        
        # 2. Numbered street intersections
        for street in extracted.get('numbered_streets', []):
            if 'and' in street:
                prioritized.append(street)
        
        # 3. Streets with explicit type
        prioritized.extend(extracted.get('streets_with_type', []))
        
        # 4. Simple numbered streets
        for street in extracted.get('numbered_streets', []):
            if 'and' not in street:
                prioritized.append(street)
        
        # 5. Neighborhoods
        prioritized.extend(extracted.get('neighborhoods', []))
        
        # 6. Landmarks (least specific, but still useful)
        prioritized.extend(extracted.get('landmarks', []))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_prioritized = []
        for loc in prioritized:
            loc_lower = loc.lower()
            if loc_lower not in seen:
                seen.add(loc_lower)
                unique_prioritized.append(loc)
        
        return unique_prioritized


def is_likely_chicago_location(entity_text: str, entity_label: str) -> bool:
    """
    Determine if an NER entity that was classified as ORG is actually a Chicago location.
    This helps catch NER misclassifications.
    """
    text_lower = entity_text.lower().strip()
    
    # Check if it's a known neighborhood
    if text_lower in CHICAGO_NEIGHBORHOODS:
        return True
    
    # Check if it's a known street
    if text_lower in CHICAGO_STREETS:
        return True
    
    # Check if it's a landmark
    if text_lower in CHICAGO_LANDMARKS:
        return True
    
    # Check for "X Ave" or "X Street" patterns
    if any(suffix in text_lower for suffix in [' ave', ' avenue', ' st', ' street', ' rd', ' road']):
        street_name = text_lower.split()[0]
        if street_name in CHICAGO_STREETS:
            return True
    
    return False


def enhance_geocoding_query(location: str, context: str = "Chicago, IL, USA") -> str:
    """
    Enhance a location string for better geocoding results.
    Adds Chicago context and handles special cases.
    """
    location_lower = location.lower()
    
    # If it's a cross-street, format for geocoding
    if ' and ' in location_lower or ' & ' in location_lower:
        # "Fullerton and Western" -> "Fullerton & Western, Chicago, IL"
        # Use case-insensitive replacement
        intersection = location.replace(' and ', ' & ').replace(' And ', ' & ')
        return f"{intersection}, Chicago, IL, USA"
    
    # If it's a numbered street
    if any(char.isdigit() for char in location):
        if 'street' not in location_lower and 'st' not in location_lower:
            # Add "Street" if missing
            if location[-2:] in ['st', 'nd', 'rd', 'th']:
                return f"{location} Street, Chicago, IL, USA"
    
    # If it's a street with Ave/St already
    if any(t in location_lower for t in [' ave', ' avenue', ' st ', ' street', ' rd', ' road']):
        return f"{location}, Chicago, IL, USA"
    
    # If it's a known neighborhood, add Chicago context
    if location_lower in CHICAGO_NEIGHBORHOODS:
        return f"{location}, Chicago, IL, USA"
    
    # If it's a landmark
    if location_lower in CHICAGO_LANDMARKS:
        return f"{location}, Chicago, IL, USA"
    
    # Default: add the provided context
    if context and context not in location:
        return f"{location}, {context}"
    
    return location
