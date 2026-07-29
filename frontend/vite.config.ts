import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],

  build: {
    // Les écrans sont chargés à la demande (voir `src/main.tsx`). Le découpage
    // ci-dessous isole en plus le socle React et le routeur, qui changent rarement :
    // une mise à jour applicative n'invalide alors pas leur cache navigateur.
    rolldownOptions: {
      output: {
        advancedChunks: {
          groups: [
            { name: "react", test: /node_modules\/(react|react-dom|scheduler)\// },
            { name: "router", test: /node_modules\/react-router/ },
          ],
        },
      },
    },
    // Seuil abaissé : le contexte d'usage est un réseau mobile sénégalais, pas une
    // fibre. Un dépassement doit se voir en revue, pas passer inaperçu.
    chunkSizeWarningLimit: 250,
  },
});
