from datetime import datetime, timezone

from config.settings import settings
from services.email_service import send_email

# Matches --series-1 / --primary in frontend/src/index.css -- the same blue
# used for the logo mark and primary buttons in the app itself.
BRAND_BLUE = "#2a78d6"
BRAND_BLUE_DARK = "#1f5fae"

# A simplified folder glyph (stroke-only, no fill) echoing the FolderKanban
# icon used next to the FileFlow wordmark in the app itself -- see
# AuthLayout.jsx. Inline SVG rather than a hosted <img> so the icon renders
# immediately with no image-blocking prompt and no external request.
_FOLDER_ICON_SVG = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M3 7a2 2 0 0 1 2-2h4.5l2 2H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" '
    'stroke="#ffffff" stroke-width="1.7" stroke-linejoin="round"/>'
    '<path d="M9 13v4M13 11v6M17 13v4" stroke="#ffffff" stroke-width="1.7" stroke-linecap="round"/>'
    "</svg>"
)


def build_reset_email_html(reset_link: str, to_email: str) -> str:
    # Table-based layout with every rule inlined: email clients (Outlook's
    # Word rendering engine especially) don't support external/embedded
    # stylesheets or flex/grid, so anything not inlined on the element
    # itself silently drops.
    expiry = settings.PASSWORD_RESET_TOKEN_EXPIRY_MINUTES
    year = datetime.now(timezone.utc).year
    return f"""
    <div style="background:#eef1f6;padding:40px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e5eb;box-shadow:0 1px 3px rgba(16,24,40,0.06);">
        <tr>
          <td style="padding:32px 36px 24px;">
            <table role="presentation" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:linear-gradient(135deg,{BRAND_BLUE},{BRAND_BLUE_DARK});width:34px;height:34px;border-radius:9px;text-align:center;vertical-align:middle;">
                  {_FOLDER_ICON_SVG}
                </td>
                <td style="padding-left:11px;font-size:16px;font-weight:700;color:#101828;letter-spacing:-0.01em;">FileFlow</td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:4px 36px 8px;">
            <div style="height:1px;background:#eef0f3;"></div>
          </td>
        </tr>
        <tr>
          <td style="padding:32px 36px 8px;">
            <h1 style="margin:0 0 16px;font-size:21px;font-weight:700;color:#101828;letter-spacing:-0.01em;">Reset your password</h1>
            <p style="margin:0 0 12px;font-size:14.5px;line-height:23px;color:#475467;">
              Hi there,
            </p>
            <p style="margin:0 0 28px;font-size:14.5px;line-height:23px;color:#475467;">
              We received a request to reset the password on your FileFlow account
              (<span style="color:#101828;font-weight:600;">{to_email}</span>). Choose a new
              password by clicking the button below.
            </p>
            <table role="presentation" cellpadding="0" cellspacing="0">
              <tr>
                <td style="border-radius:10px;background:{BRAND_BLUE};box-shadow:0 1px 2px rgba(16,24,40,0.08);">
                  <a href="{reset_link}"
                     style="display:inline-block;padding:13px 32px;font-size:14.5px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:10px;letter-spacing:0.01em;">
                    Reset password
                  </a>
                </td>
              </tr>
            </table>
            <p style="margin:20px 0 0;font-size:13px;line-height:19px;color:#98a2b3;">
              This link expires in {expiry} minutes and can only be used once.
            </p>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;background:#f7f8fa;border-radius:10px;">
              <tr>
                <td style="padding:14px 16px;font-size:12px;line-height:18px;color:#98a2b3;">
                  Button not working? Paste this link into your browser:<br>
                  <a href="{reset_link}" style="color:{BRAND_BLUE};word-break:break-all;">{reset_link}</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 36px 32px;">
            <div style="height:1px;background:#eef0f3;margin-bottom:20px;"></div>
            <p style="margin:0;font-size:12.5px;line-height:19px;color:#98a2b3;">
              If you didn't request a password reset, you can safely ignore this email --
              your password will not be changed.
            </p>
          </td>
        </tr>
      </table>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;margin:24px auto 0;">
        <tr>
          <td style="text-align:center;font-size:11.5px;line-height:18px;color:#98a2b3;">
            This email was sent to {to_email} because a password reset was requested for this account.<br>
            &copy; {year} FileFlow. All rights reserved.
          </td>
        </tr>
      </table>
    </div>
    """.strip()


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Best-effort send -- see email_service.send_email for the delivery
    contract (never raises, swallows missing-key/network failures)."""
    subject = "Reset your FileFlow password"
    return send_email(subject, build_reset_email_html(reset_link, to_email), to_email)
