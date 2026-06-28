import os
from pathlib import Path

# Single source, no fallback: credentials come from the environment. The password is read
# from POSTGRES_PASSWORD_FILE — the same mounted secret the postgres container uses
# (e.g. /run/secrets/db_password), so the value lives in exactly one place.
postgres_user = os.environ["POSTGRES_USER"]
postgres_password = Path(os.environ["POSTGRES_PASSWORD_FILE"]).read_text().strip()
