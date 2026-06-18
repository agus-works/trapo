import type { ReactElement, ReactNode } from 'react';
import { Children, cloneElement, createElement, isValidElement } from 'react';
import type { Components } from 'react-markdown';
import styles from './MarkdownDocumentView.module.css';

type MarkdownComponentProps = {
  children?: ReactNode;
  node?: unknown;
  [key: string]: unknown;
};

const TEXT_TAGS = [
  'blockquote',
  'del',
  'em',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'li',
  'p',
  'strong',
  'td',
  'th',
] as const;

const SKIPPED_ELEMENT_TYPES = new Set(['code', 'pre']);

export function createMarkdownComponents(highlightQuery: string | null): Components {
  const components: Record<string, (props: MarkdownComponentProps) => ReactNode> = {};
  for (const tag of TEXT_TAGS) {
    components[tag] = ({ children, node: _node, ...props }) =>
      createElement(tag, props, highlightReactNode(children, highlightQuery));
  }
  return {
    ...components,
    a: ({ children, node: _node, ...props }) => (
      <a {...props} rel="noreferrer" target="_blank">
        {highlightReactNode(children, highlightQuery)}
      </a>
    ),
    table: ({ children, node: _node, ...props }) => (
      <div className={styles.tableViewport}>
        <table {...props}>{children}</table>
      </div>
    ),
  } as Components;
}

function highlightReactNode(node: ReactNode, query: string | null): ReactNode {
  const normalizedQuery = normalizeQuery(query);
  if (!normalizedQuery || node === null || node === undefined || typeof node === 'boolean') {
    return node;
  }
  if (typeof node === 'string') {
    return highlightTextNode(node, normalizedQuery);
  }
  if (Array.isArray(node)) {
    return Children.map(node, (child) => highlightReactNode(child, normalizedQuery));
  }
  if (!isValidElement(node)) {
    return node;
  }
  if (typeof node.type === 'string' && SKIPPED_ELEMENT_TYPES.has(node.type)) {
    return node;
  }
  const element = node as ReactElement<{ children?: ReactNode }>;
  if (element.props.children === undefined) {
    return node;
  }
  return cloneElement(
    element,
    undefined,
    highlightReactNode(element.props.children, normalizedQuery),
  );
}

function highlightTextNode(text: string, query: string): ReactNode {
  const spans = highlightSpans(text, query);
  if (spans.length === 0) {
    return text;
  }
  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start > cursor) {
      parts.push(text.slice(cursor, span.start));
    }
    parts.push(
      <mark
        className={styles.searchHighlight}
        data-markdown-highlight="true"
        key={`${span.start}:${span.end}`}
      >
        {text.slice(span.start, span.end)}
      </mark>,
    );
    cursor = Math.max(cursor, span.end);
  }
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }
  return parts;
}

function highlightSpans(text: string, query: string): Array<{ start: number; end: number }> {
  const phraseSpans = exactPhraseSpans(text, query);
  return phraseSpans.length > 0 ? phraseSpans : exactTokenSpans(text, query);
}

function exactPhraseSpans(text: string, query: string): Array<{ start: number; end: number }> {
  const lowered = text.toLocaleLowerCase();
  const loweredQuery = query.toLocaleLowerCase();
  const spans: Array<{ start: number; end: number }> = [];
  let start = 0;
  while (true) {
    const index = lowered.indexOf(loweredQuery, start);
    if (index < 0) {
      break;
    }
    spans.push({ end: index + loweredQuery.length, start: index });
    start = index + Math.max(1, loweredQuery.length);
  }
  return spans;
}

function exactTokenSpans(text: string, query: string): Array<{ start: number; end: number }> {
  const tokens = new Set(query.match(/[\w.-]+/g)?.map((token) => token.toLocaleLowerCase()) ?? []);
  if (tokens.size === 0) {
    return [];
  }
  const spans: Array<{ start: number; end: number }> = [];
  for (const match of text.matchAll(/[\w.-]+/g)) {
    if (tokens.has(match[0].toLocaleLowerCase()) && match.index !== undefined) {
      spans.push({ end: match.index + match[0].length, start: match.index });
    }
  }
  return spans;
}

function normalizeQuery(query: string | null): string {
  return (query ?? '').trim().replace(/\s+/g, ' ');
}
