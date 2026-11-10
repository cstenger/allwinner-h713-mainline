# Frozen installer payloads

Content-addressed copies (file name = SHA-256) of the exact files the
historical one-shot installers deployed. Their tests load payloads from here
by the pinned hash, so later legitimate changes to the live sources in
`tools/` do not break, or silently change, what those installers verify.
