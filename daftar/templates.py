"""Outbound reminder templates.

WhatsApp only lets a business open a conversation with a pre-approved template,
so every reminder the firm initiates is a fixed text with variables. Claude
handles the conversation once the client replies (inside the 24h window).
"""

from .store import DOC_LABELS

MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]

DOC_LABELS_DARIJA = {
    "releve_bancaire": "relevé dyal l'banka",
    "factures_achats": "les factures dyal chra (achats)",
    "factures_ventes": "les factures dyal lbi3 (ventes)",
    "etat_paie": "l'état dyal l'khlass (paie)",
}

# level 0 = monthly kickoff, 1 = gentle nudge, 2 = firmer, 3 = last call before the deadline
TEMPLATES = {
    "francais": [
        "Bonjour {contact}, c'est la fiduciaire {firm}. Pour clôturer {month}, merci de nous envoyer ici :\n{docs}\nUne photo claire suffit. Merci !",
        "Bonjour {contact}, petit rappel pour {month}. Il nous manque encore :\n{docs}\nVous pouvez les envoyer directement ici.",
        "Bonjour {contact}, nous avons besoin de ces documents avant le {deadline} pour respecter vos échéances :\n{docs}",
        "{contact}, dernier rappel : sans ces documents avant le {deadline}, nous ne pourrons pas déposer vos déclarations à temps (risque de pénalités) :\n{docs}",
    ],
    "darija": [
        "Salam {contact}, m3akom la fiduciaire {firm}. Bach nsaliw chhar {month}, 3afak sifet lina hna :\n{docs}\nTswira wadha kafya. Choukran !",
        "Salam {contact}, ghir tadkira l chhar {month}. Mazal khassna :\n{docs}\nSifthom lina hna nichan.",
        "Salam {contact}, khassna had l wraq 9bel {deadline} bach ma nt2ekhrouch f les déclarations :\n{docs}",
        "{contact}, akhir tadkira : ila ma wslouch had l wraq 9bel {deadline}, ma nqdrouch ndiro les déclarations f l wa9t (kayna pénalité) :\n{docs}",
    ],
}

MAX_LEVEL = len(TEMPLATES["francais"]) - 1


def month_label(period: str) -> str:
    year, month = period.split("-")
    return f"{MONTHS_FR[int(month) - 1]} {year}"


def render(level: int, language: str, *, contact: str, firm: str, period: str,
           docs: list[str], deadline: str) -> str:
    templates = TEMPLATES.get(language, TEMPLATES["francais"])
    labels = DOC_LABELS_DARIJA if language == "darija" else DOC_LABELS
    lines = "\n".join(f"• {labels[d]}" for d in docs)
    return templates[min(level, MAX_LEVEL)].format(
        contact=contact, firm=firm, month=month_label(period), docs=lines, deadline=deadline,
    )
