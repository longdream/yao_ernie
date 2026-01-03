/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        gray: require('tailwindcss/colors').gray,
        black: '#000000',
        white: '#ffffff'
      },
      borderRadius: {
      },
    },
  },
  plugins: [],
}


