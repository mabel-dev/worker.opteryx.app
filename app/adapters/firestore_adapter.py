from typing import Optional

from app.core import _get_firestore_client


def get_client_record(client_id: str) -> Optional[dict]:
    db = _get_firestore_client()
    doc = db.collection("auth_clients").document(client_id).get()
    if doc.exists:
        return doc.to_dict()
    return None
