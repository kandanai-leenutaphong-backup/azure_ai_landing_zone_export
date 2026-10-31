import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/barlow-condensed/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./tailwind.css";
import { AzureSkyGallery } from "@harness/azure-sky-styling";
import "@harness/azure-sky-styling/styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><div className="min-h-screen antialiased"><AzureSkyGallery applicationPreview={{ href: "./security-review.html", label: "Security review preview" }} /></div></React.StrictMode>,
);