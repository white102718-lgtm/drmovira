import { useMemo, useState } from 'react';
import { Camera, Sparkles } from 'lucide-react';

import { createDirectorAiAssistDraft } from '../ai/directorAiAssist';
import { useDirectorStore } from '../store/directorStore';

export function AiAssistPanel() {
  const context = useDirectorStore((state) => state.hostContext);
  const project = useDirectorStore((state) => state.project);
  const updateScene = useDirectorStore((state) => state.updateScene);
  const addPresetCharacter = useDirectorStore((state) => state.addPresetCharacter);
  const addGeometryPrimitive = useDirectorStore((state) => state.addGeometryPrimitive);
  const addCameraShot = useDirectorStore((state) => state.addCameraShot);
  const [applied, setApplied] = useState(false);
  const draft = useMemo(
    () => (context ? createDirectorAiAssistDraft(context, project) : null),
    [context, project],
  );

  if (!context || !draft) return null;
  // Keep a non-null snapshot for callbacks. TypeScript cannot retain the
  // render-time narrowing for a value captured by an event handler.
  const aiDraft = draft;

  function applyAutoLayout() {
    updateScene({
      backgroundColor: aiDraft.layout.backgroundColor,
      showGround: true,
      snapToGrid: true,
    });
    for (let index = 0; index < aiDraft.layout.charactersToAdd; index += 1) {
      addPresetCharacter();
    }
    aiDraft.layout.geometry.forEach((geometry) => addGeometryPrimitive(geometry));
    setApplied(true);
  }

  return (
    <section className="panel-card ai-assist-panel" aria-label="AI 导演辅助">
      <div className="ai-assist-heading"><Sparkles aria-hidden="true" size={16} /><h2>AI 导演辅助</h2></div>
      <p>{aiDraft.layout.description}</p>
      <button type="button" className="ai-assist-layout-button" onClick={applyAutoLayout}>
        <Sparkles aria-hidden="true" size={15} /> {applied ? '再次应用自动布景' : '应用自动布景'}
      </button>
      <div className="ai-camera-candidates">
        <h3>候选机位</h3>
        {aiDraft.cameras.map((candidate) => (
          <article key={candidate.id}>
            <div><strong>{candidate.title}</strong><p>{candidate.description}</p></div>
            <button type="button" onClick={() => addCameraShot(candidate.snapshot)} title={`加入 ${candidate.title}`}>
              <Camera aria-hidden="true" size={14} /> 加入
            </button>
          </article>
        ))}
      </div>
      <p className="ai-assist-note">建议基于画布上下文生成，加入场景前均可逐项审核与修改。</p>
    </section>
  );
}
