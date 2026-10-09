"""GoHighLevel (LeadConnector API v2) client: conversations, calendar, contacts.

Env: GHL_TOKEN (Private Integration token of the SOGIXEL sub-account), GHL_LOCATION_ID.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://services.leadconnectorhq.com"
V_CONTACTS, V_CONV, V_CAL = "2021-07-28", "2021-04-15", "2021-04-15"
# GHL message types per channel
CHANNEL_TYPE = {"instagram": "IG", "facebook": "FB", "whatsapp": "WhatsApp", "email": "Email", "sms": "SMS"}


class GHLError(RuntimeError):
    pass


class GHL:
    def __init__(self, token=None, location_id=None):
        self.token = token or os.environ.get("GHL_TOKEN", "")
        self.location_id = location_id or os.environ.get("GHL_LOCATION_ID", "")

    def _call(self, method, path, version, body=None, query=None):
        if not self.token:
            raise GHLError("GHL_TOKEN is not set")
        url = BASE + path + ("?" + urllib.parse.urlencode(query) if query else "")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Version": version,
                                              "Content-Type": "application/json", "Accept": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise GHLError(f"GHL {method} {path} -> {e.code}: {e.read()[:300].decode(errors='replace')}") from e

    # --- contacts -------------------------------------------------------------------------------------------
    def contact(self, contact_id):
        return self._call("GET", f"/contacts/{contact_id}", V_CONTACTS).get("contact", {})

    def upsert_contact(self, **fields):
        body = {"locationId": self.location_id, **fields}
        return self._call("POST", "/contacts/upsert", V_CONTACTS, body).get("contact", {})

    def add_tags(self, contact_id, tags):
        return self._call("POST", f"/contacts/{contact_id}/tags", V_CONTACTS, {"tags": list(tags)})

    # --- conversations --------------------------------------------------------------------------------------
    def history(self, contact_id, limit=30):
        """Messages with this contact, oldest first: [{direction, body, type, date, id}]."""
        convs = self._call("GET", "/conversations/search", V_CONV,
                           query={"locationId": self.location_id, "contactId": contact_id}).get("conversations", [])
        if not convs:
            return []
        data = self._call("GET", f"/conversations/{convs[0]['id']}/messages", V_CONV, query={"limit": limit})
        msgs = data.get("messages", [])
        if isinstance(msgs, dict):               # the API nests the list one level down
            msgs = msgs.get("messages", [])
        out = [{"id": m.get("id", ""), "direction": m.get("direction", ""), "body": m.get("body", "") or "",
                "type": m.get("messageType", m.get("type", "")), "date": m.get("dateAdded", "")} for m in msgs]
        return sorted(out, key=lambda m: m["date"])

    def send(self, contact_id, channel, text, subject=None):
        body = {"type": CHANNEL_TYPE.get(channel, channel), "contactId": contact_id}
        if channel == "email":
            body.update(subject=subject or "Re:", html=text.replace("\n", "<br>"))
        else:
            body["message"] = text
        return self._call("POST", "/conversations/messages", V_CONV, body)

    # --- calendar -------------------------------------------------------------------------------------------
    def free_slots(self, calendar_id, start_ms, end_ms, timezone):
        data = self._call("GET", f"/calendars/{calendar_id}/free-slots", V_CAL,
                          query={"startDate": start_ms, "endDate": end_ms, "timezone": timezone})
        return [s for day, v in sorted(data.items()) if isinstance(v, dict) for s in v.get("slots", [])]

    def book(self, calendar_id, contact_id, start_iso, title):
        return self._call("POST", "/calendars/events/appointments", V_CAL, {
            "calendarId": calendar_id, "locationId": self.location_id, "contactId": contact_id,
            "startTime": start_iso, "title": title, "appointmentStatus": "confirmed"})
