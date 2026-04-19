// Frontend config. Served as a static file; values are visible to anyone.
// Restrict your Google Maps key to your domain (HTTP referrer).
// `backendUrl` is prepended to API paths. When frontend and backend are
// served from the same domain (Caddy setup), use "/api".
window.APP_CONFIG = {
  googleMapsKey: "YOUR_GOOGLE_MAPS_API_KEY",
  backendUrl: "/api",
};
