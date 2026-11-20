import React from "react";

/**
 * Small, dependency-free markdown renderer for the documents this app produces.
 *
 * Deliberately not `dangerouslySetInnerHTML`: model output is untrusted input,
 * and a React-element renderer cannot execute it. Citations become chips.
 */

const CITE = /\[(P-\d{4})(?:\s*,?\s*p\.?\s*(\d+))?\]/g;

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let index = 0;
  let key = 0;

  const pushText = (value: string) => {
    if (!value) return;
    // bold, italic, inline code — applied in order of specificity
    const pattern = /(\*\*[^*]+\*\*)|(`[^`]+`)|(\*[^*]+\*)/g;
    let last = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(value))) {
      if (match.index > last) nodes.push(value.slice(last, match.index));
      const token = match[0];
      const k = `${keyPrefix}-i${key++}`;
      if (token.startsWith("**")) nodes.push(<strong key={k}>{token.slice(2, -2)}</strong>);
      else if (token.startsWith("`")) nodes.push(<code key={k}>{token.slice(1, -1)}</code>);
      else nodes.push(<em key={k}>{token.slice(1, -1)}</em>);
      last = match.index + token.length;
    }
    if (last < value.length) nodes.push(value.slice(last));
  };

  for (const match of text.matchAll(CITE)) {
    const start = match.index ?? 0;
    if (start > index) pushText(text.slice(index, start));
    const id = match[1];
    const page = match[2];
    nodes.push(
      <span className="cite" key={`${keyPrefix}-c${key++}`} title={`${id}${page ? ` página ${page}` : ""}`}>
        {id}
        {page ? ` p.${page}` : ""}
      </span>,
    );
    index = start + match[0].length;
  }
  if (index < text.length) pushText(text.slice(index));
  return nodes;
}

function renderTable(lines: string[], key: string): React.ReactNode {
  const rows = lines.map((line) =>
    line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((cell) => cell.trim()),
  );
  const header = rows[0] ?? [];
  const body = rows.slice(1).filter((row) => !row.every((cell) => /^:?-{2,}:?$/.test(cell)));
  return (
    <table key={key} className="md-table">
      <thead>
        <tr>
          {header.map((cell, i) => (
            <th key={i}>{renderInline(cell, `${key}-h${i}`)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {body.map((row, r) => (
          <tr key={r}>
            {row.map((cell, c) => (
              <td key={c}>{renderInline(cell, `${key}-r${r}c${c}`)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i++;
      continue;
    }
    if (/^```/.test(line)) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
      i++;
      blocks.push(
        <pre key={`b${key++}`} className="md-code">
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = Math.min(6, heading[1].length);
      const content = renderInline(heading[2], `b${key}`);
      const Tag = (`h${Math.min(level + 1, 6)}` as unknown) as "h2";
      blocks.push(
        <Tag key={`b${key++}`} className={`md-h md-h${level}`}>
          {content}
        </Tag>,
      );
      i++;
      continue;
    }
    if (/^(---|\*\*\*)$/.test(line.trim())) {
      blocks.push(<hr key={`b${key++}`} />);
      i++;
      continue;
    }
    if (/^\|/.test(line.trim())) {
      const table: string[] = [];
      while (i < lines.length && /^\|/.test(lines[i].trim())) table.push(lines[i++]);
      blocks.push(renderTable(table, `b${key++}`));
      continue;
    }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line);
      const items: string[] = [];
      while (
        i < lines.length &&
        (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]) || /^\s{2,}\S/.test(lines[i]))
      ) {
        if (/^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ""));
        } else {
          items[items.length - 1] += " " + lines[i].trim();
        }
        i++;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag key={`b${key++}`} className="md-list">
          {items.map((item, n) => (
            <li key={n}>{renderInline(item, `b${key}-${n}`)}</li>
          ))}
        </ListTag>,
      );
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(
        <blockquote key={`b${key++}`} className="md-quote">
          {renderInline(quote.join(" "), `b${key}`)}
        </blockquote>,
      );
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6}\s|```|\||>\s?|\s*([-*]|\d+\.)\s+)/.test(lines[i])
    ) {
      paragraph.push(lines[i++]);
    }
    blocks.push(
      <p key={`b${key++}`} className="md-p">
        {renderInline(paragraph.join(" ").trim(), `b${key}`)}
      </p>,
    );
  }

  return <div className="md">{blocks}</div>;
}
