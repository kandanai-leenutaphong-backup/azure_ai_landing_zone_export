import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/barlow-condensed/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "../tailwind.css";
import "../../frontend/azure-sky.css";
import { SecurityReviewPreview } from "./Preview";
import "./preview.css";

createRoot(document.getElementById("root")!).render(<StrictMode><SecurityReviewPreview /></StrictMode>);