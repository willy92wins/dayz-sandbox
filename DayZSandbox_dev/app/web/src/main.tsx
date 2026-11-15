import { createRoot } from "react-dom/client";
import App from "./App";
import "dockview-react/dist/styles/dockview.css";
import "./styles.css";

const el = document.getElementById("root");
if (el) {
  createRoot(el).render(<App />);
}
