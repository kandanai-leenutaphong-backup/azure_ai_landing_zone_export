# Acquisition Contract

`webres` owns URL validation, public-address resolution, pinned HTTP/TLS transport, redirect
validation, robots handling, bounded reads, throttling and provenance. All fetch/probe/browser
requests use that boundary. Implicit environment proxies, credentials in URLs, private/multicast
addresses, non-web schemes and non-read methods are refused. HTTP and HTTPS are supported;
unresolved DNS refuses rather than deferring an unchecked connection.

`fetch` returns bytes plus `Provenance`; `open_public` is the bounded caller's transport and
`read_bounded` enforces the 16 MiB response limit. TLS retains the original server hostname while
the socket connects to a validated numeric address. Redirects independently recheck permissions.
The per-host floor is the larger of two seconds and a parsed publisher crawl delay/request rate.
It is in-process, not a cross-process quota. Robots overrides require
operator authority and are recorded by acquisition commands.

`Catalogue` keys entries by a contained artifact path. `record`, `save`, `drop_missing` and
`by_subject` preserve the source URL, retrieval metadata, hash and ownership statement. Existing
manifests cannot cause file reads through absolute paths, traversal or escaping symlinks.
Unknown adoption provenance stays unknown. The CLI's `--verify` is read-only; concurrent writers
are not coordinated and must not share one manifest.

Screenshot requests are fulfilled from the same guarded Python transport rather than continued
through a credentialed browser session. Blocked resources are counted, not silently reported as a
clean capture. Scripts may execute for rendering; service workers, WebSockets and write methods
are denied. Use process/network isolation for hostile sites; this is not a browser exploit sandbox.

No live collection harvest was performed for packaging. Offline fixture tests prove transport
decisions, provenance integrity and rendering, not current publisher permission or URL liveness.