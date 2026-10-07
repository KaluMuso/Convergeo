# Vendor invite Preview prerequisite

The vendor `/[locale]/accept-invite` page accepts only a Supabase invite token hash in the URL fragment. It calls `verifyOtp` with `type: "invite"` before allowing password setup. Supabase's default invite confirmation link verifies the token at Auth and redirects with a session fragment, so that default link cannot complete this page's flow.

Before using this flow on a protected staging Preview, an Auth owner must configure the **staging** Supabase project's Invite email template to link to:

```html
<a href="{{ .RedirectTo }}#token_hash={{ .TokenHash }}&type=invite">Accept invite</a>
```

The invite's `redirectTo` must be the exact protected vendor Preview URL with the locale path, for example `https://<immutable-vendor-preview>/en/accept-invite`, and that URL must be permitted in the staging Supabase Auth redirect allowlist. Check the effective Preview environment before any invite is sent. Do not use a generic Preview that points at production Supabase.

These hosted Auth template and redirect settings are prerequisites; this repository change does not apply them or send an invite. The invited owner chooses the password in the browser after opening the protected Preview link.
