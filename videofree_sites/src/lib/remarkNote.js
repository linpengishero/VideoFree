// Turns `::note ... ::` single-paragraph blocks in docs markdown into
// <div class="note"> elements via mdast data overrides.
export function remarkNote() {
  return function transform(tree) {
    for (const node of tree.children) {
      if (node.type !== 'paragraph' || !node.children?.length) continue;
      const first = node.children[0];
      const last = node.children[node.children.length - 1];
      if (first.type !== 'text' || !first.value.startsWith('::note')) continue;
      first.value = first.value.replace(/^::note\s*/, '');
      if (last.type === 'text') last.value = last.value.replace(/::\s*$/, '');
      node.type = 'blockquote';
      node.data = { hName: 'div', hProperties: { className: ['note'] } };
    }
  };
}
