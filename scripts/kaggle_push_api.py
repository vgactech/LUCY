#!/usr/bin/env python3
"""
LuCY — Script push kernel Kaggle via API REST v1 (Basic auth)
Endpoint correct: POST /api/v1/kernels/push

RÈGLE PERMANENTE (décision utilisateur) :
  - is_private=True    : kernel TOUJOURS en privé
  - enable_gpu=True    : GPU TOUJOURS activé
  - accelerator="gpu"  : accélérateur explicitement "gpu"

v5.0 — architecture 3 niveaux + reward adaptatif
CERTIFIED_100=false | unique_human_proven=false | DEBUG=true
"""

import json
import base64
import urllib.request
import urllib.error
import sys
import pathlib
import datetime

# ─── Configuration ──────────────────────────────────────────────
KAGGLE_CREDS = pathlib.Path.home() / ".kaggle" / "kaggle.json"
NOTEBOOK_DIR = pathlib.Path(__file__).parent.parent / "notebooks" / "arc3"
NOTEBOOK_FILE = NOTEBOOK_DIR / "lucy_arc_agi3_submission.ipynb"
METADATA_FILE = NOTEBOOK_DIR / "kernel-metadata.json"
LOG_DIR = pathlib.Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ─── Chargement credentials ─────────────────────────────────────
def load_credentials():
    with open(KAGGLE_CREDS) as f:
        creds = json.load(f)
    username = creds["username"]
    key = creds["key"]
    return username, key

# ─── Requête API Kaggle ─────────────────────────────────────────
def kaggle_request(method, path, data=None, username=None, key=None):
    url = f"https://www.kaggle.com/api/v1{path}"
    auth = base64.b64encode(f"{username}:{key}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_resp = e.read()
        try:
            return e.code, json.loads(body_resp)
        except Exception:
            return e.code, {"raw": body_resp.decode(errors="replace")[:500]}
    except Exception as e:
        return 0, {"error": str(e)}

# ─── Push kernel ────────────────────────────────────────────────
def push_kernel(username, key):
    print(f"\n[PUSH] Lecture notebook: {NOTEBOOK_FILE}")
    with open(NOTEBOOK_FILE) as f:
        notebook_content = f.read()  # texte brut du fichier JSON

    with open(METADATA_FILE) as f:
        meta = json.load(f)

    # RÈGLE PERMANENTE : privacy=True + GPU activé (décision utilisateur — v5.0)
    # is_private et enable_gpu sont FORCÉS ici indépendamment du metadata
    payload = {
        "slug": meta["id"],
        "newTitle": meta["title"],
        "text": notebook_content,
        "language": meta["language"],
        "kernelType": meta["kernel_type"],
        "isPrivate": True,           # FORCÉ — jamais public
        "enableGpu": True,           # FORCÉ — GPU toujours activé
        "accelerator": "gpu",        # FORCÉ — accélérateur explicite
        "enableInternet": meta.get("enable_internet", False),
        "competitionDataSources": meta.get("competition_sources", []),
        "datasetDataSources": meta.get("dataset_sources", []),
        "kernelDataSources": meta.get("kernel_sources", []),
        "categoryIds": [],
    }

    print(f"  [PUSH] kernel_id={meta['id']}")
    print(f"  [PUSH] is_private=True (forcé) | enable_gpu=True (forcé) | accelerator=gpu")
    print(f"  [PUSH] competition={meta.get('competition_sources', [])}")
    print(f"  [PUSH] notebook_size={len(notebook_content)} chars")

    status, data = kaggle_request("POST", "/kernels/push", data=payload,
                                   username=username, key=key)
    return status, data

# ─── Vérification statut après push ─────────────────────────────
def check_status(username, key):
    slug = "lucy-cognitive-kernel-arc-agi3"
    status, data = kaggle_request("GET", f"/kernels/{username}/{slug}/status",
                                   username=username, key=key)
    print(f"  [STATUS] HTTP {status}")
    if isinstance(data, dict):
        print(f"  [STATUS] status={data.get('status', data.get('statusNullable', '?'))}")
    return status, data

# ─── Main ────────────────────────────────────────────────────────
def main():
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log = {
        "ts": ts,
        "script": "kaggle_push_api.py",
        "DEBUG": True,
        "CERTIFIED_100": False,
        "steps": []
    }

    print("=" * 60)
    print("LuCY — Push kernel Kaggle (API REST v1 Basic auth)")
    print(f"Horodatage : {ts}")
    print("=" * 60)

    # Chargement credentials
    print("\n[STEP 1] Chargement credentials...")
    username, key = load_credentials()
    print(f"  username={username} | key_prefix={key[:8]}...")
    log["steps"].append({"step": 1, "username": username, "status": "OK"})

    # Test API
    print("\n[STEP 2] Test API Kaggle...")
    s, d = kaggle_request("GET", "/competitions/list?search=arc-prize-2026-arc-agi-3",
                           username=username, key=key)
    if s != 200:
        print(f"  ERREUR AUTH: {d}")
        log["steps"].append({"step": 2, "status": "FAIL", "error": str(d)})
        _save_log(log, ts)
        sys.exit(1)
    print(f"  HTTP {s} OK — compétitions trouvées: {len(d) if isinstance(d, list) else '?'}")
    log["steps"].append({"step": 2, "status": "OK"})

    # Push kernel
    print("\n[STEP 3] Push kernel v5.0 sur Kaggle (privacy=True, GPU=True, accelerator=gpu)...")
    push_status, push_data = push_kernel(username, key)
    print(f"\n  [PUSH RESULT] HTTP {push_status}")
    print(f"  [PUSH RESULT] {json.dumps(push_data, indent=2)[:500]}")
    log["steps"].append({"step": 3, "push_http": push_status, "push_data": push_data})

    if push_status not in (200, 201):
        print(f"\n[ERREUR] Push échoué — HTTP {push_status}")
        _save_log(log, ts)
        sys.exit(2)

    # Vérification statut
    print("\n[STEP 4] Vérification statut post-push...")
    status_code, status_data = check_status(username, key)
    log["steps"].append({"step": 4, "status_http": status_code, "status_data": status_data})

    # Résultat final
    version = push_data.get("versionNumber", push_data.get("versionNumberNullable", "?"))
    kernel_id = push_data.get("kernelId", "?")
    kernel_url = push_data.get("url", f"https://www.kaggle.com/code/{username}/lucy-cognitive-kernel-arc-agi3")

    log["result"] = "PUSH_OK"
    log["version_number"] = version
    log["kernel_id"] = kernel_id
    log["kernel_url"] = kernel_url

    _save_log(log, ts)

    print("\n" + "=" * 60)
    print(f"RÉSULTAT : PUSH_OK")
    print(f"Version  : {version}")
    print(f"Kernel ID: {kernel_id}")
    print(f"URL      : {kernel_url}")
    print("=" * 60)

def _save_log(log, ts):
    log_file = LOG_DIR / f"lucy_kaggle_push_{ts}.json"
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)
    print(f"\n[LOG] Sauvegardé → {log_file.name}")

if __name__ == "__main__":
    main()
