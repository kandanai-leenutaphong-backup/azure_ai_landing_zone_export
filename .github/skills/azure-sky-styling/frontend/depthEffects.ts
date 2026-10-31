export const depthEffects = [
  { id: "grain", label: "Static grain", className: "azs-depth-grain", target: "surface" },
  { id: "edge-light", label: "Edge light", className: "azs-depth-edge-light", target: "surface" },
  { id: "shadow", label: "Layered shadow", className: "azs-depth-shadow", target: "surface" },
  { id: "blue-shading", label: "Blue shading", className: "azs-depth-blue-shading", target: "surface" },
  { id: "sheen", label: "Broad sheen", className: "azs-depth-sheen", target: "surface" },
  { id: "tonal-ground", label: "Tonal ground", className: "azs-depth-tonal-ground", target: "ground" },
] as const;

export type DepthEffectId = typeof depthEffects[number]["id"];
export const defaultDepthEffects: DepthEffectId[] = ["grain", "edge-light", "shadow", "blue-shading"];
export const defaultDepthGrainOpacity = 3;

export function depthClassNames(selected: readonly DepthEffectId[], target: "surface" | "ground") {
  return depthEffects.filter(effect => effect.target === target && selected.includes(effect.id)).map(effect => effect.className).join(" ");
}

export function depthRecipe(selected: readonly DepthEffectId[], grainOpacity = defaultDepthGrainOpacity) {
  const ground = depthClassNames(selected, "ground");
  const surface = ["azs-depth-surface", depthClassNames(selected, "surface")].filter(Boolean).join(" ");
  const grain = selected.includes("grain") ? `; --azs-depth-grain-opacity: ${grainOpacity / 100}` : "";
  return `<link rel="stylesheet" href="./frontend/depth-effects.css">\n\n<div${ground ? ` class="${ground}"` : ""} style="padding: 24px">\n  <div class="${surface}"\n       style="padding: 24px${grain}">\n    Azure Sky\n  </div>\n</div>`;
}