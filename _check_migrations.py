"""One-off script to audit alembic revision graph."""
import re
import pathlib
from collections import defaultdict

versions_dir = pathlib.Path("api/alembic/versions")
migrations = []

for f in sorted(versions_dir.glob("*.py")):
    content = f.read_text()
    rev_match = re.search(r"^revision\s*=\s*['\"](.+?)['\"]", content, re.MULTILINE)
    down_match = re.search(r"^down_revision\s*=\s*(.*)", content, re.MULTILINE)
    if rev_match and down_match:
        rev = rev_match.group(1)
        down_raw = down_match.group(1).strip()
        migrations.append((f.name, rev, down_raw))

for name, rev, down in migrations:
    print(f"{rev:30s}  down={down:60s}  # {name}")

print(f"\nTotal: {len(migrations)} migration files")

revs = [m[1] for m in migrations]
dupes = [r for r in set(revs) if revs.count(r) > 1]
if dupes:
    print(f"\n*** DUPLICATE REVISION IDs: {dupes}")

all_revs = set(revs)
for name, rev, down_raw in migrations:
    refs = re.findall(r"['\"](\w+)['\"]", down_raw)
    for ref in refs:
        if ref not in all_revs:
            print(f"*** BROKEN REF: {rev} ({name}) references {ref} which does not exist")

children_of = set()
for name, rev, down_raw in migrations:
    refs = re.findall(r"['\"](\w+)['\"]", down_raw)
    children_of.update(refs)

heads = sorted([rev for rev in all_revs if rev not in children_of])
print(f"\nHEADS (leaf revisions not depended on by anything): {heads}")

roots = []
for name, rev, down_raw in migrations:
    if down_raw.strip() == "None":
        roots.append(rev)
print(f"ROOTS (down_revision = None): {roots}")

# Check for forward references (child date < parent date)
print("\n--- SUSPICIOUS ORDERING (child revision date < parent date) ---")
def extract_date(rev_id):
    m = re.match(r"(\d{8})", rev_id)
    return m.group(1) if m else None

for name, rev, down_raw in migrations:
    refs = re.findall(r"['\"](\w+)['\"]", down_raw)
    rev_date = extract_date(rev)
    for ref in refs:
        ref_date = extract_date(ref)
        if rev_date and ref_date and rev_date < ref_date:
            print(f"  {rev} (date {rev_date}) depends on {ref} (date {ref_date}) -- TIME TRAVEL")
