# Browser Console

The **Console** button on a synchronized virtual machine opens its corresponding management page directly on the Console tab. Virtual-machine guests use a graphical console, while container guests use a terminal console.

The button does not expose an upstream endpoint URL. The management service creates a one-time browser stream after the operator is authenticated and keeps the upstream endpoint, ticket, and TLS configuration on the server. Set **Browser console URL** in Proxbox plugin settings to the audited HTTPS management origin; invalid, insecure, or empty values hide the button.
