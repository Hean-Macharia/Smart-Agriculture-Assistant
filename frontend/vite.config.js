import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendRoutes = [
  "/health", "/auth", "/farmers", "/buyers", "/farms", "/crops",
  "/marketplace", "/orders", "/payments", "/escrow", "/payouts",
  "/transactions", "/deliveries", "/disputes", "/weather", "/advisories",
  "/market-prices", "/notifications", "/disease-detection", "/admin",
  "/pesticide-records", "/crop-planning", "/pest-knowledge", "/ussd", "/media",
];

function offlineAssetManifest() {
  return {
    name: "shambalink-offline-asset-manifest",
    generateBundle(_options, bundle) {
      const assets = Object.values(bundle)
        .filter((entry) => entry.type === "chunk" || (entry.type === "asset" && /\.(?:css|woff2?|svg|png|webp)$/i.test(entry.fileName)))
        .map((entry) => `/${entry.fileName}`);
      this.emitFile({ type: "asset", fileName: "precache-assets.json", source: JSON.stringify({ version: "1.1.0", assets }) });
    },
  };
}

export default defineConfig({
  plugins: [react(), offlineAssetManifest()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    open: true,
    proxy: Object.fromEntries(
      backendRoutes.map((route) => [route, {
        target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      }]),
    ),
  },
});
