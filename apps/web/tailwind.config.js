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
        // 故事地图可视化语义色（避免散落魔法值）：暖纸底上均通过对比度校验。
        viz: {
          open: "#b45309", // 琥珀：进行中 / 开放伏笔·情节线
          resolved: "#38564a", // moss：已回收 / 已收束
          overdue: "#b3261e", // 红：超期未回收
          muted: "rgba(0,0,0,0.25)",
        },
      },
      boxShadow: {
        panel: "0 18px 45px rgba(39, 32, 24, 0.10)",
      },
    },
  },
  plugins: [],
};
