import { useState, type CSSProperties } from "react";
import { Code2, Copy, Layers3, RotateCcw } from "lucide-react";
import { IconButton, type Notice } from "./primitives";
import { defaultDepthEffects, defaultDepthGrainOpacity, depthClassNames, depthEffects, depthRecipe, type DepthEffectId } from "./depthEffects";
import "./depth-effects.css";
import "./depth-study.css";

function SurfaceSample({ effects, name, grainOpacity = defaultDepthGrainOpacity }: { effects: readonly DepthEffectId[]; name: string; grainOpacity?: number }) {
  return <div className={`azs-depth-plane ${depthClassNames(effects, "ground")}`}>
    <div className={`azs-depth-surface azs-depth-sample ${depthClassNames(effects, "surface")}`} data-depth-sample={name} data-effects={effects.join(" ")} style={{ "--azs-depth-grain-opacity": grainOpacity / 100 } as CSSProperties}>
      <span className="azs-eyebrow">AS-001 / COLLECTION</span>
      <h4>Reference atlas</h4>
      <div className="azs-depth-sample-footer"><span><strong>12,408</strong><span className="azs-mono">records</span></span><Layers3 size={22} /></div>
    </div>
  </div>;
}

export function DepthStudy({ notify }: { notify: Notice }) {
  const [selected, setSelected] = useState<DepthEffectId[]>([...defaultDepthEffects]);
  const [grainOpacity, setGrainOpacity] = useState(defaultDepthGrainOpacity);
  const [recipeOpen, setRecipeOpen] = useState(false);
  const [copiedRecipe, setCopiedRecipe] = useState<string | null>(null);
  const toggleEffect = (id: DepthEffectId) => {
    setSelected(current => current.includes(id) ? current.filter(value => value !== id) : [...current, id]);
    setCopiedRecipe(null);
  };
  const reset = () => {
    setSelected([...defaultDepthEffects]);
    setGrainOpacity(defaultDepthGrainOpacity);
    setCopiedRecipe(null);
    setRecipeOpen(false);
  };
  async function copyRecipe(effects: readonly DepthEffectId[], opacity: number, label: string) {
    const recipe = depthRecipe(effects, opacity);
    setCopiedRecipe(recipe);
    try { await navigator.clipboard.writeText(recipe); notify(`${label} recipe copied`); }
    catch { setRecipeOpen(true); notify("Clipboard unavailable. Recipe shown in the code panel.", "error"); }
  }
  return <section id="depth" className="azs-depth-study" aria-labelledby="azs-depth-title">
    <div className="azs-material-heading">
      <div><span className="azs-eyebrow azs-muted">SURFACE FINISHES / 01.C</span><h3 id="azs-depth-title">Surface depth</h3></div>
      <div className="azs-row">
        <IconButton label="Copy combined depth recipe" onClick={() => void copyRecipe(selected, grainOpacity, "Combined depth")}><Copy size={17} /></IconButton>
        <IconButton label="Reset depth effects" onClick={reset}><RotateCcw size={17} /></IconButton>
      </div>
    </div>
    <div className="azs-depth-workbench">
      <div className="azs-depth-comparison">
        <figure><figcaption>Baseline<span className="azs-mono">Cobalt</span></figcaption><SurfaceSample effects={[]} name="baseline" /></figure>
        <figure><figcaption>Combined<output className="azs-mono" aria-live="polite">{selected.length} effects</output></figcaption><SurfaceSample effects={selected} name="combined" grainOpacity={grainOpacity} /></figure>
      </div>
      <fieldset className="azs-depth-controls">
        <legend>Effect layers</legend>
        <div className="azs-depth-toggles">{depthEffects.map(effect => <label className="azs-depth-toggle" key={effect.id}>
          <input type="checkbox" checked={selected.includes(effect.id)} onChange={() => toggleEffect(effect.id)} />
          <span>{effect.label}</span>
        </label>)}</div>
        <label className="azs-field azs-depth-grain-control" htmlFor="azs-depth-grain-opacity">Grain opacity<output className="azs-inline-value azs-mono" htmlFor="azs-depth-grain-opacity">{grainOpacity}%</output>
          <input id="azs-depth-grain-opacity" type="range" min={0} max={8} step={1} value={grainOpacity} disabled={!selected.includes("grain")} onChange={event => { setGrainOpacity(Number(event.target.value)); setCopiedRecipe(null); }} />
        </label>
      </fieldset>
    </div>
    <details className="azs-depth-recipe" open={recipeOpen} onToggle={event => setRecipeOpen(event.currentTarget.open)}>
      <summary><Code2 size={16} /><span>HTML recipe</span></summary>
      <pre><code>{copiedRecipe ?? depthRecipe(selected, grainOpacity)}</code></pre>
    </details>
    <h4 className="azs-depth-isolated-title">Isolated effects</h4>
    <div className="azs-depth-isolates">{depthEffects.map((effect, index) => <article key={effect.id} aria-labelledby={`azs-depth-${effect.id}-title`}>
      <div className="azs-depth-isolate-heading"><span className="azs-mono azs-muted">0{index + 1}</span><h5 id={`azs-depth-${effect.id}-title`}>{effect.label}</h5><IconButton label={`Copy ${effect.label.toLowerCase()} recipe`} onClick={() => void copyRecipe([effect.id], defaultDepthGrainOpacity, effect.label)}><Copy size={15} /></IconButton></div>
      <SurfaceSample effects={[effect.id]} name={effect.id} />
      <code className="azs-depth-class-name">.{effect.className}</code>
    </article>)}</div>
  </section>;
}