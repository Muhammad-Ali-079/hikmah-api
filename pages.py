"""Two simple web pages the Google Play Console asks for. Read them and edit the text to match your app before publishing."""
from . import config

_STYLE = """<style>body{font-family:Arial,sans-serif;max-width:720px;margin:32px auto;padding:0 16px;line-height:1.6;color:#222}
h1{color:#0F7B5C}h2{color:#053D2E;margin-top:28px}</style>"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title>{_STYLE}</head><body>{body}</body></html>"


def privacy() -> str:
    c = config.CONTACT_EMAIL or "the developer"
    return _page(
        f"{config.APP_NAME} Privacy Policy",
        f"""<h1>{config.APP_NAME} Privacy Policy</h1>
<h2>What we collect</h2>
<ul>
<li><b>Account:</b> your name and email address, and a password that is stored only as a one-way hash (nobody can read it).</li>
<li><b>Sign-in records:</b> the time you registered and last signed in.</li>
<li><b>In the app on your phone:</b> prayers, plans, time logs, notes and other progress are kept on your phone.</li>
<li><b>Chat (when this feature is added):</b> the questions you type, speak or upload to the Islamic assistant are sent to our server to produce an answer.</li>
</ul>
<h2>Why</h2>
<p>To create and protect your account, to send you the verification code by email, and to answer your questions.</p>
<h2>Sharing</h2>
<p>We do not sell your data and we do not show ads. Email codes are sent through our email provider (Brevo). Our database is hosted with a cloud database provider.</p>
<h2>Your choices</h2>
<p>You can delete your account and its data inside the app (Settings &gt; Delete account) or on the <a href="/account-deletion">account deletion page</a>.</p>
<h2>Contact</h2>
<p>{c}</p>""",
    )


def deletion() -> str:
    c = config.CONTACT_EMAIL or "the developer"
    return _page(
        f"Delete your {config.APP_NAME} account",
        f"""<h1>Delete your {config.APP_NAME} account</h1>
<p><b>In the app:</b> open Settings, tap <b>Delete account</b>, enter your password and confirm. Your account, name, email and server records are deleted at once.</p>
<p><b>Cannot open the app?</b> Email <b>{c}</b> from the address you registered with, with the subject "Delete my account". We delete it within 7 days.</p>
<p>Data kept only on your phone is removed when you uninstall the app.</p>""",
    )
