"""
Faste konstanter for lønkørsel.
Timesatser og overtidstillæg vedligeholdes i Excel-arkene i rodmappen
og indlæses via calculators.rates_loader.
"""

# Firmaets CVR-nummer (kolonne A i Danløn-CSV)
CVR_NUMBER = "13246505"

# Danløn-koder – placeholder indtil de rigtige koder oplyses
# (kravdokument: "Disse findes pt. ikke")
DANLOEN_CODE_NORMAL = "1"
DANLOEN_CODE_OT_BEFORE = "1"
DANLOEN_CODE_OT_13 = "1"
DANLOEN_CODE_OT_EXTRA = "1"
DANLOEN_CODE_SALT = "1"  # Danløn-kode for salttillæg – oplyses af lønafdelingen
DANLOEN_CODE_AFSPADSERING = "1"  # Danløn-kode for afspadsering – oplyses af lønafdelingen
DANLOEN_CODE_SYGDOM    = "1"     # Danløn-kode for sygdom – oplyses af lønafdelingen
DANLOEN_CODE_FERIEFRI  = "1"    # Danløn-kode for feriefri – oplyses af lønafdelingen
DANLOEN_CODE_FERIEFRI_FULDLOENNET = "5"  # Danløn-kode for feriefri timer (fuldlønnede)
DANLOEN_CODE_FERIEFRI_TIMELOENNET = "63"  # Feriefri timer (timelønnede) – under SH-udbetaling, bekræftet 2026-10-08
DANLOEN_CODE_BARSEL        = "1"    # Danløn-kode for barsel – oplyses af lønafdelingen
DANLOEN_CODE_SKOLE_KURSUS  = "1"    # Danløn-kode for kursus/skole – oplyses af lønafdelingen
DANLOEN_CODE_OVERNATNING   = "1"    # Danløn-kode for overnatning – oplyses af lønafdelingen
DANLOEN_CODE_PARAGRAF_56   = "1"    # Danløn-kode for §56 syg – oplyses af lønafdelingen
DANLOEN_CODE_BARN_1SYGEDAG = "1"    # Danløn-kode for barn 1.sygedag – oplyses af lønafdelingen
DANLOEN_CODE_SPRINGERTILLAEG = "1"  # Danløn-kode for springertillæg – oplyses af lønafdelingen
DANLOEN_CODE_SH_FULDLOENNET = "4"    # SH-betaling fuldlønnet
DANLOEN_CODE_SH_TIMELOENNET = "63"   # SH-udbetaling timelønnet

# Dagpengesatsen (§56 syg) – fast sats uanset overenskomsttype
from decimal import Decimal
DANLOEN_DAGPENGE_SATS = Decimal("137.43")
