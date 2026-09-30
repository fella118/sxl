"""Sample firm used by the demo."""

from datetime import date

from .store import Store

FIRM = "Atlas Conseil"
DEADLINE_DAY = 10
START_DAY = date(2026, 10, 1)

ALL = ["releve_bancaire", "factures_achats", "factures_ventes", "etat_paie"]
NO_PAYROLL = ["releve_bancaire", "factures_achats", "factures_ventes"]

CLIENTS = [
    ("BOUL01", "Boulangerie Al Amal SARL", "Si Ahmed", "212600000001", "darija", ALL),
    ("TRANS02", "Trans Nour Logistique", "Mme Fatima Zahra", "212600000002", "francais", ALL),
    ("CAFE03", "Café Rif", "Si Mustapha", "212600000003", "darija", NO_PAYROLL),
    ("PHAR04", "Pharmacie Ibn Sina", "Dr Bennani", "212600000004", "francais", ALL),
    ("BTP05", "Atlas Bâtiment SARL", "Si Youssef", "212600000005", "darija", ALL),
    ("GARG06", "Garage Nour", "Si Hassan", "212600000006", "darija", NO_PAYROLL),
]


def seed(store: Store) -> None:
    for code, name, contact, phone, language, docs in CLIENTS:
        store.add_client(code, name, contact, phone, language, docs)
    store.today = START_DAY
