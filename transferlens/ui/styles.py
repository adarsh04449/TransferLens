"""Visual rules for the review workspace."""

CSS = """
<style>
  [data-testid="stToolbar"] { display: none; }
  .stApp { background: #F6F3EC; }
  header[data-testid="stHeader"] { background: transparent; }
  [data-testid="stSidebar"] { background: #E7E1D6; border-right: 1px solid #D5CFC3; }
  .brand { font-family: Georgia, "Iowan Old Style", serif; font-size: 1.45rem; letter-spacing: 0.04em; margin: 0; }
  .brand-sub { color: #5C564C; font-size: 0.85rem; margin: 0.15rem 0 1rem; }
  h1 { font-family: Georgia, "Iowan Old Style", serif; font-weight: 500; letter-spacing: -0.02em; }
  .lede { color: #4A453E; font-size: 1.02rem; margin-top: -0.4rem; }
  .pill { display: inline-block; border-radius: 999px; padding: 0.12rem 0.55rem; font-size: 0.75rem; letter-spacing: 0.03em; text-transform: uppercase; }
  .pass { background: #E4EFEA; color: #1F4E46; }
  .fail { background: #F8E8E4; color: #8C2F2F; }
  .needs_confirmation { background: #F8EFDC; color: #8A5A12; }
  .unknown { background: #E6EBF0; color: #3E4C59; }
  .waiting { background: #E7E1D5; color: #5C564C; }
  .finding { border: 1px solid #DDD6C8; border-radius: 12px; padding: 0.8rem 0.9rem; margin-bottom: 0.55rem; background: #FFFcf7; }
  .finding strong { display: block; margin: 0.35rem 0 0.2rem; }
  .finding p { margin: 0; color: #3F3A34; }
  .banner { border-radius: 12px; padding: 0.75rem 0.9rem; margin-bottom: 0.8rem; background: #F8EFDC; color: #5C4310; }
  .banner.quiet { background: #E7E1D5; color: #3F3A34; }
  .tile { background: #FFFCF7; border: 1px solid #DDD6C8; border-radius: 14px; padding: 0.9rem 1rem; min-height: 7.2rem; }
  .tile-label { color: #5C564C; font-size: 0.78rem; letter-spacing: 0.04em; text-transform: uppercase; }
  .tile-value { font-family: Georgia, "Iowan Old Style", serif; font-size: 1.7rem; margin: 0.25rem 0; }
  .tile-note { color: #6B645B; font-size: 0.85rem; }
  .doc-frame { border: 1px solid #DDD6C8; border-radius: 12px; overflow: hidden; background: white; }
  .fine { color: #6B645B; font-size: 0.8rem; }
</style>
"""

ROLE_LABELS = {
    "statement": "NorthStar statement",
    "receiving_account_record": "Receiving account record",
    "client_authorization": "Client authorization",
    "northstar_transfer_form": "NorthStar transfer form",
}

STATUS_LABELS = {
    "pass": "Pass",
    "fail": "Fail",
    "needs_confirmation": "Needs confirmation",
    "unknown": "Unverified",
    "waiting": "Waiting",
}
