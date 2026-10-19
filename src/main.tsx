import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { initPwa } from "./lib/pwa";

createRoot(document.getElementById("root")!).render(<App />);

// Story 17: register the service worker + BackgroundSync queue after mount so
// it never blocks the initial paint.
void initPwa();
