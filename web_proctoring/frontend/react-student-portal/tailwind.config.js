export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca"
        }
      },
      boxShadow: {
        soft: "0 10px 24px rgba(15, 23, 42, 0.08)",
        lift: "0 16px 32px rgba(15, 23, 42, 0.14)"
      }
    }
  },
  plugins: []
};