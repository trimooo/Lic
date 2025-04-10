
import re

class EuropeanPlateDetector:
    PATTERNS = {
        'Kosovo': r'^[0-9]{3}-[A-Z]{2}-[0-9]{3}$',  # Format: 123-AB-123
        'Albania': r'^[A-Z]{2}\d{3,4}[A-Z]{2}$',    # Format: AA1234BB
        'Germany': r'^[A-Z]{1,3}-[A-Z]{1,2}\s?\d{1,4}[A-Z]?$', # Format: B-MW 1234
        'Macedonia': r'^\d{2}-[A-Z]{1,2}-\d{3}$',    # Format: 12-A-123
        'Montenegro': r'^[A-Z]{2}[A-Z0-9]{4,5}$',    # Format: PG1234A
        'Serbia': r'^[A-Z]{2}\d{3,4}[A-Z]{2}$',      # Format: BG123AA
        'Greece': r'^[A-Z]{3}-\d{4}$',               # Format: ABC-1234
    }
    
    @staticmethod
    def detect_country(plate_number):
        for country, pattern in EuropeanPlateDetector.PATTERNS.items():
            if re.match(pattern, plate_number):
                return country
        return "Unknown"

    @staticmethod
    def is_valid_plate(plate_number):
        return any(re.match(pattern, plate_number) for pattern in EuropeanPlateDetector.PATTERNS.values())
