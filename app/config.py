"""All settings come from environment variables (set them in the hosting dashboard, never in code)."""
import os
import secrets


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _db_url() -> str:
    url = _env("DATABASE_URL", "sqlite:///./app.db")
    # Neon / Supabase give "postgres://..." or "postgresql://..."; SQLAlchemy needs the driver name.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _db_url()

# Used to sign login tokens and to protect the one-time codes. Keep it long, random and secret.
# If it is missing a random one is made on each start (fine for testing: everybody is logged out on restart).
JWT_SECRET = _env("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_DAYS = 90

# Email (Brevo free plan, sent over HTTPS). Leave BREVO_API_KEY empty while testing on your PC.
BREVO_API_KEY = _env("BREVO_API_KEY")
SENDER_EMAIL = _env("SENDER_EMAIL")          # a sender you verified inside Brevo (your Gmail is fine)
SENDER_NAME = _env("SENDER_NAME", "Hikmah Life")
# Every "Contact us" message is sent to this address.
CONTACT_EMAIL = _env("CONTACT_EMAIL") or "al.nur.codefusion@gmail.com"

# Testing only: print the code in the server log instead of failing when no email key is set.
DEV_ECHO_CODE = _env("DEV_ECHO_CODE") == "1"

# Lets YOU list the registered users: GET /admin/users with header  X-Admin-Key: <this value>.
ADMIN_KEY = _env("ADMIN_KEY")

APP_NAME = "Hikmah Life"
CODE_MINUTES = 15        # how long a code works
CODE_MAX_TRIES = 5       # wrong guesses allowed per code
RESEND_SECONDS = 60      # wait between two codes
MAX_CODES_PER_HOUR = 5
MAX_FAILED_LOGINS = 8    # then the account is locked for LOCK_MINUTES
LOCK_MINUTES = 15
MIN_PASSWORD = 8
