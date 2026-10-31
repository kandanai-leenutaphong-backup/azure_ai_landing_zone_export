import templeUrl from "./assets/painterly/legeay-temple.webp";
import hallUrl from "./assets/painterly/challe-crowned-hall.webp";
import arcadeUrl from "./assets/painterly/challe-arcade.webp";
import type { PainterlyArchitectureMask } from "./distantArchitecture";

const maskSources = [
  { id: "legeay-temple", source: templeUrl },
  { id: "challe-crowned-hall", source: hallUrl },
  { id: "challe-arcade", source: arcadeUrl },
] as const;

let loadedMasks: Promise<readonly PainterlyArchitectureMask[]> | undefined;

export function loadPainterlyArchitectureMasks(): Promise<readonly PainterlyArchitectureMask[]> {
  loadedMasks ??= Promise.all(maskSources.map(async mask => {
    const image = new Image();
    image.src = mask.source;
    await image.decode();
    return { id: mask.id, image };
  })).catch(error => {
    loadedMasks = undefined;
    throw error;
  });
  return loadedMasks;
}