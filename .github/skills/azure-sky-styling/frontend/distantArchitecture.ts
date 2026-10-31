export type EdificeKind = "gateway" | "terraces" | "buttress";

export interface DistantEdifice {
  kind: EdificeKind;
  left: number;
  top: number;
  width: number;
  height: number;
  opacity: number;
  tiers: number;
  crown: number;
}

export interface DistantArchitectureScene {
  seed: number;
  edifices: DistantEdifice[];
}

export interface PainterlyArchitectureMask {
  id: string;
  image: HTMLImageElement;
}

export function generateDistantArchitecture(seed: number): DistantArchitectureScene {
  let state = seed >>> 0;
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
  const kinds: EdificeKind[] = ["gateway", "terraces", "buttress"];
  const planes = [
    { left: .16, top: .26, width: .25, height: .65, opacity: .026 },
    { left: .43, top: .33, width: .23, height: .58, opacity: .018 },
    { left: .66, top: .22, width: .29, height: .78, opacity: .032 },
    { left: -.15, top: .13, width: .46, height: .99, opacity: .067 },
    { left: .77, top: .08, width: .38, height: 1.10, opacity: .075 },
  ];
  return {
    seed: seed >>> 0,
    edifices: planes.map(plane => ({
      kind: kinds[Math.floor(random() * kinds.length)],
      left: plane.left + (random() - .5) * .09,
      top: plane.top + (random() - .5) * .13,
      width: plane.width * (.9 + random() * .2),
      height: plane.height * (.9 + random() * .15),
      opacity: plane.opacity,
      tiers: 3 + Math.floor(random() * 4),
      crown: .18 + random() * .24,
    })),
  };
}

function drawOpening(context: CanvasRenderingContext2D, left: number, top: number, width: number, height: number) {
  context.beginPath();
  context.moveTo(left, top + height);
  context.lineTo(left, top + width * .5);
  context.bezierCurveTo(left, top - width * .16, left + width, top - width * .16, left + width, top + width * .5);
  context.lineTo(left + width, top + height);
  context.closePath();
  context.fill();
}

function drawEdifice(context: CanvasRenderingContext2D, edifice: DistantEdifice, width: number, height: number) {
  const crownWidth = width * edifice.crown;
  if (edifice.kind === "gateway") {
    context.fillRect(0, height * .16, width, height * .84);
    context.fillRect(width * .08, height * .09, width * .84, height * .1);
    context.fillRect(width * .5 - crownWidth, 0, crownWidth * 2, height * .12);
    context.globalCompositeOperation = "destination-out";
    drawOpening(context, width * .28, height * .27, width * .44, height * .74);
    context.fillRect(width * .11, height * .23, width * .045, height * .38);
    context.fillRect(width * .845, height * .23, width * .045, height * .38);
  } else if (edifice.kind === "terraces") {
    for (let tier = 0; tier < edifice.tiers; tier += 1) {
      const fraction = tier / edifice.tiers;
      const tierWidth = width * (.32 + fraction * .68);
      const offset = width * .5 - tierWidth * .5;
      context.fillRect(offset, height * fraction, tierWidth, height * (1 - fraction));
      context.fillRect(offset - width * .025, height * fraction + height * .025, tierWidth + width * .05, height * .025);
    }
    context.fillRect(width * .49 - crownWidth * .2, -height * .07, crownWidth * .4, height * .16);
    context.fillRect(width * .83, height * .51, width * .11, height * .49);
    context.globalCompositeOperation = "destination-out";
    for (let opening = 0; opening < 3; opening += 1) drawOpening(context, width * (.3 + opening * .145), height * .7, width * .08, height * .31);
  } else {
    context.beginPath();
    context.moveTo(width * .1, height);
    context.lineTo(width * .28, height * .11);
    context.lineTo(width * .28, 0);
    context.lineTo(width * .7, 0);
    context.lineTo(width * .7, height * .11);
    context.lineTo(width * .9, height);
    context.closePath();
    context.fill();
    context.fillRect(width * .18, height * .15, width * .65, height * .055);
    context.fillRect(0, height * .42, width * .14, height * .58);
    context.fillRect(width * .85, height * .37, width * .15, height * .63);
    context.fillRect(width * .12, height * .55, width * .76, height * .07);
    context.globalCompositeOperation = "destination-out";
    context.fillRect(width * .47, height * .15, width * .055, height * .51);
    drawOpening(context, width * .35, height * .75, width * .3, height * .26);
  }
  context.globalCompositeOperation = "source-over";
}

export function paintDistantArchitecture(canvas: HTMLCanvasElement, scene: DistantArchitectureScene, width: number, height: number, tint = "#345a80", masks: readonly PainterlyArchitectureMask[] = []) {
  const scale = Math.min(1, 1600 / Math.max(1, width), 1100 / Math.max(1, height));
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Distant architecture requires a 2D canvas context");
  const layer = document.createElement("canvas");
  layer.width = canvas.width;
  layer.height = canvas.height;
  const painter = layer.getContext("2d");
  if (!painter) throw new Error("Distant architecture requires a 2D layer context");

  for (const [index, edifice] of scene.edifices.entries()) {
    painter.clearRect(0, 0, layer.width, layer.height);
    painter.save();
    painter.translate(edifice.left * layer.width, edifice.top * layer.height);
    painter.fillStyle = tint;
    if (masks.length) {
      const foreground = edifice.opacity > .05;
      const towers = foreground ? masks.filter(mask => mask.image.naturalHeight >= mask.image.naturalWidth) : [];
      const candidates = towers.length ? towers : masks;
      const mask = candidates[(scene.seed + index) % candidates.length];
      const slotWidth = edifice.width * layer.width;
      const slotHeight = edifice.height * layer.height;
      const stampScale = foreground ? slotHeight / mask.image.naturalHeight : Math.min(slotWidth / mask.image.naturalWidth, slotHeight / mask.image.naturalHeight);
      const stampWidth = mask.image.naturalWidth * stampScale;
      const stampHeight = mask.image.naturalHeight * stampScale;
      painter.drawImage(mask.image, (slotWidth - stampWidth) / 2, 0, stampWidth, stampHeight);
    } else {
      drawEdifice(painter, edifice, edifice.width * layer.width, edifice.height * layer.height);
    }
    painter.restore();
    if (masks.length) {
      painter.globalCompositeOperation = "source-in";
      painter.fillStyle = tint;
      painter.fillRect(0, 0, layer.width, layer.height);
    }
    painter.globalCompositeOperation = "destination-in";
    const distance = painter.createLinearGradient(0, 0, 0, layer.height);
    distance.addColorStop(0, "rgba(0,0,0,.7)");
    distance.addColorStop(.30, "rgba(0,0,0,1)");
    distance.addColorStop(.68, "rgba(0,0,0,.45)");
    distance.addColorStop(1, "rgba(0,0,0,0)");
    painter.fillStyle = distance;
    painter.fillRect(0, 0, layer.width, layer.height);
    painter.globalCompositeOperation = "source-over";
    context.globalAlpha = edifice.opacity;
    context.drawImage(layer, 0, 0);
  }
  context.globalAlpha = 1;
  context.globalCompositeOperation = "destination-in";
  const clearance = context.createLinearGradient(0, 0, canvas.width, 0);
  clearance.addColorStop(0, "rgba(0,0,0,1)");
  clearance.addColorStop(.23, "rgba(0,0,0,.8)");
  clearance.addColorStop(.43, "rgba(0,0,0,.15)");
  clearance.addColorStop(.57, "rgba(0,0,0,.15)");
  clearance.addColorStop(.8, "rgba(0,0,0,.85)");
  clearance.addColorStop(1, "rgba(0,0,0,1)");
  context.fillStyle = clearance;
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.globalCompositeOperation = "source-over";
  return canvas.toDataURL("image/png");
}