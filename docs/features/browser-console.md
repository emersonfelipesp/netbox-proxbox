# Standalone Browser Console

## Purpose

netbox-proxbox provides a Console tab directly on each synchronized NetBox `VirtualMachine`. It does not navigate to or require another management application. Other applications may provide their own consoles as parallel downstream consumers, but they are not part of this request path.

The feature supports:

- QEMU graphical consoles through noVNC;
- QEMU terminal consoles through xterm.js; and
- LXC terminal consoles through xterm.js.

LXC graphical consoles are rejected at the browser, NetBox, and proxbox-api boundaries.

## Trust boundaries

```text
Browser
  | authenticated NetBox page + CSRF-protected session request
  v
netbox-proxbox
  | exact restricted VM + open_console endpoint permission
  | typed sync-state identity + authenticated service request
  v
proxbox-api
  | encrypted, origin-bound, short-lived, one-use relay state
  | Proxmox ticket acquisition and WebSocket authentication
  v
Proxmox vncwebsocket
```

netbox-proxbox owns NetBox object authorization and the user interface. proxbox-api owns Proxmox authentication and the WebSocket transport. This split is required because stock NetBox exposes Django plugin HTTP views but does not terminate plugin WebSockets.

The browser receives only:

- the configured public proxbox-api WebSocket authority plus a fixed relay path;
- one short-lived opaque relay token;
- the relay expiry timestamp; and
- the selected console type.

The browser never receives the Proxmox hostname, port, VNC ticket, authentication header or cookie, upstream WebSocket URL, endpoint ID, API key, or TLS verification policy. None of those values may appear in browser DOM attributes, JavaScript logs, Django error responses, or proxbox-api close reasons.

## Authorization and identity

The tab requires `netbox_proxbox.open_console_proxmoxendpoint`. Session creation repeats authorization server-side and never trusts fields supplied by JavaScript.

`ProxboxVMConsoleSessionView` performs these checks in order:

1. the caller is authenticated;
2. the caller has the global console permission;
3. `VirtualMachine.objects.restrict(user, "view")` returns the exact requested VM;
4. its `ProxboxVirtualMachineSyncState` belongs to that VM;
5. the typed `ProxmoxEndpoint` is enabled and remains visible through the caller's `open_console` object restriction;
6. the typed `ProxmoxNode` belongs to that endpoint, and its current name matches the recorded synchronized name;
7. any typed Proxmox cluster belongs to the same endpoint;
8. VMID is positive and the synchronized guest type is exactly `qemu` or `lxc`;
9. exactly one trusted `FastAPIEndpoint` maps the typed endpoint to a current proxbox-api endpoint row; and
10. a recorded raw backend endpoint ID, when present, matches the resolved backend ID.

Missing, ambiguous, partial, or drifted identity fails closed. The view does not fall back to the VM name, a custom field, the first Proxmox endpoint, or an unscoped proxbox-api request.

The tab view keeps the two object types separate inside NetBox's generic view
machinery. Its permission hook checks the endpoint-owned `open_console`
permission together with any inherited `additional_permissions`,
without allowing `ObjectPermissionRequiredMixin` to apply that
action to the `VirtualMachine` queryset. The queryset is independently
restricted with the caller's VM `view` permission, and the resolved synchronized
endpoint is then checked through its own `open_console` restriction. Removing
that explicit separation turns every endpoint-authorized VM lookup into a 404
because `open_console` is not a `VirtualMachine` action.

## Session protocol

The browser sends only the selected `console_type` to the plugin session route. The plugin derives every target field server-side and calls:

```http
POST /proxmox/console/browser-sessions
Content-Type: application/json
X-Proxbox-API-Key: <server-side only>
X-Proxbox-Actor: <NetBox username>

{
  "endpoint_id": 31,
  "vmid": 101,
  "node": "pve-01",
  "vm_type": "qemu",
  "console_type": "novnc",
  "origin": "https://netbox.example.com"
}
```

proxbox-api returns a short-lived opaque token and a relative browser relay path to the NetBox server. The plugin validates the response and returns a browser-safe projection:

```json
{
  "websocket_url": "wss://relay.example.com/proxmox/console/browser-stream",
  "stream_token": "<opaque>",
  "expires_at": "2026-09-14T13:00:00+00:00",
  "console_type": "novnc"
}
```

The configured `FastAPIEndpoint.websocket_domain` and WebSocket port must identify the public TLS endpoint that serves proxbox-api. The page and relay must use HTTPS/WSS. Redirects are disabled for the authenticated server request.

The browser WebSocket automatically supplies the NetBox page `Origin`. It offers
`binary` plus a dedicated token subprotocol, while proxbox-api negotiates only
`binary`. The token never appears in the URI, query string, DOM, console output,
or access log. proxbox-api atomically consumes the token only when that origin
matches the value bound during creation. Expired, replayed, malformed, or
foreign-origin tokens cannot open a stream.

## Graphical console

The graphical client uses the vendored noVNC 1.7.0 ES-module runtime and connects without a password. The runtime includes the upstream noVNC and pako licenses and is pinned by a complete file-list and SHA-256 tree-digest test. proxbox-api performs the bounded RFB 3.8 authentication exchange with Proxmox server-side, answers the VNC challenge using the private ticket, and presents no-auth RFB to noVNC only after that upstream authentication succeeds.

The UI enables `scaleViewport` and `resizeSession`. Disconnect, reconnect, page hide, and page unload paths destroy the RFB object and remove listeners before another session can start.

## Terminal console

The terminal client uses the existing vendored xterm.js assets. It follows Proxmox termproxy framing:

- terminal output frames begin with `d` and the prefix is removed before writing to xterm;
- resize uses `1:<rows>:<cols>:0`;
- the keepalive frame is `0` followed by NUL; and
- keyboard input is forwarded only while the current WebSocket is open.

A `ResizeObserver` updates the terminal dimensions. The observer, socket, xterm instance, and event listeners are all released during disconnect and page teardown.

## Migration from the external handoff

Migration `0084_proxboxpluginsettings_console_url.py` remains immutable release history. Migration `0095_standalone_vm_console.py` removes `ProxboxPluginSettings.console_url` and adds the `open_console_proxmoxendpoint` permission. The settings form, settings API, template extension button, and external-link template no longer expose the retired handoff.

Upgrade proxbox-api first so the browser relay is available before the NetBox
plugin exposes the Console tab. Deploying the plugin first fails closed with an
unavailable-session response, but leaves operators without a working console
until the backend is upgraded.

After upgrading proxbox-api:

1. upgrade netbox-proxbox and run the normal NetBox migration process;
2. grant `netbox_proxbox.open_console_proxmoxendpoint` only to roles allowed to interact with guest consoles;
3. configure the `FastAPIEndpoint` HTTP and public WebSocket authorities with HTTPS/WSS and certificate verification; and
4. verify the Console tab with a synchronized QEMU and LXC guest.

No external console URL setting is required or accepted.

## Failure behavior

Console identity errors include a stable diagnostic code, a plain-language cause, and the exact operator action. The page offers **Repair all enabled endpoints** when the failure can be repaired by a full sync and the current user has the core Job `add` permission used by normal Proxbox sync enqueue actions. The button is a CSRF-protected POST to the existing guarded repair workflow; it reconciles compatibility fields, re-pushes endpoint configuration, and queues one full sync across every enabled Proxmox endpoint. That reconciliation can update or remove stale synchronized NetBox inventory outside the displayed VM, so the page states the scope beside the button. It does not grant permissions, enable endpoints, expose secrets, guess a missing endpoint, or bypass an active repair job.

| Symptom or code | Required action |
|---|---|
| Console tab is absent | A NetBox administrator must grant `netbox_proxbox.open_console_proxmoxendpoint` for the required endpoint and ensure the user can view the VM. Users cannot grant themselves console access. |
| `SYNC_STATE_MISSING` | Review the disclosed estate-wide scope, then select **Repair all enabled endpoints** when offered. Otherwise ask an administrator with Job `add` permission to run **Proxbox → Repair / Rebuild Proxbox sync-state**. Return after the job completes. |
| `SYNC_ENDPOINT_LINK_MISSING` | The proxbox-api endpoint can be healthy while the VM's typed NetBox endpoint or node relation is missing. Review the disclosed estate-wide scope, then select **Repair all enabled endpoints** when offered, or ask an administrator with Job `add` permission to run the same recovery action. Return after the job completes. |
| `SYNC_ENDPOINT_DISABLED` | A Proxbox administrator must enable the linked NetBox `ProxmoxEndpoint`, run a full sync, and retry. The console does not enable endpoints inline because enablement changes the endpoint's estate-wide synchronization posture. |
| Tab shows another incomplete or drifted identity code | Run a full Proxbox sync and confirm the VM sidecar links one enabled endpoint and node. Do not repair ambiguous identity by guessing an endpoint. |
| Session reports no trusted backend | Confirm the endpoint has been synchronized to exactly one enabled FastAPI backend and its stored target still matches. |
| Session requires HTTPS | Serve NetBox over HTTPS and configure a public WSS proxbox-api endpoint. |
| WebSocket closes as invalid or expired | Create a new session; tokens are short-lived, origin-bound, and one-use. |
| QEMU graphical console fails before display | Check proxbox-api and Proxmox console permissions; the browser will not receive the private failure detail. |
| LXC graphical option is absent | Expected; LXC supports terminal only. |

## Verification

Run the focused plugin tests:

```bash
uv run pytest -p no:django tests/test_vm_console_server.py tests/test_vm_console_frontend.py
```

Run the real-Django migration and view tests plus the complete repository gates before release. Validate in an authenticated browser that:

- the Console tab stays inside NetBox;
- QEMU graphical and terminal sessions exchange frames;
- LXC terminal sessions exchange frames;
- replay and expiry fail;
- disconnect and reconnect create a fresh session; and
- browser requests, rendered HTML, console logs, and network responses contain no external management URL or Proxmox ticket/authentication material.
