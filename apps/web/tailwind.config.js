/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#171512",
        paper: "#f5f1e8",
        moss: "#38564a",
        rust: "#a85535",
      },
      boxShadow: {
        panel: "0 18px 45px rgba(39, 32, 24, 0.10)",
      },
    },
  },
  plugins: [],
};
