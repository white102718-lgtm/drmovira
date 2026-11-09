import { useState } from 'react';
import { BookOpen, ChevronDown, ChevronRight } from 'lucide-react';

import { useDirectorStore } from '../store/directorStore';
import type { HostDirectorContextItem } from '../schema/hostContext';

const SECTIONS: Array<{
  key: 'briefs' | 'storyboards' | 'characters' | 'scenes' | 'referenceImages' | 'cameraDirections';
  label: string;
}> = [
  { key: 'briefs', label: '创意简报' },
  { key: 'storyboards', label: '分镜' },
  { key: 'characters', label: '角色' },
  { key: 'scenes', label: '场景' },
  { key: 'referenceImages', label: '参考图' },
  { key: 'cameraDirections', label: '机位意图' },
];

function ContextItem({ item }: { item: HostDirectorContextItem }) {
  return (
    <li className="host-context-item">
      {item.imageUrl ? (
        <img src={item.imageUrl} alt="" className="host-context-thumbnail" />
      ) : null}
      <div>
        <strong>{item.title}</strong>
        {item.description ? <p>{item.description}</p> : null}
        {item.fields?.map((field) => (
          <p key={field.label} className="host-context-field">
            {field.label}：{field.value}
          </p>
        ))}
      </div>
    </li>
  );
}

export function HostContextPanel() {
  const context = useDirectorStore((state) => state.hostContext);
  const [expanded, setExpanded] = useState(true);
  if (!context) return null;

  const sourceCount = context.sourceNodeIds.length;
  const itemCount = SECTIONS.reduce(
    (total, section) => total + context[section.key].length,
    0,
  );

  return (
    <section className="panel-card host-context-panel" aria-label="画布创意上下文">
      <button
        type="button"
        className="host-context-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span><BookOpen aria-hidden="true" size={16} /> 画布上下文</span>
        {expanded ? <ChevronDown aria-hidden="true" size={16} /> : <ChevronRight aria-hidden="true" size={16} />}
      </button>
      <p className="host-context-summary">{sourceCount} 个上游节点 · {itemCount} 条可用素材</p>
      {expanded ? (
        <div className="host-context-sections">
          {SECTIONS.map((section) => {
            const items = context[section.key];
            if (!items.length) return null;
            return (
              <section key={section.key}>
                <h3>{section.label} <span>{items.length}</span></h3>
                <ul>{items.slice(0, 4).map((item) => <ContextItem key={`${item.kind}:${item.id}`} item={item} />)}</ul>
              </section>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
