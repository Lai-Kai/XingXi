# Native deployment login through Cloudflare Tunnel

The existing account works through the local forwarded port, but the login form
does not submit through the public Tunnel hostname. Preserve all account and
corpus data and port 12026 while restoring public login.

Configure explicit development hostnames for Next.js without admitting arbitrary
origins. Verify the public form submits, HTTPS authentication works, and unknown
origins remain blocked.
