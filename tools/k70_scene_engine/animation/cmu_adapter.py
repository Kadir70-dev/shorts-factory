"""CMU motion records registered at the existing K70 motion/cache boundary."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
CMU=ROOT/"data/assets/motions/cmu/subjects"
RECORDS={
 "explain_hands":("18","18_08.amc"), "type_laptop":("79","79_85.amc"),
 "handshake":("18","18_01.amc"), "sit_down":("13","13_01.amc"),
 "stand_up":("13","13_01.amc"),
}

def import_verified():
    out=[]; cache=ROOT/"data/assets/motions/cache/cmu"; cache.mkdir(parents=True,exist_ok=True)
    for action,(subject,name) in RECORDS.items():
        amc=CMU/subject/name; asf=CMU/subject/f"{subject}.asf"
        if not amc.exists() or not asf.exists(): raise FileNotFoundError(amc)
        record={"action":action,"source":"CMU Graphics Lab Motion Capture Database","subject":subject,
                "amc":str(amc.relative_to(ROOT)),"asf":str(asf.relative_to(ROOT)),"format":"ASF/AMC",
                "license":"CMU free for all uses; raw/converted dataset resale prohibited",
                "source_url":f"https://mocap.cs.cmu.edu/search.php?subjectnumber={subject}",
                "sha256":hashlib.sha256(amc.read_bytes()).hexdigest()}
        (cache/f"{action}.json").write_text(json.dumps(record,indent=2),encoding="utf-8"); out.append(record)
    return out

