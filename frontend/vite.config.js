import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendRoutes = [
  "/health", "/auth", "/farmers", "/buyers", "/farms", "/crops",
  "/marketplace", "/orders", "/payments", "/escrow", "/payouts",
  "/transactions", "/deliveries", "/disputes", "/weather", "/advisories",
  "/market-prices", "/notifications", "/disease-detection", "/admin",
  "/pesticide-records", "/crop-planning", "/pest-knowledge", "/ussd", "/media",
];

export default defineConfig({
  plugins: [react()],
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
