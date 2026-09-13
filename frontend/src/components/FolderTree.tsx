import { useMemo, useState } from "react";

interface Node {
  name: string;
  path: string;
  children: Node[];
}

function buildTree(dirs: string[]): Node {
  const root: Node = { name: "", path: "", children: [] };
  for (const dir of dirs) {
    const parts = dir.split("/");
    let cur = root;
    let acc = "";
    for (const part of parts) {
      acc = acc ? `${acc}/${part}` : part;
      let child = cur.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part, path: acc, children: [] };
        cur.children.push(child);
      }
      cur = child;
    }
  }
  return root;
}

function TreeNode({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: Node;
  depth: number;
  selected: string;
  onSelect: (p: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = node.children.length > 0;
  return (
    <div>
      <div
        className={`tree-row ${selected === node.path ? "sel" : ""}`}
        style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => onSelect(node.path)}
      >
        <span
          className="tree-caret"
          onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        >
          {hasChildren ? (open ? "▾" : "▸") : "•"}
        </span>
        <span className="tree-name">{open && hasChildren ? "📂" : "📁"} {node.name}</span>
      </div>
      {open && node.children.map((c) => (
        <TreeNode key={c.path} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
      ))}
    </div>
  );
}

export default function FolderTree({
  dirs,
  selected,
  onSelect,
}: {
  dirs: string[];
  selected: string;
  onSelect: (p: string) => void;
}) {
  const root = useMemo(() => buildTree(dirs), [dirs]);
  if (!dirs.length) return <div className="dim" style={{ padding: 12 }}>No folders found.</div>;
  return (
    <div className="folder-tree">
      {root.children.map((c) => (
        <TreeNode key={c.path} node={c} depth={0} selected={selected} onSelect={onSelect} />
      ))}
    </div>
  );
}
